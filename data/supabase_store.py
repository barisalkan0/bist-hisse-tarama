"""
Supabase tabanlı kimlik doğrulama ve abonelik kontrolü.

Auth işlemleri (login/logout/signup): supabase-py kullanır.
Veri işlemleri (favorites/notes/blacklist/is_pro): doğrudan Supabase REST API —
    JWT her istekte Authorization header'ına elle eklenir; supabase-py'nin iç
    session yönetimine bağımlılık yoktur.

Streamlit secrets veya ortam değişkenlerinden yapılandırılır:
    SUPABASE_URL
    SUPABASE_ANON_KEY

Yapılandırılmamışsa sessizce devre dışı kalır; uygulama anonim/yerel modda çalışır.
"""
import os
import requests
from datetime import datetime, timezone


def _from_secrets(key):
    try:
        import streamlit as st
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            return st.secrets.get(key)
    except Exception:
        pass
    return None


def _creds():
    url = os.environ.get("SUPABASE_URL") or _from_secrets("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or _from_secrets("SUPABASE_ANON_KEY")
    return url, key


def is_configured() -> bool:
    """Supabase yapılandırması mevcut mu?"""
    url, key = _creds()
    return bool(url and key)


def get_client(access_token=None, refresh_token=None):
    """Supabase auth istemcisi — yalnızca login/logout/signup için kullanılır."""
    if not is_configured():
        return None
    try:
        from supabase import create_client
        url, key = _creds()
        return create_client(url, key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# REST API yardımcıları — veri işlemleri için JWT'yi elle header'a ekler
# ---------------------------------------------------------------------------

def _rest_headers(access_token: str) -> dict:
    _, anon_key = _creds()
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _rest_url(path: str) -> str:
    url, _ = _creds()
    return f"{url}/rest/v1/{path}"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(email: str, password: str):
    """
    E-posta + şifre ile giriş yapar.
    Döndürür: (user_dict, session, None) — başarı | (None, None, hata_metni) — hata
    """
    client = get_client()
    if client is None:
        return None, None, "Supabase yapılandırılmamış."
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        user_dict = {"id": res.user.id, "email": res.user.email}
        return user_dict, res.session, None
    except Exception as e:
        msg = str(e)
        if "Invalid login credentials" in msg or "invalid_grant" in msg.lower():
            return None, None, "E-posta veya şifre hatalı."
        if "Email not confirmed" in msg:
            return None, None, "E-posta henüz doğrulanmamış. Gelen kutunuzu kontrol edin."
        return None, None, f"Giriş başarısız: {msg}"


def logout():
    """Mevcut oturumu Supabase'de sonlandırır."""
    client = get_client()
    if client is None:
        return
    try:
        client.auth.sign_out()
    except Exception:
        pass


def signup(email: str, password: str) -> str | None:
    """Yeni kullanıcı kaydı. Hata varsa hata mesajı, başarıysa None."""
    client = get_client()
    if client is None:
        return "Supabase yapılandırılmamış."
    try:
        client.auth.sign_up({"email": email, "password": password})
        return None
    except Exception as e:
        msg = str(e)
        if "User already registered" in msg:
            return "Bu e-posta zaten kayıtlı."
        return f"Kayıt başarısız: {msg}"


# ---------------------------------------------------------------------------
# Abonelik kontrolü — REST API ile
# ---------------------------------------------------------------------------

def is_pro(user_id: str, access_token: str, **_) -> bool:
    """Kullanıcının aktif pro aboneliği var mı? REST API ile doğrular."""
    if not is_configured() or not access_token:
        return False
    try:
        r = requests.get(
            _rest_url("subscriptions"),
            headers=_rest_headers(access_token),
            params={
                "user_id": f"eq.{user_id}",
                "select": "status,plan,current_period_end",
            },
            timeout=10,
        )
        if not r.ok:
            return False
        for row in r.json():
            if row.get("plan") != "pro" or row.get("status") != "active":
                continue
            period_end = row.get("current_period_end")
            if period_end is None:
                return True
            try:
                end_dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                if end_dt > datetime.now(timezone.utc):
                    return True
            except Exception:
                return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Per-user Favoriler — REST API
# ---------------------------------------------------------------------------

def fav_list(user_id: str, access_token: str, **_) -> list:
    try:
        r = requests.get(
            _rest_url("favorites"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "select": "symbol"},
            timeout=10,
        )
        r.raise_for_status()
        return [x["symbol"] for x in r.json()]
    except Exception:
        return []


def fav_add(user_id: str, symbol: str, access_token: str, **_) -> str | None:
    try:
        r = requests.post(
            _rest_url("favorites"),
            headers={**_rest_headers(access_token), "Prefer": "resolution=merge-duplicates"},
            json={"user_id": user_id, "symbol": symbol},
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)


def fav_remove(user_id: str, symbol: str, access_token: str, **_) -> str | None:
    try:
        r = requests.delete(
            _rest_url("favorites"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)


# ---------------------------------------------------------------------------
# Per-user Notlar — REST API
# ---------------------------------------------------------------------------

def note_all(user_id: str, access_token: str, **_) -> dict:
    try:
        r = requests.get(
            _rest_url("notes"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "select": "symbol,note_text,updated_at"},
            timeout=10,
        )
        r.raise_for_status()
        return {
            x["symbol"]: {"text": x.get("note_text") or "", "date": x.get("updated_at") or ""}
            for x in r.json()
        }
    except Exception:
        return {}


def note_set(user_id: str, symbol: str, text: str, access_token: str, **_) -> str | None:
    try:
        r = requests.post(
            _rest_url("notes"),
            headers={**_rest_headers(access_token), "Prefer": "resolution=merge-duplicates"},
            json={
                "user_id": user_id,
                "symbol": symbol,
                "note_text": text,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)


def note_delete(user_id: str, symbol: str, access_token: str, **_) -> str | None:
    try:
        r = requests.delete(
            _rest_url("notes"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)


# ---------------------------------------------------------------------------
# Per-user Blacklist — REST API
# ---------------------------------------------------------------------------

def blacklist_list(user_id: str, access_token: str, **_) -> list:
    try:
        r = requests.get(
            _rest_url("blacklist"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "select": "symbol"},
            timeout=10,
        )
        r.raise_for_status()
        return [x["symbol"] for x in r.json()]
    except Exception:
        return []


def blacklist_add(user_id: str, symbol: str, access_token: str, **_) -> str | None:
    try:
        r = requests.post(
            _rest_url("blacklist"),
            headers={**_rest_headers(access_token), "Prefer": "resolution=merge-duplicates"},
            json={"user_id": user_id, "symbol": symbol},
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)


def blacklist_remove(user_id: str, symbol: str, access_token: str, **_) -> str | None:
    try:
        r = requests.delete(
            _rest_url("blacklist"),
            headers=_rest_headers(access_token),
            params={"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
            timeout=10,
        )
        return None if r.ok else f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return str(e)
