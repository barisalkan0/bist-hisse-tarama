"""Egitilmis ML modelinden canli skor uretimi."""
from __future__ import annotations

from pathlib import Path
import os
import warnings

import pandas as pd

from ml_signals.features import FEATURE_COLUMNS, latest_features


MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"


def _load_artifact(path=MODEL_PATH):
    if not Path(path).exists():
        return None, "Henüz doğrulanmış ML modeli yok. Eğitim için: python -m ml_signals.train"
    try:
        os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
        warnings.filterwarnings("ignore", message="Could not find the number of physical cores.*")
        import joblib
        artifact = joblib.load(path)
    except Exception as e:
        return None, f"ML modeli yüklenemedi: {e}"
    meta = artifact.get("metadata", {})
    if not meta.get("summary", {}).get("passed"):
        return None, "ML modeli var ama backtest kabul kriterini geçmemiş; canlı sinyal gösterilmiyor."
    missing = [c for c in FEATURE_COLUMNS if c not in artifact.get("feature_columns", [])]
    if missing:
        return None, "ML modeli bu uygulama sürümüyle uyumlu değil; yeniden eğitilmeli."
    return artifact, None


def _confidence(score):
    d = abs(float(score) - 0.5)
    if d >= 0.22:
        return "Yüksek"
    if d >= 0.12:
        return "Orta"
    return "Düşük"


def _reasons(row):
    reasons = []
    if row.get("vol_ratio_5_20", 0) >= 2.0:
        reasons.append("5G ciro yüksek")
    if row.get("vol_ratio_2_20", 0) >= 2.5:
        reasons.append("son 2G hacim patlaması")
    if row.get("ret_5", 0) > 3 and row.get("ret_20", 0) > 0:
        reasons.append("kısa momentum pozitif")
    if row.get("ret_20", 0) < -8 and row.get("ret_5", 0) > 0:
        reasons.append("düşüş sonrası tepki")
    if row.get("volatility_ratio_20_60", 1) < 0.80:
        reasons.append("volatilite sıkışması")
    if row.get("sma20_gap", 0) > 0 and row.get("sma50_gap", 0) > 0:
        reasons.append("ortalamaların üstünde")
    if row.get("drawdown_60", 0) < -12 and row.get("low_distance_60", 0) < 8:
        reasons.append("60G dibe yakın")
    if not reasons:
        reasons.append("model kombinasyonu")
    return ", ".join(reasons[:3])


def score_latest(data, snapshot=None, fark=None, model_path=MODEL_PATH):
    """Son kapanis icin ML skor tablosu dondurur.

    Donus: (DataFrame, hata_mesaji|None)
    """
    artifact, err = _load_artifact(model_path)
    if err:
        return pd.DataFrame(), err

    feat = latest_features(data)
    if feat.empty:
        return pd.DataFrame(), "ML skoru için yeterli geçmiş veri yok."

    cols = artifact["feature_columns"]
    model_5 = artifact["model_5"]
    model_10 = artifact["model_10"]
    p5 = model_5.predict_proba(feat[cols])[:, 1]
    p10 = model_10.predict_proba(feat[cols])[:, 1]
    score = (p5 + p10) / 2.0

    snapshot = snapshot or {}
    fark = fark or {}
    out = pd.DataFrame({
        "Sembol": feat["symbol"],
        "ML Puanı": (score * 100).round(1),
        "5G Skor": (p5 * 100).round(1),
        "10G Skor": (p10 * 100).round(1),
        "Güven": [_confidence(x) for x in score],
        "Ana Nedenler": [_reasons(r) for _, r in feat.iterrows()],
        "Son": [snapshot.get(s) for s in feat["symbol"]],
        "Fark %": [fark.get(s) for s in feat["symbol"]],
    })
    out = out.sort_values(["ML Puanı", "10G Skor"], ascending=False).reset_index(drop=True)
    return out, None
