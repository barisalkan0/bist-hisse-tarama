import unittest

import numpy as np
import pandas as pd

from ml_signals.features import build_feature_frame
from ml_signals.labels import build_label_frame, build_training_frame
from ml_signals.predict import score_latest


def _sample_data(symbols=35, days=160):
    idx = pd.bdate_range("2024-01-01", periods=days)
    out = {}
    for i in range(symbols):
        base = 10 + i
        trend = np.linspace(0, i / 20, days)
        wave = np.sin(np.arange(days) / 7) * 0.03
        close = base * (1 + trend + wave)
        volume = 1_000_000 + i * 10_000 + (np.arange(days) % 11) * 20_000
        out[f"S{i:03d}"] = pd.DataFrame(
            {"adj_close": close, "close": close, "volume": volume},
            index=idx,
        )
    return out


class MlSignalsTest(unittest.TestCase):
    def test_features_do_not_need_future_rows(self):
        data = _sample_data(symbols=1, days=150)
        full = build_feature_frame(data)
        cut = {"S000": data["S000"].iloc[:-10]}
        partial = build_feature_frame(cut)
        common_date = partial["date"].max()
        full_row = full[(full["symbol"] == "S000") & (full["date"] == common_date)].iloc[0]
        part_row = partial[partial["date"] == common_date].iloc[0]
        self.assertAlmostEqual(full_row["ret_20"], part_row["ret_20"], places=10)
        self.assertAlmostEqual(full_row["vol_ratio_5_20"], part_row["vol_ratio_5_20"], places=10)

    def test_labels_align_forward_returns(self):
        data = _sample_data(symbols=35, days=150)
        labels = build_label_frame(data)
        first = labels[labels["symbol"] == "S010"].iloc[0]
        close = data["S010"]["adj_close"]
        expected = (close.iloc[5] / close.iloc[0] - 1.0) * 100.0
        self.assertAlmostEqual(first["fwd_ret_5"], expected, places=10)
        self.assertIn(first["y_5"], (0, 1))

    def test_training_frame_contains_expected_targets(self):
        data = _sample_data()
        feat = build_feature_frame(data)
        labels = build_label_frame(data)
        frame = build_training_frame(feat, labels)
        self.assertFalse(frame.empty)
        self.assertIn("y_5", frame.columns)
        self.assertIn("y_10", frame.columns)

    def test_missing_model_is_non_fatal(self):
        data = _sample_data(symbols=2, days=150)
        scores, err = score_latest(data, model_path="missing-model.joblib")
        self.assertTrue(scores.empty)
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()

