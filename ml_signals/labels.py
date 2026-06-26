"""ML egitim etiketleri.

Etiketler, her tarih icinde ileri performansa gore capraz-kesit siralamasi
yapar. Bu sayede model mutlak piyasa yonunden cok, hisseler arasi goreli gucu
ogrenmeye calisir.
"""
from __future__ import annotations

import pandas as pd


TOP_QUANTILE = 0.70
MIN_SYMBOLS_PER_DATE = 30


def forward_returns_for_symbol(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "adj_close" not in df.columns:
        return pd.DataFrame(columns=["symbol", "date", "fwd_ret_5", "fwd_ret_10"])
    close = df["adj_close"].astype(float).sort_index()
    out = pd.DataFrame(index=close.index)
    out["symbol"] = symbol
    out["date"] = out.index
    out["fwd_ret_5"] = (close.shift(-5) / close - 1.0) * 100.0
    out["fwd_ret_10"] = (close.shift(-10) / close - 1.0) * 100.0
    return out.reset_index(drop=True)


def build_label_frame(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = [forward_returns_for_symbol(sym, df) for sym, df in data.items()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "fwd_ret_5", "fwd_ret_10", "y_5", "y_10"])

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.dropna(subset=["fwd_ret_5", "fwd_ret_10"])

    for horizon in (5, 10):
        ret_col = f"fwd_ret_{horizon}"
        rank_col = f"rank_{horizon}"
        y_col = f"y_{horizon}"
        out[rank_col] = out.groupby("date")[ret_col].rank(pct=True, method="average")
        counts = out.groupby("date")[ret_col].transform("count")
        out[y_col] = (out[rank_col] >= TOP_QUANTILE).astype(int)

    enough_symbols = out.groupby("date")["symbol"].transform("count") >= MIN_SYMBOLS_PER_DATE
    out = out[enough_symbols].copy()

    market_10 = out.groupby("date")["fwd_ret_10"].transform("mean")
    out["rel_fwd_ret_10"] = out["fwd_ret_10"] - market_10
    return out.sort_values(["date", "symbol"]).reset_index(drop=True)


def build_training_frame(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    if features.empty or labels.empty:
        return pd.DataFrame()
    cols = ["symbol", "date", "fwd_ret_5", "fwd_ret_10", "rel_fwd_ret_10", "y_5", "y_10"]
    merged = features.merge(labels[cols], on=["symbol", "date"], how="inner")
    return merged.sort_values(["date", "symbol"]).reset_index(drop=True)
