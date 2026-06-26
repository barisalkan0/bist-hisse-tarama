"""
Tarama: Sessizlik Sonrasi Hareketlenme —
Sakin/dar bantta giderken son 2 gunde hacmi patlayan likit hisseleri yakalar.
YON TAHMINI YOKTUR; yalnizca kurulum (sikisma + hacim patlamasi) isaretlenir.
"""
import pandas as pd

from screeners import base
import settings as cfg


def run(
    data,
    min_ciro=cfg.MIN_CIRO,
    max_contraction=cfg.MAX_CONTRACTION,
    max_drift=cfg.MAX_DRIFT,
    min_spike=cfg.MIN_SPIKE,
    snapshot=None,
    fark=None,
):
    snapshot = snapshot or {}
    fark = fark or {}
    rows = []
    for sym, df in data.items():
        close = df["adj_close"]
        vol = df["volume"].astype(float)

        vc = base.volatility_contraction(close)
        if vc is None:
            continue
        _, _, contraction = vc

        drift = base.recent_drift(close)
        if drift is None:
            continue

        vs = base.volume_spike(vol)
        if vs is None:
            continue
        tbase, spike = vs

        if not (
            tbase >= min_ciro
            and contraction <= max_contraction
            and abs(drift) <= max_drift
            and spike >= min_spike
        ):
            continue

        rows.append(
            {
                "Sembol": sym,
                "Son": snapshot.get(sym, round(float(close.iloc[-1]), 2)),
                "Fark %": fark.get(sym),
                "Hacim Patlaması": round(spike, 2),
                "Sıkışma": round(contraction, 2),
                "Sakin Sapma %": round(drift, 2),
                "20G Ciro (TL)": round(tbase),
                "Son Tarih": base.date_str(df, 0),
            }
        )

    cols = [
        "Sembol", "Son", "Fark %", "Hacim Patlaması", "Sıkışma",
        "Sakin Sapma %", "20G Ciro (TL)", "Son Tarih",
    ]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values("Hacim Patlaması", ascending=False).reset_index(drop=True)
    return out
