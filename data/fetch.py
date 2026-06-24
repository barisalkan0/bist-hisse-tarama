"""
Yahoo Finance'ten gecmis gunluk veri cekimi (yfinance).

- auto_adjust=True -> DUZELTILMIS fiyat. BIST'te sik gorulen bedelsiz sermaye
  artirimi/bolunme carpitmasi boylece otomatik duzeltilir.
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
            "Close": "close", "Adj Close": "close", "Volume": "volume",
        }
    )
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep]
    # Kapanisi bos gunleri (ornekn henuz kapanmamis bugunku seans) at - yoksa
    # screener'larda close[-1] NaN olur.
    if "close" in df.columns:
        df = df.dropna(subset=["close"])
    else:
        df = df.dropna(how="all")
    return df


def update_symbol(symbol, full=False):
    """Tek hisseyi gunceller. full=True ise tam backfill, degilse incremental."""
    yahoo = symbol + cfg.YAHOO_SUFFIX
    last = None if full else cache.get_last_date(symbol)
    try:
        if last:
            # Son tarihten bugune (PK sayesinde tekrar eden gunler sorunsuz)
            df = yf.download(
                yahoo, start=last, auto_adjust=True, progress=False,
                threads=False,
            )
        else:
            df = yf.download(
                yahoo, period=cfg.BACKFILL_PERIOD, auto_adjust=True,
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
                    yahoos, start=start, auto_adjust=True, progress=False,
                    group_by="ticker", threads=True,
                )
            else:
                data = yf.download(
                    yahoos, period=cfg.BACKFILL_PERIOD, auto_adjust=True,
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
