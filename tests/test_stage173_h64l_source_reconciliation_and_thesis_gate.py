import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


s173 = load_module("stage173", ROOT / "app/stage173_h64l_source_reconciliation_and_thesis_gate.py")
s171 = load_module("stage171h", ROOT / "app/stage171h_h64l_forward_feature_materializer.py")
s172 = load_module("stage172", ROOT / "app/stage172_dual_track_decision_audit.py")


def synthetic_wgc_records(n=36):
    rows = []
    for i, date in enumerate(pd.date_range("2023-01-31", periods=n, freq="ME")):
        funds = {
            "gld us equity": 900 + i * 2.0,
            "iau us equity": 450 + i * 1.0,
            "phys us equity": 100 + i * 0.2,
            "sgol us equity": 45 + i * 0.1,
            "igln ln equity": 220 + i * 0.4,
            "sgld ln equity": 210 + i * 0.3,
            "4gld gr equity": 170 + i * 0.2,
            "gold au equity": 30 + i * 0.05,
        }
        total = sum(funds.values())
        row = {
            "ticker": str(date),
            "All units in tonnes unless otherwise specified": 1800 + i * 20.0,
            "col_2": total * 32150.7466,
            "col_3": total,
            "col_4": total * 1800 * 1_000_000,
            **funds,
        }
        rows.append(row)
    return rows


class Stage173Tests(unittest.TestCase):
    def test_stage173_resolves_col3_by_fund_sum(self):
        series, meta = s173.resolve_holdings_column(synthetic_wgc_records())
        self.assertEqual(meta["selected_column"], "col_3")
        self.assertLess(meta["selected_score"]["median_relative_error_to_fund_sum"], 1e-10)
        self.assertEqual(len(series), 36)

    def test_stage171_materializer_uses_same_semantic_resolver(self):
        result = s171._resolve_wgc_holdings_records(synthetic_wgc_records(), Path("synthetic.csv"))
        self.assertIsNotNone(result)
        self.assertEqual(result.attrs["holdings_column"], "col_3")
        self.assertEqual(result.attrs["resolver"], "FUND_SUM_RECONCILIATION")

    def test_stage171_rejects_ambiguous_price_only_rows(self):
        rows = []
        for i, date in enumerate(pd.date_range("2025-01-31", periods=12, freq="ME")):
            rows.append({
                "ticker": str(date),
                "All units in tonnes unless otherwise specified": 3000 + i * 10,
                "a equity": 100.0,
                "b equity": 120.0,
                "c equity": 130.0,
                "d equity": 140.0,
                "e equity": 150.0,
            })
        self.assertIsNone(s171._resolve_wgc_holdings_records(rows, Path("bad.csv")))

    def test_stage172_missing_track_a_is_inconclusive_not_kill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = {
                "data": {"h64l_feature_candidates": ["missing.csv"]},
                "track_a": {"etf_release_lag_days_if_missing": 26},
            }
            m5 = pd.DataFrame({
                "ts": pd.date_range("2025-01-01", periods=1000, freq="5min", tz="UTC"),
                "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0,
            })
            out = root / "reports"
            out.mkdir()
            result = s172.run_track_a(root, cfg, m5, out)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["decision"], "INCONCLUSIVE_BLOCKED")

    def test_stage172_correction_kills_only_tested_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "reports/stage172_dual_track_decision_audit"
            report.mkdir(parents=True)
            summary = {
                "track_a": {"status": "BLOCKED", "decision": "KILL", "issues": ["missing"]},
                "track_b": {
                    "decision": "NO_BASELINE_SURVIVOR",
                    "results": [
                        {"strategy": "A", "direction": "LONG", "survives": False, "holdout_metrics": {"trades": 20}},
                        {"strategy": "B", "direction": "SHORT", "survives": False, "holdout_metrics": {"trades": 0}},
                    ],
                },
            }
            (report / "stage172_summary.json").write_text(json.dumps(summary))
            out = root / "reports/stage173"
            out.mkdir(parents=True)
            result = s173.correct_stage172(root, {"summary_candidates": [str(report / "stage172_summary.json")]}, out)
            self.assertEqual(result["track_a_corrected"]["decision"], "INCONCLUSIVE_BLOCKED")
            self.assertEqual(result["track_b_exact_tested_formulations_killed"], [{"strategy": "A", "direction": "LONG"}])

    def test_archaeology_uses_stage64_paths_not_current_script_decoys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "archive").mkdir()
            (root / "app").mkdir()
            (root / "archive/stage64r_rule.json").write_text(json.dumps({"rule":"H64L","dxy_source":"DX-Y.NYB","holding_days":20,"etf_flow_tonnes_3m":1}))
            (root / "app/current_stage.py").write_text("Stage64R DTWEXBGS ICE DXY holding_days=99 H64L")
            cfg = {
                "roots":["archive","app"],
                "extensions":[".json",".py"],
                "excluded_path_tokens":[],
                "maximum_file_size_bytes":100000
            }
            result = s173.archaeology(root, cfg)
            self.assertEqual(result["dxy_source_contract_status"], "ORIGINAL_STAGE64_EVIDENCE_POINTS_TO_ICE_DXY")
            self.assertEqual(result["holding_horizon_candidates"], [20])


if __name__ == "__main__":
    unittest.main()
