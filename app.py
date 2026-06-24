"""
BIST Hisse Tarama — Streamlit arayuzu.

Calistirmak icin:  streamlit run app.py   (veya calistir.bat'a cift tikla)
"""
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import settings as cfg
from data import cache, universe, fetch
from screeners import base, dip_donus, hacim_fiyat

st.set_page_config(page_title="BIST Hisse Tarama", page_icon="📈", layout="wide")

cache.init_db()


# ----------------------------------------------------------------------------
# Yardimci: veri yukleme (onbellekli, surum anahtariyla taze tutulur)
# ----------------------------------------------------------------------------
def _data_version():
    return st.session_state.get("data_version", 0)


@st.cache_data(show_spinner=False)
def load_data(version):
    return base.load_all(min_days=30, exclude_blacklist=True)


@st.cache_data(show_spinner=False)
def load_snapshot(version):
    snap = cache.get_snapshot()
    son_map = {}
    if not snap.empty:
        son_map = {r["symbol"]: r["son"] for _, r in snap.iterrows() if pd.notna(r["son"])}
    return snap, son_map


def bump_version():
    st.session_state["data_version"] = _data_version() + 1
    load_data.clear()
    load_snapshot.clear()


# ----------------------------------------------------------------------------
# Veri guncelleme islemleri
# ----------------------------------------------------------------------------
def refresh_snapshot():
    """mynet'ten anlik tabloyu ceker (hizli)."""
    rows = universe.fetch_universe()
    cache.save_snapshot(rows)
    return rows


def run_price_update(full=False):
    """Tum hisselerin gecmis verisini gunceller (full=ilk backfill)."""
    rows = cache.get_snapshot()
    symbols = list(rows["symbol"]) if not rows.empty else cache.symbols_in_cache()
    names = {r["symbol"]: r["name"] for r in (
        [{"symbol": s, "name": n} for s, n in zip(rows["symbol"], rows["name"])]
        if not rows.empty else []
    )}

    prog = st.progress(0.0, text="Veriler indiriliyor...")

    def cb(done, total, sym):
        prog.progress(done / total, text=f"{done}/{total} — {sym}")

    total_rows, errors = fetch.update_all(symbols, names=names, progress_cb=cb)
    prog.empty()
    return total_rows, errors


def maybe_auto_update():
    """
    Acilista eksik gunleri otomatik tamamlar (catch-up). En fazla 30 dakikada bir
    calisir; boylece (ozellikle bulutta) baban linke her girdiginde beklemez.
    Onbellek bossa hicbir sey yapmaz (kullanici 'Ilk veri indirme'ye basar).
    """
    newest = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]
    if not (newest and cache.symbols_in_cache()):
        return
    if newest >= date.today().isoformat():
        return  # zaten guncel
    last = cache.get_setting("last_auto_update")
    if last:
        try:
            if (datetime.now() - datetime.fromisoformat(last)).total_seconds() < 1800:
                return  # son 30 dk icinde guncellendi
        except ValueError:
            pass
    st.info("Kacirilan gunler guncelleniyor (internet gerekir)...")
    try:
        run_price_update(full=False)
        cache.set_setting("last_auto_update", datetime.now().isoformat())
    except Exception as e:
        st.warning(f"Gecmis veri guncellenemedi (eski veriyle devam): {e}")


# Ilk acilista: mynet snapshot'i cek + gecmis veride eksik gunleri otomatik tamamla.
# Boylece bilgisayar gunlerce kapali kalsa bile, acildiginda Yahoo'daki tam gecmisten
# kacirilan tum gunler tek seferde geri yuklenir (catch-up).
if "boot" not in st.session_state:
    with st.spinner("Anlik veriler aliniyor..."):
        try:
            refresh_snapshot()
        except Exception as e:
            st.warning(f"mynet anlik verisi alinamadi (internet?): {e}")
    maybe_auto_update()
    st.session_state["boot"] = True
    bump_version()


snap_df, son_map = load_snapshot(_data_version())
cached_syms = cache.symbols_in_cache()


# ----------------------------------------------------------------------------
# Kenar cubugu
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("📈 BIST Hisse Tarama")

    last_upd = cache.last_global_update()
    if last_upd:
        st.caption(f"Gecmis veri son guncelleme: {last_upd}")
    st.caption(f"Onbellekteki hisse: {len(cached_syms)}")
    if not snap_df.empty:
        cap = snap_df["captured"].max()
        st.caption(f"Anlik veri (mynet): {cap}")

    # Bayatlik uyarisi
    if cached_syms:
        gmax = cache.connect().execute("SELECT MAX(date) FROM prices").fetchone()[0]
        if gmax:
            age = (date.today() - date.fromisoformat(gmax)).days
            if age > cfg.STALE_DAYS:
                st.warning(f"⚠️ Gecmis veri {age} gun once ({gmax}). Guncelleyin.")

    st.divider()

    if not cached_syms:
        st.info("Gecmis veri henuz yok. Ilk indirme birkac dakika surer.")
        if st.button("⬇️ Ilk veri indirme", type="primary", width="stretch"):
            tr, errs = run_price_update(full=True)
            bump_version()
            st.success(f"{tr} satir eklendi.")
            if errs:
                st.caption(f"{len(errs)} partide uyari oldu.")
            st.rerun()
    else:
        if st.button("🔄 Verileri Guncelle", type="primary", width="stretch"):
            try:
                refresh_snapshot()
            except Exception as e:
                st.warning(f"Anlik veri alinamadi: {e}")
            tr, errs = run_price_update(full=False)
            bump_version()
            st.success(f"Guncellendi (+{tr} satir).")
            st.rerun()

    st.divider()
    st.caption("Gun sonu (EOD) veriye dayanir. Kaynak: mynet (liste/anlik) + "
               "Yahoo Finance (gecmis, duzeltilmis fiyat).")


# ----------------------------------------------------------------------------
# Grafik yardimcisi
# ----------------------------------------------------------------------------
def price_volume_chart(symbol, days):
    df = cache.get_prices(symbol)
    if df.empty:
        st.info("Bu hisse icin gecmis veri yok.")
        return
    sub = df.iloc[-days:] if days < len(df) else df
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=sub.index, y=sub["close"], name="Fiyat (duzeltilmis)",
                   line=dict(color="#1f77b4")),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(x=sub.index, y=sub["volume"], name="Hacim (lot)",
               marker_color="rgba(150,150,150,0.4)"),
        secondary_y=True,
    )
    fig.update_layout(
        height=380, margin=dict(l=10, r=10, t=40, b=10),
        title=f"{symbol} — son {days} islem gunu",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="Fiyat (TL)", secondary_y=False)
    fig.update_yaxes(title_text="Hacim", secondary_y=True, showgrid=False)
    st.plotly_chart(fig, width="stretch")


def hide_control(result_df, key):
    """Sonuc tablosundan bir hisseyi hizlica gizleme (kara liste)."""
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
    pick = st.selectbox("Grafigini gor", syms, key=f"chart_{key}")
    if pick:
        price_volume_chart(pick, days)


# ----------------------------------------------------------------------------
# Sekmeler
# ----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["🔻➡️🔺 Dipten Donus", "📊 Hacim / Fiyat", "📋 Tum Hisseler", "🚫 Devre Disi"]
)

data = load_data(_data_version())


# --- Tab 1: Dipten Donus ---
with tab1:
    st.subheader("Uzun suredir dusup son gunlerde toparlayanlar")
    c1, c2, c3 = st.columns(3)
    with c1:
        period_lbl = st.selectbox("Donem", list(cfg.PERIODS.keys()), index=2)
    with c2:
        recov_lbl = st.selectbox("Toparlanma penceresi", list(cfg.RECOVERY_WINDOWS.keys()), index=1)
    with c3:
        method_lbl = st.radio("Dusus tanimi", ["Trend bazli", "Kati (gun sayisi)"], horizontal=False)

    if method_lbl == "Trend bazli":
        decline = st.slider("Donemde en az dusus (%)", 5, 60, int(cfg.DEFAULT_DECLINE_PCT))
        method = "trend"
        down_ratio = cfg.DEFAULT_DOWN_DAY_RATIO
    else:
        down_ratio = st.slider("Dusus gunu orani (%)", 50, 75,
                               int(cfg.DEFAULT_DOWN_DAY_RATIO * 100)) / 100.0
        method = "kati"
        decline = cfg.DEFAULT_DECLINE_PCT

    period_days = cfg.PERIODS[period_lbl]
    recov_days = cfg.RECOVERY_WINDOWS[recov_lbl]

    if not data:
        st.info("Once kenar cubugundan veriyi indirin.")
    else:
        res = dip_donus.run(
            data, period_days, recov_days, method=method,
            decline_pct=decline, down_ratio=down_ratio, snapshot=son_map,
        )
        st.write(f"**{len(res)} hisse** bulundu — {period_lbl} dusus + {recov_lbl} toparlanma.")
        st.dataframe(res, width="stretch", hide_index=True)
        if not res.empty:
            chart_picker(res, period_days, "t1")
            hide_control(res, "t1")


# --- Tab 2: Hacim / Fiyat ---
with tab2:
    st.subheader("Hacim artarken fiyati dusenler")
    c1, c2 = st.columns(2)
    with c1:
        win = st.selectbox("Gun penceresi", [2, 3, 5], index=1)
    with c2:
        mult = st.slider("Hacim, 20G ortalamanin en az kati", 1.0, 4.0,
                         float(cfg.DEFAULT_VOLUME_MULTIPLE), 0.1)

    if not data:
        st.info("Once kenar cubugundan veriyi indirin.")
    else:
        res2 = hacim_fiyat.run(data, window=win, vol_multiple=mult, snapshot=son_map)
        st.write(f"**{len(res2)} hisse** bulundu — son {win} gun fiyat dusus + yuksek hacim.")
        st.dataframe(res2, width="stretch", hide_index=True)
        if not res2.empty:
            chart_picker(res2, 90, "t2")
            hide_control(res2, "t2")


# --- Tab 3: Tum Hisseler (mynet anlik) ---
with tab3:
    st.subheader("Tum hisseler — anlik (mynet)")
    if snap_df.empty:
        st.info("Anlik veri yok. Kenar cubugundan guncelleyin.")
    else:
        show = snap_df[["symbol", "name", "son", "fark", "hacim_lot", "hacim_tl", "saat"]].copy()
        show.columns = ["Sembol", "Ad", "Son", "Fark %", "Hacim (Lot)", "Hacim (TL)", "Saat"]
        q = st.text_input("Hisse ara", "").strip().upper()
        if q:
            show = show[show["Sembol"].str.contains(q) | show["Ad"].str.upper().str.contains(q)]
        st.dataframe(show, width="stretch", hide_index=True, height=520)
        st.caption(f"Toplam {len(show)} hisse.")


# --- Tab 4: Devre Disi (kara liste) ---
with tab4:
    st.subheader("Devre disi birakilan hisseler")
    st.caption("Buradaki hisseler taramalarda gosterilmez.")
    black = cache.get_blacklist()
    all_syms = sorted(set(cached_syms) | set(snap_df["symbol"]) if not snap_df.empty else cached_syms)

    add = st.multiselect("Gizlenecek hisse ekle", [s for s in all_syms if s not in black])
    if st.button("Eklenenleri gizle") and add:
        for s in add:
            cache.add_blacklist(s)
        bump_version()
        st.rerun()

    st.divider()
    if black:
        st.write("**Su an gizli olanlar:**")
        for s in black:
            col1, col2 = st.columns([4, 1])
            col1.write(s)
            if col2.button("Geri al", key=f"un_{s}"):
                cache.remove_blacklist(s)
                bump_version()
                st.rerun()
    else:
        st.info("Gizlenen hisse yok.")
