import unittest
import sqlite3

import numpy as np
import pandas as pd

from ml_signals import daily, radar
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
        self.assertIn("y_up_5", frame.columns)
        self.assertIn("y_up_10", frame.columns)

    def test_missing_model_is_non_fatal(self):
        data = _sample_data(symbols=2, days=150)
        scores, err = score_latest(data, model_path="missing-model.joblib")
        self.assertTrue(scores.empty)
        self.assertIsNotNone(err)

    def test_daily_snapshot_writes_once_per_data_date(self):
        db = sqlite3.connect(":memory:")
        df = pd.DataFrame([{
            "Hisse": "TEST",
            "Radar Durumu": "Güçlü Aday",
            "Yükseliş Puanı": 65.0,
            "Göreli Güç": 58.0,
            "5G Yükseliş": 64.0,
            "10G Yükseliş": 66.0,
            "Güven": "Orta",
            "Vade": "5-10 iş günü",
            "Basit Neden": "Fiyat kısa vadede güç toplamış",
            "Ana Risk": "Puan düşerse dikkat",
            "Son": 10.0,
            "Fark %": 1.2,
        }])
        watch_df = df.copy()
        watch_df["Hisse"] = "WATCH"
        watch_df["Radar Durumu"] = "Kendi Takibim"
        self.assertTrue(daily.save_snapshot_once(df, "2026-06-25", db=db))
        self.assertFalse(daily.save_snapshot_once(df, "2026-06-25", db=db))
        self.assertTrue(daily.save_snapshot_once(watch_df, "2026-06-25", db=db, allow_append=True))
        stored = daily.load_snapshot("2026-06-25", db=db)
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored.iloc[0]["Hisse"], "TEST")
        self.assertIn("Yükseliş Puanı", stored.columns)
        self.assertIn("Göreli Güç", stored.columns)
        self.assertIn("Takip Planı", stored.columns)
        self.assertTrue(stored.iloc[0]["Takip Planı"])
        daily.refresh_market_fields("2026-06-25", snapshot={"TEST": 11.0}, fark={"TEST": 2.5}, db=db)
        updated = daily.load_snapshot("2026-06-25", db=db)
        self.assertEqual(float(updated.iloc[0]["Son"]), 11.0)
        self.assertEqual(float(updated.iloc[0]["Fark %"]), 2.5)

    def test_daily_outcomes_are_recorded_after_horizon(self):
        db = sqlite3.connect(":memory:")
        signal = pd.DataFrame([{
            "Hisse": "TEST",
            "Radar Durumu": "Takip Edilecek",
            "Yükseliş Puanı": 62.0,
            "Göreli Güç": 55.0,
            "5G Yükseliş": 61.0,
            "10G Yükseliş": 63.0,
            "Güven": "Orta",
            "Vade": "5-10 iş günü",
            "Basit Neden": "Fiyat güç toplamış",
            "Ana Risk": "Puan düşerse dikkat",
            "Son": 10.0,
            "Fark %": 0.0,
        }])
        self.assertTrue(daily.save_snapshot_once(signal, "2026-06-25", db=db))
        idx = pd.bdate_range("2026-06-25", periods=12)
        prices = pd.DataFrame(
            {"adj_close": [10.0, 10.1, 10.2, 10.3, 10.4, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.0]},
            index=idx,
        )
        written = daily.evaluate_outcomes({"TEST": prices}, as_of_date=idx[-1].date().isoformat(), db=db)
        self.assertEqual(written, 2)
        outcomes = daily.load_outcomes(db=db)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(set(outcomes["Sonuç Vadesi"]), {"5 iş günü", "10 iş günü"})
        self.assertTrue((outcomes["Tuttu mu?"] == "Tuttu").all())
        self.assertIn("Yükseliş Puanı", outcomes.columns)
        self.assertIn("En Yüksek %", outcomes.columns)
        summary = daily.outcome_summary(outcomes)
        self.assertEqual(summary["signals"], 2)
        self.assertAlmostEqual(summary["success_rate"], 100.0)
        breakdown = daily.outcome_breakdown(outcomes)
        self.assertEqual(int(breakdown.iloc[0]["Sinyal"]), 2)

    def test_radar_text_is_plain_language(self):
        row = pd.Series({
            "vol_ratio_5_20": 2.2,
            "vol_ratio_2_20": 2.8,
            "ret_5": 4.0,
            "ret_20": 6.0,
            "volatility_ratio_20_60": 0.7,
            "sma20_gap": 2.0,
            "sma50_gap": 3.0,
            "low_distance_60": 7.0,
        })
        text = radar.simple_reason(row)
        self.assertNotIn("vol_ratio", text)
        self.assertNotIn("sma", text.lower())
        self.assertIn("para girişi", text)


if __name__ == "__main__":
    unittest.main()
