"""
VPS gunluk veri guncelleme (cron'dan calisir).

Akis: Is Yatirim'dan gunluk fiyat + aylik gecmisi ceker, yerel SQLite'i gunceller,
VACUUM + gzip'ler ve Supabase Storage'a yukler. Yukleme icin "robot" maintainer
hesabiyla giris yapilir (JWT) -> kovadaki maintainer-only yazma politikasi gecerli.
Canli uygulama bu dosyayi acilista indirir; boylece veri elle mudahale olmadan taze kalir.

Gerekli ortam degiskenleri (VPS'te root-only /etc/hisse.env):
  SUPABASE_URL          = https://<proje>.supabase.co
  SUPABASE_ANON_KEY     = <anon public key>
  BOT_EMAIL             = robot hesabinin e-postasi
  BOT_PASSWORD          = robot hesabinin sifresi   (ASLA repoya/loga yazma)

Calistirma (VPS):
  cd /root/bist-hisse-tarama && set -a && . /etc/hisse.env && set +a && ./venv/bin/python -m scripts.refresh_data
"""
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def main():
    for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "BOT_EMAIL", "BOT_PASSWORD"):
        if not os.environ.get(k):
            log("EKSIK ortam degiskeni:", k)
            sys.exit(1)

    from data import cache, fetch, universe, supabase_store

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

    # 2) Gunluk fiyat (artimli) + aylik gecmis
    total, errs = fetch.update_all(symbols, names=names, full=False)
    log(f"gunluk: +{total} satir, {len(errs)} hata")
    mtotal, merrs = fetch.update_monthly(symbols)
    log(f"aylik: +{mtotal} satir, {len(merrs)} hata")

    # 3) Veri-kalitesi kapisi (bozuk/eksik veri iyi asset'i ezmesin)
    nsym = len(cache.symbols_in_cache())
    if nsym < 100 or len(errs) > 0.2 * max(nsym, 1):
        log(f"KALITE DUSUK (sym={nsym}, err={len(errs)}); UPLOAD ATLANDI")
        sys.exit(2)

    # 4) Robot hesabiyla giris -> JWT
    user, sess, err = supabase_store.login(os.environ["BOT_EMAIL"], os.environ["BOT_PASSWORD"])
    if err or not sess:
        log("LOGIN HATA:", err)
        sys.exit(3)

    # 5) VACUUM + gzip + Storage upload
    src = cache._work_path()
    tmp = os.path.join(tempfile.gettempdir(), "_refresh_upload.sqlite")
    try:
        shutil.copy2(src, tmp)
        c = sqlite3.connect(tmp)
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
    uerr = supabase_store.storage_upload(gz, sess.access_token)
    if uerr:
        log("UPLOAD HATA:", uerr)
        sys.exit(4)
    log("OK: Supabase Storage guncellendi")


if __name__ == "__main__":
    main()
