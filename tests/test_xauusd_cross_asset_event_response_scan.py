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

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_cross_asset_event_response_scan.py"
spec = importlib.util.spec_from_file_location("event_scan", MODULE_PATH)
scan = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(scan)


class EventResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        (self.tmp / "app").mkdir()
        (self.tmp / "configs").mkdir()
        shutil.copy2(MODULE_PATH, self.tmp / "app/xauusd_cross_asset_event_response_scan.py")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_panel(self, ref_return=20.0, diag_return=20.0, n_ref=360, n_diag=72):
        report = self.tmp / scan.PANEL_REPORT_REL
        report.mkdir(parents=True)
        ref_times = pd.date_range("2016-01-04 08:00", periods=n_ref, freq="4h", tz="UTC")
        diag_times = pd.date_range("2025-01-02 08:00", periods=n_diag, freq="4h", tz="UTC")
        times = ref_times.append(diag_times)
        roles = ["REFERENCE_2016_2024"] * n_ref + ["SEEN_DIAGNOSTIC_NOT_PRISTINE_HOLDOUT"] * n_diag
        pattern = np.tile([2.0, -2.0, 0.0, 1.5, -1.5], int(np.ceil(len(times)/5)))[:len(times)]
        # USD impulse is (-EUR + JPY)/2; use EUR=-pattern and JPY=pattern.
        features = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": roles,
            "core_h1_4h_history_ready": 1,
            # Legacy daily-panel flags are intentionally zero; the repaired scanner
            # must derive response windows from the raw timestamp source instead.
            "official_event_blackout_active": 0,
            "official_event_blackout_count": 0,
            "xauusd_m15_ret_4": np.zeros(len(times)),
            "xagusd_m15_ret_4": -pattern,
            "eurusd_m15_ret_4": -pattern,
            "usdjpy_m15_ret_4": pattern,
        })
        fwd = np.where(pattern > 0, -ref_return, np.where(pattern < 0, ref_return, 0.0)).astype(float)
        fwd[n_ref:] = np.where(pattern[n_ref:] > 0, -diag_return, np.where(pattern[n_ref:] < 0, diag_return, 0.0))
        targets = pd.DataFrame({
            "decision_time_utc": times.astype(str),
            "sample_role": roles,
            "exit_time_4h_utc": (times + pd.Timedelta(hours=4)).astype(str),
            "forward_return_4h_bps": fwd,
            "exit_time_12h_utc": (times + pd.Timedelta(hours=12)).astype(str),
            "forward_return_12h_bps": fwd,
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
            "failed_gates": [], "feature_target_time_match": True,
            "availability_leakage_counts": {"all": 0},
        }))
        (report / "cross_asset_panel_contract.json").write_text(json.dumps({"program": scan.PANEL_PROGRAM}))
        pd.DataFrame({
            "column": features.columns,
            "reference_coverage": 1.0,
            "fixed_scan_policy": "AVAILABLE_WITH_MISSINGNESS_CONTROL",
        }).to_csv(report / "cross_asset_feature_policy.csv", index=False)
        large = {"files": [
            {"path": fpath.name, "size": fpath.stat().st_size, "sha256": scan.sha256_file(fpath)},
            {"path": tpath.name, "size": tpath.stat().st_size, "sha256": scan.sha256_file(tpath)},
        ]}
        (report / "cross_asset_large_file_manifest.json").write_text(json.dumps(large))
        event_path = self.tmp / scan.EVENT_SOURCE_DEFAULT_REL
        event_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "event_time_utc": (times - pd.Timedelta(minutes=30)).astype(str),
            "source": "TEST_OFFICIAL",
            "category": "TEST_EVENT",
            "title": "Synthetic official event",
        }).to_csv(event_path, index=False)
        return features, targets

    def write_config(self, force_fail=False):
        cfg = {
            "program": scan.PROGRAM,
            "reference_start_utc": "2016-01-01T00:00:00Z",
            "reference_end_utc": "2025-01-01T00:00:00Z",
            "diagnostic_start_utc": "2025-01-01T00:00:00Z",
            "diagnostic_end_utc": "2027-01-01T00:00:00Z",
            "official_event_source_relative_path": scan.EVENT_SOURCE_DEFAULT_REL.as_posix(),
            "official_event_source_expected_sha256": "",
            "minimum_official_event_source_rows": 1,
            "event_response_min_lag_minutes": 15,
            "event_response_max_lag_minutes": 120,
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
            "minimum_reference_event_rows": 10,
            "maximum_reference_survivors_for_diagnostic": 2,
            "reference_folds": [
                {"name":"a","start_utc":"2016-01-01T00:00:00Z","end_utc":"2019-01-01T00:00:00Z"},
                {"name":"b","start_utc":"2019-01-01T00:00:00Z","end_utc":"2022-01-01T00:00:00Z"},
                {"name":"c","start_utc":"2022-01-01T00:00:00Z","end_utc":"2025-01-01T00:00:00Z"},
            ],
            "reference_gates": {
                "minimum_panel_rows": 10, "minimum_trades": 5,
                "minimum_mean_severe_bps": 9999.0 if force_fail else 0.0,
                "minimum_profit_factor": 1.0, "minimum_bootstrap_p10_bps": -100.0,
                "minimum_positive_folds": 0, "minimum_worst_fold_mean_bps": -100.0,
                "maximum_positive_year_profit_share": 1.0, "minimum_locked_risk_cagr": -1.0,
            },
            "diagnostic_kill_gates": {"minimum_trades": 2, "minimum_profit_factor": 0.5},
            "rolling_z_features": {
                "z_usd_m15_impulse": "usd_m15_impulse",
                "z_xag_m15_impulse": "xagusd_m15_ret_4",
                "z_xau_m15_impulse": "xauusd_m15_ret_4",
            },
            "candidates": [{
                "candidate_id":"test_short", "family":"TEST", "side":"SHORT", "horizon_hours":4,
                "conditions":[
                    {"column":"z_usd_m15_impulse","op":">=","value":0.5},
                    {"column":"z_xag_m15_impulse","op":"<=","value":-0.5},
                ],
            }],
            "paper_order_allowed": False, "demo_order_allowed": False, "live_order_allowed": False,
        }
        path = self.tmp / scan.CONFIG_REL
        path.write_text(json.dumps(cfg))
        return path

    def test_past_only_zscore(self):
        f = pd.DataFrame({"x": np.arange(100, dtype=float)})
        cfg = {"rolling_z_window_rows":20,"rolling_z_min_periods":5,"rolling_z_features":{"z":"x"}}
        a = scan.add_past_only_zscores(f, cfg)["z"].copy()
        f.loc[99,"x"] = 1e9
        b = scan.add_past_only_zscores(f, cfg)["z"]
        pd.testing.assert_series_equal(a.iloc[:99], b.iloc[:99])

    def test_event_eligibility_requires_active_event(self):
        times = pd.date_range("2020-01-01", periods=3, freq="h", tz="UTC")
        frame = pd.DataFrame({
            "decision_time_utc": times, "core_h1_4h_history_ready":1,
            "official_event_response_active":[0,1,0],
            "forward_return_4h_bps":1.0, "exit_time_4h_utc":times+pd.Timedelta(hours=4),
        })
        cfg={"allowed_hours_utc":list(range(24)),"allowed_weekdays":list(range(7))}
        self.assertEqual(scan.common_eligibility(frame,4,cfg).tolist(), [False,True,False])

    def test_usd_impulse_derivation(self):
        self.write_panel(n_ref=20,n_diag=5)
        cfg=self.write_config()
        frame=scan.load_panel_data(self.tmp, scan.load_config(cfg))
        expected=(-pd.to_numeric(frame["eurusd_m15_ret_4"]) + pd.to_numeric(frame["usdjpy_m15_ret_4"]))/2
        np.testing.assert_allclose(frame["usd_m15_impulse"], expected)

    def test_non_overlap(self):
        times=pd.date_range("2020-01-01",periods=10,freq="h",tz="UTC")
        frame=pd.DataFrame({"decision_time_utc":times,"exit_time_4h_utc":times+pd.Timedelta(hours=4),"forward_return_4h_bps":10.0})
        cand={"candidate_id":"x","family":"f","side":"LONG","horizon_hours":4,"conditions":[]}
        out=scan.non_overlapping_trades(frame,pd.Series(True,index=frame.index),cand,{"normal_cost_bps":1,"severe_cost_bps":2},"REFERENCE")
        self.assertEqual(out["decision_time_utc"].dt.hour.tolist(), [0,4,8])

    def test_preflight(self):
        self.write_panel()
        result=scan.preflight(self.tmp,self.write_config())
        self.assertTrue(result["pass"])
        self.assertGreaterEqual(result["official_event_response_rows"],10)

    def test_preflight_rejects_too_few_events(self):
        self.write_panel(n_ref=5,n_diag=0)
        cfg=self.write_config()
        payload=json.loads(cfg.read_text()); payload["minimum_reference_event_rows"]=10; cfg.write_text(json.dumps(payload))
        with self.assertRaises(scan.ScanError): scan.preflight(self.tmp,cfg)

    def test_no_survivor_keeps_diagnostic_closed(self):
        self.write_panel(); cfg=self.write_config(force_fail=True); out=self.tmp/"out"
        summary=scan.run(self.tmp,cfg,out)
        self.assertEqual(summary["reference_pass_count"],0)
        self.assertFalse(summary["diagnostic_evaluated"])
        self.assertFalse((out/"event_response_diagnostic_access_lock.json").exists())

    def test_survivor_freezes_before_diagnostic(self):
        self.write_panel(); cfg=self.write_config(); out=self.tmp/"out"
        summary=scan.run(self.tmp,cfg,out)
        self.assertGreaterEqual(summary["reference_pass_count"],1)
        self.assertTrue(summary["diagnostic_evaluated"])
        self.assertTrue((out/"event_response_reference_survivor_contract.json").is_file())
        self.assertTrue((out/"event_response_diagnostic_access_lock.json").is_file())

    def test_collect_excludes_large_inputs(self):
        self.write_panel(); cfg=self.write_config(force_fail=True); scan.run(self.tmp,cfg)
        output=self.tmp/"result.zip"; scan.collect(self.tmp,output)
        with zipfile.ZipFile(output) as z: names=z.namelist()
        self.assertNotIn("cross_asset_intraday_features.csv",names)
        self.assertIn("cross_asset_event_response_summary.json",names)

    def test_packaged_registry_is_fixed(self):
        cfg=scan.load_config(Path(__file__).resolve().parents[1]/scan.CONFIG_REL)
        self.assertEqual(len(cfg["candidates"]),6)
        self.assertEqual({x["horizon_hours"] for x in cfg["candidates"]},{4,12})
        self.assertTrue(all(x["family"].startswith("EVENT_") for x in cfg["candidates"]))

    def test_static_no_execution(self):
        self.assertEqual(scan.static_execution_violations(Path(__file__).resolve().parents[1]),[])

    def test_streaming_reader_mixed_types(self):
        path=self.tmp/"mixed.csv"
        pd.DataFrame({"a":["1","2","x"],"b":[1,2,3],"c":["u","v","w"]}).to_csv(path,index=False)
        out=scan.read_projected_csv(path,["a","c"],chunk_rows=2)
        self.assertEqual(out.shape,(3,2))
        self.assertEqual(out.columns.tolist(),["a","c"])

    def test_hash_mismatch_fails_preflight(self):
        self.write_panel(); cfg=self.write_config()
        path=self.tmp/scan.PANEL_REPORT_REL/"cross_asset_intraday_features.csv"
        path.write_text(path.read_text()+"\n")
        with self.assertRaises(scan.ScanError):
            scan.preflight(self.tmp,cfg)

    def test_packaged_conditions_execute(self):
        cfg=scan.load_config(Path(__file__).resolve().parents[1]/scan.CONFIG_REL)
        n=2500
        times=pd.date_range("2020-01-01",periods=n,freq="h",tz="UTC")
        frame=pd.DataFrame({
            "decision_time_utc":times,
            "sample_role":"REFERENCE_2016_2024",
            "core_h1_4h_history_ready":1,
            "official_event_response_active":1,
            "official_event_response_count":1,
            "event_count_capped":1,
            "xauusd_m15_ret_4":np.sin(np.arange(n)/13),
            "xagusd_m15_ret_4":np.cos(np.arange(n)/17),
            "eurusd_m15_ret_4":np.sin(np.arange(n)/19),
            "usdjpy_m15_ret_4":np.cos(np.arange(n)/23),
            "usd_m15_impulse":np.sin(np.arange(n)/29),
            "exit_time_4h_utc":times+pd.Timedelta(hours=4),
            "forward_return_4h_bps":5.0,
            "exit_time_12h_utc":times+pd.Timedelta(hours=12),
            "forward_return_12h_bps":5.0,
        })
        frame=scan.add_past_only_zscores(frame,cfg)
        for cand in cfg["candidates"]:
            universe,signal=scan.candidate_masks(frame,cand,cfg)
            self.assertEqual(len(universe),n)
            self.assertEqual(len(signal),n)

    def test_raw_event_source_overrides_zero_legacy_panel_flags(self):
        features, _ = self.write_panel(n_ref=20, n_diag=5)
        self.assertEqual(int(features["official_event_blackout_active"].sum()), 0)
        cfg = self.write_config()
        frame = scan.load_panel_data(self.tmp, scan.load_config(cfg))
        self.assertGreater(int(frame["official_event_response_active"].sum()), 0)
        self.assertNotIn("official_event_blackout_active", frame.columns)

    def test_event_response_minimum_lag_excludes_too_recent_event(self):
        decisions = pd.DataFrame({
            "decision_time_utc": pd.to_datetime(["2020-01-01T14:00:00Z", "2020-01-01T15:00:00Z"])
        })
        events = pd.DataFrame({
            "event_time_utc": pd.to_datetime(["2020-01-01T13:55:00Z", "2020-01-01T14:00:00Z"])
        })
        out = scan.attach_event_response_flags(decisions, events, {
            "event_response_min_lag_minutes": 15,
            "event_response_max_lag_minutes": 120,
        })
        self.assertEqual(out["official_event_response_count"].tolist(), [0, 2])

    def test_preflight_counts_raw_timestamp_windows_not_daily_flags(self):
        features, _ = self.write_panel(n_ref=40, n_diag=0)
        self.assertEqual(int(features["official_event_blackout_active"].sum()), 0)
        result = scan.preflight(self.tmp, self.write_config())
        self.assertGreaterEqual(result["official_event_response_rows"], 10)
        self.assertGreaterEqual(result["official_event_source_rows"], 1)

    def test_preflight_failure_does_not_poison_run_directory(self):
        path = scan.failure_output_path(self.tmp, "preflight")
        self.assertEqual(path, self.tmp / scan.PREFLIGHT_FAILURE_REL)
        self.assertNotEqual(path.parent, self.tmp / scan.REPORT_REL)

    def test_packaged_event_source_is_reference_locked(self):
        cfg = scan.load_config(Path(__file__).resolve().parents[1] / scan.CONFIG_REL)
        self.assertEqual(
            cfg["official_event_source_relative_path"],
            "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv",
        )
        self.assertEqual(
            cfg["official_event_source_expected_sha256"],
            "601f587e0128d4322bc3ea5071545e53adf035b5e08fdbafa72cf16a550ec560",
        )
        self.assertEqual(cfg["event_response_min_lag_minutes"], 15)
        self.assertEqual(cfg["event_response_max_lag_minutes"], 120)

    def test_failure_payload_contains_context_and_traceback(self):
        scan.set_run_context("UNIT_STAGE","unit_candidate",3)
        try:
            raise scan.ScanError("boom")
        except Exception as exc:
            payload=scan.failure_payload(exc)
        self.assertEqual(payload["stage"],"UNIT_STAGE")
        self.assertEqual(payload["candidate_id"],"unit_candidate")
        self.assertEqual(payload["candidate_index"],3)
        self.assertIn("ScanError: boom",payload["traceback"])


if __name__ == "__main__":
    unittest.main()
