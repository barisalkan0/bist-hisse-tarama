"""
BİST Hisse Tarama — Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py   (veya calistir.bat'a çift tıkla)
"""
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import settings as cfg
from data import cache, universe, fetch, store
from screeners import base, dip_donus, hacim_fiyat

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
# Yardımcı: veri yükleme (önbellekli, sürüm anahtarıyla taze tutulur)
# ----------------------------------------------------------------------------
def _data_version():
    return st.session_state.get("data_version", 0)


@st.cache_data(show_spinner=False)
def load_data(version):
    return base.load_all(min_days=30, exclude_blacklist=True)


@st.cache_data(show_spinner=False)
def load_snapshot(version):
    snap = cache.get_snapshot()
    son_map, fark_map = {}, {}
    if not snap.empty:
        for _, r in snap.iterrows():
            if pd.notna(r["son"]):
                son_map[r["symbol"]] = r["son"]
            if pd.notna(r["fark"]):
                fark_map[r["symbol"]] = r["fark"]
    return snap, son_map, fark_map


def bump_version():
    st.session_state["data_version"] = _data_version() + 1
    load_data.clear()
    load_snapshot.clear()


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
    try:
        cache.sync_blacklist_from_remote()
    except Exception:
        pass
    with st.spinner("Anlık veriler alınıyor..."):
        try:
            refresh_snapshot()
        except Exception as e:
            st.warning(f"mynet anlık verisi alınamadı (internet?): {e}")
    maybe_auto_update()
    st.session_state["boot"] = True
    bump_version()


snap_df, son_map, fark_map = load_snapshot(_data_version())
cached_syms = cache.symbols_in_cache()


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


def style_results(df):
    """Tarama sonuç tablosu için Styler: % sütunları renkli, sayılar biçimli."""
    if df.empty:
        return df
    pct_cols = [c for c in df.columns if "%" in c]
    fmt = {}
    for c in df.columns:
        if c in pct_cols:
            fmt[c] = "{:+.2f}"
        elif c == "Son":
            fmt[c] = "{:.2f}"
        elif c == "Hacim/20G Ort":
            fmt[c] = "{:.2f}×"
    sty = df.style
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
    """Sütun seç/gizle (popover) kontrollü, biçimli sonuç tablosu."""
    if df.empty:
        st.dataframe(df, width="stretch", hide_index=True)
        return
    cols = column_popover(list(df.columns), key, fixed)
    st.dataframe(style_results(df[cols]), width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# Kenar çubuğu
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("BİST Hisse Tarama")

    gmax = None
    if cached_syms:
        gmax = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]

    m1, m2 = st.columns(2)
    m1.metric("Veri tarihi", gmax or "—")
    m2.metric("Hisse", len(cached_syms))
    if not snap_df.empty:
        cap = str(snap_df["captured"].max()).replace("T", " ")[:16]
        st.caption(f"📡 Anlık veri (mynet): {cap}")

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
        height=400, margin=dict(l=10, r=10, t=46, b=10),
        title=dict(text=f"<b>{symbol}</b> — son {days} işlem günü", font=dict(size=16)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Fiyat (TL)", secondary_y=False, showgrid=True,
                     gridcolor="rgba(0,0,0,0.05)")
    fig.update_yaxes(title_text="Hacim", secondary_y=True, showgrid=False)
    fig.update_xaxes(showgrid=False)
    st.plotly_chart(fig, width="stretch")


def hide_control(result_df, key):
    """Sonuç tablosundan bir hisseyi hızlıca gizleme (kara liste)."""
    if result_df.empty:
        return
    syms = list(result_df["Sembol"])
    col1, col2 = st.columns([3, 1])
    with col1:
        pick = st.selectbox("Hisseyi gizle (kara liste)", ["—"] + syms, key=f"hide_{key}")
    with col2:
        st.write("")
        if st.button("Gizle", key=f"hidebtn_{key}") and pick != "—":
            cache.add_blacklist(pick)
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
tab1, tab2, tab3, tab4 = st.tabs(
    ["🔻➡️🔺 Dipten Dönüş", "📊 Hacim / Fiyat", "📋 Tüm Hisseler", "🚫 Devre Dışı"]
)

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
        render_table(res, "t1")
        if not res.empty:
            chart_picker(res, period_days, "t1")
            hide_control(res, "t1")


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
        render_table(res2, "t2")
        if not res2.empty:
            chart_picker(res2, 90, "t2")
            hide_control(res2, "t2")


# --- Tab 3: Tüm Hisseler (mynet anlık) ---
with tab3:
    st.subheader("Tüm hisseler — anlık (mynet)")
    if snap_df.empty:
        st.info("Anlık veri yok. Kenar çubuğundan güncelleyin.")
    else:
        show = snap_df[["symbol", "name", "son", "fark", "hacim_lot",
                        "hacim_tl", "saat"]].copy()
        show.columns = ["Sembol", "Ad", "Son", "Fark %", "Hacim (Lot)",
                        "Hacim (TL)", "Saat"]
        q = st.text_input("Hisse ara", "").strip().upper()
        cols = column_popover(list(show.columns), "t3", fixed=("Sembol",))
        if q:
            show = show[show["Sembol"].str.contains(q)
                        | show["Ad"].str.upper().str.contains(q)]
        st.dataframe(
            show[cols], width="stretch", hide_index=True, height=520,
            column_config={
                "Son": st.column_config.NumberColumn(format="%.2f"),
                "Fark %": st.column_config.NumberColumn(format="%.2f"),
                "Hacim (Lot)": st.column_config.NumberColumn(format="%d"),
                "Hacim (TL)": st.column_config.NumberColumn(format="%.0f"),
            },
        )
        st.caption(f"Toplam {len(show)} hisse.")


# --- Tab 4: Devre Dışı (kara liste) ---
with tab4:
    st.subheader("Devre dışı bırakılan hisseler")
    st.caption("Buradaki hisseler taramalarda gösterilmez.")
    black = cache.get_blacklist()
    base_syms = set(cached_syms)
    if not snap_df.empty:
        base_syms |= set(snap_df["symbol"])
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
