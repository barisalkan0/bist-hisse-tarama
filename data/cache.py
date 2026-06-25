"""
SQLite onbellek katmani.

Tablolar:
  prices    -> her hisse icin gunluk DUZELTILMIS (adjusted) OHLCV. Trend analizi
               bunu kullanir; bedelsiz/bolunme carpitmasi olmaz.
  meta      -> hisse adi, son veri tarihi, son guncelleme zamani
  snapshot  -> mynet'ten gelen en son anlik veri (Son/Fark/Hacim)
  blacklist -> kullanicinin elle gizledigi semboller
  settings  -> arayuz tercih/esik kaliciligi (key/value)
"""
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, date, time as dttime, timezone, timedelta

import pandas as pd

# BIST seansi ~18:10'da kapanir. Kapanis kesinlesmeden (bu saatten once) o gunun
# verisi ANLIK/gecicidir; saklamayiz. 18:30'u guvenli esik aliriz (15 dk gecikme payi).
_IST = timezone(timedelta(hours=3))
_SESSION_FINAL = dttime(18, 30)


def provisional_date():
    """Bugunku seans henuz kesinlesmediyse bugunun tarihini (ISO), aksi halde None doner.
    Saat dilimi İstanbul'a sabitlenir (bulut UTC'de calissa bile dogru olsun)."""
    ist = datetime.now(_IST)
    if ist.time() < _SESSION_FINAL:
        return ist.date().isoformat()
    return None

import settings as cfg
from data import store

_DB = None


def _repo():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed_path():
    return os.path.join(_repo(), cfg.SEED_PATH)


def _work_path():
    """
    Yazilabilir CALISMA veritabani yolu. Streamlit Cloud'da repo /mount/src altinda
    ve dosya sistemi gecici; ayrica commit'lenen dosyaya runtime'da yazmak git pull
    ile cakisip dosyayi bozuyor. Bu yuzden bulutta /tmp altinda calisiriz; commit'lenen
    seed'e ASLA yazmayiz. Yerelde repo altindaki calisma dosyasi kullanilir.
    """
    repo = _repo()
    if repo.replace("\\", "/").startswith("/mount/src") or os.environ.get("HISSE_USE_TMP_DB"):
        return os.path.join(tempfile.gettempdir(), "hisse_cache.sqlite")
    return os.path.join(repo, cfg.DB_PATH)


def _ensure_seeded(work):
    """Calisma DB'si yoksa veya bozuksa, commit'lenen seed'den kopyalar."""
    need = not os.path.exists(work)
    if not need:
        try:
            c = sqlite3.connect(work)
            ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            c.close()
            need = (ok != "ok")
        except Exception:
            need = True
    if need:
        seed = _seed_path()
        if os.path.exists(seed):
            try:
                os.makedirs(os.path.dirname(work), exist_ok=True)
                shutil.copy2(seed, work)
            except Exception:
                pass


def connect():
    global _DB
    if _DB is None:
        work = _work_path()
        _ensure_seeded(work)
        _DB = sqlite3.connect(work, check_same_thread=False)
        _DB.row_factory = sqlite3.Row
    return _DB


def init_db():
    db = connect()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS prices (
            symbol TEXT, date TEXT,
            open REAL, high REAL, low REAL,
            close REAL,        -- HAM kapanis (ciro/hacim hesabi icin)
            adj_close REAL,    -- DUZELTILMIS kapanis (trend/getiri icin)
            volume INTEGER,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS meta (
            symbol TEXT PRIMARY KEY, name TEXT, last_date TEXT, last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS snapshot (
            symbol TEXT PRIMARY KEY, name TEXT, son REAL, fark REAL,
            hacim_lot INTEGER, hacim_tl REAL, saat TEXT, captured TEXT
        );
        CREATE TABLE IF NOT EXISTS blacklist (symbol TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    # Eski semadan gelen veritabanlarina adj_close kolonunu ekle (yoksa)
    cols = [r[1] for r in db.execute("PRAGMA table_info(prices)").fetchall()]
    if "adj_close" not in cols:
        db.execute("ALTER TABLE prices ADD COLUMN adj_close REAL")
    # Kapanisi bos satirlari temizle (henuz kapanmamis seans kaydi sizmis olabilir)
    db.execute("DELETE FROM prices WHERE close IS NULL OR adj_close IS NULL")
    # Seans kesinlesmeden once sizmis bugunku ANLIK satirlari temizle
    pv = provisional_date()
    if pv:
        db.execute("DELETE FROM prices WHERE date = ?", (pv,))
    db.commit()


# ---------- prices ----------
def upsert_prices(symbol, df):
    """df: index=tarih(datetime), kolonlar open/high/low/close/volume."""
    if df is None or df.empty:
        return 0
    db = connect()
    rows = []
    for idx, r in df.iterrows():
        d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)
        rows.append(
            (
                symbol, d,
                _f(r.get("open")), _f(r.get("high")), _f(r.get("low")),
                _f(r.get("close")), _f(r.get("adj_close")), _i(r.get("volume")),
            )
        )
    db.executemany(
        "INSERT OR REPLACE INTO prices "
        "(symbol,date,open,high,low,close,adj_close,volume) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    db.commit()
    return len(rows)


def get_prices(symbol):
    """Bir hissenin tum gunluk verisini pandas DataFrame olarak doner (tarih sirali)."""
    db = connect()
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, adj_close, volume FROM prices "
        "WHERE symbol=? ORDER BY date",
        db, params=(symbol,), parse_dates=["date"],
    )
    if not df.empty:
        df = df.set_index("date")
    return df


def get_last_date(symbol):
    db = connect()
    cur = db.execute("SELECT MAX(date) FROM prices WHERE symbol=?", (symbol,))
    v = cur.fetchone()[0]
    return v  # 'YYYY-MM-DD' veya None


def symbols_in_cache():
    db = connect()
    cur = db.execute("SELECT DISTINCT symbol FROM prices ORDER BY symbol")
    return [r[0] for r in cur.fetchall()]


def global_min_last_date():
    """Onbellekteki tum hisselerin en eski 'son tarih'i (incremental cekim baslangici)."""
    db = connect()
    cur = db.execute("SELECT MIN(m) FROM (SELECT MAX(date) m FROM prices GROUP BY symbol)")
    return cur.fetchone()[0]


# ---------- meta ----------
def set_meta(symbol, name, last_date):
    db = connect()
    db.execute(
        "INSERT OR REPLACE INTO meta (symbol,name,last_date,last_updated) VALUES (?,?,?,?)",
        (symbol, name, last_date, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


def get_meta_name(symbol):
    db = connect()
    cur = db.execute("SELECT name FROM meta WHERE symbol=?", (symbol,))
    r = cur.fetchone()
    return r[0] if r else symbol


def last_global_update():
    db = connect()
    cur = db.execute("SELECT MAX(last_updated) FROM meta")
    return cur.fetchone()[0]


# ---------- snapshot ----------
def save_snapshot(rows):
    """rows: universe.fetch_universe() ciktisi."""
    db = connect()
    now = datetime.now().isoformat(timespec="seconds")
    data = [
        (r["symbol"], r["name"], r["son"], r["fark"], r["hacim_lot"],
         r["hacim_tl"], r["saat"], now)
        for r in rows
    ]
    db.executemany(
        "INSERT OR REPLACE INTO snapshot "
        "(symbol,name,son,fark,hacim_lot,hacim_tl,saat,captured) VALUES (?,?,?,?,?,?,?,?)",
        data,
    )
    db.commit()


def get_snapshot():
    db = connect()
    return pd.read_sql_query("SELECT * FROM snapshot ORDER BY symbol", db)


def closing_snapshot():
    """
    KAPANIS (gun sonu) bazli anlik-benzeri tablo. mynet'in canli snapshot'i yerine
    kullanilir; boylece seans ici oynamalara takilmadan hep son kapanis gosterilir.
    Son = ham kapanis; Fark % = duzeltilmis kapanislardan (bedelsiz yanilmaz);
    Hacim = son kapanis hacmi. Doner: symbol, ad, son, fark, hacim_lot, hacim_tl, tarih.
    """
    db = connect()
    q = """
    WITH ranked AS (
      SELECT symbol, date, close, adj_close, volume,
             ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
      FROM prices
    )
    SELECT l.symbol AS symbol,
           COALESCE(m.name, l.symbol) AS ad,
           l.close AS son,
           CASE WHEN p.adj_close IS NOT NULL AND p.adj_close <> 0
                THEN (l.adj_close / p.adj_close - 1.0) * 100.0 END AS fark,
           l.volume AS hacim_lot,
           l.close * l.volume AS hacim_tl,
           l.date AS tarih
    FROM ranked l
    LEFT JOIN ranked p ON p.symbol = l.symbol AND p.rn = 2
    LEFT JOIN meta m ON m.symbol = l.symbol
    WHERE l.rn = 1
    ORDER BY l.symbol
    """
    return pd.read_sql_query(q, db)


def snapshot_symbols():
    db = connect()
    cur = db.execute("SELECT symbol FROM snapshot ORDER BY symbol")
    return [r[0] for r in cur.fetchall()]


# ---------- blacklist ----------
# Yereldeki SQLite hizli okuma icindir; kalici kaynak (varsa) Upstash'tir.
def add_blacklist(symbol):
    db = connect()
    db.execute("INSERT OR IGNORE INTO blacklist (symbol) VALUES (?)", (symbol,))
    db.commit()
    try:
        store.blacklist_add(symbol)   # kalici depoya da yaz
    except Exception:
        pass


def remove_blacklist(symbol):
    db = connect()
    db.execute("DELETE FROM blacklist WHERE symbol=?", (symbol,))
    db.commit()
    try:
        store.blacklist_remove(symbol)
    except Exception:
        pass


def get_blacklist():
    db = connect()
    cur = db.execute("SELECT symbol FROM blacklist ORDER BY symbol")
    return [r[0] for r in cur.fetchall()]


def sync_blacklist_from_remote():
    """
    Kalici depo (Upstash) etkinse, gizleme listesini oradan cekip yereli onunla
    esitler. Acilista bir kez cagrilir; boylece yeniden baslamada liste kaybolmaz.
    Devre disiysa (yerel kullanim) hicbir sey yapmaz.
    """
    try:
        members = store.blacklist_members()
    except Exception:
        members = None
    if members is None:
        return  # Upstash devre disi -> yerel liste korunur
    db = connect()
    db.execute("DELETE FROM blacklist")
    db.executemany("INSERT OR IGNORE INTO blacklist (symbol) VALUES (?)",
                   [(m,) for m in members])
    db.commit()


# ---------- settings ----------
def set_setting(key, value):
    db = connect()
    db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))
    db.commit()


def get_setting(key, default=None):
    db = connect()
    cur = db.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    return r[0] if r else default


# ---------- yardimci ----------
def _f(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return int(f) if f is not None else None
