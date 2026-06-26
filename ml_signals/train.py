"""ML sinyal modelini egitir ve zaman sirali backtest yapar.

Kullanim:
    python -m ml_signals.train

Model yalnizca backtest gecerse kaydedilir. Basarisiz model canli uygulamada
gosterilmez; rapor JSON dosyasinda nedenleri gorulur.
"""
from __future__ import annotations

import argparse
import json
import os
import warnings
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
warnings.filterwarnings("ignore", message="Could not find the number of physical cores.*")

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline

from data import cache
from screeners import base
from ml_signals.features import FEATURE_COLUMNS, build_feature_frame
from ml_signals.labels import build_label_frame, build_training_frame


ARTIFACT_DIR = Path(__file__).resolve().parent
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
REPORT_PATH = ARTIFACT_DIR / "backtest_report.json"
RANDOM_STATE = 42


def _make_model():
    clf = HistGradientBoostingClassifier(
        max_iter=180,
        learning_rate=0.05,
        max_leaf_nodes=24,
        l2_regularization=0.05,
        early_stopping=True,
        random_state=RANDOM_STATE,
    )
    return make_pipeline(SimpleImputer(strategy="median"), clf)


def _walk_forward_splits(dates, n_splits=4, min_train_days=252, test_days=63):
    unique = pd.Series(pd.to_datetime(sorted(pd.unique(dates))))
    if len(unique) < min_train_days + test_days:
        return []
    starts = np.linspace(min_train_days, len(unique) - test_days, num=n_splits, dtype=int)
    splits = []
    for start in sorted(set(starts)):
        train_dates = set(unique.iloc[:start])
        test_dates = set(unique.iloc[start:start + test_days])
        if train_dates and test_dates:
            splits.append((train_dates, test_dates))
    return splits


def _safe_auc(y, p):
    if len(set(y)) < 2:
        return None
    return float(roc_auc_score(y, p))


def _safe_ap(y, p):
    if len(set(y)) < 2:
        return None
    return float(average_precision_score(y, p))


def _top20_rel_return(df, score_col):
    vals = []
    for _, g in df.groupby("date"):
        top = g.nlargest(20, score_col)
        if not top.empty:
            vals.append(float(top["rel_fwd_ret_10"].mean()))
    return float(np.mean(vals)) if vals else None


def _fit_pair(train_df):
    x = train_df[FEATURE_COLUMNS]
    m5 = _make_model()
    m10 = _make_model()
    m5.fit(x, train_df["y_5"])
    m10.fit(x, train_df["y_10"])
    return m5, m10


def _predict_pair(m5, m10, df):
    x = df[FEATURE_COLUMNS]
    p5 = m5.predict_proba(x)[:, 1]
    p10 = m10.predict_proba(x)[:, 1]
    return p5, p10, (p5 + p10) / 2.0


def backtest(frame):
    folds = []
    scored = []
    splits = _walk_forward_splits(frame["date"])
    for i, (train_dates, test_dates) in enumerate(splits, start=1):
        tr = frame[frame["date"].isin(train_dates)].copy()
        te = frame[frame["date"].isin(test_dates)].copy()
        if tr.empty or te.empty:
            continue
        m5, m10 = _fit_pair(tr)
        te["score_5"] = 0.0
        te["score_10"] = 0.0
        te["ml_score"] = 0.0
        te["score_5"], te["score_10"], te["ml_score"] = _predict_pair(m5, m10, te)
        te["baseline_momentum"] = te["ret_20"]
        te["baseline_volume"] = te["vol_ratio_5_20"]
        te["baseline_squeeze"] = -te["volatility_ratio_20_60"].fillna(1.0) + te["vol_ratio_2_20"].fillna(1.0)
        scored.append(te)
        folds.append({
            "fold": i,
            "train_start": str(min(train_dates).date()),
            "train_end": str(max(train_dates).date()),
            "test_start": str(min(test_dates).date()),
            "test_end": str(max(test_dates).date()),
            "rows_train": int(len(tr)),
            "rows_test": int(len(te)),
            "auc_5": _safe_auc(te["y_5"], te["score_5"]),
            "auc_10": _safe_auc(te["y_10"], te["score_10"]),
            "ap_5": _safe_ap(te["y_5"], te["score_5"]),
            "ap_10": _safe_ap(te["y_10"], te["score_10"]),
            "top20_rel_fwd_ret_10": _top20_rel_return(te, "ml_score"),
        })

    if not scored:
        return {"folds": [], "summary": {"passed": False, "reason": "Yeterli zaman sirali fold olusmadi."}}

    all_scored = pd.concat(scored, ignore_index=True)
    ml = _top20_rel_return(all_scored, "ml_score")
    baselines = {
        "momentum": _top20_rel_return(all_scored, "baseline_momentum"),
        "volume": _top20_rel_return(all_scored, "baseline_volume"),
        "squeeze": _top20_rel_return(all_scored, "baseline_squeeze"),
    }
    beat_count = sum(1 for v in baselines.values() if v is not None and ml is not None and ml > v + 0.10)
    passed = bool(ml is not None and ml > 0 and beat_count >= 1)
    return {
        "folds": folds,
        "summary": {
            "passed": passed,
            "top20_rel_fwd_ret_10": ml,
            "baseline_top20_rel_fwd_ret_10": baselines,
            "beat_baseline_count": int(beat_count),
            "reason": None if passed else "ML top20 secimi pozitif olmali ve en az bir basit baz cizgiyi 0.10 puan gecmeli.",
        },
    }


def _feature_importance(model, frame):
    sample = frame.sort_values("date").tail(min(len(frame), 3000))
    if sample.empty or len(set(sample["y_10"])) < 2:
        return []
    try:
        res = permutation_importance(
            model,
            sample[FEATURE_COLUMNS],
            sample["y_10"],
            n_repeats=5,
            random_state=RANDOM_STATE,
            scoring="average_precision",
        )
    except Exception:
        return []
    pairs = sorted(zip(FEATURE_COLUMNS, res.importances_mean), key=lambda x: x[1], reverse=True)
    return [{"feature": k, "importance": round(float(v), 6)} for k, v in pairs[:12]]


def train_and_maybe_save(force_save=False):
    cache.init_db()
    data = base.load_all(min_days=120, exclude_blacklist=False)
    feat = build_feature_frame(data)
    lab = build_label_frame(data)
    frame = build_training_frame(feat, lab).dropna(subset=["y_5", "y_10"])
    if frame.empty:
        report = {"summary": {"passed": False, "reason": "Egitim icin yeterli veri yok."}}
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    report = backtest(frame)
    report["data"] = {
        "rows": int(len(frame)),
        "symbols": int(frame["symbol"].nunique()),
        "start": str(frame["date"].min().date()),
        "end": str(frame["date"].max().date()),
        "features": FEATURE_COLUMNS,
    }

    passed = bool(report.get("summary", {}).get("passed"))
    if passed or force_save:
        m5, m10 = _fit_pair(frame)
        report["feature_importance"] = _feature_importance(m10, frame)
        artifact = {
            "model_5": m5,
            "model_10": m10,
            "feature_columns": FEATURE_COLUMNS,
            "trained_until": str(frame["date"].max().date()),
            "metadata": report,
        }
        joblib.dump(artifact, MODEL_PATH)
        report["model_path"] = str(MODEL_PATH)
    else:
        report["model_path"] = None

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-save", action="store_true", help="Backtest gecmese bile modeli kaydet.")
    args = ap.parse_args()
    report = train_and_maybe_save(force_save=args.force_save)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Rapor: {REPORT_PATH}")
    if report.get("model_path"):
        print(f"Model: {report['model_path']}")
    else:
        print("Model kaydedilmedi; backtest kabul kriterini gecmedi.")


if __name__ == "__main__":
    main()
