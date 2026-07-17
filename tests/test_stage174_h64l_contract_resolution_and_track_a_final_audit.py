import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / "app" / "stage174_h64l_contract_resolution_and_track_a_final_audit.py"
spec = importlib.util.spec_from_file_location("stage174", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class Stage174Tests(unittest.TestCase):
    def test_authoritative_horizon_outvotes_incidental_value(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "r.json"; p1.write_text(json.dumps({"candidate": {"horizon_days": 120}}))
            p2 = root / "m.json"; p2.write_text(json.dumps({"debug": {"horizon_days": 60}}))
            cfg = {"contracts": {"horizon_authority": [
                {"path": "r.json", "authority": "DIRECT", "weight": 10},
                {"path": "m.json", "authority": "EARLY", "weight": 2}],
                "minimum_horizon_authority_weight": 8, "minimum_horizon_vote_share": 0.65}}
            out = mod.resolve_horizon_contract(root, cfg)
            self.assertEqual(out["status"], "RESOLVED")
            self.assertEqual(out["holding_days"], 120)

    def test_horizon_remains_blocked_without_authority(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {"contracts": {"horizon_authority": [], "minimum_horizon_authority_weight": 8, "minimum_horizon_vote_share": 0.65}}
            out = mod.resolve_horizon_contract(Path(td), cfg)
            self.assertEqual(out["status"], "HOLDING_HORIZON_UNRESOLVED")

    def test_stage64k_requires_explicit_availability(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            df = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=600), **{c: 1.0 for c in mod.REQ_FEATURES}})
            df.to_csv(p, index=False)
            with self.assertRaises(ValueError):
                mod.normalize_h64l_features(p, Path(td) / "out.csv")

    def test_stage64k_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"; out = Path(td) / "out.csv"
            dates = pd.date_range("2020-01-01", periods=600, tz="UTC")
            df = pd.DataFrame({"feature_date_utc": dates, "sample_available_after_utc": dates + pd.Timedelta(days=2), **{c: np.linspace(-1, 1, 600) for c in mod.REQ_FEATURES}})
            df.to_csv(p, index=False)
            meta = mod.normalize_h64l_features(p, out)
            self.assertEqual(meta["status"], "PASS")
            self.assertEqual(meta["rows"], 600)

    def test_episode_builder_uses_boolean_transition_and_gap(self):
        dates = pd.date_range("2024-01-01", periods=8, freq="30D", tz="UTC")
        df = pd.DataFrame({"date": dates, "active": [0, 1, 1, 0, 1, 0, 1, 0]})
        out = mod.build_episodes(df, "active", 100)
        self.assertEqual(len(out), 2)
        self.assertTrue(out["raw_start"].all())


    def test_dxy_fingerprint_uses_source_metadata_and_scale(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data/macro_regime/normalized").mkdir(parents=True)
            (root / "data/exogenous").mkdir(parents=True)
            dates = pd.date_range("2020-01-01", periods=500, freq="D", tz="UTC")
            level = 100 + np.cumsum(np.sin(np.arange(500) / 17) * 0.05 + 0.01)
            ret = pd.Series(level).pct_change(20).to_numpy() * 100.0
            target = pd.DataFrame({"feature_date_utc": dates, "dxy_ret_20d": ret})
            target_path = root / "data/macro_regime/normalized/stage64k.csv"
            target.to_csv(target_path, index=False)
            candidate = pd.DataFrame({"date_utc": dates, "close": level, "source_series": "DTWEXBGS"})
            candidate.to_csv(root / "data/exogenous/dxy.csv", index=False)
            cfg = {"data": {"dxy_candidates": ["data/exogenous/dxy.csv"], "dxy_globs": []}, "contracts": {
                "dxy_authority_paths": [], "maximum_dxy_candidates": 10, "minimum_dxy_overlap_rows": 200,
                "minimum_dxy_correlation": 0.995, "minimum_dxy_sign_agreement": 0.98,
                "maximum_dxy_median_abs_error": 0.0005}}
            out = mod.fingerprint_dxy_contract(root, cfg, target_path)
            self.assertEqual(out["status"], "RESOLVED")
            self.assertEqual(out["source_contract"], "FRED_DTWEXBGS")
            self.assertEqual(out["best_match"]["scale_factor"], 100.0)

    def test_no_execution_or_ml_path_in_source(self):
        text = MODULE.read_text().lower()
        self.assertNotIn("send_order", text)
        self.assertNotIn("order_send", text)
        self.assertNotIn("sklearn", text)
        self.assertNotIn("xgboost", text)


if __name__ == "__main__":
    unittest.main()
