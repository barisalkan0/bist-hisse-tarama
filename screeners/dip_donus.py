"""
Tarama 1 — Dipten Donus:
Uzun suredir dusen AMA son gunlerde toparlanmaya baslayan hisseler.

Dusus tanimi iki yontemle (kullanici secer):
  - "trend": donemde net >= decline_pct dusus VE fiyat 20/50 gunluk ort. altinda
  - "kati" : donemdeki gunlerin >= down_ratio'su dusus gunu

Toparlanma: son `recovery_days` gunde net pozitif getiri.
"""
import pandas as pd

from screeners import base
import settings as cfg


def run(
    data,
    period_days,
    recovery_days,
    method="trend",
    decline_pct=cfg.DEFAULT_DECLINE_PCT,
    down_ratio=cfg.DEFAULT_DOWN_DAY_RATIO,
    snapshot=None,
):
    """
    data: {symbol: DataFrame}
    snapshot: {symbol: son_fiyat} (opsiyonel, sonuca eklenir)
    Doner: pandas DataFrame (bos olabilir), getiriye gore sirali.
    """
    snapshot = snapshot or {}
    rows = []
    for sym, df in data.items():
        close = df["adj_close"]   # trend/getiri duzeltilmis fiyattan
        if len(close) <= period_days:
            continue

        period_ret = base.pct_change_over(close, period_days)
        recov_ret = base.pct_change_over(close, recovery_days)
        if period_ret is None or recov_ret is None:
            continue

        # --- dusus kosulu ---
        if method == "trend":
            # Net dusus + hala uzun vadeli ortalamanin (SMA50) altinda.
            # NOT: kisa ortalama (SMA20) kosulu konmaz; cunku son gunlerdeki
            # toparlanma fiyati kisa ortalamanin uzerine cikarip hisseyi yanlislikla
            # eleyebilir.
            s50 = base.sma(close, cfg.SMA_LONG)
            last = float(close.iloc[-1])
            falling = (
                period_ret <= -abs(decline_pct)
                and s50 is not None and last < s50
            )
        else:  # kati
            ratio = base.down_day_ratio(close, period_days)
            falling = ratio is not None and ratio >= down_ratio

        # --- toparlanma kosulu ---
        recovering = recov_ret > 0
        if not (falling and recovering):
            continue

        rows.append(
            {
                "Sembol": sym,
                "Son": snapshot.get(sym, round(float(close.iloc[-1]), 2)),
                "Dönem Getirisi %": round(period_ret, 2),
                "Toparlanma %": round(recov_ret, 2),
                "Dönem Başı": base.date_str(df, period_days),
                "Toparlanma Başı": base.date_str(df, recovery_days),
                "Dönem Sonu": base.date_str(df, 0),
            }
        )

    cols = ["Sembol", "Son", "Dönem Getirisi %", "Toparlanma %",
            "Dönem Başı", "Toparlanma Başı", "Dönem Sonu"]
    out = pd.DataFrame(rows, columns=cols)
    if not out.empty:
        # En cok dusup en cok toparlanan ustte
        out = out.sort_values("Dönem Getirisi %").reset_index(drop=True)
    return out
