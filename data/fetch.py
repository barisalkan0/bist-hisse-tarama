"""
İş Yatırım'dan geçmiş (gün sonu / EOD) veri çekimi.

NEDEN İş Yatırım (Yahoo değil): Yahoo, BİST hisselerinde bedelsiz/bölünmeyi
DÜZELTMİYOR (close == adj_close), bu yüzden bedelsiz günlerinde sahte ~%75 "çöküş"ler
ve işlem-durması sonrası sahte sıçramalar (ör. KGYO Temmuz +%1015) oluşuyordu; bu hem
dipten-dönüş taramasını hem mevsimselliği bozuyordu. İş Yatırım'ın `HGDG_KAPANIS` alanı
BİST-uyumlu DÜZELTİLMİŞ kapanıştır (mynet ve babanın aracı kurum ekranıyla birebir),
`HGDG_HACIM` = TL ciro. Doğrulandı: BFREN 06-10-2025 → 169,40 / 69.315.547 (mynet ile aynı).

Tek istek tüm aralığı döndürür (cap yok; 15y ≈ 3,2s). Sembol başına bir HTTP isteği;
hız için AĞ çağrıları paralel (ThreadPool), DB yazımı ANA thread'de sıralı (SQLite güvenliği).
EOD: bugünkü seans kesinleşmeden (18:30 IST öncesi) bugünkü satır atılır.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

import settings as cfg
from data import cache

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.isyatirim.com.tr/",
}
_TIMEOUT = 25
_WORKERS = 8
# Aylığa indirgeme kuralı (pandas 2.2+ 'ME', öncesi 'M')
_MRULE = "ME" if pd.__version__ >= "2.2" else "M"


def _ddmmyyyy(d):
    return d.strftime("%d-%m-%Y")


def _years_ago(n):
    today = date.today()
    try:
        return today.replace(year=today.year - n)
    except ValueError:        # 29 Şubat
        return today.replace(year=today.year - n, day=28)


def fetch_history(symbol, start, end):
    """İş Yatırım'dan [start, end] günlük veri (start/end: date). AĞ çağrısı; DB yok.
    Doner: normalize df (close/adj_close/volume) ya da None."""
    params = {"hisse": symbol, "startdate": _ddmmyyyy(start), "enddate": _ddmmyyyy(end)}
    r = requests.get(cfg.ISYATIRIM_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    records = r.json().get("value") or []
    return _normalize(records)


def _normalize(records):
    """İş Yatırım kayıtları -> standart df.
    close = adj_close = HGDG_KAPANIS (düzeltilmiş); volume = HGDG_HACIM (TL ciro)."""
    rows = []
    for x in records:
        tarih = x.get("HGDG_TARIH")
        kapanis = x.get("HGDG_KAPANIS")
        if not tarih or kapanis in (None, ""):
            continue
        try:
            d = pd.to_datetime(tarih, format="%d-%m-%Y")
            c = float(kapanis)
        except (ValueError, TypeError):
            continue
        if c <= 0:
            continue
        vol = x.get("HGDG_HACIM")
        try:
            v = float(vol) if vol not in (None, "") else 0.0
        except (ValueError, TypeError):
            v = 0.0
        rows.append((d, c, v))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "close", "volume"]).set_index("date")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["adj_close"] = df["close"]          # HGDG_KAPANIS zaten düzeltilmiş
    # Seans kesinleşmeden bugünkü ANLIK satırı ele (sadece kesin kapanışlar kalsın)
    pv = cache.provisional_date()
    if pv is not None and len(df):
        df = df[[ts.date().isoformat() != pv for ts in df.index]]
    if df.empty:
        return None
    return df[["close", "adj_close", "volume"]]


# ---------------- günlük (prices) ----------------
def _fetch_daily(symbol, full):
    """AĞ ONLY (thread-güvenli, DB'ye dokunmaz). Doner (symbol, df, err, was_full)."""
    today = date.today()
    try:
        if full:
            return symbol, fetch_history(symbol, _years_ago(cfg.BACKFILL_YEARS), today), None, True
        win_start = today - timedelta(days=45)   # kısa artımlı pencere
        return symbol, fetch_history(symbol, win_start, today), None, False
    except Exception as e:
        return symbol, None, str(e), full


def update_symbol(symbol, full=False):
    """Tek hisseyi günceller (DB ana thread'de). Doner: (satir, hata|None)."""
    _, df, err, was_full = _fetch_daily(symbol, full or not cache.get_last_date(symbol))
    if err:
        return 0, err
    if df is None or df.empty:
        return 0, None
    df = _maybe_refull(symbol, df, was_full)
    n = cache.upsert_prices(symbol, df)
    if n:
        cache.set_meta(symbol, cache.get_meta_name(symbol), cache.get_last_date(symbol))
    return n, None


def _maybe_refull(symbol, df, was_full):
    """Artımlı pencerede örtüşen günün düzeltilmiş değeri değiştiyse (bedelsiz = oran
    kırılması) tüm geçmiş yeniden ölçeklenmiştir -> tam 2y yeniden çek (DB ana thread)."""
    if was_full or df is None or df.empty:
        return df
    first = df.index[0].date().isoformat()
    old = cache.connect().execute(
        "SELECT adj_close FROM prices WHERE symbol=? AND date=?", (symbol, first)
    ).fetchone()
    if old and old[0]:
        try:
            if abs(float(df["adj_close"].iloc[0]) / float(old[0]) - 1.0) > 0.01:
                full = fetch_history(symbol, _years_ago(cfg.BACKFILL_YEARS), date.today())
                if full is not None and not full.empty:
                    return full
        except (ValueError, ZeroDivisionError, requests.RequestException):
            pass
    return df


def update_all(symbols, names=None, progress_cb=None, full=False, workers=_WORKERS):
    """
    Tüm sembolleri günceller. AĞ paralel, DB yazımı ana thread (sıralı).
    full=True: tam 2y backfill. names: {symbol: ad}. Doner: (satir, hata_listesi).
    """
    names = names or {}
    total = len(symbols)
    done = total_rows = 0
    errors = []
    # Önbellek (neredeyse) boşsa herkes için tam backfill
    if not full and len(cache.symbols_in_cache()) < total * 0.5:
        full = True

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_daily, s, full): s for s in symbols}
        for fut in as_completed(futs):
            symbol, df, err, was_full = fut.result()
            if err:
                errors.append(f"{symbol}: {err}")
            elif df is not None and not df.empty:
                df = _maybe_refull(symbol, df, was_full)   # ana thread (DB)
                total_rows += cache.upsert_prices(symbol, df)
                cache.set_meta(symbol, names.get(symbol) or cache.get_meta_name(symbol),
                               cache.get_last_date(symbol))
            done += 1
            if progress_cb:
                progress_cb(done, total, symbol)
    return total_rows, errors


# ---------------- aylık (monthly, mevsimsellik) ----------------
def _fetch_monthly(symbol, start, end):
    """AĞ + resample ONLY (DB yok). Doner (symbol, monthly_df|None, err|None)."""
    try:
        df = fetch_history(symbol, start, end)
        if df is None or df.empty:
            return symbol, None, None
        m = df[["close", "adj_close"]].resample(_MRULE).last().dropna()
        return symbol, m, None
    except Exception as e:
        return symbol, None, str(e)


def update_monthly(symbols, years=None, progress_cb=None, workers=_WORKERS):
    """~15y günlük çekip ay-sonuna indirger -> monthly tablosu. Doner: (satir, hatalar)."""
    years = years or cfg.MONTHLY_YEARS
    start, today = _years_ago(years), date.today()
    total = len(symbols)
    done = total_rows = 0
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_monthly, s, start, today): s for s in symbols}
        for fut in as_completed(futs):
            symbol, m, err = fut.result()
            if err:
                errors.append(f"{symbol}: {err}")
            elif m is not None and not m.empty:
                total_rows += cache.upsert_monthly(symbol, m)   # ana thread (DB)
            done += 1
            if progress_cb:
                progress_cb(done, total, symbol)
    return total_rows, errors
