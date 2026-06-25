"""
Mevsimsellik (seasonality) — TANIMLAYICI istatistik, tahmin DEĞİL.

Uzun aylık geçmişten (adj_close) her takvim ayının davranışını çıkarır:
  - Ort. Getiri %   : o ayın yıllar boyunca ortalama aylık getirisi (ham)
  - Mevsimsel Fark % : ayın ortalaması − hissenin GENEL aylık ortalaması (de-trend);
                       enflasyon eğilimini ayıklar -> asıl mevsimsellik sinyali budur
  - İsabet           : o ayın pozitif olduğu yıl sayısı / toplam yıl
  - Yıl              : örneklem (kaç yıl)

Önemli: TL enflasyonunda her ay nominal pozitif eğilimlidir; bu yüzden ham ortalama
yanıltıcıdır, "Mevsimsel Fark" merkezlenmiş gerçek sinyaldir.
"""
import datetime as _dt

import numpy as np
import pandas as pd

AY_TAM = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def monthly_returns(df, drop_incomplete=True):
    """adj_close'tan aylık % getiri serisi (ay tarihine göre indeksli)."""
    if df is None or df.empty or "adj_close" not in df.columns:
        return pd.Series(dtype=float)
    s = df["adj_close"].dropna()
    if len(s) < 2:
        return pd.Series(dtype=float)
    ret = s.pct_change().dropna() * 100.0
    if drop_incomplete and len(ret):
        # Son nokta bu ay (henüz tamamlanmamış) ise at
        today = _dt.date.today()
        last = ret.index[-1]
        if last.year == today.year and last.month == today.month:
            ret = ret.iloc[:-1]
    return ret


def _month_stats(ret, month):
    """Tek ay (1-12) için: (ort, medyan, pozitif_yil, toplam_yil) ya da None.
    Medyan, uç (patlama) yıllara karşı dayanıklı 'tipik' ölçüdür."""
    if ret.empty:
        return None
    vals = ret[ret.index.month == month]
    if len(vals) == 0:
        return None
    return float(vals.mean()), float(vals.median()), int((vals > 0).sum()), int(len(vals))


def month_year_breakdown(df, month):
    """Bir ayın yıl yıl gerçek getirisi (DataFrame: Yıl, Getiri %).
    'Bu ortalama hangi yıldan geliyor?' sorusunu gözle doğrulamak için."""
    ret = monthly_returns(df)
    if ret.empty:
        return pd.DataFrame(columns=["Yıl", "Getiri %"])
    vals = ret[ret.index.month == month]
    rows = [{"Yıl": int(d.year), "Getiri %": round(float(v), 2)} for d, v in vals.items()]
    return pd.DataFrame(rows, columns=["Yıl", "Getiri %"])


def stock_seasonality(df):
    """Bir hisse için 12 ayın mevsimsellik tablosu (DataFrame)."""
    ret = monthly_returns(df)
    if ret.empty:
        return pd.DataFrame()
    overall = float(ret.mean())   # de-trend referansı
    rows = []
    for m in range(1, 13):
        st = _month_stats(ret, m)
        if st is None:
            continue
        avg, med, pos, yrs = st
        rows.append({
            "Ay": AY_TAM[m - 1],
            "_m": m,
            "Ort. Getiri %": round(avg, 2),
            "Medyan %": round(med, 2),
            "Mevsimsel Fark %": round(avg - overall, 2),
            "İsabet": f"{pos}/{yrs}",
            "Yıl": yrs,
        })
    out = pd.DataFrame(rows)
    return out


def month_scan(all_monthly, month, min_years=7, strong=True):
    """
    Seçilen ayda (1-12) mevsimsel olarak güçlü (strong=True) ya da zayıf hisseler.
    min_years yıldan az veriye sahip hisseler ELENİR (gürültüyü sinyal sanmamak için).
    Mevsimsel Fark'a göre sıralanır; ortalama + isabet + yıl birlikte gösterilir.
    """
    rows = []
    for sym, df in all_monthly.items():
        ret = monthly_returns(df)
        if ret.empty:
            continue
        st = _month_stats(ret, month)
        if st is None:
            continue
        avg, med, pos, yrs = st
        if yrs < min_years:
            continue
        overall = float(ret.mean())
        rows.append({
            "Sembol": sym,
            "Ort. Getiri %": round(avg, 2),
            "Medyan %": round(med, 2),
            "Mevsimsel Fark %": round(avg - overall, 2),
            "İsabet": f"{pos}/{yrs}",
            "Yıl": yrs,
        })
    cols = ["Sembol", "Ort. Getiri %", "Medyan %", "Mevsimsel Fark %", "İsabet", "Yıl"]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values("Mevsimsel Fark %", ascending=not strong).reset_index(drop=True)
    return out
