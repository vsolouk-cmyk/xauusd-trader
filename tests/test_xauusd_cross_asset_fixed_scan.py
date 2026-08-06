from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_cross_asset_fixed_scan.py"
spec = importlib.util.spec_from_file_location("fixed_scan", MODULE_PATH)
scan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(scan)


class FixedScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "app").mkdir()
        (self.tmp / "configs").mkdir()
        shutil.copy2(MODULE_PATH, self.tmp / "app/xauusd_cross_asset_fixed_scan.py")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_panel(self, ref_return: float = 25.0, diag_return: float = 25.0, n_ref: int = 240, n_diag: int = 48):
        report = self.tmp / scan.PANEL_REPORT_REL
        report.mkdir(parents=True)
        ref_times = pd.date_range("2016-01-04 06:00", periods=n_ref, freq="4h", tz="UTC")
        diag_times = pd.date_range("2025-01-02 06:00", periods=n_diag, freq="4h", tz="UTC")
        times = ref_times.append(diag_times)
        roles = ["REFERENCE_2016_2024"] * n_ref + ["SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT"] * n_diag
        raw = np.tile([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, -1.0], int(np.ceil(len(times) / 7)))[:len(times)]
        features = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": roles,
            "core_h1_4h_history_ready": 1,
            "official_event_blackout_active": 0,
            "raw_signal": raw,
        })
        forward = np.where(raw > 0, ref_return, -5.0).astype(float)
        forward[n_ref:] = np.where(raw[n_ref:] > 0, diag_return, -5.0)
        targets = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": roles,
            "exit_time_4h_utc": (times + pd.Timedelta(hours=4)).astype(str),
            "forward_return_4h_bps": forward,
        })
        fpath = report / "cross_asset_intraday_features.csv"
        tpath = report / "cross_asset_intraday_targets.csv"
        features.to_csv(fpath, index=False)
        targets.to_csv(tpath, index=False)
        summary = {
            "program": scan.PANEL_PROGRAM,
            "decision": "PASS_CROSS_ASSET_INTRADAY_CAUSAL_PANEL_READY_FOR_FIXED_SCAN",
            "pass": True,
            "feature_rows": len(features),
        }
        quality = {
            "failed_gates": [],
            "feature_target_time_match": True,
            "availability_leakage_counts": {"x": 0},
        }
        contract = {"program": scan.PANEL_PROGRAM}
        for name, payload in [
            ("cross_asset_panel_summary.json", summary),
            ("cross_asset_panel_quality.json", quality),
            ("cross_asset_panel_contract.json", contract),
        ]:
            (report / name).write_text(json.dumps(payload))
        pd.DataFrame({
            "column": features.columns,
            "reference_coverage": 1.0,
            "fixed_scan_policy": "AVAILABLE_WITH_MISSINGNESS_CONTROL",
        }).to_csv(report / "cross_asset_feature_policy.csv", index=False)
        large = {
            "files": [
                {"path": fpath.name, "size": fpath.stat().st_size, "sha256": scan.sha256_file(fpath), "rows": len(features), "columns": len(features.columns)},
                {"path": tpath.name, "size": tpath.stat().st_size, "sha256": scan.sha256_file(tpath), "rows": len(targets), "columns": len(targets.columns)},
            ]
        }
        (report / "cross_asset_large_file_manifest.json").write_text(json.dumps(large))
        return features, targets

    def write_config(self, pass_gates: bool = True):
        payload = {
            "program": scan.PROGRAM,
            "reference_start_utc": "2016-01-01T00:00:00Z",
            "reference_end_utc": "2025-01-01T00:00:00Z",
            "diagnostic_start_utc": "2025-01-01T00:00:00Z",
            "diagnostic_end_utc": "2027-01-01T00:00:00Z",
            "normal_cost_bps": 1.0,
            "severe_cost_bps": 2.0,
            "locked_notional_to_equity": 0.15,
            "allowed_hours_utc": list(range(24)),
            "allowed_weekdays": list(range(7)),
            "rolling_z_window_rows": 20,
            "rolling_z_min_periods": 5,
            "bootstrap_reps": 100,
            "bootstrap_block_trades": 3,
            "bootstrap_seed": 7,
            "maximum_reference_survivors_for_diagnostic": 2,
            "reference_folds": [
                {"name": "a", "start_utc": "2016-01-01T00:00:00Z", "end_utc": "2019-01-01T00:00:00Z"},
                {"name": "b", "start_utc": "2019-01-01T00:00:00Z", "end_utc": "2022-01-01T00:00:00Z"},
                {"name": "c", "start_utc": "2022-01-01T00:00:00Z", "end_utc": "2025-01-01T00:00:00Z"},
            ],
            "reference_gates": {
                "minimum_panel_rows": 10,
                "minimum_trades": 10,
                "minimum_mean_severe_bps": 0.0,
                "minimum_profit_factor": 1.01,
                "minimum_bootstrap_p10_bps": 0.0,
                "minimum_positive_folds": 1,
                "minimum_worst_fold_mean_bps": -100.0,
                "maximum_positive_year_profit_share": 1.0,
                "minimum_locked_risk_cagr": -1.0,
            },
            "diagnostic_kill_gates": {"minimum_trades": 2, "minimum_profit_factor": 1.0},
            "rolling_z_features": {},
            "candidates": [{
                "candidate_id": "raw_long",
                "family": "TEST",
                "side": "LONG",
                "horizon_hours": 4,
                "conditions": [{"column": "raw_signal", "op": ">", "value": 0.0}],
            }],
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        }
        if not pass_gates:
            payload["reference_gates"]["minimum_mean_severe_bps"] = 9999.0
        path = self.tmp / scan.CONFIG_REL
        path.write_text(json.dumps(payload))
        return path

    def test_past_only_zscore_does_not_change_earlier_values(self):
        f = pd.DataFrame({"x": np.arange(100, dtype=float)})
        cfg = {"rolling_z_window_rows": 20, "rolling_z_min_periods": 5, "rolling_z_features": {"z_x": "x"}}
        a = scan.add_past_only_zscores(f, cfg)["z_x"].copy()
        f.loc[99, "x"] = 1e9
        b = scan.add_past_only_zscores(f, cfg)["z_x"]
        pd.testing.assert_series_equal(a.iloc[:99], b.iloc[:99])

    def test_non_overlapping_trades(self):
        times = pd.date_range("2020-01-01", periods=10, freq="h", tz="UTC")
        frame = pd.DataFrame({
            "decision_time_utc": times,
            "exit_time_4h_utc": times + pd.Timedelta(hours=4),
            "forward_return_4h_bps": 10.0,
        })
        cand = {"candidate_id": "x", "family": "f", "side": "LONG", "horizon_hours": 4, "conditions": []}
        cfg = {"normal_cost_bps": 1.0, "severe_cost_bps": 2.0}
        out = scan.non_overlapping_trades(frame, pd.Series(True, index=frame.index), cand, cfg, "REFERENCE")
        self.assertEqual(out["decision_time_utc"].dt.hour.tolist(), [0, 4, 8])

    def test_preflight_verifies_panel_and_no_orders(self):
        self.write_panel()
        cfg = self.write_config()
        result = scan.preflight(self.tmp, cfg)
        self.assertTrue(result["pass"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["static_execution_violations"], [])

    def test_hash_mismatch_fails(self):
        self.write_panel()
        cfg = self.write_config()
        path = self.tmp / scan.PANEL_REPORT_REL / "cross_asset_intraday_features.csv"
        path.write_text(path.read_text() + "\n")
        with self.assertRaises(scan.ScanError):
            scan.preflight(self.tmp, cfg)

    def test_no_reference_survivor_does_not_evaluate_diagnostic(self):
        self.write_panel()
        cfg = self.write_config(pass_gates=False)
        out = self.tmp / "out"
        summary = scan.run(self.tmp, cfg, out)
        self.assertEqual(summary["reference_pass_count"], 0)
        self.assertFalse(summary["diagnostic_evaluated"])
        self.assertFalse((out / "cross_asset_diagnostic_access_lock.json").exists())
        self.assertFalse((out / "cross_asset_diagnostic_metrics.csv").exists())

    def test_reference_survivor_freezes_before_diagnostic(self):
        self.write_panel(ref_return=25.0, diag_return=25.0)
        cfg = self.write_config()
        out = self.tmp / "out"
        summary = scan.run(self.tmp, cfg, out)
        self.assertEqual(summary["reference_pass_count"], 1)
        self.assertTrue(summary["diagnostic_evaluated"])
        self.assertTrue((out / "cross_asset_reference_survivor_contract.json").is_file())
        self.assertTrue((out / "cross_asset_diagnostic_access_lock.json").is_file())

    def test_diagnostic_mutation_does_not_change_reference_metrics(self):
        self.write_panel(ref_return=25.0, diag_return=25.0)
        cfg = self.write_config()
        out1 = self.tmp / "out1"
        scan.run(self.tmp, cfg, out1)
        ref1 = pd.read_csv(out1 / "cross_asset_reference_metrics.csv")
        tpath = self.tmp / scan.PANEL_REPORT_REL / "cross_asset_intraday_targets.csv"
        targets = pd.read_csv(tpath)
        mask = targets["sample_role"].eq("SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT")
        targets.loc[mask, "forward_return_4h_bps"] = -9999.0
        targets.to_csv(tpath, index=False)
        large_path = self.tmp / scan.PANEL_REPORT_REL / "cross_asset_large_file_manifest.json"
        large = json.loads(large_path.read_text())
        item = next(x for x in large["files"] if x["path"] == tpath.name)
        item["size"] = tpath.stat().st_size
        item["sha256"] = scan.sha256_file(tpath)
        large_path.write_text(json.dumps(large))
        out2 = self.tmp / "out2"
        scan.run(self.tmp, cfg, out2)
        ref2 = pd.read_csv(out2 / "cross_asset_reference_metrics.csv")
        pd.testing.assert_frame_equal(ref1, ref2)

    def test_collect_excludes_large_panel_inputs(self):
        self.write_panel()
        cfg = self.write_config()
        scan.run(self.tmp, cfg)
        output = self.tmp / "result.zip"
        scan.collect(self.tmp, output)
        with zipfile.ZipFile(output) as z:
            names = z.namelist()
        self.assertNotIn("cross_asset_intraday_features.csv", names)
        self.assertNotIn("cross_asset_intraday_targets.csv", names)
        self.assertIn("cross_asset_fixed_scan_summary.json", names)

    def test_event_and_hour_filter(self):
        times = pd.to_datetime(["2020-01-01T05:00:00Z", "2020-01-01T06:00:00Z", "2020-01-01T07:00:00Z"])
        frame = pd.DataFrame({
            "decision_time_utc": times,
            "core_h1_4h_history_ready": [1, 1, 1],
            "official_event_blackout_active": [0, 1, 0],
            "forward_return_4h_bps": [1, 1, 1],
            "exit_time_4h_utc": times + pd.Timedelta(hours=4),
        })
        cfg = {"allowed_hours_utc": [6, 7], "allowed_weekdays": list(range(7))}
        mask = scan.common_eligibility(frame, 4, cfg)
        self.assertEqual(mask.tolist(), [False, False, True])

    def test_bootstrap_is_deterministic(self):
        values = np.arange(-10, 11, dtype=float)
        a = scan.block_bootstrap_mean(values, 100, 4, 5)
        b = scan.block_bootstrap_mean(values, 100, 4, 5)
        self.assertEqual(a, b)

    def test_packaged_registry_is_fixed_and_unique(self):
        cfg = scan.load_config(Path(__file__).resolve().parents[1] / scan.CONFIG_REL)
        self.assertEqual(len(cfg["candidates"]), 12)
        ids = [x["candidate_id"] for x in cfg["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({x["horizon_hours"] for x in cfg["candidates"]}, {4, 12})

    def test_packaged_registry_avoids_excluded_24h_features(self):
        cfg = scan.load_config(Path(__file__).resolve().parents[1] / scan.CONFIG_REL)
        used = {c["column"] for x in cfg["candidates"] for c in x["conditions"]}
        self.assertFalse(any("ret_24" in x or "rv_24" in x for x in used))


    def test_packaged_registry_conditions_execute_without_missing_columns(self):
        cfg = scan.load_config(Path(__file__).resolve().parents[1] / scan.CONFIG_REL)
        n = 2000
        times = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
        data = {
            "decision_time_utc": times,
            "sample_role": "REFERENCE_2016_2024",
            "core_h1_4h_history_ready": 1,
            "official_event_blackout_active": 0,
            "exit_time_4h_utc": times + pd.Timedelta(hours=4),
            "forward_return_4h_bps": 5.0,
            "exit_time_12h_utc": times + pd.Timedelta(hours=12),
            "forward_return_12h_bps": 5.0,
        }
        for source in cfg["rolling_z_features"].values():
            data[source] = np.sin(np.arange(n) / 17.0)
        for candidate in cfg["candidates"]:
            for condition in candidate["conditions"]:
                col = condition["column"]
                if not col.startswith("z_") and col not in data:
                    data[col] = np.cos(np.arange(n) / 29.0)
        frame = scan.add_past_only_zscores(pd.DataFrame(data), cfg)
        for candidate in cfg["candidates"]:
            universe, signal = scan.candidate_masks(frame, candidate, cfg)
            self.assertEqual(len(universe), n)
            self.assertEqual(len(signal), n)

    def test_empty_candidate_fold_rows_keep_candidate_identity(self):
        trades = pd.DataFrame(columns=["candidate_id", "decision_time_utc", "severe_net_bps"])
        cfg = {"reference_folds": [{"name": "x", "start_utc": "2016-01-01T00:00:00Z", "end_utc": "2017-01-01T00:00:00Z"}]}
        folds = scan.fold_metrics(trades, cfg, "candidate_x")
        self.assertEqual(folds.loc[0, "candidate_id"], "candidate_x")

    def test_static_scan_has_no_execution_behavior(self):
        self.assertEqual(scan.static_execution_violations(Path(__file__).resolve().parents[1]), [])

    def test_zero_trade_registry_writes_headered_empty_trade_artifact(self):
        self.write_panel()
        cfg_path = self.write_config(pass_gates=False)
        payload = json.loads(cfg_path.read_text())
        payload["candidates"][0]["conditions"] = [{"column": "raw_signal", "op": ">", "value": 9999.0}]
        cfg_path.write_text(json.dumps(payload))
        out = self.tmp / "zero_trade_out"
        summary = scan.run(self.tmp, cfg_path, out)
        self.assertEqual(summary["reference_pass_count"], 0)
        trades = pd.read_csv(out / "cross_asset_reference_trades.csv.gz")
        self.assertEqual(len(trades), 0)
        self.assertIn("candidate_id", trades.columns)
        self.assertIn("signal_raw_signal", trades.columns)

    def test_write_csv_gz_rejects_schema_less_frame(self):
        with self.assertRaises(scan.ScanError):
            scan.write_csv_gz(self.tmp / "bad.csv.gz", pd.DataFrame())

    def test_failure_payload_contains_stage_candidate_and_traceback(self):
        scan.set_run_context("REFERENCE_METRICS", "candidate_x", 4)
        try:
            raise IndexError("synthetic")
        except Exception as exc:
            payload = scan.failure_payload(exc)
        self.assertEqual(payload["stage"], "REFERENCE_METRICS")
        self.assertEqual(payload["candidate_id"], "candidate_x")
        self.assertEqual(payload["candidate_index"], 4)
        self.assertIn("IndexError: synthetic", payload["traceback"])

    def test_packaged_registry_full_zero_signal_run_completes_fail_closed(self):
        cfg_source = Path(__file__).resolve().parents[1] / scan.CONFIG_REL
        cfg = json.loads(cfg_source.read_text())
        cfg["reference_gates"]["minimum_panel_rows"] = 100
        cfg["bootstrap_reps"] = 25
        cfg["rolling_z_window_rows"] = 48
        cfg["rolling_z_min_periods"] = 24
        cfg_path = self.tmp / scan.CONFIG_REL
        cfg_path.write_text(json.dumps(cfg))

        report = self.tmp / scan.PANEL_REPORT_REL
        report.mkdir(parents=True)
        times = pd.date_range("2020-01-01 00:00", periods=1000, freq="h", tz="UTC")
        feature_cols, target_cols = scan.required_columns(cfg)
        features = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": "REFERENCE_2016_2024",
            "core_h1_4h_history_ready": 1,
            "official_event_blackout_active": 0,
        })
        for col in feature_cols:
            if col not in features.columns:
                features[col] = 0.0
        targets = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": "REFERENCE_2016_2024",
            "exit_time_4h_utc": (times + pd.Timedelta(hours=4)).astype(str),
            "forward_return_4h_bps": 0.0,
            "exit_time_12h_utc": (times + pd.Timedelta(hours=12)).astype(str),
            "forward_return_12h_bps": 0.0,
        })
        fpath = report / "cross_asset_intraday_features.csv"
        tpath = report / "cross_asset_intraday_targets.csv"
        features.to_csv(fpath, index=False)
        targets.to_csv(tpath, index=False)
        (report / "cross_asset_panel_summary.json").write_text(json.dumps({
            "program": scan.PANEL_PROGRAM,
            "decision": "PASS_CROSS_ASSET_INTRADAY_CAUSAL_PANEL_READY_FOR_FIXED_SCAN",
            "pass": True,
            "feature_rows": len(features),
        }))
        (report / "cross_asset_panel_quality.json").write_text(json.dumps({
            "failed_gates": [],
            "feature_target_time_match": True,
            "availability_leakage_counts": {"x": 0},
        }))
        (report / "cross_asset_panel_contract.json").write_text(json.dumps({"program": scan.PANEL_PROGRAM}))
        pd.DataFrame({
            "column": features.columns,
            "reference_coverage": 1.0,
            "fixed_scan_policy": "AVAILABLE_WITH_MISSINGNESS_CONTROL",
        }).to_csv(report / "cross_asset_feature_policy.csv", index=False)
        (report / "cross_asset_large_file_manifest.json").write_text(json.dumps({"files": [
            {"path": fpath.name, "size": fpath.stat().st_size, "sha256": scan.sha256_file(fpath)},
            {"path": tpath.name, "size": tpath.stat().st_size, "sha256": scan.sha256_file(tpath)},
        ]}))

        out = self.tmp / "full_registry_zero_signal"
        summary = scan.run(self.tmp, cfg_path, out)
        self.assertEqual(summary["reference_pass_count"], 0)
        self.assertFalse(summary["diagnostic_evaluated"])
        empty_trades = pd.read_csv(out / "cross_asset_reference_trades.csv.gz")
        self.assertEqual(len(empty_trades), 0)
        self.assertIn("candidate_id", empty_trades.columns)

    def test_packaged_registry_empty_trades_have_stable_union_schema(self):
        cfg = scan.load_config(Path(__file__).resolve().parents[1] / scan.CONFIG_REL)
        empty = scan.empty_trade_frame(cfg)
        self.assertGreater(len(empty.columns), len(scan.BASE_TRADE_COLUMNS))
        self.assertEqual(len(empty), 0)
        self.assertEqual(len(empty.columns), len(set(empty.columns)))

    def test_streaming_projected_reader_handles_mixed_types_without_one_shot_concat(self):
        path = self.tmp / "mixed.csv"
        rows = ["decision_time_utc,mixed_numeric,other"]
        for i in range(25050):
            mixed = str(i) if i < 12000 else ("" if i < 18000 else f"2026-01-{(i % 28) + 1:02d}T00:00:00Z")
            rows.append(f"2020-01-01T{i % 24:02d}:00:00Z,{mixed},{i}")
        path.write_text("\n".join(rows) + "\n")
        out = scan.read_projected_csv(path, ["decision_time_utc", "mixed_numeric"], chunk_rows=4096)
        self.assertEqual(len(out), 25050)
        self.assertEqual(out.columns.tolist(), ["decision_time_utc", "mixed_numeric"])
        self.assertEqual(str(out.dtypes["mixed_numeric"]), "string")

    def test_load_panel_data_never_uses_one_shot_usecols_reader(self):
        self.write_panel()
        cfg_path = self.write_config()
        cfg = scan.load_config(cfg_path)
        original = scan.pd.read_csv
        calls = []

        def guarded_read_csv(*args, **kwargs):
            calls.append(dict(kwargs))
            if kwargs.get("usecols") is not None and kwargs.get("chunksize") is None:
                raise AssertionError("one-shot usecols reader is forbidden")
            return original(*args, **kwargs)

        scan.pd.read_csv = guarded_read_csv
        try:
            frame = scan.load_panel_data(self.tmp, cfg)
        finally:
            scan.pd.read_csv = original
        self.assertGreater(len(frame), 0)
        projected = [x for x in calls if x.get("usecols") is not None]
        self.assertTrue(projected)
        self.assertTrue(all(x.get("chunksize") for x in projected))
        self.assertTrue(all(x.get("dtype") == "string" for x in projected))

    def test_projected_reader_rejects_duplicate_header(self):
        path = self.tmp / "duplicate.csv"
        path.write_text("a,a,b\n1,2,3\n")
        with self.assertRaises(scan.ScanError):
            scan.read_projected_csv(path, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
