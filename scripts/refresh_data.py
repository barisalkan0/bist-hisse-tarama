"""
VPS gunluk veri guncelleme (cron'dan calisir).

Akis: Is Yatirim'dan gunluk fiyat (+ ay basinda aylik gecmis) ceker, yerel SQLite'i
gunceller, VACUUM + gzip'ler ve Supabase Storage'a yukler. Yukleme service_role ile yapilir
(VPS guvenilir arka-uc; anahtar root-only /etc/hisse.env'de, RLS baypas edilir).
Canli uygulama bu dosyayi acilista indirir; veri elle mudahale olmadan taze kalir.

Gerekli ortam degiskenleri (VPS'te root-only /etc/hisse.env):
  SUPABASE_URL          = https://<proje>.supabase.co
  SUPABASE_SERVICE_KEY  = <service_role secret>   (ASLA repoya/loga yazma)

Calistirma (VPS):
  cd /root/bist-hisse-tarama && set -a && . /etc/hisse.env && set +a && ./venv/bin/python -m scripts.refresh_data
"""
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime

import requests

STORAGE_BUCKET = "market-data"
STORAGE_OBJECT = "cache.sqlite.gz"


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def _upload_service(gz_bytes, url, service_key):
    """Storage'a service_role ile yukler (RLS baypas). Basari None, aksi halde hata metni."""
    try:
        r = requests.post(
            f"{url}/storage/v1/object/{STORAGE_BUCKET}/{STORAGE_OBJECT}",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/gzip",
                "x-upsert": "true",
            },
            data=gz_bytes,
            timeout=120,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return str(e)


# ---------------------------------------------------------------------------
# Akilli Radar -> Supabase Postgres senkronu (G1 guvenlik duzeltmesi, 2026-07-02)
# Ucretli radar/sonuc verisi artik tier-RLS'li Postgres tablolarinda; public
# gzip'e (adim 6) ARTIK GIRMIYOR. Streamlit radar sekmesi bu tablolari kendi
# REST cagrisiyla okur (data/supabase_store.py: radar_snapshot/radar_outcomes).
# ---------------------------------------------------------------------------
_RADAR_SNAPSHOT_COLS = [
    "data_date", "symbol", "model_kind", "radar_status", "ml_score", "score_5",
    "score_10", "relative_score", "confidence", "data_confidence",
    "liquidity_label", "trend_label", "volume_label", "horizon",
    "simple_reason", "main_risk", "son", "fark", "created_at",
]
_RADAR_OUTCOME_COLS = [
    "signal_date", "symbol", "model_kind", "radar_status", "ml_score", "score_5",
    "score_10", "relative_score", "confidence", "signal_horizon", "simple_reason",
    "main_risk", "horizon_days", "start_price", "end_date", "end_price",
    "abs_return", "max_return", "min_return", "success", "evaluated_at",
]
_RADAR_TEXT_COLS = {
    "radar_status", "confidence", "data_confidence", "liquidity_label",
    "trend_label", "volume_label", "horizon", "simple_reason", "main_risk",
    "signal_horizon",
}


def _normalize_text(v):
    """Eski satirlarda gorulebilen mojibake'i (UTF-8 metnin yanlislikla Latin-1
    olarak okunmasi, ornek: 'GÃ¼Ã§lÃ¼') duzeltir. Zaten duzgunse dokunmaz."""
    if not isinstance(v, str) or "Ã" not in v:
        return v
    try:
        return v.encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return v


def _rows_as_dicts(db, table, cols):
    rows = db.execute(f"SELECT {','.join(cols)} FROM {table}").fetchall()
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        for k in _RADAR_TEXT_COLS & d.keys():
            d[k] = _normalize_text(d[k])
        out.append(d)
    return out


def _upsert_chunked(url, service_key, table, on_conflict, rows, chunk=500):
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        r = requests.post(
            f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
            headers=headers, json=batch, timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"{table} upsert HTTP {r.status_code}: {r.text[:300]}")


def _sync_radar_to_postgres(db, url, service_key):
    snap_rows = _rows_as_dicts(db, "ml_radar_snapshot", _RADAR_SNAPSHOT_COLS)
    out_rows = _rows_as_dicts(db, "ml_radar_outcome", _RADAR_OUTCOME_COLS)
    _upsert_chunked(url, service_key, "radar_snapshots", "data_date,symbol,model_kind", snap_rows)
    _upsert_chunked(url, service_key, "radar_outcomes",
                     "signal_date,symbol,model_kind,horizon_days", out_rows)
    log(f"radar->Postgres: snapshot={len(snap_rows)} satir, outcome={len(out_rows)} satir senkronize edildi")


def main():
    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and service_key):
        log("EKSIK ortam degiskeni: SUPABASE_URL / SUPABASE_SERVICE_KEY")
        sys.exit(1)

    from data import cache, fetch, universe

    # 1) Sembol listesi + isimler (mynet)
    try:
        rows = universe.fetch_universe()
        cache.save_snapshot(rows)
    except Exception as e:
        log("snapshot uyari (onbellek sembolleriyle devam):", e)
    snap = cache.get_snapshot()
    if not snap.empty:
        symbols = list(snap["symbol"])
        names = {s: n for s, n in zip(snap["symbol"], snap["name"])}
    else:
        symbols = cache.symbols_in_cache()
        names = {}
    if not symbols:
        log("sembol yok; cikiliyor")
        sys.exit(1)

    # 2) Gunluk fiyat (artimli, her gun)
    total, errs = fetch.update_all(symbols, names=names, full=False)
    log(f"gunluk: +{total} satir, {len(errs)} hata")

    # 3) Aylik gecmis: sadece ay basinda (1-5) yenile (her gun 611 istek israfini onler)
    if date.today().day <= 5:
        mtotal, merrs = fetch.update_monthly(symbols)
        log(f"aylik: +{mtotal} satir, {len(merrs)} hata (ay basi yenilemesi)")
    else:
        log("aylik: atlandi (ay basi degil)")

    # 4) Veri-kalitesi kapisi (bozuk/eksik veri iyi asset'i ezmesin)
    nsym = len(cache.symbols_in_cache())
    if nsym < 100 or len(errs) > 0.2 * max(nsym, 1):
        log(f"KALITE DUSUK (sym={nsym}, gunluk_err={len(errs)}); UPLOAD ATLANDI")
        sys.exit(2)

    # 5) Akilli Radar'i GUNDE 1 KEZ burada hesapla (upload'dan ONCE) — boylece
    # gzip'e giren DB'de gunun radar snapshot'i zaten hazir olur ve hicbir
    # Streamlit kullanicisi ilk-hesaplama icin beklemez (ml_radar_snapshot'taki
    # data_date+symbol+model_kind PK dedup'i sayesinde Streamlit tarafi ayni
    # gun icin tekrar skorlama yapmaz, sadece mevcut kaydi okur). Bu adim
    # basarisiz olsa da fiyat verisinin upload'ini ENGELLEMEZ (radar ikincil).
    try:
        from screeners import base
        from ml_signals import daily as ml_daily

        radar_data = base.load_all(min_days=30, exclude_blacklist=True)
        radar_date = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]
        if radar_data and radar_date:
            _, radar_err, radar_info = ml_daily.today_radar(radar_data, data_date=radar_date)
            if radar_err:
                log("radar uyari:", radar_err)
            else:
                log(f"radar: data_date={radar_info.get('data_date')} created={radar_info.get('created')}")
            # 5G/10G sonuc takibi de burada hesaplanir: Streamlit artik radar
            # tablolarini yerel SQLite'tan degil Postgres'ten okuyacagi icin
            # (bkz. asagida 5b ve adim 6) kendi tarafinda bu hesaplamayi
            # tetikleyemez; cron tek kaynak haline gelir.
            try:
                n_eval = ml_daily.evaluate_outcomes(radar_data, as_of_date=radar_date)
                log(f"radar sonuc takibi: {n_eval} kayit guncellendi")
            except Exception as e:
                log("radar sonuc takibi HATA:", e)
        else:
            log("radar atlandi: veri veya tarih yok")
    except Exception as e:
        log("radar HATA (upload yine de devam ediyor):", e)

    # 5b) Radar/Sonuc verisini Supabase Postgres'e senkronize et (G1 duzeltmesi).
    # Hatasi loglanir ama fiyat upload'ini ENGELLEMEZ (radar ikincil).
    try:
        _sync_radar_to_postgres(cache.connect(), url, service_key)
    except Exception as e:
        log("radar->Postgres senkron HATA (upload yine de devam ediyor):", e)

    # 6) VACUUM + gzip + Storage upload (service_role)
    src = cache._work_path()
    tmp = os.path.join(tempfile.gettempdir(), "_refresh_upload.sqlite")
    try:
        shutil.copy2(src, tmp)
        c = sqlite3.connect(tmp)
        # G1 duzeltmesi: ucretli radar/sonuc verisi artik Postgres'te tier-RLS
        # ile korunuyor (adim 5b onceden senkronize etti); public gzip'e
        # girmemesi icin bu iki tablo yalnizca YUKLENEN KOPYADAN silinir
        # (canli calisan DB dokunulmaz, script zaten kopya uzerinde calisiyor).
        c.execute("DROP TABLE IF EXISTS ml_radar_snapshot")
        c.execute("DROP TABLE IF EXISTS ml_radar_outcome")
        c.execute("VACUUM")
        c.close()
        with open(tmp, "rb") as f:
            gz = gzip.compress(f.read(), 6)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    log(f"gzip boyut: {len(gz) // 1024} KB")
    uerr = _upload_service(gz, url, service_key)
    if uerr:
        log("UPLOAD HATA:", uerr)
        sys.exit(4)
    log("OK: Supabase Storage guncellendi")


if __name__ == "__main__":
    main()
