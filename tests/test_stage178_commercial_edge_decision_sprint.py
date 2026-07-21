from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import subprocess
import json
import unittest
import sys
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage178_commercial_edge_decision_sprint.py"
spec = importlib.util.spec_from_file_location("stage178", MODULE_PATH)
stage178 = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = stage178
spec.loader.exec_module(stage178)


class Stage178Tests(unittest.TestCase):
    def synthetic_frame(self, rows: int = 1200) -> pd.DataFrame:
        timestamp = 1_600_000_000_000 + np.arange(rows, dtype=np.int64) * stage178.MS_HOUR
        base = 1800.0 + np.cumsum(np.sin(np.arange(rows) / 12.0) * 0.2 + 0.03)
        open_ = np.r_[base[0], base[:-1]]
        close = base
        high = np.maximum(open_, close) + 0.5
        low = np.minimum(open_, close) - 0.5
        volume = 1000.0 + (np.arange(rows) % 100)
        frame = pd.DataFrame(
            {
                "timestamp": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        frame["dt"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        return frame.set_index("dt", drop=False)

    def test_directional_target_uses_next_open(self):
        frame = self.synthetic_frame(100)
        target = stage178.directional_target(frame, 6, 0.0)
        i = 20
        expected = (frame["close"].iloc[i + 6] / frame["open"].iloc[i + 1] - 1.0) * 10000
        self.assertAlmostEqual(target["underlying_bps"].iloc[i], expected, places=10)

    def test_feature_builder_is_causal_at_prefix(self):
        frame = self.synthetic_frame(800)
        full, columns = stage178.build_features(frame)
        prefix, _ = stage178.build_features(frame.iloc[:600].copy())
        for column in columns:
            a = full[column].iloc[500]
            b = prefix[column].iloc[500]
            if pd.isna(a) and pd.isna(b):
                continue
            self.assertAlmostEqual(float(a), float(b), places=12, msg=column)

    def test_probability_direction_threshold(self):
        p = np.array([0.1, 0.4, 0.5, 0.6, 0.9])
        got = stage178.probability_to_direction(p, 0.6)
        self.assertEqual(got.tolist(), [-1, -1, 0, 1, 1])

    def test_non_overlapping_trade_selection(self):
        frame = self.synthetic_frame(20)
        rows = pd.DataFrame(
            {
                "timestamp": frame["timestamp"].iloc[:10].to_numpy(),
                "underlying_bps": np.repeat(10.0, 10),
                "resolution_hours": np.repeat(3.0, 10),
            }
        )
        probabilities = np.repeat(0.9, 10)
        trades = stage178.non_overlapping_trades(
            rows, probabilities, 0.6, 3.0, 4.5, "fold", "model", "target"
        )
        self.assertEqual(trades["timestamp"].tolist(), rows["timestamp"].iloc[[0, 3, 6, 9]].tolist())

    def test_metrics_and_concentration(self):
        timestamps = pd.to_datetime(
            ["2024-01-01", "2024-02-01", "2025-01-01", "2025-02-01"], utc=True
        )
        trades = pd.DataFrame(
            {
                "dt": timestamps,
                "net_bps": [10.0, -5.0, 8.0, -2.0],
                "severe_net_bps": [8.5, -6.5, 6.5, -3.5],
            }
        )
        metrics = stage178.trade_metrics(trades)
        self.assertEqual(metrics["trades"], 4)
        self.assertAlmostEqual(metrics["profit_factor"], 18 / 7)
        self.assertAlmostEqual(metrics["max_year_share"], 0.5)
        self.assertAlmostEqual(metrics["max_month_share"], 0.25)

    def test_sqlite_schema_loader_prefers_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "CREATE TABLE dukascopy_h1_canonical (timestamp INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT, m5_bar_count INTEGER)"
                )
                connection.execute(
                    "INSERT INTO dukascopy_h1_canonical VALUES (?,?,?,?,?,?,?,?)",
                    (1_600_000_000_000, 1, 2, 0.5, 1.5, 10, "test", 12),
                )
                connection.commit()
            frame, table = stage178.load_ohlcv_table(path, ["dukascopy_h1_canonical"])
            self.assertEqual(table, "dukascopy_h1_canonical")
            self.assertEqual(len(frame), 1)

    def test_triple_barrier_resolves_upper_hit(self):
        frame = self.synthetic_frame(100)
        frame.loc[:, "high"] = frame["high"] + 5.0
        target = stage178.triple_barrier_target(frame, 24, 0.1, 0.0)
        finite = target["underlying_bps"].dropna()
        self.assertGreater(len(finite), 0)
        self.assertTrue(np.isfinite(finite.to_numpy()).all())

    def test_evaluation_dataset_keeps_neutral_outcomes(self):
        frame = self.synthetic_frame(800)
        features, columns = stage178.build_features(frame)
        target = stage178.directional_target(frame, 6, cost_bps=10_000.0)
        training = stage178.model_dataset(features, target, columns, require_label=True)
        evaluation = stage178.model_dataset(features, target, columns, require_label=False)
        self.assertEqual(len(training), 0)
        self.assertGreater(len(evaluation), 100)
        self.assertTrue(evaluation["label"].isna().all())

    def test_module_import_survives_missing_joblib(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "joblib.py"
            blocker.write_text("raise ModuleNotFoundError('simulated missing joblib')\n", encoding="utf-8")
            code = (
                "import importlib.util, pathlib, sys; "
                f"p=pathlib.Path({str(MODULE_PATH)!r}); "
                "s=importlib.util.spec_from_file_location('stage178_no_joblib', p); "
                "m=importlib.util.module_from_spec(s); "
                "sys.modules[s.name]=m; "
                "s.loader.exec_module(m); "
                "print('IMPORT_OK')"
            )
            env = dict(__import__('os').environ)
            env["PYTHONPATH"] = tmp
            result = subprocess.run(
                [sys.executable, "-c", code],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("IMPORT_OK", result.stdout)

    def test_dependency_preflight_is_concise_when_joblib_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "joblib.py"
            blocker.write_text("raise ModuleNotFoundError('simulated missing joblib')\n", encoding="utf-8")
            env = dict(__import__('os').environ)
            env["PYTHONPATH"] = tmp
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--check-dependencies"],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("requirements/stage178.txt", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(stage178.ml_dependencies_available()[0], "Stage178 ML dependencies unavailable")
    def test_end_to_end_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            reference_db = tmp_path / "reference.sqlite"
            amarkets_db = tmp_path / "amarkets.sqlite"
            rng = np.random.default_rng(178)
            rows = 9000
            timestamp = int(pd.Timestamp("2019-01-01", tz="UTC").timestamp() * 1000) + np.arange(rows, dtype=np.int64) * stage178.MS_HOUR
            innovations = rng.normal(0.0, 0.35, rows)
            returns = np.zeros(rows)
            for i in range(1, rows):
                returns[i] = 0.25 * returns[i - 1] + innovations[i]
            close = 1500.0 + np.cumsum(returns)
            open_ = np.r_[close[0], close[:-1]]
            high = np.maximum(open_, close) + 0.4
            low = np.minimum(open_, close) - 0.4
            volume = 1000 + (np.arange(rows) % 50)
            with closing(sqlite3.connect(reference_db)) as connection:
                connection.execute("CREATE TABLE dukascopy_h1_canonical (timestamp INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT, m5_bar_count INTEGER)")
                connection.executemany(
                    "INSERT INTO dukascopy_h1_canonical VALUES (?,?,?,?,?,?,?,?)",
                    zip(timestamp.tolist(), open_.tolist(), high.tolist(), low.tolist(), close.tolist(), volume.tolist(), ["test"] * rows, [12] * rows),
                )
                connection.commit()
            with closing(sqlite3.connect(amarkets_db)) as connection:
                connection.execute("CREATE TABLE amarkets_h1_from_m5_utc (timestamp INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL, m5_bar_count INTEGER)")
                connection.executemany(
                    "INSERT INTO amarkets_h1_from_m5_utc VALUES (?,?,?,?,?,?,?)",
                    zip(timestamp.tolist(), open_.tolist(), high.tolist(), low.tolist(), close.tolist(), volume.tolist(), [12] * rows),
                )
                connection.commit()
            config = {
                "stage": "178-test",
                "reference_db": str(reference_db),
                "amarkets_db": str(amarkets_db),
                "output_dir": str(tmp_path / "reports"),
                "model_output_dir": str(tmp_path / "model"),
                "random_state": 178,
                "training_stride_hours": 2,
                "minimum_training_rows": 500,
                "probability_threshold": 0.55,
                "round_trip_cost_bps": 0.2,
                "severe_round_trip_cost_bps": 0.3,
                "final_holdout_start": "2019-10-15T00:00:00",
                "models": ["logistic"],
                "targets": [{"key": "direction_6h", "kind": "directional", "horizon_hours": 6, "barrier_atr_mult": None}],
                "reference_walk_forward_folds": [
                    {"name": "WF_A", "test_start": "2019-04-01T00:00:00", "test_end": "2019-07-01T00:00:00"},
                    {"name": "WF_B", "test_start": "2019-07-01T00:00:00", "test_end": "2019-10-01T00:00:00"}
                ],
                "reference_gates": {
                    "minimum_trades": 2,
                    "minimum_mean_net_bps": -999,
                    "minimum_mean_severe_net_bps": -999,
                    "minimum_profit_factor": 0,
                    "minimum_positive_fold_share": 0,
                    "maximum_year_share": 1,
                    "minimum_margin_over_trend24_bps": -999
                },
                "holdout_gates": {
                    "minimum_trades": 1,
                    "minimum_mean_net_bps": -999,
                    "minimum_mean_severe_net_bps": -999,
                    "minimum_profit_factor": 0,
                    "maximum_month_share": 1,
                    "minimum_degradation_ratio": -999,
                    "minimum_margin_over_trend24_bps": -999
                }
            }
            config_path = tmp_path / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--config", str(config_path)],
                text=True,
                capture_output=True,
            )
            self.assertIn(result.returncode, (0, 2), msg=result.stdout + result.stderr)
            summary_path = tmp_path / "reports" / "stage178_summary.json"
            self.assertTrue(summary_path.exists(), msg=result.stdout + result.stderr)
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["candidate_count"], 1)
            self.assertFalse(payload["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
