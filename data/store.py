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
import os

import requests

_BLACKLIST_KEY = "blacklist"


def _creds():
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        try:
            import streamlit as st
            url = url or st.secrets.get("UPSTASH_REDIS_REST_URL")
            token = token or st.secrets.get("UPSTASH_REDIS_REST_TOKEN")
        except Exception:
            pass
    return url, token


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
