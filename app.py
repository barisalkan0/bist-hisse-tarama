"""
BİST Hisse Tarama — Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py   (veya calistir.bat'a çift tıkla)
"""
import html
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import settings as cfg
from data import cache, universe, fetch, store
from screeners import base, dip_donus, hacim_fiyat, hafta52

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
    if x is None or pd.isna(x):
        return "—"
    s = f"{x:,.{dec}f}"
    return s.translate(str.maketrans({",": ".", ".": ","}))


def tr_pct(x):
    if x is None or pd.isna(x):
        return "—"
    return f"{x:+.2f}".replace(".", ",")


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

    total_rows, errors = fetch.update_all(symbols, names=names, progress_cb=cb)
    prog.empty()
    return total_rows, errors


def maybe_auto_update():
    """
    Açılışta eksik günleri otomatik tamamlar (catch-up). En fazla 30 dakikada bir
    çalışır; böylece (özellikle bulutta) babam linke her girdiğinde beklemez.
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
    maybe_auto_update()
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
        elif c in ("Son", "Hacim (Lot)", "Hacim (TL)"):
            fmt[c] = lambda v: tr_num(v, 2)
        elif c == "Hacim/20G Ort":
            fmt[c] = lambda v: (tr_num(v, 2) + "×") if pd.notna(v) else "—"
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


def render_table(df, key, fixed=("Sembol",)):
    """Sütun seç/gizle (popover) kontrollü, biçimli, favori-vurgulu sonuç tablosu."""
    if df.empty:
        st.dataframe(df, width="stretch", hide_index=True)
        return
    cols = column_popover(list(df.columns), key, fixed)
    favs = set(cache.get_favorites())
    st.dataframe(style_results(df[cols], favorites=favs),
                 width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# Kenar çubuğu
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("BİST Hisse Tarama")

    m1, m2 = st.columns(2)
    m1.metric("Son kapanış", gmax or "—")
    m2.metric("Hisse", len(cached_syms))
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

    st.divider()
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
        "**Kaynak:** mynet (liste + anlık), Yahoo Finance (geçmiş, düzeltilmiş fiyat)."
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
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=sub.index, y=sub["volume"], name="Hacim (lot)",
               marker_color="rgba(79,70,229,0.16)"),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(x=sub.index, y=sub["adj_close"], name="Fiyat (düzeltilmiş)",
                   mode="lines", line=dict(color="#4F46E5", width=2.4),
                   fill="tozeroy", fillcolor="rgba(79,70,229,0.07)"),
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
    fig.update_yaxes(title_text="Hacim", secondary_y=True, showgrid=False)

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


def row_actions(result_df, key):
    """Sonuç tablosundan favori aç/kapa + gizleme (kara liste)."""
    if result_df.empty:
        return
    syms = list(result_df["Sembol"])
    favs = set(cache.get_favorites())
    c1, c2 = st.columns(2)
    with c1:
        pick = st.selectbox("⭐ Favori aç/kapa", ["—"] + syms, key=f"fav_{key}")
        if pick != "—":
            lbl = "★ Favoriden çıkar" if pick in favs else "☆ Favorile"
            if st.button(lbl, key=f"favbtn_{key}"):
                cache.remove_favorite(pick) if pick in favs else cache.add_favorite(pick)
                bump_version()
                st.rerun()
    with c2:
        pick2 = st.selectbox("🚫 Gizle (kara liste)", ["—"] + syms, key=f"hide_{key}")
        if pick2 != "—" and st.button("Gizle", key=f"hidebtn_{key}"):
            cache.add_blacklist(pick2)
            bump_version()
            st.rerun()


def chart_picker(result_df, days, key):
    if result_df.empty:
        return
    syms = list(result_df["Sembol"])
    pick = st.selectbox("Grafiğini gör", syms, key=f"chart_{key}")
    if pick:
        price_volume_chart(pick, days)


# ----------------------------------------------------------------------------
# Sekmeler
# ----------------------------------------------------------------------------
(tab_summary, tab1, tab2, tab_52, tab3,
 tab_fav, tab_notes, tab4) = st.tabs(
    ["🏠 Özet", "🔻➡️🔺 Dipten Dönüş", "📊 Hacim / Fiyat", "📉 52 Hafta",
     "📋 Tüm Hisseler", "⭐ Favoriler", "📝 Notlar", "🚫 Devre Dışı"]
)


# --- Özet (Günün özeti / dashboard) ---
with tab_summary:
    st.subheader("🏠 Günün özeti")
    if close_df.empty:
        st.info("Veri yok. Kenar çubuğundan güncelleyin.")
    else:
        favs_s = set(cache.get_favorites())
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
        render_table(res_show, "t1")
        if not res_show.empty:
            chart_picker(res_show, period_days, "t1")
            row_actions(res_show, "t1")


# --- Tab 2: Hacim / Fiyat ---
with tab2:
    st.subheader("Hacim artarken fiyatı düşenler")
    c1, c2 = st.columns(2)
    with c1:
        win = st.selectbox("Gün penceresi", [2, 3, 5, 7, 10], index=1)
    with c2:
        mult = st.slider("Hacim, 20G ortalamanın en az katı", 1.0, 4.0,
                         float(cfg.DEFAULT_VOLUME_MULTIPLE), 0.1)

    st.caption("Hacim karşılaştırması ciro (lot × fiyat) bazlıdır; bedelsiz/bölünme "
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
        render_table(res2_show, "t2")
        if not res2_show.empty:
            chart_picker(res2_show, 90, "t2")
            row_actions(res2_show, "t2")


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
        render_table(r52_show, "t52")
        if not r52_show.empty:
            chart_picker(r52_show, 252, "t52")
            row_actions(r52_show, "t52")


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
        cols = column_popover(list(show.columns), "t3", fixed=("Sembol",))
        if q:
            show = show[show["Sembol"].str.contains(q)
                        | show["Ad"].str.upper().str.contains(q)]
        favs = set(cache.get_favorites())
        st.dataframe(style_results(show[cols], favorites=favs), width="stretch",
                     hide_index=True, height=520)
        st.caption(f"Toplam {len(show)} hisse — son kesin kapanış.")
        row_actions(show, "t3")


# --- Favoriler ---
with tab_fav:
    st.subheader("⭐ Favori hisseler")
    favs = cache.get_favorites()
    if not favs:
        st.info("Henüz favori yok. Tablolardaki **⭐ Favori aç/kapa** ile ekleyebilirsin.")
    else:
        notes = cache.get_notes()
        fav_show = close_df[close_df["symbol"].isin(favs)][
            ["symbol", "ad", "son", "fark", "hacim_lot", "hacim_tl", "tarih"]].copy()
        fav_show.columns = ["Sembol", "Ad", "Son", "Fark %", "Hacim (Lot)",
                            "Hacim (TL)", "Tarih"]
        st.dataframe(style_results(fav_show, favorites=set(favs)),
                     width="stretch", hide_index=True)

        st.divider()
        pick = st.selectbox("Favori detayı / grafik", favs, key="fav_detail")
        if pick:
            if st.button("★ Favoriden çıkar", key="fav_remove_detail"):
                cache.remove_favorite(pick)
                bump_version()
                st.rerun()
            nt = notes.get(pick)
            if nt and nt.get("text"):
                st.markdown(note_card_html(pick, nt), unsafe_allow_html=True)
            price_volume_chart(pick, 126)


# --- Notlar ---
with tab_notes:
    st.subheader("📝 Notlar")
    st.caption("İstediğin hisse için not bırak; tarihiyle kaydedilir ve aynı linke "
               "giren herkes görür.")
    notes = cache.get_notes()
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
                cache.set_note(sel, txt.strip())
            else:
                cache.delete_note(sel)
            bump_version()
            st.rerun()
        if cur and c2.button("🗑️ Sil", key="note_del"):
            cache.delete_note(sel)
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
    st.caption("Buradaki hisseler taramalarda gösterilmez.")
    black = cache.get_blacklist()
    base_syms = set(cached_syms)
    if not close_df.empty:
        base_syms |= set(close_df["symbol"])
    all_syms = sorted(base_syms)

    add = st.multiselect("Gizlenecek hisse ekle", [s for s in all_syms if s not in black])
    if st.button("Eklenenleri gizle") and add:
        for s in add:
            cache.add_blacklist(s)
        bump_version()
        st.rerun()

    st.divider()
    if black:
        st.markdown("**Şu an gizli olanlar:**")
        for s in black:
            col1, col2 = st.columns([4, 1])
            col1.write(s)
            if col2.button("Geri al", key=f"un_{s}"):
                cache.remove_blacklist(s)
                bump_version()
                st.rerun()
    else:
        st.info("Gizlenen hisse yok.")
