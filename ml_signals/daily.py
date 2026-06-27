"""Gunluk tekil Akilli Radar snapshot yonetimi."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from data import cache
from ml_signals import radar
from ml_signals.labels import UP_THRESHOLD_5, UP_THRESHOLD_10
from ml_signals.predict import score_latest


MODEL_KIND = "absolute_upside_v4"
OUTCOME_THRESHOLDS = {5: UP_THRESHOLD_5, 10: UP_THRESHOLD_10}

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ml_radar_snapshot (
    data_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    model_kind TEXT NOT NULL DEFAULT 'absolute_upside_v4',
    radar_status TEXT NOT NULL,
    ml_score REAL,
    score_5 REAL,
    score_10 REAL,
    relative_score REAL,
    confidence TEXT,
    data_confidence TEXT,
    liquidity_label TEXT,
    trend_label TEXT,
    volume_label TEXT,
    horizon TEXT,
    simple_reason TEXT,
    main_risk TEXT,
    son REAL,
    fark REAL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (data_date, symbol, model_kind)
)
"""

OUTCOME_SQL = """
CREATE TABLE IF NOT EXISTS ml_radar_outcome (
    signal_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    model_kind TEXT NOT NULL,
    radar_status TEXT NOT NULL,
    ml_score REAL,
    score_5 REAL,
    score_10 REAL,
    relative_score REAL,
    confidence TEXT,
    signal_horizon TEXT,
    simple_reason TEXT,
    main_risk TEXT,
    horizon_days INTEGER NOT NULL,
    start_price REAL,
    end_date TEXT,
    end_price REAL,
    abs_return REAL,
    max_return REAL,
    min_return REAL,
    success INTEGER,
    evaluated_at TEXT NOT NULL,
    PRIMARY KEY (signal_date, symbol, model_kind, horizon_days)
)
"""


def init_db(db=None):
    db = db or cache.connect()
    db.execute(TABLE_SQL)
    db.execute(OUTCOME_SQL)
    _ensure_columns(db, "ml_radar_snapshot", {
        "model_kind": "TEXT DEFAULT 'absolute_upside_v4'",
        "relative_score": "REAL",
        "data_confidence": "TEXT",
        "liquidity_label": "TEXT",
        "trend_label": "TEXT",
        "volume_label": "TEXT",
    })
    _ensure_columns(db, "ml_radar_outcome", {
        "ml_score": "REAL",
        "score_5": "REAL",
        "score_10": "REAL",
        "relative_score": "REAL",
        "confidence": "TEXT",
        "signal_horizon": "TEXT",
        "simple_reason": "TEXT",
        "main_risk": "TEXT",
        "max_return": "REAL",
        "min_return": "REAL",
    })
    db.commit()
    return db


def _ensure_columns(db, table, cols):
    existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, spec in cols.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def _display(rows) -> pd.DataFrame:
    cols = [
        "data_date", "symbol", "radar_status", "ml_score", "score_5", "score_10", "relative_score",
        "confidence", "data_confidence", "liquidity_label", "trend_label", "volume_label",
        "horizon", "simple_reason", "main_risk", "son", "fark", "created_at",
    ]
    if not rows:
        return pd.DataFrame(columns=[
            "Veri Tarihi", "Hisse", "Radar Durumu", "Yükseliş Puanı", "Göreli Güç",
            "ML Puanı", "5G Yükseliş", "10G Yükseliş", "5G Skor", "10G Skor",
            "Güven", "Veri Güveni", "Likidite", "Trend", "Hacim",
            "Vade", "5G Sonuç Günü", "10G Sonuç Günü", "Takip Planı",
            "Basit Neden", "Ana Risk", "Son", "Fark %",
            "created_at", "data_date",
        ])
    df = pd.DataFrame([dict(zip(cols, r)) for r in rows])
    follow = [
        radar.follow_plan(str(r["radar_status"]), str(r["confidence"]), float(r["ml_score"] or 0))
        for _, r in df.iterrows()
    ]
    return pd.DataFrame({
        "Veri Tarihi": df["data_date"],
        "Hisse": df["symbol"],
        "Radar Durumu": df["radar_status"],
        "Yükseliş Puanı": df["ml_score"],
        "Göreli Güç": df["relative_score"],
        "ML Puanı": df["ml_score"],
        "5G Yükseliş": df["score_5"],
        "10G Yükseliş": df["score_10"],
        "5G Skor": df["score_5"],
        "10G Skor": df["score_10"],
        "Güven": df["confidence"],
        "Veri Güveni": df["data_confidence"],
        "Likidite": df["liquidity_label"],
        "Trend": df["trend_label"],
        "Hacim": df["volume_label"],
        "Vade": df["horizon"],
        "5G Sonuç Günü": "—",
        "10G Sonuç Günü": "—",
        "Takip Planı": follow,
        "Basit Neden": df["simple_reason"],
        "Ana Risk": df["main_risk"],
        "Son": df["son"],
        "Fark %": df["fark"],
        "created_at": df["created_at"],
        "data_date": df["data_date"],
    })


def load_snapshot(data_date: str, db=None) -> pd.DataFrame:
    db = init_db(db)
    rows = db.execute(
        """
        SELECT data_date, symbol, radar_status, ml_score, score_5, score_10, relative_score,
               confidence, data_confidence, liquidity_label, trend_label, volume_label,
               horizon, simple_reason, main_risk, son, fark, created_at
        FROM ml_radar_snapshot
        WHERE data_date=? AND COALESCE(model_kind, '')=?
        ORDER BY
          CASE radar_status
            WHEN 'GÃ¼Ã§lÃ¼ Aday' THEN 0
            WHEN 'Takip Edilecek' THEN 1
            WHEN 'Riskli Ama Hareketli' THEN 2
            ELSE 3
          END,
          ml_score DESC,
          score_10 DESC
        """,
        (data_date, MODEL_KIND),
    ).fetchall()
    return _display(rows)


def refresh_market_fields(data_date: str, snapshot=None, fark=None, db=None) -> int:
    """Ayni gun ML'i tekrar calistirmadan Son/Fark gosterim alanlarini gunceller."""
    snapshot = snapshot or {}
    fark = fark or {}
    if not snapshot and not fark:
        return 0
    db = init_db(db)
    rows = []
    symbols = set(snapshot) | set(fark)
    for sym in symbols:
        rows.append((_f(snapshot.get(sym)), _f(fark.get(sym)), data_date, sym))
    db.executemany(
        "UPDATE ml_radar_snapshot SET son=COALESCE(?, son), fark=COALESCE(?, fark) "
        "WHERE data_date=? AND symbol=? AND COALESCE(model_kind, '')=?",
        [(son, f, d, s, MODEL_KIND) for son, f, d, s in rows],
    )
    db.commit()
    return len(rows)


def save_snapshot_once(radar_df: pd.DataFrame, data_date: str, db=None, allow_append: bool = False) -> bool:
    """Ayni data_date daha once kayitliysa radar listesini yeniden yazmaz.

    allow_append=True yalnizca kullanicinin kendi takip listesine ekledigi
    sembolleri ayni gunun snapshot'ina tamamlamak icin kullanilir.
    """
    db = init_db(db)
    exists = db.execute(
        "SELECT 1 FROM ml_radar_snapshot WHERE data_date=? AND COALESCE(model_kind, '')=? LIMIT 1",
        (data_date, MODEL_KIND),
    ).fetchone()
    if exists and not allow_append:
        return False
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for _, r in radar_df.iterrows():
        sym = str(r.get("Hisse") or r.get("Sembol") or "").strip().upper()
        if not sym:
            continue
        rows.append((
            data_date,
            sym,
            MODEL_KIND,
            r.get("Radar Durumu", "İzle"),
            _f(r.get("Yükseliş Puanı", r.get("ML Puanı"))),
            _f(r.get("5G Yükseliş", r.get("5G Skor"))),
            _f(r.get("10G Yükseliş", r.get("10G Skor"))),
            _f(r.get("Göreli Güç")),
            r.get("Güven"),
            r.get("Veri Güveni"),
            r.get("Likidite"),
            r.get("Trend"),
            r.get("Hacim"),
            r.get("Vade"),
            r.get("Basit Neden"),
            r.get("Ana Risk"),
            _f(r.get("Son")),
            _f(r.get("Fark %")),
            now,
        ))
    if not rows:
        return False
    cur = db.executemany(
        """
        INSERT OR IGNORE INTO ml_radar_snapshot
        (data_date, symbol, model_kind, radar_status, ml_score, score_5, score_10, relative_score,
         confidence, data_confidence, liquidity_label, trend_label, volume_label,
         horizon, simple_reason, main_risk, son, fark, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    db.commit()
    return cur.rowcount > 0


def today_radar(data, snapshot=None, fark=None, data_date=None, watch_symbols=None):
    """Son kapanis tarihi icin tekil radar snapshot'i dondurur.

    Donus: (DataFrame, hata|None, bilgi)
    """
    if not data_date:
        data_date = _latest_data_date(data)
    if not data_date:
        return pd.DataFrame(), "Radar için kapanÄ±ÅŸ tarihi bulunamadÄ±.", {}

    existing = load_snapshot(data_date)
    if not existing.empty:
        refresh_market_fields(data_date, snapshot=snapshot, fark=fark)
        _append_watch_symbols(data, data_date, watch_symbols, snapshot=snapshot, fark=fark)
        return _with_result_dates(load_snapshot(data_date), data), None, {"data_date": data_date, "created": False}

    scores, err = score_latest(data, snapshot=snapshot, fark=fark)
    if err:
        return pd.DataFrame(), err, {"data_date": data_date, "created": False}
    selected = radar.select_candidates(scores)
    selected = _with_watch_symbols(selected, scores, watch_symbols)
    if selected.empty:
        return pd.DataFrame(), "BugÃ¼n radara girecek aday bulunamadÄ±.", {
            "data_date": data_date,
            "created": False,
        }
    saved = save_snapshot_once(selected, data_date)
    return _with_result_dates(load_snapshot(data_date), data), None, {"data_date": data_date, "created": saved}


def evaluate_outcomes(data, as_of_date=None, db=None) -> int:
    """Suresi dolan radar/takip sinyallerinin 5G ve 10G sonucunu kaydeder."""
    db = init_db(db)
    rows = db.execute(
        """
        SELECT data_date, symbol, radar_status, ml_score, score_5, score_10,
               relative_score, confidence, horizon, simple_reason, main_risk, son
        FROM ml_radar_snapshot
        WHERE COALESCE(model_kind, '')=? AND radar_status <> 'İzle'
        """,
        (MODEL_KIND,),
    ).fetchall()
    if not rows:
        return 0

    now = datetime.now().isoformat(timespec="seconds")
    out_rows = []
    for (
        signal_date, symbol, status, ml_score, score_5, score_10, relative_score,
        confidence, signal_horizon, simple_reason, main_risk, stored_start,
    ) in rows:
        price_info = _future_prices(data.get(symbol), signal_date, as_of_date=as_of_date)
        if not price_info:
            continue
        start_date, start_price, future = price_info
        for horizon, threshold in OUTCOME_THRESHOLDS.items():
            item = future.get(horizon)
            if not item:
                continue
            end_date, end_price, max_return, min_return = item
            abs_return = (end_price / start_price - 1.0) * 100.0 if start_price else None
            if abs_return is None:
                continue
            out_rows.append((
                signal_date,
                symbol,
                MODEL_KIND,
                status,
                _f(ml_score),
                _f(score_5),
                _f(score_10),
                _f(relative_score),
                confidence,
                signal_horizon,
                simple_reason,
                main_risk,
                horizon,
                _f(stored_start) or float(start_price),
                end_date,
                float(end_price),
                float(abs_return),
                float(max_return),
                float(min_return),
                1 if abs_return >= threshold else 0,
                now,
            ))
    if not out_rows:
        return 0

    cur = db.executemany(
        """
        INSERT OR REPLACE INTO ml_radar_outcome
        (signal_date, symbol, model_kind, radar_status, ml_score, score_5, score_10,
         relative_score, confidence, signal_horizon, simple_reason, main_risk,
         horizon_days, start_price, end_date, end_price, abs_return, max_return,
         min_return, success, evaluated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        out_rows,
    )
    db.commit()
    return cur.rowcount


def load_outcomes(limit: int | None = None, db=None) -> pd.DataFrame:
    db = init_db(db)
    sql = """
        SELECT signal_date, symbol, radar_status, ml_score, score_5, score_10,
               relative_score, confidence, signal_horizon, simple_reason, main_risk,
               horizon_days, start_price, end_date, end_price, abs_return,
               max_return, min_return, success, evaluated_at
        FROM ml_radar_outcome
        WHERE COALESCE(model_kind, '')=?
        ORDER BY signal_date DESC, horizon_days ASC, abs_return DESC
    """
    params = [MODEL_KIND]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = db.execute(sql, params).fetchall()
    if not rows:
        return pd.DataFrame(columns=[
            "Sinyal Tarihi", "Hisse", "Radar Durumu", "Yükseliş Puanı", "Göreli Güç",
            "Güven", "Vade", "Sonuç Vadesi", "Başlangıç", "Sonuç Tarihi",
            "Sonuç Fiyatı", "Getiri %", "En Yüksek %", "En Düşük %",
            "Tuttu mu?", "Basit Neden", "Ana Risk", "evaluated_at",
        ])
    cols = [
        "signal_date", "symbol", "radar_status", "ml_score", "score_5", "score_10",
        "relative_score", "confidence", "signal_horizon", "simple_reason", "main_risk",
        "horizon_days", "start_price", "end_date", "end_price", "abs_return",
        "max_return", "min_return", "success", "evaluated_at",
    ]
    df = pd.DataFrame([dict(zip(cols, r)) for r in rows])
    return pd.DataFrame({
        "Sinyal Tarihi": df["signal_date"],
        "Hisse": df["symbol"],
        "Radar Durumu": df["radar_status"],
        "Yükseliş Puanı": df["ml_score"],
        "5G Yükseliş": df["score_5"],
        "10G Yükseliş": df["score_10"],
        "Göreli Güç": df["relative_score"],
        "Güven": df["confidence"],
        "Vade": df["signal_horizon"],
        "Sonuç Vadesi": df["horizon_days"].astype(str) + " iş günü",
        "Başlangıç": df["start_price"],
        "Sonuç Tarihi": df["end_date"],
        "Sonuç Fiyatı": df["end_price"],
        "Getiri %": df["abs_return"],
        "En Yüksek %": df["max_return"],
        "En Düşük %": df["min_return"],
        "Tuttu mu?": df["success"].map({1: "Tuttu", 0: "Tutmadı"}),
        "Basit Neden": df["simple_reason"],
        "Ana Risk": df["main_risk"],
        "evaluated_at": df["evaluated_at"],
    })


def outcome_summary(outcomes: pd.DataFrame) -> dict:
    if outcomes.empty:
        return {
            "signals": 0, "success_rate": None, "avg_return": None,
            "avg_5": None, "avg_10": None, "best_status": "â€”",
        }
    df = outcomes.copy()
    df["_success"] = df["Tuttu mu?"].eq("Tuttu")
    df["_ret"] = pd.to_numeric(df["Getiri %"], errors="coerce")
    by_status = (
        df.groupby("Radar Durumu")["_ret"].mean().sort_values(ascending=False)
        if "Radar Durumu" in df else pd.Series(dtype=float)
    )
    return {
        "signals": int(len(df)),
        "success_rate": float(df["_success"].mean() * 100.0),
        "avg_return": float(df["_ret"].mean()),
        "avg_5": _mean_for_horizon(df, "5 iÅŸ gÃ¼nÃ¼"),
        "avg_10": _mean_for_horizon(df, "10 iÅŸ gÃ¼nÃ¼"),
        "best_status": str(by_status.index[0]) if not by_status.empty else "â€”",
    }


def outcome_breakdown(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes.empty:
        return pd.DataFrame(columns=[
            "Radar Durumu", "Sinyal", "İsabet %", "Ort. Getiri %",
            "Ort. En Yüksek %", "Ort. En Düşük %", "En İyi %", "En Kötü %",
        ])
    df = outcomes.copy()
    df["_success"] = df["Tuttu mu?"].eq("Tuttu")
    for col in ["Getiri %", "En Yüksek %", "En Düşük %"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    g = df.groupby("Radar Durumu", dropna=False)
    out = g.agg(
        Sinyal=("Hisse", "count"),
        **{
            "İsabet %": ("_success", lambda s: float(s.mean() * 100.0)),
            "Ort. Getiri %": ("Getiri %", "mean"),
            "Ort. En Yüksek %": ("En Yüksek %", "mean"),
            "Ort. En Düşük %": ("En Düşük %", "mean"),
            "En İyi %": ("Getiri %", "max"),
            "En Kötü %": ("Getiri %", "min"),
        },
    ).reset_index()
    return out.sort_values(["Ort. Getiri %", "İsabet %"], ascending=False).reset_index(drop=True)


def _with_watch_symbols(selected: pd.DataFrame, scores: pd.DataFrame, watch_symbols) -> pd.DataFrame:
    watch = _symbol_set(watch_symbols)
    if not watch or scores.empty:
        return selected
    selected = selected.copy()
    present = _symbol_set(selected.get("Hisse", []))
    missing = watch - present
    if not missing:
        return selected
    watch_rows = scores[scores["Hisse"].isin(missing)].copy()
    if watch_rows.empty:
        return selected
    watch_rows["Radar Durumu"] = "Kendi Takibim"
    out = pd.concat([selected, watch_rows], ignore_index=True)
    return out.drop_duplicates(subset=["Hisse"], keep="first").reset_index(drop=True)


def _append_watch_symbols(data, data_date: str, watch_symbols, snapshot=None, fark=None, db=None) -> int:
    watch = _symbol_set(watch_symbols)
    if not watch:
        return 0
    db = init_db(db)
    rows = db.execute(
        """
        SELECT symbol
        FROM ml_radar_snapshot
        WHERE data_date=? AND COALESCE(model_kind, '')=?
        """,
        (data_date, MODEL_KIND),
    ).fetchall()
    existing = {str(r[0]).upper() for r in rows}
    missing = watch - existing
    if not missing:
        return 0

    scores, err = score_latest(data, snapshot=snapshot, fark=fark)
    if err or scores.empty:
        return 0
    add = scores[scores["Hisse"].isin(missing)].copy()
    if add.empty:
        return 0
    add["Radar Durumu"] = "Kendi Takibim"
    before = db.total_changes
    save_snapshot_once(add, data_date, db=db, allow_append=True)
    return db.total_changes - before


def _with_result_dates(display: pd.DataFrame, data) -> pd.DataFrame:
    """Radar tablosuna 5G/10G sonucunun hangi gune denk geldigini ekler."""
    if display.empty:
        return display
    out = display.copy()
    for col in ("5G Sonuç Günü", "10G Sonuç Günü"):
        if col not in out.columns:
            out[col] = "—"
    for idx, row in out.iterrows():
        symbol = str(row.get("Hisse", "")).strip().upper()
        signal_date = row.get("data_date") or row.get("Veri Tarihi")
        out.at[idx, "5G Sonuç Günü"] = _target_result_date(data.get(symbol), signal_date, 5)
        out.at[idx, "10G Sonuç Günü"] = _target_result_date(data.get(symbol), signal_date, 10)
    return out


def _target_result_date(df: pd.DataFrame | None, signal_date, horizon: int) -> str:
    """Mumkunse gercek cache islem gununu, yoksa hafta sonu atlayan tahmini gunu verir."""
    try:
        signal_ts = pd.to_datetime(signal_date).normalize()
    except Exception:
        return "—"
    if df is not None and not df.empty:
        try:
            idx = pd.to_datetime(df.index).normalize()
            pos = idx.get_indexer([signal_ts])
            if len(pos) and pos[0] >= 0:
                target_pos = int(pos[0]) + int(horizon)
                if target_pos < len(idx):
                    return _fmt_result_date(idx[target_pos])
        except Exception:
            pass
    try:
        target = pd.bdate_range(signal_ts + pd.Timedelta(days=1), periods=int(horizon))[-1]
        return _fmt_result_date(target)
    except Exception:
        return "—"


def _fmt_result_date(value) -> str:
    try:
        ts = pd.to_datetime(value)
        return f"{ts.day:02d}.{ts.month:02d}.{ts.year}"
    except Exception:
        return str(value)[:10] if value is not None else "—"


def _future_prices(df: pd.DataFrame | None, signal_date: str, as_of_date=None):
    if df is None or df.empty or "adj_close" not in df.columns:
        return None
    close = df["adj_close"].dropna().astype(float).sort_index()
    if close.empty:
        return None
    close.index = pd.to_datetime(close.index)
    if as_of_date:
        close = close[close.index.normalize() <= pd.to_datetime(as_of_date).normalize()]
    signal_ts = pd.to_datetime(signal_date).normalize()
    pos = close.index.normalize().get_indexer([signal_ts])
    if len(pos) == 0 or pos[0] < 0:
        return None
    start_pos = int(pos[0])
    start_price = float(close.iloc[start_pos])
    future = {}
    for horizon in OUTCOME_THRESHOLDS:
        end_pos = start_pos + horizon
        if end_pos < len(close):
            end_ts = close.index[end_pos]
            path = close.iloc[start_pos:end_pos + 1]
            future[horizon] = (
                end_ts.date().isoformat() if hasattr(end_ts, "date") else str(end_ts)[:10],
                float(close.iloc[end_pos]),
                float((path.max() / start_price - 1.0) * 100.0),
                float((path.min() / start_price - 1.0) * 100.0),
            )
    if not future:
        return None
    start_ts = close.index[start_pos]
    start_date = start_ts.date().isoformat() if hasattr(start_ts, "date") else str(start_ts)[:10]
    return start_date, start_price, future


def _latest_data_date(data) -> str | None:
    dates = []
    for df in data.values():
        if df is not None and not df.empty:
            idx = df.index[-1]
            dates.append(idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10])
    return max(dates) if dates else None


def _f(v):
    try:
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _symbol_set(values) -> set[str]:
    if values is None:
        return set()
    return {str(v).strip().upper() for v in values if str(v).strip()}


def _mean_for_horizon(df: pd.DataFrame, horizon: str):
    sub = df[df["Sonuç Vadesi"] == horizon]
    if sub.empty:
        return None
    return float(pd.to_numeric(sub["Getiri %"], errors="coerce").mean())

