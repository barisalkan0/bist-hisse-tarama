"""Tarama motoru icin ortak yardimcilar.

Tum hesaplar onbellekteki DUZELTILMIS (adjusted) kapanis serisi uzerinden yapilir.
"""
import pandas as pd

from data import cache
import settings as cfg


def load_all(min_days=30, exclude_blacklist=True):
    """
    Onbellekteki tum hisseleri {symbol: DataFrame} olarak yukler.
    Yeterli gun verisi olmayan ve kara listedekiler atlanir.
    """
    black = set(cache.get_blacklist()) if exclude_blacklist else set()
    out = {}
    for sym in cache.symbols_in_cache():
        if sym in black:
            continue
        df = cache.get_prices(sym)
        if len(df) >= min_days:
            out[sym] = df
    return out


def pct_change_over(close, lookback):
    """lookback gun oncesine gore yuzde getiri. Yetersiz veri -> None."""
    if len(close) <= lookback:
        return None
    a = close.iloc[-1 - lookback]
    b = close.iloc[-1]
    if a is None or a == 0 or pd.isna(a):
        return None
    return (b / a - 1.0) * 100.0


def sma(close, window):
    if len(close) < window:
        return None
    return float(close.iloc[-window:].mean())


def down_day_ratio(close, lookback):
    """Son `lookback` gunde dusus gunlerinin orani (0-1)."""
    if len(close) <= lookback:
        return None
    window = close.iloc[-1 - lookback :]
    diffs = window.diff().dropna()
    if len(diffs) == 0:
        return None
    return float((diffs < 0).sum() / len(diffs))


def volume_ratio(volume, window):
    """Son `window` gun ortalama hacmin, 20 gunluk ortalamaya orani."""
    if len(volume) < cfg.SMA_SHORT + 1:
        return None
    recent = float(volume.iloc[-window:].mean())
    base = float(volume.iloc[-cfg.SMA_SHORT :].mean())
    if base == 0:
        return None
    return recent / base


def date_str(df, offset=0):
    """offset=0 son tarih, offset=N -> N gun oncesi tarihi (YYYY-MM-DD)."""
    idx = -1 - offset
    if abs(idx) > len(df):
        return None
    return df.index[idx].date().isoformat()


def snapshot_son(symbol):
    """mynet snapshot'tan guncel 'Son' fiyat (varsa)."""
    snap = cache.get_snapshot()
    row = snap[snap["symbol"] == symbol]
    if not row.empty:
        return float(row.iloc[0]["son"]) if pd.notna(row.iloc[0]["son"]) else None
    return None
