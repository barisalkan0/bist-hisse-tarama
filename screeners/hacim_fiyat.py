"""
Tarama 2 — Hacim Artiyor, Fiyat Dusuyor:
Son N gunde fiyat duserken islem hacmi 20 gunluk ortalamasinin belirgin uzerinde
olan hisseler. Hacim Lot (adet) bazinda ve 20 gunluk ortalamaya normalize edilir
(TL hacmi enflasyonla kayar, yaniltir).
"""
import pandas as pd

from screeners import base
import settings as cfg


def run(
    data,
    window=cfg.DEFAULT_VOLUME_WINDOW,
    vol_multiple=cfg.DEFAULT_VOLUME_MULTIPLE,
    snapshot=None,
    fark=None,
):
    snapshot = snapshot or {}
    fark = fark or {}
    rows = []
    for sym, df in data.items():
        close = df["adj_close"]   # fiyat dususu duzeltilmis fiyattan (bedelsiz yanilmaz)
        if len(close) <= max(window, cfg.SMA_SHORT) + 1:
            continue

        price_ret = base.pct_change_over(close, window)
        vratio = base.turnover_ratio(df, window)   # ciro bazli, bedelsize dayanikli
        if price_ret is None or vratio is None:
            continue

        if price_ret < 0 and vratio >= vol_multiple:
            rows.append(
                {
                    "Sembol": sym,
                    "Son": snapshot.get(sym, round(float(close.iloc[-1]), 2)),
                    "Fark %": fark.get(sym),
                    f"{window}G Fiyat %": round(price_ret, 2),
                    "Hacim/20G Ort": round(vratio, 2),
                    "Başlangıç": base.date_str(df, window),
                    "Son Tarih": base.date_str(df, 0),
                }
            )

    cols = ["Sembol", "Son", "Fark %", f"{window}G Fiyat %", "Hacim/20G Ort",
            "Başlangıç", "Son Tarih"]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        out = out.sort_values("Hacim/20G Ort", ascending=False).reset_index(drop=True)
    return out
