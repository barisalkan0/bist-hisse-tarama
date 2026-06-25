"""Tarama motoru icin ortak yardimcilar.

Fiyat/trend hesaplari DUZELTILMIS kapanis (adj_close = Is Yatirim HGDG_KAPANIS)
uzerinden yapilir (bedelsiz/bolunme carpitmasi olmaz). Hacim karsilastirmasi ise
TL CIRO (HGDG_HACIM) uzerinden yapilir; bu olcu bedelsizde sureklidir.
"""
import numpy as np
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
        if len(df) >= min_days and "adj_close" in df.columns:
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


def turnover_ratio(df, window):
    """
    Son `window` gun ortalama CIRO'nun, 20 gunluk ortalama ciroya orani.
    `volume` zaten Is Yatirim TL cirosudur (HGDG_HACIM); bedelsize dayaniklidir.
    Yetersiz veri -> None.
    """
    if len(df) < cfg.SMA_SHORT + 1:
        return None
    turnover = df["volume"].astype(float)
    recent = float(turnover.iloc[-window:].mean())
    base = float(turnover.iloc[-cfg.SMA_SHORT :].mean())
    if base == 0 or pd.isna(base):
        return None
    return recent / base


def date_str(df, offset=0):
    """offset=0 son tarih, offset=N -> N gun oncesi tarihi (YYYY-MM-DD)."""
    idx = -1 - offset
    if abs(idx) > len(df):
        return None
    return df.index[idx].date().isoformat()


def business_days_behind(date_iso):
    """Verilen tarih ile bugun arasindaki IS GUNU sayisi (hafta sonu sayilmaz).
    Bayatlik uyarisinin tatil/hafta sonu yuzunden yanlis yanmamasi icin kullanilir.
    """
    if not date_iso:
        return None
    try:
        return int(np.busday_count(np.datetime64(date_iso), np.datetime64("today")))
    except Exception:
        return None
