"""
Supabase tabanlı kimlik doğrulama ve abonelik kontrolü.

Streamlit secrets veya ortam değişkenlerinden yapılandırılır:
    SUPABASE_URL
    SUPABASE_ANON_KEY

Yapılandırılmamışsa sessizce devre dışı kalır; uygulama anonim/yerel modda çalışır.
"""
import os
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


def get_client(access_token: str | None = None, refresh_token: str | None = None):
    """
    Supabase istemcisi oluşturur.
    access_token + refresh_token verilirse kimlik doğrulanmış modda çalışır.
    Yapılandırılmamışsa None döner.
    """
    if not is_configured():
        return None
    try:
        from supabase import create_client
        url, key = _creds()
        client = create_client(url, key)
        if access_token and refresh_token:
            try:
                client.auth.set_session(access_token, refresh_token)
            except Exception:
                pass
        return client
    except Exception:
        return None


def login(email: str, password: str):
    """
    E-posta + şifre ile giriş yapar.

    Döndürür:
        (user_dict, session, None)  — başarı
        (None, None, hata_metni)   — hata
    """
    client = get_client()
    if client is None:
        return None, None, "Supabase yapılandırılmamış."
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        user_dict = {
            "id": res.user.id,
            "email": res.user.email,
        }
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


def is_pro(user_id: str, access_token: str, refresh_token: str) -> bool:
    """
    Kullanıcının aktif pro aboneliği var mı kontrol eder (server-side, RLS ile).

    Supabase yapılandırılmamışsa veya hata olursa False döner.
    Bu fonksiyon her Radar sekmesi açılışında çağrılır; hafif tutulmuştur.
    """
    client = get_client(access_token, refresh_token)
    if client is None:
        return False
    try:
        res = (
            client.table("subscriptions")
            .select("status, current_period_end, plan")
            .eq("user_id", user_id)
            .execute()
        )
        rows = res.data or []
        for row in rows:
            if row.get("plan") != "pro":
                continue
            if row.get("status") != "active":
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
