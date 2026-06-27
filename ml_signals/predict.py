"""Egitilmis ML modelinden canli skor uretimi."""
from __future__ import annotations

from pathlib import Path
import os
import warnings

import numpy as np
import pandas as pd

from ml_signals import radar
from ml_signals.features import FEATURE_COLUMNS, latest_features


MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"
MODEL_KIND = "absolute_upside_v4"


def _load_artifact(path=MODEL_PATH):
    if not Path(path).exists():
        return None, "Henüz doğrulanmış ML modeli yok. Eğitim için: python -m ml_signals.train"
    try:
        os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
        warnings.filterwarnings("ignore", message="Could not find the number of physical cores.*")
        import joblib
        artifact = joblib.load(path)
    except Exception as e:
        return None, f"ML modeli yüklenemedi: {e}"
    meta = artifact.get("metadata", {})
    if artifact.get("model_kind") != MODEL_KIND:
        return None, "ML modeli eski hedef/sürümle eğitilmiş; yükseliş radarı için yeniden eÄŸitilmeli."
    if not meta.get("summary", {}).get("passed"):
        return None, "ML modeli var ama backtest kabul kriterini geçmemiş; canlı sinyal gösterilmiyor."
    missing = [c for c in FEATURE_COLUMNS if c not in artifact.get("feature_columns", [])]
    if missing:
        return None, "ML modeli bu uygulama sürümüyle uyumlu değil; yeniden eÄŸitilmeli."
    required_models = ["up_model_5", "up_model_10", "rel_model_5", "rel_model_10"]
    if any(k not in artifact for k in required_models):
        return None, "ML modeli eski hedefle eğitilmiş; yükseliş radarı için yeniden eÄŸitilmeli."
    return artifact, None


def _confidence(score):
    d = abs(float(score) - 0.5)
    if d >= 0.22:
        return "Yüksek"
    if d >= 0.12:
        return "Orta"
    return "DÃ¼ÅŸÃ¼k"


def _positive_proba(model, x):
    proba = model.predict_proba(x)
    estimator = model.steps[-1][1] if hasattr(model, "steps") else model
    classes = list(getattr(estimator, "classes_", [0, 1]))
    if 1 not in classes:
        return np.zeros(len(x))
    return proba[:, classes.index(1)]


def _reasons(row):
    reasons = []
    if row.get("vol_ratio_5_20", 0) >= 2.0:
        reasons.append("5G ciro yüksek")
    if row.get("vol_ratio_2_20", 0) >= 2.5:
        reasons.append("son 2G hacim patlamasÄ±")
    if row.get("ret_5", 0) > 3 and row.get("ret_20", 0) > 0:
        reasons.append("kÄ±sa momentum pozitif")
    if row.get("ret_20", 0) < -8 and row.get("ret_5", 0) > 0:
        reasons.append("dÃ¼ÅŸÃ¼ÅŸ sonrasÄ± tepki")
    if row.get("volatility_ratio_20_60", 1) < 0.80:
        reasons.append("volatilite sÄ±kÄ±ÅŸmasÄ±")
    if row.get("sma20_gap", 0) > 0 and row.get("sma50_gap", 0) > 0:
        reasons.append("ortalamalarÄ±n Ã¼stÃ¼nde")
    if row.get("drawdown_60", 0) < -12 and row.get("low_distance_60", 0) < 8:
        reasons.append("60G dibe yakın")
    if not reasons:
        reasons.append("model kombinasyonu")
    return ", ".join(reasons[:3])


def score_latest(data, snapshot=None, fark=None, model_path=MODEL_PATH):
    """Son kapanis icin ML skor tablosu dondurur.

    Donus: (DataFrame, hata_mesaji|None)
    """
    artifact, err = _load_artifact(model_path)
    if err:
        return pd.DataFrame(), err

    feat = latest_features(data)
    if feat.empty:
        return pd.DataFrame(), "ML skoru için yeterli geçmiş veri yok."

    cols = artifact["feature_columns"]
    up5 = _positive_proba(artifact["up_model_5"], feat[cols])
    up10 = _positive_proba(artifact["up_model_10"], feat[cols])
    up_score = (up5 + up10) / 2.0
    rel5 = _positive_proba(artifact["rel_model_5"], feat[cols])
    rel10 = _positive_proba(artifact["rel_model_10"], feat[cols])
    rel_score = (rel5 + rel10) / 2.0

    snapshot = snapshot or {}
    fark = fark or {}
    rows = []
    for i, (_, r) in enumerate(feat.iterrows()):
        sym = r["symbol"]
        s5 = round(float(up5[i]) * 100.0, 1)
        s10 = round(float(up10[i]) * 100.0, 1)
        up = round(float(up_score[i]) * 100.0, 1)
        rel = round(float(rel_score[i]) * 100.0, 1)
        son = snapshot.get(sym)
        f = fark.get(sym)
        status = radar.radar_status(up, s5, s10, r, f, relative_score=rel)
        conf = radar.adjust_confidence(radar.confidence(float(up_score[i]), s5, s10), r)
        rows.append({
            "Sembol": sym,
            "Hisse": sym,
            "data_date": r["date"].date().isoformat() if hasattr(r["date"], "date") else str(r["date"])[:10],
            "Radar Durumu": status,
            "Yükseliş Puanı": up,
            "Göreli Güç": rel,
            "ML Puanı": up,
            "5G Yükseliş": s5,
            "10G Yükseliş": s10,
            "5G Skor": s5,
            "10G Skor": s10,
            "Güven": conf,
            "Veri Güveni": radar.data_confidence(r),
            "Likidite": radar.liquidity_label(r),
            "Trend": radar.trend_label(r),
            "Hacim": radar.volume_label(r),
            "Vade": radar.horizon(s5, s10),
            "Takip Planı": radar.follow_plan(status, conf, up),
            "Basit Neden": radar.simple_reason(r),
            "Ana Risk": radar.main_risk(r, f),
            "Ana Nedenler": radar.simple_reason(r),
            "Son": son,
            "Fark %": f,
        })
    out = pd.DataFrame(rows)
    out = out.sort_values(["Yükseliş Puanı", "Göreli Güç"], ascending=False).reset_index(drop=True)
    return out, None
