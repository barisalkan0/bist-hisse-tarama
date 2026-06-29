"""
BİST Hisse Tarama — Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py   (veya calistir.bat'a çift tıkla)
"""
import html
import json
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import settings as cfg
from data import cache, universe, fetch, store, supabase_store
from ml_signals import daily as ml_daily
from ml_signals import radar as ml_radar
from screeners import base, dip_donus, hacim_fiyat, hafta52, mevsim, sessizlik

st.set_page_config(page_title="BİST Hisse Tarama", page_icon="📈", layout="wide")

cache.init_db()


# ----------------------------------------------------------------------------
# Görünüm (CSS) + başlık
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
      header[data-testid="stHeader"] { background: transparent; }
      .block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1320px; }

      .app-hero {
        background: linear-gradient(120deg,#4F46E5 0%,#6366F1 48%,#0EA5E9 100%);
        color:#fff; padding: 22px 28px; border-radius: 16px; margin-bottom: 18px;
        box-shadow: 0 12px 30px rgba(79,70,229,.22);
      }
      .app-hero h1 { margin:0; font-size:1.65rem; font-weight:800; letter-spacing:-.02em; }
      .app-hero p  { margin:6px 0 0; opacity:.93; font-size:.95rem; font-weight:400; }

      .stTabs [data-baseweb="tab-list"] { gap: 6px; }
      .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0 0; padding: 9px 16px; font-weight: 600;
      }
      .stTabs [aria-selected="true"] { background: #EEF0FE; color:#4F46E5; }

      [data-testid="stMetric"] {
        background:#fff; border:1px solid #E7EAF3; border-radius:12px;
        padding:10px 14px; box-shadow:0 1px 2px rgba(16,24,40,.04);
      }
      [data-testid="stMetricValue"] { font-size:1.05rem; font-weight:700; }

      [data-testid="stDataFrame"] {
        border-radius:12px; overflow:hidden; border:1px solid #E7EAF3;
      }
      .stButton>button { border-radius:10px; font-weight:600; }
      section[data-testid="stSidebar"] { border-right:1px solid #EEF1F7; }
      section[data-testid="stSidebar"] h2 { font-weight:800; letter-spacing:-.01em; }

      /* Not kartı (elit görünüm) */
      .note-card {
        background: linear-gradient(180deg,#FFFDF5 0%,#FFFBEB 100%);
        border:1px solid #FDE8B0; border-left:4px solid #F59E0B;
        border-radius:12px; padding:12px 16px; margin:8px 0;
        box-shadow:0 1px 2px rgba(245,158,11,.08);
      }
      .note-card .nc-head { display:flex; justify-content:space-between; align-items:baseline; }
      .note-card .nc-sym { font-weight:800; color:#92400E; font-size:1.02rem; }
      .note-card .nc-date { color:#B45309; font-size:.78rem; }
      .note-card .nc-text { margin-top:6px; color:#1F2937; white-space:pre-wrap; }
      .fav-chip { color:#B45309; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="app-hero">'
    '<h1>📈 BİST Hisse Tarama</h1>'
    '<p>Uzun süredir düşüp toparlamaya başlayanlar, hacim hareketleri ve daha fazlası '
    '— gün sonu verisiyle, düzeltilmiş fiyatlarla.</p>'
    '</div>',
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Türkçe biçimlendirme yardımcıları
# ----------------------------------------------------------------------------
TR_AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
TR_AY_TAM = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tr_num(x, dec=2):
    """Türkçe sayı biçimi: binlik '.', ondalık ',' -> 96.110.687,00"""
    val = _as_number(x)
    if val is None:
        if x is None or pd.isna(x):
            return "—"
        return str(x)
    s = f"{val:,.{dec}f}"
    return s.translate(str.maketrans({",": ".", ".": ","}))


def _as_number(x):
    if x is None or pd.isna(x):
        return None
    if isinstance(x, str):
        txt = x.strip()
        if not txt or txt == "—":
            return None
        if any(ch.isalpha() for ch in txt):
            return None
        txt = txt.replace("%", "").replace("×", "").replace(" ", "")
        if "," in txt:
            txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = x
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def tr_pct(x):
    val = _as_number(x)
    if val is None:
        if x is None or pd.isna(x):
            return "—"
        return str(x)
    return f"{val:+.2f}".replace(".", ",")


def tr_date(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d.day} {TR_AY_TAM[d.month - 1]} {d.year}"
    except Exception:
        return str(iso)


def note_card_html(sym, note):
    """Bir notu elit bir kart olarak HTML döndürür."""
    return (
        "<div class='note-card'><div class='nc-head'>"
        f"<span class='nc-sym'>📝 {html.escape(str(sym))}</span>"
        f"<span class='nc-date'>{html.escape(str(note.get('date', '')))}</span>"
        "</div>"
        f"<div class='nc-text'>{html.escape(str(note.get('text', '')))}</div></div>"
    )


# ----------------------------------------------------------------------------
# Yardımcı: veri yükleme (önbellekli, sürüm anahtarıyla taze tutulur)
# ----------------------------------------------------------------------------
def _data_version():
    return st.session_state.get("data_version", 0)


@st.cache_data(show_spinner=False)
def load_data(version):
    return base.load_all(min_days=30, exclude_blacklist=True)


@st.cache_data(show_spinner=False)
def load_all_monthly(version):
    return cache.get_all_monthly(min_points=24)  # mevsimsellik için aylık geçmiş


@st.cache_data(show_spinner=False)
def load_closing(version):
    """Gösterimde kullanılan KAPANIŞ (gün sonu) tablosu + Son/Fark haritaları.
    Canlı mynet snapshot'ı yerine kapanış verisinden üretilir; anlık oynamalara
    takılmaz, hep son kesin kapanışı gösterir."""
    cs = cache.closing_snapshot()
    son_map, fark_map = {}, {}
    if not cs.empty:
        for _, r in cs.iterrows():
            if pd.notna(r["son"]):
                son_map[r["symbol"]] = r["son"]
            if pd.notna(r["fark"]):
                fark_map[r["symbol"]] = r["fark"]
    return cs, son_map, fark_map


@st.cache_data(show_spinner=False)
def load_ml_report(version):
    path = Path("ml_signals") / "backtest_report.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def bump_version():
    st.session_state["data_version"] = _data_version() + 1
    load_data.clear()
    load_closing.clear()


# ----------------------------------------------------------------------------
# Veri güncelleme işlemleri
# ----------------------------------------------------------------------------
def refresh_snapshot():
    """mynet'ten anlık tabloyu çeker (hızlı)."""
    rows = universe.fetch_universe()
    cache.save_snapshot(rows)
    return rows


def run_price_update(full=False):
    """Tüm hisselerin geçmiş verisini günceller (full=ilk backfill)."""
    rows = cache.get_snapshot()
    symbols = list(rows["symbol"]) if not rows.empty else cache.symbols_in_cache()
    names = {s: n for s, n in zip(rows["symbol"], rows["name"])} if not rows.empty else {}

    prog = st.progress(0.0, text="Veriler indiriliyor...")

    def cb(done, total, sym):
        prog.progress(done / total, text=f"{done}/{total} — {sym}")

    total_rows, errors = fetch.update_all(symbols, names=names, progress_cb=cb, full=full)
    prog.empty()
    return total_rows, errors


def run_monthly_update():
    """Mevsimsellik icin uzun aylik gecmisi gunceller."""
    rows = cache.get_snapshot()
    symbols = list(rows["symbol"]) if not rows.empty else cache.symbols_in_cache()

    prog = st.progress(0.0, text="Aylık geçmiş indiriliyor...")

    def cb(done, total, sym):
        prog.progress(done / total, text=f"{done}/{total} — {sym}")

    total_rows, errors = fetch.update_monthly(symbols, progress_cb=cb)
    prog.empty()
    return total_rows, errors


def maybe_auto_update():
    """
    Açılışta eksik günleri otomatik tamamlar (catch-up). En fazla 30 dakikada bir
    çalışır; böylece (özellikle bulutta) kullanıcı linke her girdiğinde beklemez.
    Önbellek boşsa hiçbir şey yapmaz (kullanıcı 'İlk veri indirme'ye basar).
    """
    newest = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]
    if not (newest and cache.symbols_in_cache()):
        return
    if newest >= date.today().isoformat():
        return  # zaten güncel
    last = cache.get_setting("last_auto_update")
    if last:
        try:
            if (datetime.now() - datetime.fromisoformat(last)).total_seconds() < 1800:
                return  # son 30 dk içinde güncellendi
        except ValueError:
            pass
    st.info("Kaçırılan günler güncelleniyor (internet gerekir)...")
    try:
        run_price_update(full=False)
        cache.set_setting("last_auto_update", datetime.now().isoformat())
    except Exception as e:
        st.warning(f"Geçmiş veri güncellenemedi (eski veriyle devam): {e}")


# İlk açılışta: mynet snapshot'ı çek + geçmiş veride eksik günleri otomatik tamamla.
if "boot" not in st.session_state:
    # Kalici depo (Upstash) baglantisini bir kez teshis et ve gizleme listesini esitle
    try:
        st.session_state["store_diag"] = store.diagnose()
    except Exception as e:
        st.session_state["store_diag"] = (False, False, str(e))
    for _sync in (cache.sync_blacklist_from_remote,
                  cache.sync_favorites_from_remote,
                  cache.sync_notes_from_remote):
        try:
            _sync()
        except Exception:
            pass
    with st.spinner("Hisse listesi alınıyor..."):
        try:
            refresh_snapshot()   # yalnızca sembol listesi + isimler için
        except Exception:
            pass  # liste alınamazsa önbellekteki sembollerle devam
    st.session_state["boot"] = True
    bump_version()


close_df, son_map, fark_map = load_closing(_data_version())
cached_syms = cache.symbols_in_cache()

# En guncel kapanis tarihi (hem ust baslikta hem kenar cubugunda kullanilir)
gmax = None
if cached_syms:
    gmax = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]
if gmax:
    st.caption(f"📅 **Son güncel kapanış:** {tr_date(gmax)}")


# ----------------------------------------------------------------------------
# Tablo biçimlendirme (renkli yüzdeler, ondalık formatı)
# ----------------------------------------------------------------------------
def _pct_color(v):
    if isinstance(v, (int, float)) and not pd.isna(v):
        if v > 0:
            return "color:#15803D; font-weight:600;"
        if v < 0:
            return "color:#DC2626; font-weight:600;"
    return ""


def style_results(df, favorites=None):
    """Tarama sonuç tablosu için Styler: % sütunları renkli, sayılar Türkçe biçimli,
    favori hisselerin satırı sarımsı vurgulu."""
    if df.empty:
        return df
    favorites = favorites or set()
    pct_cols = [c for c in df.columns if "%" in c]
    fmt = {}
    for c in df.columns:
        if c in pct_cols:
            fmt[c] = tr_pct
        elif c in ("Son", "Hacim (Lot)", "Hacim (TL)", "20G Ciro (TL)", "Sıkışma"):
            fmt[c] = lambda v: tr_num(v, 2)
        elif c in ("Hacim/20G Ort", "Hacim Patlaması"):
            fmt[c] = lambda v: (tr_num(v, 2) + "×") if pd.notna(v) else "—"
        elif c in (
            "ML Puanı", "Yükseliş Puanı", "Göreli Güç",
            "5G Skor", "10G Skor", "5G Yükseliş", "10G Yükseliş",
        ):
            fmt[c] = lambda v: tr_num(v, 1) if pd.notna(v) else "—"
        elif c in ("Başlangıç", "Sonuç Fiyatı"):
            fmt[c] = lambda v: tr_num(v, 2) if pd.notna(v) else "—"
        elif c == "İsabet":   # pozitif yıl oranı (%) - tek sayı, +/- renklendirmesiz
            fmt[c] = lambda v: ("%" + tr_num(v, 0)) if pd.notna(v) else "—"
        elif c.endswith("Uzaklık"):
            fmt[c] = lambda v: (tr_num(v, 2) + "%") if pd.notna(v) else "—"
    sty = df.style
    if favorites and "Sembol" in df.columns:
        def _fav_row(row):
            if row.get("Sembol") in favorites:
                return ["background-color:#FFF7E0;"] * len(row)
            return [""] * len(row)
        sty = sty.apply(_fav_row, axis=1)
    if pct_cols:
        sty = sty.map(_pct_color, subset=pct_cols)
    return sty.format(fmt, na_rep="—")


def column_popover(columns, key, fixed=("Sembol",)):
    """Küçük bir butona tıklayınca açılan, tikli (checkbox) sütun seç/gizle menüsü.
    Seçili sütun adlarını (orijinal sırada) döndürür."""
    optional = [c for c in columns if c not in fixed]
    with st.popover("⚙️ Sütunlar"):
        st.caption("Görünecek sütunlar")
        for c in optional:
            st.checkbox(c, value=True, key=f"colchk_{key}_{c}")
    chosen = [c for c in optional if st.session_state.get(f"colchk_{key}_{c}", True)]
    return [c for c in columns if c in fixed or c in chosen]


def render_table(df, key, fixed=("Sembol",), chart_days=126, height=None):
    """Şık (renkli + favori sarımsı vurgulu) tablo. Favoriler en üstte sıralanır;
    bir satıra tıklayınca altında favori/not/gizle/grafik açılır. Tablonun üstündeki
    🔍 ile harf harf canlı arama yapılabilir."""
    if df.empty:
        st.dataframe(df, width="stretch", hide_index=True)
        return
    # Aksiyon sonrası tablo anahtarini degistirerek seçimi sıfırlarız (nonce).
    # Boylece yeniden siralamada eski konumda yanlis hisse secili kalmaz.
    nonce = st.session_state.get(f"nonce_{key}", 0)
    skey = f"tbl_{key}_{nonce}"

    favs = set(_get_favs())
    df = df.reset_index(drop=True)
    if "Sembol" in df.columns and favs:
        df = (df.assign(_f=df["Sembol"].isin(favs))
                .sort_values("_f", ascending=False, kind="stable")
                .drop(columns="_f").reset_index(drop=True))

    cols = column_popover(list(df.columns), key, fixed)
    st.caption("👆 Bir satıra tıkla → ⭐ favori / 📝 not / grafik.   "
               "🔍 (tablonun üstü) ile harf harf canlı ara.")
    df_kwargs = dict(width="stretch", hide_index=True, on_select="rerun",
                     selection_mode="single-row", key=skey)
    if height is not None:
        df_kwargs["height"] = height
    event = st.dataframe(style_results(df[cols], favorites=favs), **df_kwargs)
    try:
        sel = list(event.selection.rows)
    except Exception:
        sel = []
    if sel:
        _row_detail(str(df.iloc[sel[0]]["Sembol"]), key, chart_days)


# ----------------------------------------------------------------------------
# Kenar çubuğu
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("BİST Hisse Tarama")

    try:
        _gd = date.fromisoformat(gmax) if gmax else None
        _son_lbl = f"{_gd.day} {TR_AY[_gd.month - 1]} {_gd.year}" if _gd else "—"
    except (ValueError, TypeError):
        _son_lbl = gmax or "—"
    # Tarih dar metrik kartında kesilmesin diye tam genişlik
    st.metric("Son kapanış", _son_lbl)
    st.metric("İzlenen hisse", len(cached_syms))
    st.caption("Değerler son **kesin kapanış** (gün sonu) bazlıdır; seans içi anlık "
               "fiyatlara takılmaz.")

    # Bayatlık uyarısı — İŞ GÜNÜ bazlı (tatil/hafta sonu yanlış uyarmasın)
    if gmax:
        behind = base.business_days_behind(gmax)
        if behind is not None and behind > cfg.STALE_DAYS:
            st.warning(f"⚠️ Geçmiş veri {behind} iş günü geride ({gmax}). Güncelleyin.")

    st.divider()

    if not cached_syms:
        st.info("Geçmiş veri henüz yok. İlk indirme birkaç dakika sürer.")
        if st.button("⬇️ İlk veri indirme", type="primary", width="stretch"):
            tr, errs = run_price_update(full=True)
            bump_version()
            st.success(f"{tr} satır eklendi.")
            if errs:
                st.caption(f"{len(errs)} partide uyarı oldu.")
            st.rerun()
    else:
        if st.button("🔄 Verileri Güncelle", type="primary", width="stretch"):
            try:
                refresh_snapshot()
            except Exception as e:
                st.warning(f"Anlık veri alınamadı: {e}")
            tr, errs = run_price_update(full=False)
            bump_version()
            st.success(f"Güncellendi (+{tr} satır).")
            st.rerun()
        with st.expander("🧠 ML veri bakımı", expanded=False):
            st.caption(
                f"Normal güncelleme eksik günleri tamamlar. Uzun geçmiş yenileme, günlük "
                f"fiyat/ciro verisini yaklaşık {cfg.BACKFILL_YEARS} yıla kadar yeniden çeker; "
                "model eğitimi için daha sağlam geçmiş sağlar."
            )
            if st.button("Uzun geçmişi yenile", width="stretch"):
                try:
                    refresh_snapshot()
                except Exception as e:
                    st.warning(f"Sembol listesi alınamadı: {e}")
                tr, errs = run_price_update(full=True)
                mr, merrs = run_monthly_update()
                bump_version()
                st.success(f"Uzun geçmiş yenilendi: günlük +{tr} satır, aylık +{mr} satır.")
                if errs or merrs:
                    st.caption(f"{len(errs) + len(merrs)} partide uyarı oldu.")
                st.rerun()

    st.divider()
    # ---- Hesap / Giriş ----
    if supabase_store.is_configured():
        _sb_user = st.session_state.get("user")
        if _sb_user:
            st.caption(f"👤 **{_sb_user['email']}**")
            if "_pro_now" not in st.session_state:
                st.session_state["_pro_now"] = supabase_store.is_pro(
                    _sb_user["id"], st.session_state.get("access_token", ""))
            if st.session_state["_pro_now"]:
                st.caption("✅ Pro abonelik aktif")
            else:
                st.caption("🔓 Ücretsiz hesap — Favoriler, Notlar ve Akıllı Radar Pro gerektirir")
            with st.expander("🔧 Teşhis (geçici)"):
                _diag_at = st.session_state.get("access_token", "")
                st.write("configured:", supabase_store.is_configured())
                st.write("token var:", bool(_diag_at), "uzunluk:", len(_diag_at))
                st.write("user id:", _sb_user["id"])
                if st.button("Supabase yazma testi", key="diag_write"):
                    _derr = supabase_store.fav_add(_sb_user["id"], "_TEST_", _diag_at)
                    st.write("sonuç:", _derr or "OK (HTTP 2xx)")
            if st.button("Çıkış yap", key="auth_logout", width="stretch"):
                supabase_store.logout()
                for _k in ("user", "access_token", "refresh_token", "_pro_now"):
                    st.session_state.pop(_k, None)
                st.rerun()
        else:
            with st.expander("🔑 Giriş yap"):
                _auth_email = st.text_input("E-posta", key="auth_email")
                _auth_pw = st.text_input("Şifre", type="password", key="auth_pw")
                if st.button("Giriş", key="auth_login_btn", width="stretch"):
                    if _auth_email and _auth_pw:
                        _u, _sess, _err = supabase_store.login(_auth_email, _auth_pw)
                        if _err:
                            st.error(_err)
                        else:
                            st.session_state["user"] = _u
                            st.session_state["access_token"] = _sess.access_token
                            st.session_state["refresh_token"] = _sess.refresh_token
                            st.session_state.pop("_pro_now", None)
                            st.rerun()
                    else:
                        st.warning("E-posta ve şifre girin.")
            with st.expander("📝 Kayıt ol"):
                _reg_email = st.text_input("E-posta", key="reg_email")
                _reg_pw = st.text_input("Şifre (en az 6 karakter)", type="password", key="reg_pw")
                if st.button("Kayıt ol", key="reg_btn", width="stretch"):
                    if _reg_email and _reg_pw:
                        _reg_err = supabase_store.signup(_reg_email, _reg_pw)
                        if _reg_err:
                            st.error(_reg_err)
                        else:
                            st.success("Kayıt başarılı! E-postanızı onaylayın, ardından giriş yapın.")
                    else:
                        st.warning("E-posta ve şifre girin.")
    else:
        _en, _ok, _err = st.session_state.get("store_diag", (False, False, None))
        if _ok:
            st.caption("🟢 Kalıcı gizleme: **bağlı** (Upstash) — liste yeniden başlamada korunur.")
        elif _en:
            st.caption("🟠 Kalıcı gizleme: anahtar **var** ama **bağlanılamadı**.")
            with st.expander("Hata ayrıntısı"):
                st.code(_err or "bilinmiyor")
        else:
            st.caption("🟡 Kalıcı gizleme: anahtar **okunamadı** (Secrets adı/formatı?).")
            with st.expander("Teşhis: uygulamanın gördüğü anahtar adları"):
                st.write("Değerler değil, yalnızca **isimler** (gizli değil):")
                st.code("\n".join(store.secret_keys()) or "(hiç anahtar yok)")
                st.caption("Burada `UPSTASH_REDIS_REST_URL` ve `UPSTASH_REDIS_REST_TOKEN` "
                           "isimlerini birebir görmüyorsan, Secrets'taki isim/format hatalıdır.")
    st.caption(
        "Gün sonu (EOD) veriye dayanır.\n\n"
        "**Kaynak:** mynet (hisse listesi + isimler), İş Yatırım (geçmiş kapanış + "
        "TL ciro, BİST-uyumlu **düzeltilmiş** fiyat)."
    )


# ----------------------------------------------------------------------------
# Grafik yardımcısı
# ----------------------------------------------------------------------------
def price_volume_chart(symbol, days):
    df = cache.get_prices(symbol)
    if df.empty:
        st.info("Bu hisse için geçmiş veri yok.")
        return
    sub = df.iloc[-days:] if days < len(df) else df
    vmax = float(sub["volume"].max()) or 1.0
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # Hacim: ALTTA dikey çubuklar (eksen 4×vmax'e kadar -> çubuklar en fazla %25 yükseklik)
    fig.add_trace(
        go.Bar(x=sub.index, y=sub["volume"], name="Hacim (TL)",
               marker_color="rgba(79,70,229,0.22)"),
        secondary_y=True,
    )
    # Fiyat: BASKIN, son (kapanış) değerlerine göre çizgi (dolgu yok -> hareket net görünür)
    fig.add_trace(
        go.Scatter(x=sub.index, y=sub["adj_close"], name="Fiyat (kapanış)",
                   mode="lines", line=dict(color="#4F46E5", width=2.4)),
        secondary_y=False,
    )
    fig.update_layout(
        template="plotly_white",
        height=430, margin=dict(l=10, r=10, t=56, b=80),
        title=dict(text=f"<b>{symbol}</b> — son {days} işlem günü",
                   font=dict(size=16), y=0.97, yanchor="top"),
        # Efsane (legend) ALTTA - baslikla cakismasin
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0.5, xanchor="center"),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Fiyat (TL)", secondary_y=False, showgrid=True,
                     gridcolor="rgba(0,0,0,0.05)")
    # Hacim eksenini 4×vmax'e sabitle -> çubuklar altta kalır, fiyat baskın görünür
    fig.update_yaxes(title_text="Hacim (TL)", secondary_y=True, showgrid=False,
                     range=[0, vmax * 4])

    # Turkce aylik eksen etiketleri (Jan -> Oca ...)
    tickvals, ticktext, seen = [], [], set()
    for ts in sub.index:
        key = (ts.year, ts.month)
        if key not in seen:
            seen.add(key)
            tickvals.append(ts)
            ticktext.append(f"{TR_AY[ts.month - 1]} {ts.year}")
    fig.update_xaxes(showgrid=False, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    st.plotly_chart(fig, width="stretch")


def radar_price_chart(symbol, days=126, signal_date=None):
    """Akilli Radar detayi icin fiyat + hacim + ana ortalama cizgileri."""
    df = cache.get_prices(symbol)
    if df.empty:
        st.info("Bu hisse için geçmiş veri yok.")
        return
    sub = df.iloc[-days:] if days < len(df) else df
    close = sub["adj_close"].astype(float)
    vol = sub["volume"].astype(float)
    vmax = float(vol.max()) or 1.0
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=sub.index, y=vol, name="Ciro", marker_color="rgba(79,70,229,0.20)"),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(x=sub.index, y=close, name="Fiyat", mode="lines",
                   line=dict(color="#4F46E5", width=2.5)),
        secondary_y=False,
    )
    sma20 = close.rolling(20, min_periods=10).mean()
    sma50 = close.rolling(50, min_periods=25).mean()
    fig.add_trace(
        go.Scatter(x=sub.index, y=sma20, name="20 günlük ortalama", mode="lines",
                   line=dict(color="#0EA5E9", width=1.6)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=sub.index, y=sma50, name="50 günlük ortalama", mode="lines",
                   line=dict(color="#F59E0B", width=1.6)),
        secondary_y=False,
    )
    last60 = close.iloc[-60:] if len(close) >= 60 else close
    if not last60.empty:
        fig.add_hline(y=float(last60.min()), line_dash="dot", line_color="#DC2626",
                      annotation_text="60G dip", annotation_position="bottom right")
        fig.add_hline(y=float(last60.max()), line_dash="dot", line_color="#15803D",
                      annotation_text="60G zirve", annotation_position="top right")
    if signal_date:
        try:
            sd = pd.to_datetime(signal_date)
            if sub.index.min() <= sd <= sub.index.max():
                fig.add_vline(x=sd, line_dash="dash", line_color="#7C3AED",
                              annotation_text="Radar", annotation_position="top")
        except Exception:
            pass
    fig.update_layout(
        template="plotly_white",
        height=430,
        margin=dict(l=10, r=10, t=52, b=80),
        title=dict(text=f"<b>{symbol}</b> — radar grafiği", font=dict(size=16)),
        legend=dict(orientation="h", yanchor="top", y=-0.20, x=0.5, xanchor="center"),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Fiyat (TL)", secondary_y=False, showgrid=True,
                     gridcolor="rgba(0,0,0,0.05)")
    fig.update_yaxes(title_text="Ciro (TL)", secondary_y=True, showgrid=False,
                     range=[0, vmax * 4])
    st.plotly_chart(fig, width="stretch")


def render_radar_table(df, key):
    """Akilli Radar aday tablosu ve satir detayi."""
    if df.empty:
        st.info("Bugün radara giren aday yok.")
        return
    df = df.reset_index(drop=True)
    cols = [c for c in ml_radar.DISPLAY_COLUMNS if c in df.columns]
    event = st.dataframe(
        style_results(df[cols]),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"radar_tbl_{key}",
        height=430,
    )
    try:
        sel = list(event.selection.rows)
    except Exception:
        sel = []
    if sel:
        _radar_row_detail(df.iloc[sel[0]])


def render_outcomes_panel(outcomes):
    """Radar sonuc hafizasi: ozet, kirilim ve tekil sinyal gecmisi."""
    st.caption(
        "Bu ekran radarın karar hafızasıdır. Her satır geçmişte verilmiş bir sinyalin "
        "5 veya 10 iş günü sonra ne yaptığını gösterir; kayıtlar model kalitesini ölçmek "
        "ve ileride yeniden eğitimde kullanmak için saklanır."
    )
    if outcomes.empty:
        st.info("Henüz süresi dolmuş radar sonucu yok. 5/10 iş günü doldukça burası kendiliğinden dolacak.")
        return

    summary = ml_daily.outcome_summary(outcomes)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kayıt", int(summary["signals"]))
    c2.metric("İsabet", _fmt_metric_pct(summary["success_rate"]))
    c3.metric("Ort. getiri", _fmt_metric_pct(summary["avg_return"]))
    c4.metric("10G ort.", _fmt_metric_pct(summary["avg_10"]))
    c5.metric("En iyi grup", summary["best_status"])

    breakdown = ml_daily.outcome_breakdown(outcomes)
    if not breakdown.empty:
        st.markdown("**Radar gruplarına göre performans**")
        st.dataframe(
            style_results(breakdown),
            width="stretch",
            hide_index=True,
            height=min(260, 52 + len(breakdown) * 44),
        )

    st.markdown("**Tekil sinyal geçmişi**")
    f1, f2, f3, f4 = st.columns([1.4, 1.1, 1.1, 1.4])
    with f1:
        statuses = ["Hepsi"] + sorted(outcomes["Radar Durumu"].dropna().unique().tolist())
        status_filter = st.selectbox("Radar durumu", statuses, key="out_status")
    with f2:
        horizon_filter = st.selectbox("Sonuç vadesi", ["Hepsi", "5 iş günü", "10 iş günü"], key="out_horizon")
    with f3:
        result_filter = st.selectbox("Sonuç", ["Hepsi", "Tuttu", "Tutmadı"], key="out_result")
    with f4:
        q_out = st.text_input("Hisse ara", key="out_q").strip().upper()

    show = outcomes.copy()
    if status_filter != "Hepsi":
        show = show[show["Radar Durumu"] == status_filter]
    if horizon_filter != "Hepsi":
        show = show[show["Sonuç Vadesi"] == horizon_filter]
    if result_filter != "Hepsi":
        show = show[show["Tuttu mu?"] == result_filter]
    if q_out:
        show = show[show["Hisse"].str.contains(q_out, na=False)]

    cols = [
        "Sinyal Tarihi", "Hisse", "Radar Durumu", "Yükseliş Puanı", "Göreli Güç",
        "Güven", "Sonuç Vadesi", "Başlangıç", "Sonuç Tarihi", "Sonuç Fiyatı",
        "Getiri %", "En Yüksek %", "En Düşük %", "Tuttu mu?", "Basit Neden", "Ana Risk",
    ]
    cols = [c for c in cols if c in show.columns]
    event = st.dataframe(
        style_results(show[cols]),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="outcomes_table",
        height=460,
    )
    try:
        sel = list(event.selection.rows)
    except Exception:
        sel = []
    if sel:
        _outcome_row_detail(show.iloc[sel[0]])


def _outcome_row_detail(row):
    sym = str(row.get("Hisse", ""))
    st.divider()
    st.markdown(f"### {sym} — sonuç detayı")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sinyal", tr_date(row.get("Sinyal Tarihi")))
    c2.metric("Sonuç vadesi", str(row.get("Sonuç Vadesi", "—")))
    c3.metric("Getiri", _fmt_metric_pct(row.get("Getiri %")))
    c4.metric("Sonuç", str(row.get("Tuttu mu?", "—")))
    st.markdown(f"**Sinyal anındaki neden:** {row.get('Basit Neden', '—')}")
    st.markdown(f"**O gün görülen ana risk:** {row.get('Ana Risk', '—')}")
    st.caption(
        f"Başlangıç {tr_num(row.get('Başlangıç'), 2)} TL, sonuç fiyatı "
        f"{tr_num(row.get('Sonuç Fiyatı'), 2)} TL. Bu vade içinde en yüksek "
        f"{_fmt_metric_pct(row.get('En Yüksek %'))}, en düşük "
        f"{_fmt_metric_pct(row.get('En Düşük %'))} görüldü."
    )
    radar_price_chart(sym, days=160, signal_date=row.get("Sinyal Tarihi"))


def _fmt_metric_pct(v):
    val = _as_number(v)
    if val is None:
        return "—"
    return f"{val:+.1f}%".replace(".", ",")


def _radar_row_detail(row):
    sym = str(row.get("Hisse", ""))
    st.divider()
    st.markdown(f"### {sym} — {row.get('Radar Durumu', '')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Yükseliş Puanı", tr_num(row.get("Yükseliş Puanı", row.get("ML Puanı")), 1))
    c2.metric("Göreli Güç", tr_num(row.get("Göreli Güç"), 1))
    c3.metric("Güven", str(row.get("Güven", "—")))
    c4.metric("Vade", str(row.get("Vade", "—")))
    st.caption(
        "Yükseliş Puanı fiyatın 5-10 iş günü içinde anlamlı yükselme ihtimalini; "
        "Göreli Güç aynı dönemde BIST evrenine göre güçlü kalma ihtimalini gösterir."
    )
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Veri Güveni", str(row.get("Veri Güveni", "—")))
    k2.metric("Likidite", str(row.get("Likidite", "—")))
    k3.metric("Trend", str(row.get("Trend", "—")))
    k4.metric("Hacim", str(row.get("Hacim", "—")))
    reason = str(row.get("Basit Neden", "—"))
    risk = str(row.get("Ana Risk", "—"))
    st.markdown(f"**Neden listede?** {reason}")
    st.caption(_radar_reason_explain(reason))
    st.markdown(f"**Ne olursa dikkat?** {risk}")
    st.caption(_radar_risk_explain(risk))
    st.markdown(f"**Takip planı:** {row.get('Takip Planı', _radar_follow_text(row))}")
    if row.get("Güven") == "Yüksek":
        st.success("Model ve teknik koşullar aynı yöne daha net bakıyor. Yine de tek başına al/sat kararı değildir.")
    elif row.get("Güven") == "Orta":
        st.info("Sinyal var; fiyat davranışı ve hacim teyidi izlenmeli.")
    else:
        st.warning("Sinyal zayıf; sadece izleme listesine almak daha doğru.")
    radar_price_chart(sym, days=126, signal_date=row.get("data_date") or row.get("Veri Tarihi"))
    with st.expander("Grafik nasıl okunur?", expanded=True):
        st.markdown(
            "- **Mor çizgi fiyat:** Yukarı gidiyorsa hisse güçleniyor, aşağı dönüyorsa sinyal zayıflıyor.\n"
            "- **Mavi çizgi 20 günlük ortalama:** Kısa vadeli yönü gösterir. Fiyat bunun üstündeyse kısa vade daha olumlu okunur.\n"
            "- **Turuncu çizgi 50 günlük ortalama:** Daha sakin ana yönü gösterir. Fiyat bunun üstündeyse genel görüntü daha güçlüdür.\n"
            "- **Açık mor sütunlar ciro:** Sütunlar yükseliyorsa harekete para/hacim eşlik ediyor demektir.\n"
            "- **Yeşil noktalı çizgi 60G zirve:** Fiyat buraya yakınsa hisse zaten çok yükselmiş olabilir.\n"
            "- **Kırmızı noktalı çizgi 60G dip:** Fiyat buraya yakınsa tepki arıyor olabilir ama zayıflık riski de vardır.\n"
            "- **Radar dikey çizgisi:** Modelin bugünkü kapanışta bu hisseyi radara aldığı günü gösterir."
        )


def _radar_reason_explain(text):
    parts = []
    if "ortalamaların üzerinde" in text:
        parts.append("Fiyat son dönemdeki ortalama fiyatlarının üstünde kaldığı için trend bozulmamış görünüyor.")
    if "para girişi" in text or "hacim" in text:
        parts.append("İşlem hacmi/ciro artışı, hareketin daha fazla kişi tarafından izlendiğini gösterir.")
    if "güç toplamış" in text:
        parts.append("Son birkaç günlük fiyat hareketi yukarı yönde güçlenmiş.")
    if "Dar banttan" in text:
        parts.append("Fiyat bir süredir sıkışmış; böyle durumlarda sert hareket ihtimali artabilir.")
    if "Düşüşten sonra" in text:
        parts.append("Önce düşmüş, sonra toparlanma denemesi başlamış.")
    if "Dibe yakın" in text:
        parts.append("Fiyat son 60 günlük düşük seviyelere yakın; tepki potansiyeli var ama risk de yüksek.")
    if not parts:
        parts.append("Model birden fazla küçük işareti birlikte olumlu görmüş.")
    return " ".join(parts)


def _radar_risk_explain(text):
    if "Hacim teyidi zayıf" in text:
        return "Fiyat iyi yerde olabilir ama yeterli işlem hacmi yoksa hareket kalıcı olmayabilir; bu yüzden önce izlemek daha doğru."
    if "fazla koşmuş" in text or "hızlı yükselmiş" in text:
        return "Hisse kısa sürede çok yükseldiyse yeni alıcı bulamazsa geri çekilebilir."
    if "Bugün zayıf" in text:
        return "Günlük hareket aşağıysa toparlanma henüz teyit almamış olabilir."
    if "Oynaklık yüksek" in text:
        return "Bu tip hisseler hızlı yükselip hızlı düşebilir; stop/zarar riski daha yüksektir."
    if "ortalamaların altına" in text or "Kısa ortalamanın altında" in text:
        return "Fiyat ortalamaların altına inerse modelin gördüğü olumlu yapı bozulabilir."
    return "Risk gerçekleşirse bu hisseyi zorlamak yerine listeden çıkmasını veya yeniden güçlenmesini beklemek daha mantıklı."


def _radar_follow_text(row):
    status = str(row.get("Radar Durumu", ""))
    confidence = str(row.get("Güven", ""))
    if status == "Güçlü Aday":
        return "Bugün incele; 2-3 gün listede kalıp kalmadığına bak."
    if status == "Takip Edilecek":
        return "3-5 gün izle; puan artarsa ciddiye al."
    if status == "Riskli Ama Hareketli":
        return "Acele etme; geri çekilme ve hacim teyidi bekle."
    if confidence == "Düşük":
        return "Sadece izle; zayıflarsa uğraşma."
    return "5-10 iş günü içinde puanın güçlenip güçlenmediğini izle."


# ----------------------------------------------------------------------------
# Veri erişim katmanı: Supabase (giriş yapılmışsa) veya yerel SQLite/Upstash
# ----------------------------------------------------------------------------
def _active_user():
    return st.session_state.get("user")


def _tokens():
    return st.session_state.get("access_token", ""), st.session_state.get("refresh_token", "")


def _is_pro_now() -> bool:
    """Aktif kullanıcı Pro mu? Render başına bir kez hesaplanır (session_state'te önbellek)."""
    if not supabase_store.is_configured():
        return False  # yerel/anon mod → kapı yok (geriye dönük uyum)
    user = _active_user()
    if not user:
        return False
    if "_pro_now" not in st.session_state:
        at, _ = _tokens()
        st.session_state["_pro_now"] = supabase_store.is_pro(user["id"], at)
    return st.session_state["_pro_now"]


def _get_favs() -> list:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            return supabase_store.fav_list(user["id"], at, rt)
        return []
    return cache.get_favorites()


def _add_fav(sym: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.fav_add(user["id"], sym, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Favori kaydedilemedi: {err}"
    else:
        cache.add_favorite(sym)


def _remove_fav(sym: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.fav_remove(user["id"], sym, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Favori silinemedi: {err}"
    else:
        cache.remove_favorite(sym)


def _get_notes() -> dict:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            return supabase_store.note_all(user["id"], at, rt)
        return {}
    return cache.get_notes()


def _set_note(sym: str, text: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.note_set(user["id"], sym, text, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Not kaydedilemedi: {err}"
    else:
        cache.set_note(sym, text)


def _delete_note(sym: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.note_delete(user["id"], sym, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Not silinemedi: {err}"
    else:
        cache.delete_note(sym)


def _get_blacklist() -> list:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            return supabase_store.blacklist_list(user["id"], at, rt)
        return []
    return cache.get_blacklist()


def _add_blacklist(sym: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.blacklist_add(user["id"], sym, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Gizleme kaydedilemedi: {err}"
    else:
        cache.add_blacklist(sym)


def _remove_blacklist(sym: str) -> None:
    user = _active_user()
    if supabase_store.is_configured():
        if user:
            at, rt = _tokens()
            err = supabase_store.blacklist_remove(user["id"], sym, at, rt)
            if err:
                st.session_state["_sb_err"] = f"Gizleme kaldırılamadı: {err}"
    else:
        cache.remove_blacklist(sym)


def _clear_selection(key):
    """Aksiyon sonrası tablo seçimini sıfırla (nonce'u artırarak yeni widget)."""
    st.session_state[f"nonce_{key}"] = st.session_state.get(f"nonce_{key}", 0) + 1


def _row_detail(sym, key, chart_days):
    """Seçili hisse paneli: favori aç/kapa, gizle, not (tarihli), grafik."""
    _sb_mode = supabase_store.is_configured()
    _logged_in = _active_user() is not None
    _can_use = (not _sb_mode) or _is_pro_now()

    favs = set(_get_favs())
    notes = _get_notes()
    is_fav = sym in favs
    st.markdown(f"### {'⭐ ' if is_fav else ''}{sym}")

    if not _can_use:
        if not _logged_in:
            st.caption("🔐 Favori ve not **Pro üyelere özel** — kenar çubuğundan giriş yapın.")
        else:
            st.caption("🔒 Favori ve not **Pro abonelik** gerektirir.")
    else:
        b1, b2 = st.columns(2)
        if b1.button("★ Favoriden çıkar" if is_fav else "☆ Favorile",
                     key=f"favbtn_{key}", width="stretch"):
            _remove_fav(sym) if is_fav else _add_fav(sym)
            _clear_selection(key)
            bump_version()
            st.rerun()
        if b2.button("🚫 Gizle (kara liste)", key=f"hidebtn_{key}", width="stretch"):
            _add_blacklist(sym)
            _clear_selection(key)
            bump_version()
            st.rerun()

        cur = notes.get(sym, {})
        txt = st.text_area("📝 Not", value=cur.get("text", ""),
                           key=f"note_{key}_{sym}", height=80,
                           placeholder="Bu hisse için notun...")
        if st.button("💾 Notu kaydet", key=f"notesave_{key}"):
            if txt.strip():
                _set_note(sym, txt.strip())
            else:
                _delete_note(sym)
            _clear_selection(key)
            bump_version()
            st.rerun()
        if cur.get("date"):
            st.caption(f"📝 Not tarihi: {cur['date']}")

    price_volume_chart(sym, chart_days)


# ----------------------------------------------------------------------------
# Radar sekmesi içeriği (abonelik kapısı arkasında çağrılır)
# ----------------------------------------------------------------------------
def _render_radar_tab():
    """Akıllı Radar sekme içeriği — sadece pro kullanıcılar görür."""
    with st.expander("Kendi takip listem", expanded=False):
        favs_now = _get_favs()
        syms_pool = set(cached_syms)
        if not close_df.empty:
            syms_pool |= set(close_df["symbol"])
        addable = [s for s in sorted(syms_pool) if s not in favs_now]
        add_watch = st.multiselect("Takibe eklenecek hisse", addable, key="radar_watch_add")
        if st.button("Takibe ekle", key="radar_watch_add_btn") and add_watch:
            for s in add_watch:
                _add_fav(s)
            bump_version()
            st.rerun()
        favs_now = _get_favs()
        if favs_now:
            st.caption("Takipteki hisseler:")
            for s in favs_now:
                c1, c2 = st.columns([4, 1])
                c1.write(s)
                if c2.button("Çıkar", key=f"radar_watch_remove_{s}"):
                    _remove_fav(s)
                    bump_version()
                    st.rerun()
        else:
            st.caption("Henüz takip listene eklenmiş hisse yok.")

    favs_now = _get_favs()
    radar_df, radar_err, radar_info = ml_daily.today_radar(
        data, snapshot=son_map, fark=fark_map, data_date=gmax, watch_symbols=favs_now
    )
    if radar_err:
        st.info(radar_err)
        st.code("python -m ml_signals.train")
        st.caption(
            "Model yoksa veya backtest geçmediyse radar canlı aday göstermez. "
            "Bu bilinçli güvenlik kuralıdır."
        )
    else:
        try:
            ml_daily.evaluate_outcomes(data, as_of_date=gmax)
        except Exception as e:
            st.warning(f"Sonuç kayıtları güncellenemedi: {e}")

        data_date = radar_info.get("data_date") or (gmax or "—")
        if radar_info.get("created"):
            st.success(f"{tr_date(data_date)} kapanışı için bugünün radar listesi oluşturuldu.")
        else:
            st.caption(f"{tr_date(data_date)} kapanışı daha önce işlendi; aynı gün ikinci radar kaydı yazılmadı.")

        counts = radar_df["Radar Durumu"].value_counts()
        strong_count = int(counts.get("Güçlü Aday", 0))
        watch_count = int(counts.get("Takip Edilecek", 0))
        risky_count = int(counts.get("Riskli Ama Hareketli", 0))
        own_count = int(len(set(favs_now) & set(radar_df["Hisse"])))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Bugün güçlü sinyal", strong_count)
        m2.metric("Teyit bekleyen", watch_count)
        m3.metric("Hareketli / riskli", risky_count)
        m4.metric("Kendi takibim", own_count)
        st.caption(
            "Yükseliş Puanı 0-100 arasıdır. 50 civarı zayıf, 60 üstü izlemeye değer, "
            "70 üstü daha güçlü sinyal sayılır. Göreli Güç destekleyici filtredir."
        )
        if strong_count == 0:
            st.info(
                "Bugün güçlü sinyal yoksa bu normaldir. Sistem zayıf günü zorla aday üretmez; "
                "yalnızca takip etmeye değer hisseleri ayrı gösterir."
            )
        with st.expander("Liste anlamları", expanded=False):
            st.markdown(
                "- **Bugün Güçlü Sinyal:** Yükseliş puanı, göreli güç, veri geçmişi ve likidite birlikte olumlu; bugün detaylı incelenir.\n"
                "- **Teyit Bekleyenler:** Yükseliş ihtimali var ama göreli güç, hacim veya trend tarafında teyit eksik; 3-5 iş günü puan/grafik izlenir.\n"
                "- **Hareketli / Riskli:** Hissede hareket var ama oynaklık, zayıf teyit veya hızlı yükseliş riski yüksek; acele edilmez.\n"
                "- **Kendi Takibim:** Senin eklediğin hisseler; radara girmese bile sonucu kayda alınır.\n"
                "- **Sonuçlar:** Süresi dolan sinyallerin 5/10 iş günü sonra gerçekten tutup tutmadığını gösterir."
            )

        view_label_map = {
            "Radar Listesi": "Tümü",
            "Bugün Güçlü Sinyal": "Güçlü Aday",
            "Teyit Bekleyenler": "Takip Edilecek",
            "Hareketli / Riskli": "Riskli Ama Hareketli",
            "Kendi Takibim": "Kendi Takibim",
            "Sonuçlar": "Sonuçlar",
        }
        selected_label = st.pills(
            "Liste",
            list(view_label_map.keys()),
            default="Radar Listesi",
            selection_mode="single",
        ) or "Radar Listesi"
        view = view_label_map[selected_label]
        if view == "Sonuçlar":
            outcomes = ml_daily.load_outcomes()
            render_outcomes_panel(outcomes)
        elif view == "Kendi Takibim":
            favs = set(_get_favs())
            show = radar_df[radar_df["Hisse"].isin(favs)].copy() if favs else radar_df.iloc[0:0]
        else:
            show = radar_df if view == "Tümü" else radar_df[radar_df["Radar Durumu"] == view]
        if view != "Sonuçlar":
            q_ml = st.text_input("Hisse ara", key="q_ml").strip().upper()
            if q_ml:
                show = show[show["Hisse"].str.contains(q_ml)]
            display_show = show.copy()
            if "Radar Durumu" in display_show.columns:
                display_show["Radar Durumu"] = display_show["Radar Durumu"].replace({
                    "Güçlü Aday": "Bugün Güçlü Sinyal",
                    "Takip Edilecek": "Teyit Bekleyen",
                    "Riskli Ama Hareketli": "Hareketli / Riskli",
                })
            st.markdown(f"**{len(display_show)} aday** gösteriliyor. Satıra tıkla → açıklama ve grafik.")
            render_radar_table(display_show, "tml")


# Supabase yazma hatası varsa bir sonraki render'da göster
if "_sb_err" in st.session_state:
    st.error(st.session_state.pop("_sb_err"))

# ----------------------------------------------------------------------------
# Sekmeler
# ----------------------------------------------------------------------------
(tab_summary, tab1, tab2, tab_52, tab_mevsim, tab_hareketlenme, tab_ml, tab3,
 tab_fav, tab_notes, tab4) = st.tabs(
    ["🏠 Özet", "🔻➡️🔺 Dipten Dönüş", "📊 Hacim / Fiyat", "📉 52 Hafta",
     "📅 Mevsimsellik", "⚡ Hareketlenme", "🧠 Akıllı Radar", "📋 Tüm Hisseler",
     "⭐ Favoriler", "📝 Notlar", "🚫 Devre Dışı"]
)


# --- Özet (Günün özeti / dashboard) ---
with tab_summary:
    st.subheader("🏠 Günün özeti")
    if close_df.empty:
        st.info("Veri yok. Kenar çubuğundan güncelleyin.")
    else:
        favs_s = set(_get_favs())
        d = close_df.dropna(subset=["fark"])
        mc = st.columns(3)
        mc[0].metric("📈 Yükselen", int((d["fark"] > 0).sum()))
        mc[1].metric("📉 Düşen", int((d["fark"] < 0).sum()))
        mc[2].metric("Toplam hisse", len(close_df))

        def _disp(sub, pairs):
            x = sub[[s for s, _ in pairs]].copy()
            x.columns = [n for _, n in pairs]
            return x

        ca, cb = st.columns(2)
        with ca:
            st.markdown("**📈 En çok artanlar**")
            top = _disp(d.nlargest(12, "fark"),
                        [("symbol", "Sembol"), ("son", "Son"), ("fark", "Fark %")])
            st.dataframe(style_results(top, favorites=favs_s),
                         width="stretch", hide_index=True)
        with cb:
            st.markdown("**📉 En çok azalanlar**")
            bot = _disp(d.nsmallest(12, "fark"),
                        [("symbol", "Sembol"), ("son", "Son"), ("fark", "Fark %")])
            st.dataframe(style_results(bot, favorites=favs_s),
                         width="stretch", hide_index=True)

        st.markdown("**🔥 Hacme göre en hareketliler**")
        vol = _disp(d.nlargest(15, "hacim_tl"),
                    [("symbol", "Sembol"), ("ad", "Ad"), ("son", "Son"),
                     ("fark", "Fark %"), ("hacim_tl", "Hacim (TL)")])
        st.dataframe(style_results(vol, favorites=favs_s),
                     width="stretch", hide_index=True)
        st.caption(f"Son kesin kapanış: {tr_date(gmax)}")

data = load_data(_data_version())


# --- Tab 1: Dipten Dönüş ---
with tab1:
    st.subheader("Uzun süredir düşüp son günlerde toparlayanlar")
    period_lbl = st.pills("Dönem", list(cfg.PERIODS.keys()),
                          default="3 Ay", selection_mode="single") or "3 Ay"
    recov_lbl = st.pills("Toparlanma penceresi", list(cfg.RECOVERY_WINDOWS.keys()),
                         default="Son 3 Gün", selection_mode="single") or "Son 3 Gün"
    method_lbl = st.radio("Düşüş tanımı", ["Katı (gün sayısı)", "Trend bazlı"])

    if method_lbl == "Trend bazlı":
        decline = st.slider("Dönemde en az düşüş (%)", 5, 60, int(cfg.DEFAULT_DECLINE_PCT))
        method = "trend"
        down_ratio = cfg.DEFAULT_DOWN_DAY_RATIO
    else:
        down_ratio = st.slider("Düşüş günü oranı (%)", 50, 75,
                               int(cfg.DEFAULT_DOWN_DAY_RATIO * 100)) / 100.0
        method = "kati"
        decline = cfg.DEFAULT_DECLINE_PCT

    period_days = cfg.PERIODS[period_lbl]
    recov_days = cfg.RECOVERY_WINDOWS[recov_lbl]

    if not data:
        st.info("Önce kenar çubuğundan veriyi indirin.")
    else:
        res = dip_donus.run(
            data, period_days, recov_days, method=method,
            decline_pct=decline, down_ratio=down_ratio,
            snapshot=son_map, fark=fark_map,
        )
        st.markdown(f"**{len(res)} hisse** bulundu — {period_lbl} düşüş + "
                    f"{recov_lbl.lower()} toparlanma.")
        q1 = st.text_input("Hisse ara", key="q_t1").strip().upper()
        res_show = res[res["Sembol"].str.contains(q1)] if q1 else res
        render_table(res_show, "t1", chart_days=period_days)


# --- Tab 2: Hacim / Fiyat ---
with tab2:
    st.subheader("Hacim artarken fiyatı düşenler")
    c1, c2 = st.columns(2)
    with c1:
        win = st.selectbox("Gün penceresi", [2, 3, 5, 7, 10], index=1)
    with c2:
        mult = st.slider("Hacim, 20G ortalamanın en az katı", 1.0, 4.0,
                         float(cfg.DEFAULT_VOLUME_MULTIPLE), 0.1)

    st.caption("Hacim karşılaştırması TL ciro (İş Yatırım) bazlıdır; bedelsiz/bölünme "
               "yanılmasına karşı dayanıklıdır.")

    if not data:
        st.info("Önce kenar çubuğundan veriyi indirin.")
    else:
        res2 = hacim_fiyat.run(data, window=win, vol_multiple=mult,
                               snapshot=son_map, fark=fark_map)
        st.markdown(f"**{len(res2)} hisse** bulundu — son {win} gün fiyat düşüşü + "
                    "yüksek hacim.")
        q2 = st.text_input("Hisse ara", key="q_t2").strip().upper()
        res2_show = res2[res2["Sembol"].str.contains(q2)] if q2 else res2
        render_table(res2_show, "t2", chart_days=90)


# --- 52 Hafta dip/zirve ---
with tab_52:
    st.subheader("52 hafta dip/zirve yakınlığı")
    cma, cmb = st.columns([2, 2])
    with cma:
        mode_lbl = st.radio("Hangisi?", ["📉 Dibe yakın", "📈 Zirveye yakın"],
                            horizontal=True)
    with cmb:
        thr = st.slider("Uzaklık eşiği (%)", 1, 30, 10)
    mode = "dip" if "Dibe" in mode_lbl else "zirve"

    if not data:
        st.info("Önce kenar çubuğundan veriyi indirin.")
    else:
        r52 = hafta52.run(data, mode=mode, threshold=float(thr),
                          snapshot=son_map, fark=fark_map)
        nere = "yıllık dibe" if mode == "dip" else "yıllık zirveye"
        st.markdown(f"**{len(r52)} hisse** — {nere} %{thr} ve daha yakın.")
        q52 = st.text_input("Hisse ara", key="q_52").strip().upper()
        r52_show = r52[r52["Sembol"].str.contains(q52)] if q52 else r52
        render_table(r52_show, "t52", chart_days=252)


# --- Mevsimsellik ---
with tab_mevsim:
    st.subheader("📅 Mevsimsellik — geçmiş aylık davranış")
    st.caption("⚠️ **Geçmiş veriye dayalı istatistiktir; gelecek garantisi DEĞİLDİR.** "
               "Az yıllı veriler güvenilmezdir. **Mevsimsel Fark** = ayın ortalamasının, "
               "hissenin genel aylık ortalamasından sapması (+: tipikten güçlü, −: zayıf) "
               "— enflasyon eğilimi ayıklanmış asıl sinyaldir.")
    monthly = load_all_monthly(_data_version())
    if not monthly:
        st.info("Aylık veri yok. Kenar çubuğundan 'Verileri Güncelle' deneyin.")
    else:
        mode = st.radio("Görünüm", ["Hisse detayı", "Ay taraması"], horizontal=True)

        if mode == "Hisse detayı":
            sym = st.selectbox("Hisse", sorted(monthly.keys()), key="mevsim_sym")
            seas = mevsim.stock_seasonality(monthly[sym])
            if seas.empty:
                st.warning("Bu hisse için yeterli aylık veri yok.")
            else:
                yrs = int(seas["Yıl"].max())
                if yrs < 5:
                    st.warning(f"⚠️ Yalnızca ~{yrs} yıllık veri — güvenilmez, dikkatli yorumla.")
                colors = ["#15803D" if v >= 0 else "#DC2626"
                          for v in seas["Mevsimsel Fark %"]]
                fig = go.Figure(go.Bar(x=seas["Ay"], y=seas["Mevsimsel Fark %"],
                                       marker_color=colors))
                fig.update_layout(template="plotly_white", height=330,
                                  margin=dict(l=10, r=10, t=46, b=10),
                                  title=dict(text=f"<b>{sym}</b> — aylara göre mevsimsel güç (%)",
                                             font=dict(size=15)),
                                  yaxis_title="Mevsimsel Fark %")
                st.plotly_chart(fig, width="stretch")
                st.dataframe(style_results(seas.drop(columns=["_m"])),
                             width="stretch", hide_index=True)
                st.caption(f"{sym} için {yrs} yıllık aylık veriye dayanır. "
                           "**Medyan**, uç (patlama) yıllara karşı dayanıklı 'tipik' getiridir; "
                           "ortalamadan çok farklıysa o ay birkaç uç yıldan beslenmiştir.")

                # 🔍 Yıl yıl döküm — ortalamanın arkasını gör
                st.divider()
                st.markdown("**🔍 Yıl yıl döküm** — bir ayın ortalamasının hangi yıldan "
                            "geldiğini kendi gözünle gör:")
                strong_m = int(seas.loc[seas["Mevsimsel Fark %"].idxmax(), "_m"])
                bm = st.selectbox("Ay", list(range(1, 13)), index=strong_m - 1,
                                  format_func=lambda m: mevsim.AY_TAM[m - 1],
                                  key="mevsim_bd_ay")
                bd = mevsim.month_year_breakdown(monthly[sym], bm)
                if bd.empty:
                    st.info("Bu ay için yıl yıl veri yok.")
                else:
                    bcolors = ["#15803D" if v >= 0 else "#DC2626" for v in bd["Getiri %"]]
                    f2 = go.Figure(go.Bar(x=bd["Yıl"].astype(str), y=bd["Getiri %"],
                                          marker_color=bcolors))
                    f2.update_layout(
                        template="plotly_white", height=300,
                        margin=dict(l=10, r=10, t=46, b=10),
                        title=dict(text=f"<b>{sym} — {mevsim.AY_TAM[bm - 1]}</b> ayı, "
                                        "yıl yıl getirisi (%)", font=dict(size=14)),
                        yaxis_title="Getiri %")
                    st.plotly_chart(f2, width="stretch")
                    bdv = bd.copy()
                    bdv["Yıl"] = bdv["Yıl"].astype(str)
                    st.dataframe(style_results(bdv), width="stretch", hide_index=True)
                    ort = float(bd["Getiri %"].mean())
                    med = float(bd["Getiri %"].median())
                    st.caption(f"**{mevsim.AY_TAM[bm - 1]}** → Ortalama **{tr_num(ort, 1)}%** · "
                               f"Medyan **{tr_num(med, 1)}%**. İkisi çok farklıysa, "
                               "büyük ortalamayı birkaç uç yıl şişiriyordur — dikkat.")

        else:  # Ay taraması
            next_m = (date.today().month % 12) + 1
            c1, c2, c3 = st.columns(3)
            with c1:
                ay = st.selectbox("Ay", list(range(1, 13)), index=next_m - 1,
                                  format_func=lambda m: mevsim.AY_TAM[m - 1])
            with c2:
                yon = st.radio("Yön", ["Güçlü", "Zayıf"], horizontal=True)
            with c3:
                miny = st.slider("En az yıl", 5, 15, 7)
            res = mevsim.month_scan(monthly, ay, min_years=miny, strong=(yon == "Güçlü"))
            st.markdown(f"**{len(res)} hisse** — **{mevsim.AY_TAM[ay - 1]}** ayında tarihsel "
                        f"{'güçlü' if yon == 'Güçlü' else 'zayıf'} (≥{miny} yıl veri).")
            qm = st.text_input("Hisse ara", key="q_mevsim").strip().upper()
            res_show = res[res["Sembol"].str.contains(qm)] if qm else res
            render_table(res_show, "tmevsim", chart_days=252)


# --- Sessizlik Sonrası Hareketlenme ---
with tab_hareketlenme:
    st.subheader("⚡ Sessizlik Sonrası Hareketlenme")
    st.caption(
        "⚠️ **Kurulum (sakin + hacim patlaması) yakalanır; YÖN tahmin DEĞİLDİR.** "
        "'Fark %' yalnızca bugünkü yön bilgisidir; tek başına al/sat sinyali değildir. "
        "Sakin bantta giderken son 2 günde hacmi patlayan likit hisseler listelenir."
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        min_ciro_m = st.slider("Min ciro (Milyon TL)", 1, 100,
                               int(cfg.MIN_CIRO / 1_000_000))
    with c2:
        min_spike_ui = st.slider("Min hacim katı (×)", 1.0, 8.0,
                                 float(cfg.MIN_SPIKE), 0.1)
    with c3:
        max_contr_ui = st.slider("Max sıkışma", 0.50, 1.00,
                                 float(cfg.MAX_CONTRACTION), 0.01)
    with c4:
        max_drift_ui = st.slider("Max sapma %", 2.0, 30.0,
                                 float(cfg.MAX_DRIFT), 0.5)

    if not data:
        st.info("Önce kenar çubuğundan veriyi indirin.")
    else:
        res_har = sessizlik.run(
            data,
            min_ciro=min_ciro_m * 1_000_000,
            max_contraction=max_contr_ui,
            max_drift=max_drift_ui,
            min_spike=min_spike_ui,
            snapshot=son_map,
            fark=fark_map,
        )
        st.markdown(f"**{len(res_har)} hisse** bulundu — sakin bant + hacim patlaması.")
        q_har = st.text_input("Hisse ara", key="q_har").strip().upper()
        res_har_show = res_har[res_har["Sembol"].str.contains(q_har)] if q_har else res_har
        render_table(res_har_show, "thar", chart_days=90)


# --- Akıllı Radar ---
with tab_ml:
    st.subheader("🧠 Akıllı Radar")
    st.caption(
        "Bu ekran **al/sat tavsiyesi değildir**. Son kesin kapanış verisine göre "
        "5-10 iş günü içinde anlamlı yükseliş ihtimali olan adayları "
        "seçer; nedeni ve riski sade dille gösterir."
    )
    st.info(
        "**Yükseliş Puanı** ana göstergedir: modelin 5-10 iş günü içinde fiyatın belirli "
        "bir eşik üstünde yükselme ihtimalini 0-100 arası okumasıdır. **Göreli Güç** yardımcı "
        "göstergedir: aynı dönemde BIST evreninden daha iyi kalma ihtimalini gösterir."
    )
    report = load_ml_report(_data_version())
    if report:
        summary = report.get("summary", {})
        data_info = report.get("data", {})
        with st.expander("Model durumu", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Backtest", "Geçti" if summary.get("passed") else "Geçmedi")
            c2.metric("Top20 10G", _fmt_metric_pct(summary.get("top20_abs_fwd_ret_10")))
            c3.metric("Hisse", data_info.get("symbols", "—"))
            c4.metric("Eğitim aralığı", f"{data_info.get('start', '—')} → {data_info.get('end', '—')}")
            st.caption(
                "Bu rapor eğitim verisi üzerinde zaman sıralı walk-forward testten gelir. "
                "Uzun geçmiş yenilendikten sonra model tekrar eğitilirse bu özet de değişir."
            )
    if not data:
        st.info("Önce kenar çubuğundan veriyi indirin.")
    else:
        _r_user = st.session_state.get("user")
        _r_unlocked = not supabase_store.is_configured()
        if supabase_store.is_configured():
            if _r_user is None:
                st.warning("🔐 Bu özelliği görmek için **kenar çubuğundan giriş yapın**.")
                st.caption("Akıllı Radar Pro abonelik gerektirir. Kenar çubuğundaki 'Giriş yap' bölümünü kullanın.")
            elif not _is_pro_now():
                st.warning("🔒 **Akıllı Radar Pro abonelik gerektirir.**")
                st.caption("Pro plana geçerek tüm radar özelliklerini açabilirsiniz.")
            else:
                _r_unlocked = True
        if _r_unlocked:
            _render_radar_tab()


# --- Tab 3: Tüm Hisseler (son kapanış) ---
with tab3:
    st.subheader("Tüm hisseler — son kapanış")
    if close_df.empty:
        st.info("Veri yok. Kenar çubuğundan güncelleyin.")
    else:
        show = close_df[["symbol", "ad", "son", "fark", "hacim_lot",
                         "hacim_tl", "tarih"]].copy()
        show.columns = ["Sembol", "Ad", "Son", "Fark %", "Hacim (Lot)",
                        "Hacim (TL)", "Tarih"]
        q = st.text_input("Hisse ara", "", key="q_t3").strip().upper()
        if q:
            show = show[show["Sembol"].str.contains(q)
                        | show["Ad"].str.upper().str.contains(q)]
        st.caption(f"Toplam {len(show)} hisse — son kesin kapanış.")
        render_table(show, "t3", chart_days=126, height=520)


# --- Favoriler ---
with tab_fav:
    st.subheader("⭐ Favori hisseler")
    if supabase_store.is_configured() and not _is_pro_now():
        if _active_user() is None:
            st.warning("🔐 Favoriler **Pro üyelere özel** — kenar çubuğundan giriş yapın.")
        else:
            st.warning("🔒 Favoriler **Pro abonelik** gerektirir.")
    else:
        favs = _get_favs()
        if not favs:
            st.info("Henüz favori yok. Tablolarda bir satıra tıklayıp **☆ Favorile** "
                    "ile ekleyebilirsin.")
        elif close_df.empty:
            st.info("Veri yok. Kenar çubuğundan güncelleyin.")
        else:
            fav_show = close_df[close_df["symbol"].isin(favs)][
                ["symbol", "ad", "son", "fark", "hacim_lot", "hacim_tl", "tarih"]].copy()
            fav_show.columns = ["Sembol", "Ad", "Son", "Fark %", "Hacim (Lot)",
                                "Hacim (TL)", "Tarih"]
            render_table(fav_show, "tfav", chart_days=126)


# --- Notlar ---
with tab_notes:
    st.subheader("📝 Notlar")
    if supabase_store.is_configured() and not _is_pro_now():
        if _active_user() is None:
            st.warning("🔐 Notlar **Pro üyelere özel** — kenar çubuğundan giriş yapın.")
        else:
            st.warning("🔒 Notlar **Pro abonelik** gerektirir.")
    else:
        st.caption("İstediğin hisse için not bırak; tarihiyle kaydedilir.")
        notes = _get_notes()
        syms_pool = set(cached_syms)
        if not close_df.empty:
            syms_pool |= set(close_df["symbol"])
        note_syms = sorted(syms_pool)

        sel = st.selectbox("Hisse seç", note_syms, key="note_sym") if note_syms else None
        if sel:
            cur = notes.get(sel, {})
            txt = st.text_area("Not", value=cur.get("text", ""),
                               key=f"note_txt_{sel}", height=110,
                               placeholder="Bu hisse hakkında notun...")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("💾 Kaydet", key="note_save"):
                if txt.strip():
                    _set_note(sel, txt.strip())
                else:
                    _delete_note(sel)
                bump_version()
                st.rerun()
            if cur and c2.button("🗑️ Sil", key="note_del"):
                _delete_note(sel)
                bump_version()
                st.rerun()

        st.divider()
        if notes:
            st.markdown(f"**Tüm notlar ({len(notes)}):**")
            for sym in sorted(notes):
                st.markdown(note_card_html(sym, notes[sym]), unsafe_allow_html=True)
        else:
            st.info("Henüz not yok. Yukarıdan bir hisse seçip not ekleyebilirsin.")


# --- Tab 4: Devre Dışı (kara liste) ---
with tab4:
    st.subheader("Devre dışı bırakılan hisseler")
    if supabase_store.is_configured() and not _is_pro_now():
        if _active_user() is None:
            st.warning("🔐 Gizleme listesi **Pro üyelere özel** — kenar çubuğundan giriş yapın.")
        else:
            st.warning("🔒 Gizleme listesi **Pro abonelik** gerektirir.")
    else:
        st.caption("Buradaki hisseler taramalarda gösterilmez.")
        black = _get_blacklist()
        base_syms = set(cached_syms)
        if not close_df.empty:
            base_syms |= set(close_df["symbol"])
        all_syms = sorted(base_syms)

        add = st.multiselect("Gizlenecek hisse ekle", [s for s in all_syms if s not in black])
        if st.button("Eklenenleri gizle") and add:
            for s in add:
                _add_blacklist(s)
            bump_version()
            st.rerun()

        st.divider()
        if black:
            st.markdown("**Şu an gizli olanlar:**")
            for s in black:
                col1, col2 = st.columns([4, 1])
                col1.write(s)
                if col2.button("Geri al", key=f"un_{s}"):
                    _remove_blacklist(s)
                    bump_version()
                    st.rerun()
        else:
            st.info("Gizlenen hisse yok.")
