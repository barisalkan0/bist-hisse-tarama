"""Fiyat/hacim tabanli ML ozellikleri.

Tum ozellikler ilgili satirin tarihindeki veya daha eski veriden hesaplanir.
Gelecek getiriler burada uretilmez; etiketleme `labels.py` icindedir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_10",
    "ret_20",
    "ret_60",
    "vol_ratio_2_20",
    "vol_ratio_5_20",
    "vol_ratio_10_20",
    "volatility_10",
    "volatility_20",
    "volatility_60",
    "volatility_ratio_20_60",
    "sma20_gap",
    "sma50_gap",
    "sma20_slope_5",
    "drawdown_60",
    "drawdown_252",
    "low_distance_60",
    "turnover_z20",
    "history_days",
    "history_years",
    "turnover_ma20",
    "turnover_ma20_log",
    "turnover_ma60_log",
    "turnover_stability_20_60",
    "price_range_20",
    "quiet_volume_pressure",
    "seasonality_mean",
    "seasonality_hit",
    "seasonality_years",
]

REQUIRED_MIN_DAYS = 90


def _safe_pct(a: pd.Series, periods: int) -> pd.Series:
    return a.pct_change(periods=periods) * 100.0


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    den = den.replace(0, np.nan)
    return num / den


def make_features_for_symbol(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Tek hisse icin gunluk ML ozellikleri dondurur."""
    if df is None or df.empty or "adj_close" not in df.columns or "volume" not in df.columns:
        return pd.DataFrame(columns=["symbol", "date", *FEATURE_COLUMNS])

    x = df[["adj_close", "volume"]].copy().sort_index()
    x = x.dropna(subset=["adj_close"])
    if len(x) < REQUIRED_MIN_DAYS:
        return pd.DataFrame(columns=["symbol", "date", *FEATURE_COLUMNS])

    close = x["adj_close"].astype(float)
    turnover = x["volume"].astype(float)
    ret1 = close.pct_change()

    out = pd.DataFrame(index=x.index)
    out["symbol"] = symbol
    out["date"] = out.index
    out["history_days"] = np.arange(1, len(out) + 1, dtype=float)
    out["history_years"] = out["history_days"] / 252.0

    for n in (1, 3, 5, 10, 20, 60):
        out[f"ret_{n}"] = _safe_pct(close, n)

    vol20 = turnover.rolling(20, min_periods=10).mean()
    vol60 = turnover.rolling(60, min_periods=30).mean()
    out["turnover_ma20"] = vol20
    out["turnover_ma20_log"] = np.log1p(vol20)
    out["turnover_ma60_log"] = np.log1p(vol60)
    out["turnover_stability_20_60"] = _ratio(vol20, vol60)
    for n in (2, 5, 10):
        out[f"vol_ratio_{n}_20"] = _ratio(
            turnover.rolling(n, min_periods=n).mean(), vol20
        )

    out["volatility_10"] = ret1.rolling(10, min_periods=8).std() * 100.0
    out["volatility_20"] = ret1.rolling(20, min_periods=15).std() * 100.0
    out["volatility_60"] = ret1.rolling(60, min_periods=40).std() * 100.0
    out["volatility_ratio_20_60"] = _ratio(out["volatility_20"], out["volatility_60"])

    sma20 = close.rolling(20, min_periods=15).mean()
    sma50 = close.rolling(50, min_periods=35).mean()
    out["sma20_gap"] = (close / sma20 - 1.0) * 100.0
    out["sma50_gap"] = (close / sma50 - 1.0) * 100.0
    out["sma20_slope_5"] = _safe_pct(sma20, 5)

    high60 = close.rolling(60, min_periods=40).max()
    low60 = close.rolling(60, min_periods=40).min()
    high252 = close.rolling(252, min_periods=120).max()
    high20 = close.rolling(20, min_periods=15).max()
    low20 = close.rolling(20, min_periods=15).min()
    out["price_range_20"] = (high20 / low20 - 1.0) * 100.0
    out["drawdown_60"] = (close / high60 - 1.0) * 100.0
    out["drawdown_252"] = (close / high252 - 1.0) * 100.0
    out["low_distance_60"] = (close / low60 - 1.0) * 100.0
    out["quiet_volume_pressure"] = _ratio(out["vol_ratio_2_20"], out["price_range_20"].clip(lower=1.0))

    mean20 = turnover.rolling(20, min_periods=15).mean()
    std20 = turnover.rolling(20, min_periods=15).std().replace(0, np.nan)
    out["turnover_z20"] = (turnover - mean20) / std20

    seas = _past_seasonality(close)
    out["seasonality_mean"] = seas["seasonality_mean"]
    out["seasonality_hit"] = seas["seasonality_hit"]
    out["seasonality_years"] = seas["seasonality_years"]
    out = out.replace([np.inf, -np.inf], np.nan)

    return out[["symbol", "date", *FEATURE_COLUMNS]].dropna(subset=["ret_20", "vol_ratio_5_20"])


def _past_seasonality(close: pd.Series) -> pd.DataFrame:
    """Her gun icin yalnizca onceki tamamlanmis aylardan mevsimsellik ozeti uretir."""
    idx = close.index
    out = pd.DataFrame(index=idx)
    out["seasonality_mean"] = np.nan
    out["seasonality_hit"] = np.nan
    out["seasonality_years"] = 0.0
    if len(close) < 60:
        return out

    rule = "ME" if pd.__version__ >= "2.2" else "M"
    monthly = close.resample(rule).last().pct_change().dropna() * 100.0
    if monthly.empty:
        return out

    periods = pd.Series(idx.to_period("M"), index=idx)
    mean_map, hit_map, years_map = {}, {}, {}
    for period in periods.drop_duplicates().tolist():
        month_start = period.to_timestamp()
        prior_all = monthly[monthly.index < month_start]
        same_month = prior_all[prior_all.index.month == period.month]
        if same_month.empty:
            mean_map[period] = np.nan
            hit_map[period] = np.nan
            years_map[period] = 0.0
            continue
        overall = float(prior_all.mean()) if not prior_all.empty else 0.0
        mean_map[period] = float(same_month.mean() - overall)
        hit_map[period] = float((same_month > 0).mean() * 100.0)
        years_map[period] = float(len(same_month))

    out["seasonality_mean"] = periods.map(mean_map).astype(float)
    out["seasonality_hit"] = periods.map(hit_map).astype(float)
    out["seasonality_years"] = periods.map(years_map).astype(float)
    return out


def build_feature_frame(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{symbol: fiyat_df} sozlugunden tum hisse-gun ozellik tablosu uretir."""
    frames = [make_features_for_symbol(sym, df) for sym, df in data.items()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", *FEATURE_COLUMNS])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values(["date", "symbol"]).reset_index(drop=True)


def latest_features(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Her hisse icin son mevcut gunun ozellik satirini dondurur."""
    feat = build_feature_frame(data)
    if feat.empty:
        return feat
    idx = feat.groupby("symbol")["date"].idxmax()
    return feat.loc[idx].sort_values("symbol").reset_index(drop=True)
