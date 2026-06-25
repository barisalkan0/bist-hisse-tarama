"""
Yahoo Finance'ten gecmis gunluk veri cekimi (yfinance).

- auto_adjust=False -> hem HAM kapanis (Close) hem DUZELTILMIS kapanis (Adj Close)
  alinir. Trend/getiri duzeltilmis fiyattan (bedelsiz/bolunme carpitmasi olmaz),
  hacim cirosu ise ham fiyattan hesaplanir (lot*ham_fiyat bedelsizde sureklidir).
- Ilk calistirmada ~2 yillik backfill; sonrasinda yalnizca eksik son gunler
  (incremental) cekilir. Yahoo erisilemezse onbellek korunur, cokme olmaz.
- Hiz icin parti (batch) halinde indirilir.
"""
import logging
import time

import pandas as pd
import yfinance as yf

# Yahoo'da olmayan/yeni semboller icin yfinance'in bastigi hata mesajlarini sustur
# (kod bu durumlari zaten zarifce atliyor; konsol temiz kalsin).
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

import settings as cfg
from data import cache


def _normalize(df):
    """yfinance ciktisini standart kucuk-harf kolonlara indirger."""
    if df is None or df.empty:
        return None
    df = df.rename(
        columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
        }
    )
    # Bazi durumlarda 'Adj Close' gelmezse ham kapanisi duzeltilmis olarak da kullan
    if "adj_close" not in df.columns and "close" in df.columns:
        df["adj_close"] = df["close"]
    keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume"]
            if c in df.columns]
    df = df[keep]
    # Kapanisi bos gunleri (orn. henuz kapanmamis bugunku seans) at - yoksa
    # screener'larda close[-1] NaN olur.
    subset = [c for c in ["close", "adj_close"] if c in df.columns]
    df = df.dropna(subset=subset) if subset else df.dropna(how="all")
    # Seans kesinlesmeden once bugunku ANLIK satiri ELE (sadece kesin kapanislar kalsin)
    pv = cache.provisional_date()
    if pv is not None and len(df):
        df = df[[ts.date().isoformat() != pv for ts in df.index]]
    return df


def update_symbol(symbol, full=False):
    """Tek hisseyi gunceller. full=True ise tam backfill, degilse incremental."""
    yahoo = symbol + cfg.YAHOO_SUFFIX
    last = None if full else cache.get_last_date(symbol)
    try:
        if last:
            # Son tarihten bugune (PK sayesinde tekrar eden gunler sorunsuz)
            df = yf.download(
                yahoo, start=last, auto_adjust=False, progress=False,
                threads=False,
            )
        else:
            df = yf.download(
                yahoo, period=cfg.BACKFILL_PERIOD, auto_adjust=False,
                progress=False, threads=False,
            )
    except Exception as e:  # ag hatasi vs. -> onbellek korunur
        return 0, str(e)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = _normalize(df)
    n = cache.upsert_prices(symbol, df)
    if n:
        cache.set_meta(symbol, cache.get_meta_name(symbol), cache.get_last_date(symbol))
    return n, None


def update_all(symbols, names=None, progress_cb=None, batch_size=40, pause=0.4):
    """
    Tum sembolleri parti halinde gunceller.

    names: {symbol: ad} -> meta'ya yazmak icin (opsiyonel).
    progress_cb(done, total, symbol) -> ilerleme bildirimi (opsiyonel).
    Doner: (guncellenen_satir, hata_listesi)
    """
    names = names or {}
    total = len(symbols)
    done = 0
    total_rows = 0
    errors = []

    # Cogu hissenin onbellegi varsa ortak incremental baslangic tarihi belirle
    have_cache = len(cache.symbols_in_cache()) > total * 0.5

    for i in range(0, total, batch_size):
        chunk = symbols[i : i + batch_size]
        yahoos = [s + cfg.YAHOO_SUFFIX for s in chunk]
        try:
            if have_cache:
                start = cache.global_min_last_date()
                data = yf.download(
                    yahoos, start=start, auto_adjust=False, progress=False,
                    group_by="ticker", threads=True,
                )
            else:
                data = yf.download(
                    yahoos, period=cfg.BACKFILL_PERIOD, auto_adjust=False,
                    progress=False, group_by="ticker", threads=True,
                )
        except Exception as e:
            errors.append(f"{chunk[0]}..: {e}")
            data = None

        for s, y in zip(chunk, yahoos):
            sub = None
            try:
                if data is not None and isinstance(data.columns, pd.MultiIndex):
                    if y in data.columns.get_level_values(0):
                        sub = data[y]
                elif data is not None and len(chunk) == 1:
                    sub = data
            except Exception:
                sub = None

            sub = _normalize(sub) if sub is not None else None
            if sub is not None and not sub.empty:
                total_rows += cache.upsert_prices(s, sub)
                cache.set_meta(s, names.get(s, cache.get_meta_name(s)), cache.get_last_date(s))
            done += 1
            if progress_cb:
                progress_cb(done, total, s)

        time.sleep(pause)  # Yahoo rate-limit'e saygi

    return total_rows, errors


def update_monthly(symbols, period="15y", progress_cb=None, batch_size=40, pause=0.4):
    """
    Mevsimsellik icin uzun AYLIK gecmis ceker (interval=1mo). Kucuk veridir; sik
    guncelleme gerektirmez. Doner: (eklenen_satir, hata_listesi).
    """
    total = len(symbols)
    done, total_rows = 0, 0
    errors = []
    for i in range(0, total, batch_size):
        chunk = symbols[i : i + batch_size]
        yahoos = [s + cfg.YAHOO_SUFFIX for s in chunk]
        try:
            data = yf.download(
                yahoos, period=period, interval="1mo", auto_adjust=False,
                progress=False, group_by="ticker", threads=True,
            )
        except Exception as e:
            errors.append(f"{chunk[0]}..: {e}")
            data = None

        for s, y in zip(chunk, yahoos):
            sub = None
            try:
                if data is not None and isinstance(data.columns, pd.MultiIndex):
                    if y in data.columns.get_level_values(0):
                        sub = data[y]
                elif data is not None and len(chunk) == 1:
                    sub = data
            except Exception:
                sub = None

            sub = _normalize(sub) if sub is not None else None
            if sub is not None and not sub.empty:
                total_rows += cache.upsert_monthly(s, sub)
            done += 1
            if progress_cb:
                progress_cb(done, total, s)

        time.sleep(pause)

    return total_rows, errors
