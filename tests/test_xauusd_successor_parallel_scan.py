from __future__ import annotations

import importlib.util
from contextlib import closing
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_successor_parallel_scan.py"
SPEC = importlib.util.spec_from_file_location("xauusd_successor_parallel_scan", MODULE_PATH)
assert SPEC and SPEC.loader
scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scan
SPEC.loader.exec_module(scan)


class SuccessorParallelScanTests(unittest.TestCase):
    def make_contract(self, root: Path, **overrides):
        payload = {
            "contract": "EU_DST_GMT_OFFSET_PAIR",
            "decision": "BLOCK_AMARKETS_TIME_CONTRACT_UNRESOLVED",
            "dst_calendar": "EU",
            "dst_shift_minutes": -180,
            "standard_shift_minutes": -120,
            "selection_used_holdout": False,
        }
        payload.update(overrides)
        path = root / "reports" / "stage177c_amarkets_dst_contract" / "stage177c_time_contract.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def make_alignment_db(self, root: Path, rows: int = 2200, start="2020-01-01T00:00:00Z"):
        path = root / "data" / "local" / "stage177c_amarkets_alignment" / "xauusd_amarkets_alignment.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamps = pd.date_range(start, periods=rows, freq="h", tz="UTC").as_unit("us")
        trend = np.exp(np.linspace(0.0, 0.35, rows)) * 1500.0
        seasonal = 1.0 + 0.002 * np.sin(np.arange(rows) / 12.0)
        close = trend * seasonal
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) * 1.0006
        low = np.minimum(open_, close) * 0.9994
        frame = pd.DataFrame(
            {
                "timestamp": scan.datetime_to_epoch_ms(timestamps),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
                "m5_bar_count": 12,
            }
        )
        with closing(sqlite3.connect(path)) as connection:
            frame.to_sql("amarkets_h1_from_m5_utc", connection, index=False, if_exists="replace")
        return path, frame

    def make_event_db(self, root: Path):
        path = root / "data" / "local" / "historical_event_context" / "xauusd_historical_event_context.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(
            [
                {
                    "event_time_utc": "2020-01-20T12:00:00Z",
                    "source": "FED",
                    "category": "FOMC_STATEMENT",
                    "title": "Synthetic event",
                    "blackout_before_minutes": 60.0,
                    "blackout_after_minutes": 60.0,
                }
            ]
        )
        with closing(sqlite3.connect(path)) as connection:
            frame.to_sql("official_events", connection, index=False, if_exists="replace")
        return path

    def base_config(self):
        return {
            "alignment_db": "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite",
            "event_db": "data/local/historical_event_context/xauusd_historical_event_context.sqlite",
            "time_contract": "reports/stage177c_amarkets_dst_contract/stage177c_time_contract.json",
            "h1_table": "amarkets_h1_from_m5_utc",
            "minimum_m5_bar_count": 12,
            "reference_start": "2020-01-01T00:00:00Z",
            "holdout_start": "2020-02-15T00:00:00Z",
            "normal_cost_bps": 0.0,
            "severe_cost_bps": 0.0,
            "maximum_notional_to_equity": 0.1570396406876166,
            "shortlist_size": 2,
            "bootstrap": {"block_length": 3, "replications": 80, "random_state": 7},
            "reference_folds": [
                {"name": "A", "start": "2020-01-01T00:00:00Z", "end": "2020-01-25T00:00:00Z"},
                {"name": "B", "start": "2020-01-25T00:00:00Z", "end": "2020-02-15T00:00:00Z"},
            ],
            "reference_gates": {
                "minimum_trades": 2,
                "minimum_severe_mean_bps": -999.0,
                "minimum_profit_factor": 0.0,
                "minimum_bootstrap_p10_bps": -999.0,
                "minimum_positive_fold_share": 0.0,
                "minimum_strict_replay_cagr": -1.0,
            },
            "holdout_gates": {
                "minimum_trades": 1,
                "minimum_severe_mean_bps": -999.0,
                "minimum_profit_factor": 0.0,
                "minimum_bootstrap_p10_bps": -999.0,
            },
            "full_history_gates": {
                "maximum_single_year_profit_share": 1.0,
                "minimum_strict_replay_cagr": -1.0,
            },
            "candidates": [
                {
                    "key": "trend",
                    "family": "trend_continuation",
                    "horizon_hours": 12,
                    "event_policy": "ignore",
                    "parameters": {"lookback_hours": 24, "trend_window": 120, "minimum_move": 0.0},
                },
                {
                    "key": "breakout",
                    "family": "range_breakout",
                    "horizon_hours": 12,
                    "event_policy": "ignore",
                    "parameters": {"range_window": 24, "buffer_atr": 0.0},
                },
            ],
        }

    def test_time_contract_accepts_locked_semantics_despite_legacy_decision_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_contract(Path(tmp))
            result = scan.read_alignment_contract(path)
            self.assertTrue(result["pass"])
            self.assertTrue(all(result["checks"].values()))

    def test_time_contract_rejects_wrong_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_contract(Path(tmp), dst_shift_minutes=-120)
            with self.assertRaises(scan.ScanError):
                scan.read_alignment_contract(path)

    def test_datetime_to_epoch_ms_is_resolution_invariant(self):
        timestamps_ns = pd.date_range(
            "2020-01-01T00:00:00Z", periods=3, freq="h", tz="UTC"
        )
        timestamps_us = timestamps_ns.as_unit("us")
        expected = np.array(
            [1577836800000, 1577840400000, 1577844000000], dtype=np.int64
        )
        np.testing.assert_array_equal(scan.datetime_to_epoch_ms(timestamps_ns), expected)
        np.testing.assert_array_equal(scan.datetime_to_epoch_ms(timestamps_us), expected)

    def test_outcome_arrays_requires_exact_hourly_path(self):
        timestamps = pd.to_datetime(
            ["2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z", "2020-01-01T03:00:00Z"]
        )
        frame = pd.DataFrame(
            {
                "timestamp": scan.datetime_to_epoch_ms(timestamps),
                "open": [1.0, 1.1, 1.2],
                "close": [1.05, 1.15, 1.25],
            }
        )
        result = scan.outcome_arrays(frame, 2)
        self.assertEqual(len(result), 0)

    def test_event_features_are_causal_and_blackout_bounded(self):
        timestamps = pd.date_range("2020-01-20T09:00:00Z", periods=8, freq="h", tz="UTC").as_unit("us")
        frame = pd.DataFrame(
            {
                "timestamp": scan.datetime_to_epoch_ms(timestamps),
                "dt": timestamps,
                "open": np.arange(8) + 100.0,
                "high": np.arange(8) + 101.0,
                "low": np.arange(8) + 99.0,
                "close": np.arange(8) + 100.5,
                "volume": 1.0,
            }
        )
        events = pd.DataFrame(
            {
                "event_time_utc": ["2020-01-20T12:00:00Z"],
                "event_dt": pd.to_datetime(["2020-01-20T12:00:00Z"], utc=True),
                "source": ["FED"],
                "category": ["FOMC_STATEMENT"],
                "title": ["x"],
                "blackout_before_minutes": [60.0],
                "blackout_after_minutes": [60.0],
            }
        )
        features = scan.build_features(frame, events)
        at_event = features[features["signal_time"] == pd.Timestamp("2020-01-20T12:00:00Z")]
        self.assertTrue(bool(at_event.iloc[0]["event_blackout"]))
        later = features[features["signal_time"] == pd.Timestamp("2020-01-20T14:00:00Z")]
        self.assertTrue(bool(later.iloc[0]["recent_event_3h"]))
        self.assertFalse(bool(later.iloc[0]["event_blackout"]))

    def test_non_overlapping_candidate_trades(self):
        timestamps = pd.date_range("2020-01-01", periods=400, freq="h", tz="UTC").as_unit("us")
        close = 100.0 * np.exp(np.arange(400) * 0.001)
        frame = pd.DataFrame(
            {
                "timestamp": scan.datetime_to_epoch_ms(timestamps),
                "dt": timestamps,
                "open": np.r_[close[0], close[:-1]],
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": 1.0,
            }
        )
        features = scan.build_features(frame, pd.DataFrame())
        spec = scan.CandidateSpec(
            "t", "trend_continuation", 12,
            {"lookback_hours": 24, "trend_window": 120, "minimum_move": 0.0},
            "ignore",
        )
        trades = scan.candidate_trades(features, spec, 0.0, 0.0)
        self.assertGreater(len(trades), 1)
        deltas = np.diff(trades["entry_timestamp"].to_numpy(np.int64))
        self.assertTrue(np.all(deltas >= 12 * scan.MS_HOUR))

    def test_positive_bootstrap(self):
        result = scan.moving_block_bootstrap([1, 2, 3, 4], 2, 200, 1)
        self.assertGreater(result["p10_mean_bps"], 0)
        self.assertEqual(result["probability_mean_le_zero"], 0.0)

    def test_year_profit_concentration_uses_positive_pnl_not_trade_count(self):
        frame = pd.DataFrame(
            {
                "entry_utc": pd.to_datetime(
                    ["2020-01-01", "2020-02-01", "2021-01-01"], utc=True
                ),
                "severe_net_bps": [5.0, 5.0, 10.0],
            }
        )
        self.assertAlmostEqual(scan.year_profit_concentration(frame, "severe_net_bps"), 0.5)

    def test_shortlist_is_family_diverse(self):
        rows = [
            {"key": "a", "family": "trend", "reference_pass": True, "robust_score": 10.0},
            {"key": "b", "family": "trend", "reference_pass": True, "robust_score": 9.0},
            {"key": "c", "family": "breakout", "reference_pass": False, "robust_score": 8.0},
        ]
        result = scan.select_family_diverse_shortlist(rows, 2)
        self.assertEqual([row["key"] for row in result], ["a", "c"])

    def test_end_to_end_run_freezes_shortlist_before_holdout_and_locks_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_alignment_db(root)
            self.make_event_db(root)
            self.make_contract(root)
            config = self.base_config()
            config_path = root / "configs" / "test.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config), encoding="utf-8")
            out = root / "reports" / "scan"
            summary = scan.run(root, config_path, out)
            self.assertFalse(summary["selection_used_holdout"])
            self.assertTrue((out / "successor_shortlist_contract.json").is_file())
            self.assertTrue((out / "successor_holdout_access_lock.json").is_file())
            contract = json.loads((out / "successor_shortlist_contract.json").read_text())
            self.assertFalse(contract["selection_used_holdout"])
            self.assertFalse(contract["execution_allowed"])
            with self.assertRaises(scan.ScanError) as caught:
                scan.run(root, config_path, out)
            self.assertIn(scan.DECISION_LOCKED, str(caught.exception))

    def test_run_outputs_never_authorize_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_alignment_db(root)
            self.make_event_db(root)
            self.make_contract(root)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(self.base_config()), encoding="utf-8")
            summary = scan.run(root, config_path, root / "out")
            self.assertFalse(summary["paper_order_allowed"])
            self.assertFalse(summary["demo_order_allowed"])
            self.assertFalse(summary["live_order_allowed"])

    def test_collect_results_packages_only_current_scan_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_alignment_db(root)
            self.make_event_db(root)
            self.make_contract(root)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(self.base_config()), encoding="utf-8")
            out = root / "out"
            scan.run(root, config_path, out)
            destination = root / "results.zip"
            result = scan.collect_results(root, config_path, out, destination)
            self.assertTrue(result["pass"])
            self.assertTrue(destination.is_file())
            import zipfile
            with zipfile.ZipFile(destination) as archive:
                names = set(archive.namelist())
            self.assertIn("RESULTS_MANIFEST.json", names)
            self.assertIn("reports/successor_scan_summary.json", names)
            self.assertIn("config/config.json", names)

    def test_packaged_candidate_registry_feature_contract_includes_12h_session_range(self):
        root = MODULE_PATH.parents[1]
        config = json.loads(
            (root / "configs" / "xauusd_successor_parallel_scan_v1.json").read_text(
                encoding="utf-8"
            )
        )
        candidates = scan.parse_candidates(config)
        plan = scan.candidate_feature_plan(candidates)
        self.assertIn(12, plan["rolling_windows"])

        timestamps = pd.date_range(
            "2020-01-01", periods=500, freq="h", tz="UTC"
        ).as_unit("us")
        close = 100.0 * np.exp(np.arange(500) * 0.0005)
        frame = pd.DataFrame(
            {
                "timestamp": scan.datetime_to_epoch_ms(timestamps),
                "dt": timestamps,
                "open": np.r_[close[0], close[:-1]],
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": 1.0,
            }
        )
        features = scan.build_features(frame, pd.DataFrame(), candidates)
        contract = scan.validate_candidate_feature_contract(features, candidates)
        self.assertTrue(contract["pass"])
        self.assertIn("prior_high_12", features.columns)
        self.assertIn("prior_low_12", features.columns)
        for candidate in candidates:
            signal = scan.directional_signal(features, candidate)
            self.assertEqual(len(signal), len(features))

    def test_packaged_candidate_registry_runs_end_to_end_without_feature_keyerror(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_alignment_db(root, rows=2600)
            self.make_event_db(root)
            self.make_contract(root)

            package_root = MODULE_PATH.parents[1]
            config = json.loads(
                (
                    package_root
                    / "configs"
                    / "xauusd_successor_parallel_scan_v1.json"
                ).read_text(encoding="utf-8")
            )
            base = self.base_config()
            for key in [
                "alignment_db",
                "event_db",
                "time_contract",
                "h1_table",
                "minimum_m5_bar_count",
                "reference_start",
                "holdout_start",
                "normal_cost_bps",
                "severe_cost_bps",
                "maximum_notional_to_equity",
                "bootstrap",
                "reference_folds",
                "reference_gates",
                "holdout_gates",
                "full_history_gates",
            ]:
                config[key] = base[key]
            config["shortlist_size"] = 3

            config_path = root / "configs" / "full_registry.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(config), encoding="utf-8")
            out = root / "reports" / "full_registry_scan"
            out.mkdir(parents=True, exist_ok=True)
            (out / "successor_scan_failure.json").write_text(
                json.dumps({"decision": "STALE_PRE_REPAIR_FAILURE"}),
                encoding="utf-8",
            )
            summary = scan.run(root, config_path, out)
            self.assertEqual(summary["candidate_count"], len(config["candidates"]))
            self.assertTrue((out / "successor_scan_summary.json").is_file())
            self.assertFalse((out / "successor_scan_failure.json").exists())
            contract = summary["data_quality"]["feature_contract"]
            self.assertTrue(contract["pass"])
            self.assertIn(12, contract["feature_plan"]["rolling_windows"])

    def test_load_h1_rejects_incomplete_m5_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, frame = self.make_alignment_db(root, rows=300)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("UPDATE amarkets_h1_from_m5_utc SET m5_bar_count=5")
                connection.commit()
            with self.assertRaises(scan.ScanError):
                scan.load_h1(path, "amarkets_h1_from_m5_utc", 12)


if __name__ == "__main__":
    unittest.main()
