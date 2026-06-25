"""
Kalici bulut deposu (Upstash Redis, REST API uzerinden).

Streamlit Community Cloud'un dosya sistemi gecici oldugu icin, kullanicinin
elle yaptigi 'devre disi (gizleme)' listesi yeniden baslamada kaybolur. Bu modul
o listeyi Upstash Redis'te (ucretsiz) kalici tutar. Kimlik bilgisi yoksa
(yerelde) sessizce devre disi kalir; uygulama yalnizca yerel SQLite kullanir.

Gerekli gizli anahtarlar (Streamlit Cloud > Settings > Secrets, ya da ortam degiskeni):
    UPSTASH_REDIS_REST_URL
    UPSTASH_REDIS_REST_TOKEN

Gizleme listesi Redis'te 'blacklist' adli bir SET olarak tutulur.
"""
import json
import os

import requests

_BLACKLIST_KEY = "blacklist"
_FAV_KEY = "favorites"
_NOTES_KEY = "notes"


def _from_secrets(key):
    """st.secrets'tan bir anahtari guvenli okur (farkli surumlerde calisir)."""
    try:
        import streamlit as st
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            return st.secrets.get(key)  # bazi surumler icin
    except Exception:
        pass
    return None


def _creds():
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or _from_secrets("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or _from_secrets("UPSTASH_REDIS_REST_TOKEN")
    return url, token


def secret_keys():
    """
    Teshis: uygulamanin gordugu secret ANAHTAR ADLARINI doner (DEGERLERI DEGIL).
    Yanlis isim / bos / bolum (section) altinda gomulu mu anlamak icin.
    """
    names = [f"env:{k}" for k in os.environ if "UPSTASH" in k.upper()]
    try:
        import streamlit as st
        try:
            names += [str(k) for k in st.secrets.keys()]
        except Exception as e:
            names.append(f"(secrets okunamadı: {type(e).__name__})")
    except Exception:
        names.append("(streamlit yok)")
    return names


def enabled():
    url, token = _creds()
    return bool(url and token)


def ping():
    """Upstash'e gercekten ulasilabiliyor mu? (kimlik dogru + erisilebilir)."""
    if not enabled():
        return False
    try:
        return _cmd("PING") == "PONG"
    except Exception:
        return False


def diagnose():
    """
    Baglanti durumunu teshis eder. Doner: (anahtar_var, baglanti_ok, hata_metni).
    Token'i ifsa etmez; hata metni yalnizca URL/durum bilgisi icerir.
    """
    if not enabled():
        return (False, False, "Kimlik bilgisi okunamadı (Secrets adı/formatı?).")
    try:
        res = _cmd("PING")
        if res == "PONG":
            return (True, True, None)
        return (True, False, f"Beklenmedik yanıt: {res!r}")
    except Exception as e:
        return (True, False, str(e))


def _cmd(*args):
    """Tek bir Redis komutunu REST ile calistirir. Hata olursa istisna firlatir."""
    url, token = _creds()
    if not url or not token:
        return None
    resp = requests.post(
        url.rstrip("/"),
        json=list(args),
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    resp.raise_for_status()
    return resp.json().get("result")


def blacklist_add(symbol):
    if enabled():
        _cmd("SADD", _BLACKLIST_KEY, symbol)


def blacklist_remove(symbol):
    if enabled():
        _cmd("SREM", _BLACKLIST_KEY, symbol)


def blacklist_members():
    """Upstash'teki gizleme listesini doner (liste). Devre disiysa None."""
    if not enabled():
        return None
    res = _cmd("SMEMBERS", _BLACKLIST_KEY)
    return list(res) if res else []


# ---------- Favoriler (Redis SET) ----------
def fav_add(symbol):
    if enabled():
        _cmd("SADD", _FAV_KEY, symbol)


def fav_remove(symbol):
    if enabled():
        _cmd("SREM", _FAV_KEY, symbol)


def fav_members():
    if not enabled():
        return None
    res = _cmd("SMEMBERS", _FAV_KEY)
    return list(res) if res else []


# ---------- Notlar (Redis HASH: symbol -> JSON {text, date}) ----------
def note_set(symbol, text, date):
    if enabled():
        _cmd("HSET", _NOTES_KEY, symbol, json.dumps({"text": text, "date": date}))


def note_delete(symbol):
    if enabled():
        _cmd("HDEL", _NOTES_KEY, symbol)


def _parse_note(v):
    try:
        d = json.loads(v)
        if isinstance(d, dict):
            return {"text": d.get("text", ""), "date": d.get("date", "")}
    except Exception:
        pass
    return {"text": str(v), "date": ""}


def note_all():
    """Tum notlari {symbol: {text, date}} olarak doner. Devre disiysa None."""
    if not enabled():
        return None
    res = _cmd("HGETALL", _NOTES_KEY)
    out = {}
    if isinstance(res, dict):
        for f, v in res.items():
            out[f] = _parse_note(v)
    elif isinstance(res, list):
        it = iter(res)
        for f in it:
            v = next(it, None)
            out[f] = _parse_note(v)
    return out
