"""Akilli Radar icin sade metinler ve aday secimi."""
from __future__ import annotations

import pandas as pd


DISPLAY_COLUMNS = [
    "Hisse",
    "Radar Durumu",
    "Yükseliş Puanı",
    "Göreli Güç",
    "Güven",
    "Veri Güveni",
    "Likidite",
    "Trend",
    "Hacim",
    "Vade",
    "5G Sonuç Günü",
    "10G Sonuç Günü",
    "Takip Planı",
    "Basit Neden",
    "Ana Risk",
    "Son",
    "Fark %",
]


def confidence(score_0_1: float, score_5: float, score_10: float) -> str:
    """Skor guvenini sade kullanici etiketiyle dondurur."""
    score = float(score_0_1) * 100.0
    if score >= 68 and min(score_5, score_10) >= 62:
        return "Yüksek"
    if score >= 58 and min(score_5, score_10) >= 52:
        return "Orta"
    return "Düşük"


def horizon(score_5: float, score_10: float) -> str:
    if score_10 >= score_5 + 4:
        return "10 iş günü"
    if score_5 >= score_10 + 4:
        return "5 iş günü"
    return "5-10 iş günü"


def simple_reason(row: pd.Series) -> str:
    reasons = []
    if row.get("vol_ratio_5_20", 0) >= 2.0:
        reasons.append("Son günlerde para girişi belirgin artmış")
    if row.get("vol_ratio_2_20", 0) >= 2.5:
        reasons.append("Son iki günde hacim dikkat çekmiş")
    if row.get("ret_5", 0) > 3 and row.get("ret_20", 0) > 0:
        reasons.append("Fiyat kısa vadede güç toplamış")
    if row.get("ret_20", 0) < -8 and row.get("ret_5", 0) > 0:
        reasons.append("Düşüşten sonra toparlanma denemesi var")
    if row.get("volatility_ratio_20_60", 1) < 0.80:
        reasons.append("Dar banttan çıkmaya çalışıyor olabilir")
    if row.get("sma20_gap", 0) > 0 and row.get("sma50_gap", 0) > 0:
        reasons.append("Fiyat önemli ortalamaların üzerinde")
    if row.get("low_distance_60", 999) < 8:
        reasons.append("Dibe yakın yerden tepki arıyor olabilir")
    if row.get("seasonality_years", 0) >= 4 and row.get("seasonality_mean", 0) > 2:
        reasons.append("Bulunduğu ay geçmişte destekleyici olmuş")
    if not reasons:
        reasons.append("Model birden fazla küçük olumlu işareti birlikte görüyor")
    return "; ".join(reasons[:2])


def main_risk(row: pd.Series, fark_value) -> str:
    try:
        fark = float(fark_value)
    except (TypeError, ValueError):
        fark = None

    if row.get("history_days", 0) < 120:
        return "Geçmiş veri sınırlı; model bu hisseyi daha temkinli okur"
    if row.get("turnover_ma20", 0) < 5_000_000:
        return "Likidite zayıf; küçük işlemler fiyatı sert oynatabilir"
    if fark is not None and fark >= 8:
        return "Bugün fazla koşmuş; acele etmek riskli olabilir"
    if row.get("ret_1", 0) >= 8:
        return "Son kapanışta hızlı yükselmiş; geri çekilme olabilir"
    if fark is not None and fark <= -3:
        return "Bugün zayıf; toparlanma teyidi beklenmeli"
    if row.get("volatility_20", 0) >= 6:
        return "Oynaklık yüksek; sert hareket edebilir"
    if row.get("vol_ratio_5_20", 1) < 1.1:
        return "Hacim teyidi zayıf; sadece izlemek daha doğru"
    if row.get("sma20_gap", 0) < 0:
        return "Kısa ortalamanın altında; sinyal kolay bozulabilir"
    return "Puan düşerse veya ortalamaların altına sarkarsa dikkat"


def follow_plan(status: str, confidence: str, score: float) -> str:
    """Radar satiri icin kisa takip plani."""
    if status == "Güçlü Aday":
        if confidence == "Yüksek":
            return "Bugün incele; 5-10 iş günü takip et"
        return "Bugün incele; 2-3 gün teyit ara"
    if status == "Takip Edilecek":
        return "3-5 gün izle; puan artarsa ciddiye al"
    if status == "Riskli Ama Hareketli":
        return "Acele etme; geri çekilme ve hacim teyidi bekle"
    if score >= 50:
        return "Sadece izle; güçlenirse radara döner"
    return "Şimdilik uğraşma"


def data_confidence(row: pd.Series) -> str:
    days = float(row.get("history_days", 0) or 0)
    if days >= 500:
        return "Güçlü"
    if days >= 250:
        return "Orta"
    if days >= 120:
        return "Sınırlı"
    return "Çok sınırlı"


def liquidity_label(row: pd.Series) -> str:
    turnover = float(row.get("turnover_ma20", 0) or 0)
    if turnover >= 100_000_000:
        return "Yüksek"
    if turnover >= 20_000_000:
        return "Orta"
    if turnover >= 5_000_000:
        return "Düşük"
    return "Çok düşük"


def trend_label(row: pd.Series) -> str:
    if row.get("sma20_gap", 0) > 0 and row.get("sma50_gap", 0) > 0 and row.get("ret_20", 0) > 0:
        return "Güçlü"
    if row.get("ret_5", 0) > 0 and row.get("sma20_gap", 0) > -2:
        return "Toparlanıyor"
    if row.get("sma20_gap", 0) < 0:
        return "Zayıf"
    return "Nötr"


def volume_label(row: pd.Series) -> str:
    if row.get("vol_ratio_2_20", 0) >= 2.5 or row.get("turnover_z20", 0) >= 2:
        return "Patlama"
    if row.get("vol_ratio_5_20", 0) >= 1.5:
        return "Artıyor"
    if row.get("vol_ratio_5_20", 1) < 1.0:
        return "Zayıf"
    return "Normal"


def adjust_confidence(confidence: str, row: pd.Series) -> str:
    levels = ["Düşük", "Orta", "Yüksek"]
    try:
        idx = levels.index(confidence)
    except ValueError:
        idx = 0
    if row.get("history_days", 0) < 120 or row.get("turnover_ma20", 0) < 5_000_000:
        idx -= 1
    return levels[max(0, idx)]


def radar_status(
    score: float,
    score_5: float,
    score_10: float,
    row: pd.Series,
    fark_value,
    relative_score: float | None = None,
) -> str:
    try:
        fark = float(fark_value)
    except (TypeError, ValueError):
        fark = 0.0

    rel = 50.0 if relative_score is None else float(relative_score)
    enough_history = row.get("history_days", 0) >= 120
    enough_liquidity = row.get("turnover_ma20", 0) >= 5_000_000
    if score >= 60 and min(score_5, score_10) >= 55 and rel >= 50 and fark < 10 and enough_history and enough_liquidity:
        return "Güçlü Aday"
    if score >= 55:
        return "Takip Edilecek"
    if score >= 50 and (abs(fark) >= 5 or row.get("vol_ratio_5_20", 0) >= 1.7):
        return "Riskli Ama Hareketli"
    return "İzle"


def select_candidates(scores: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Ham skor tablosundan secmece radar listesi uretir."""
    if scores.empty:
        return scores
    priority = {
        "Güçlü Aday": 0,
        "Takip Edilecek": 1,
        "Riskli Ama Hareketli": 2,
        "İzle": 3,
    }
    cand = scores[scores["Radar Durumu"] != "İzle"].copy()
    if cand.empty:
        cand = scores.nlargest(min(10, len(scores)), "Yükseliş Puanı").copy()
        cand["Radar Durumu"] = "Takip Edilecek"
        cand["Ana Risk"] = "Sinyal zayıf; sadece izleme listesine al"
    cand["_p"] = cand["Radar Durumu"].map(priority).fillna(9)
    cand = cand.sort_values(["_p", "Yükseliş Puanı", "Göreli Güç"], ascending=[True, False, False])
    return cand.drop(columns=["_p"]).head(limit).reset_index(drop=True)
