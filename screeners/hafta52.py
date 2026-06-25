"""
Tarama: 52 hafta (yıl) dip/zirve yakınlığı.

Her hisse için son ~252 işlem gününün (düzeltilmiş kapanış) en düşük/en yüksek
seviyesine göre güncel fiyatın uzaklığını hesaplar:
  - "dip"   modu: yıllık dibe yakın olanlar (ucuza gelmiş olabilir)
  - "zirve" modu: yıllık zirveye yakın / kıranlar
Düzeltilmiş fiyat kullanılır (bedelsiz/bölünme yanılması olmasın).
"""
import pandas as pd


def run(data, mode="dip", threshold=10.0, lookback=252, snapshot=None, fark=None):
    snapshot = snapshot or {}
    fark = fark or {}
    rows = []
    for sym, df in data.items():
        close = df["adj_close"]
        if len(close) < 60:   # anlamlı bir aralık için yeterli veri
            continue
        window = close.iloc[-lookback:] if len(close) >= lookback else close
        low = float(window.min())
        high = float(window.max())
        cur = float(close.iloc[-1])
        if low <= 0 or high <= 0:
            continue
        dibe = (cur / low - 1.0) * 100.0       # dibin yüzde kaç üstünde
        zirveye = (high / cur - 1.0) * 100.0   # zirvenin yüzde kaç altında

        if mode == "dip" and dibe > threshold:
            continue
        if mode == "zirve" and zirveye > threshold:
            continue

        rows.append(
            {
                "Sembol": sym,
                "Son": snapshot.get(sym, round(cur, 2)),
                "Fark %": fark.get(sym),
                "Dibe Uzaklık": round(dibe, 2),
                "Zirveye Uzaklık": round(zirveye, 2),
            }
        )

    cols = ["Sembol", "Son", "Fark %", "Dibe Uzaklık", "Zirveye Uzaklık"]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        sort_col = "Dibe Uzaklık" if mode == "dip" else "Zirveye Uzaklık"
        out = out.sort_values(sort_col).reset_index(drop=True)
    return out
