import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from app import xauusd_final_alpha_trend as m


class FinalAlphaTrendTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(Path("configs/xauusd_final_alpha_trend.json").read_text())

    def test_eu_dst_contract_winter(self):
        x = pd.Timestamp("2024-01-15 12:00:00")
        y = m.server_naive_to_utc(x, -120, -180)
        self.assertEqual(str(y), "2024-01-15 10:00:00+00:00")

    def test_eu_dst_contract_summer(self):
        x = pd.Timestamp("2024-07-15 12:00:00")
        y = m.server_naive_to_utc(x, -120, -180)
        self.assertEqual(str(y), "2024-07-15 09:00:00+00:00")

    def test_load_realistic_mt5_schema(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h1.csv"
            dates = pd.date_range("2022-01-01", periods=10050, freq="h")
            px = 1800 + np.arange(len(dates)) * 0.001
            df = pd.DataFrame({
                "<DATE>": dates.strftime("%Y.%m.%d"),
                "<TIME>": dates.strftime("%H:%M:%S"),
                "<OPEN>": px,
                "<HIGH>": px + 1,
                "<LOW>": px - 1,
                "<CLOSE>": px + 0.2,
            })
            df.to_csv(p, index=False, sep="\t")
            got = m.load_mt5_h1(p, self.cfg)
            self.assertGreaterEqual(len(got), len(df) - 2)
            self.assertFalse(got["timestamp_utc"].duplicated().any())
            self.assertEqual(got.attrs["loader"], "MT5_DATE_TIME_EU_DST")

    def test_ohlc_failure_is_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h1.csv"
            dates = pd.date_range("2022-01-01", periods=10050, freq="h")
            df = pd.DataFrame({
                "<DATE>": dates.strftime("%Y.%m.%d"), "<TIME>": dates.strftime("%H:%M:%S"),
                "<OPEN>": 100.0, "<HIGH>": 99.0, "<LOW>": 98.0, "<CLOSE>": 100.0,
            })
            df.to_csv(p, index=False)
            with self.assertRaises(m.CampaignError):
                m.load_mt5_h1(p, self.cfg)

    def _daily_h1(self, start="2010-01-01", end="2026-08-01", drift=0.0005):
        d = pd.date_range(start, end, freq="D", tz="UTC")
        r = np.full(len(d), drift)
        close = 100 * np.cumprod(1 + r)
        out = pd.DataFrame({
            "timestamp_utc": d,
            "open": close / (1 + drift),
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
        })
        return out

    def test_monthly_signal_is_past_only(self):
        h1 = self._daily_h1()
        a = m.build_monthly_strategy(h1, self.cfg)
        changed = h1.copy()
        cut = pd.Timestamp("2020-01-01", tz="UTC")
        changed.loc[changed["timestamp_utc"] >= cut, ["open", "high", "low", "close"]] *= 3.0
        b = m.build_monthly_strategy(changed, self.cfg)
        aa = a.loc[a["entry_utc"] < cut, ["entry_utc", "signal", "ex_ante_vol"]].reset_index(drop=True)
        bb = b.loc[b["entry_utc"] < cut, ["entry_utc", "signal", "ex_ante_vol"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(aa, bb)

    def test_signal_uses_12_month_return_sign(self):
        h1 = self._daily_h1(drift=0.001)
        x = m.build_monthly_strategy(h1, self.cfg)
        self.assertTrue((x["signal"] == 1).all())

    def test_position_cap(self):
        h1 = self._daily_h1(drift=0.00001)
        x = m.build_monthly_strategy(h1, self.cfg)
        self.assertLessEqual(float(x["position"].abs().max()), 2.0 + 1e-12)

    def test_turnover_cost_flip(self):
        df = pd.DataFrame({"position": [1.0, -1.0]})
        turnover = (df["position"] - df["position"].shift(1).fillna(0)).abs()
        self.assertEqual(list(turnover), [1.0, 2.0])

    def test_bootstrap_deterministic(self):
        x = np.arange(10, dtype=float)
        a = m.moving_block_bootstrap_means(x, 20, 3, 9)
        b = m.moving_block_bootstrap_means(x, 20, 3, 9)
        np.testing.assert_array_equal(a, b)

    def test_reference_boundary_excludes_crossing_month(self):
        h1 = self._daily_h1()
        monthly = m.build_monthly_strategy(h1, self.cfg)
        boundary = pd.Timestamp(self.cfg["reference_end_utc"])
        ref = monthly.loc[monthly["exit_utc"] < boundary]
        self.assertTrue((ref["exit_utc"] < boundary).all())
        crossing = monthly.loc[(monthly["entry_utc"] < boundary) & (monthly["exit_utc"] >= boundary)]
        self.assertLessEqual(len(crossing), 1)

    def test_diagnostic_not_evaluated_if_reference_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "configs").mkdir()
            cfg = dict(self.cfg)
            cfg["reference_gates"] = dict(cfg["reference_gates"])
            cfg["reference_gates"]["min_severe_annualized_return"] = 99.0
            (root / "configs/xauusd_final_alpha_trend.json").write_text(json.dumps(cfg))
            p = root / "h1.csv"
            dates = pd.date_range("2010-01-01", "2026-08-01", freq="h")
            rng = np.random.default_rng(17)
            rets = rng.normal(0.00002, 0.0008, len(dates))
            px = 100 * np.cumprod(1.0 + rets)
            pd.DataFrame({
                "timestamp": dates.astype(str), "open": px, "high": px*1.001, "low": px*0.999, "close": px
            }).to_csv(p, index=False)
            with mock.patch.object(m, "diagnostic_gate_checks", side_effect=AssertionError("diagnostic opened")):
                result = m.run_campaign(root, root / "configs/xauusd_final_alpha_trend.json", str(p), "run")
            self.assertEqual(result["decision"], m.REF_FAIL)
            self.assertFalse(result["diagnostic_2025_plus_evaluated"])

    def test_reference_gate_can_pass_strong_series(self):
        n = 132
        dates = pd.date_range("2013-01-01", periods=n, freq="MS", tz="UTC")
        rng = np.random.default_rng(3)
        r = rng.normal(0.012, 0.015, n)
        passive = rng.normal(0.002, 0.015, n)
        df = pd.DataFrame({"entry_utc": dates, "exit_utc": dates + pd.offsets.MonthBegin(1), "net_return_severe": r, "passive_net_return_severe": passive})
        met = m.metrics(df, "net_return_severe", self.cfg)
        folds = m.fold_metrics(df, "net_return_severe")
        years = m.year_metrics(df, "net_return_severe")
        paired = m.paired_excess_metrics(df, self.cfg, "net_return_severe", "passive_net_return_severe")
        checks = m.reference_gate_checks(df, self.cfg, met, folds, years, paired)
        self.assertTrue(checks["all"])

    def test_reference_gate_rejects_null(self):
        n = 132
        dates = pd.date_range("2013-01-01", periods=n, freq="MS", tz="UTC")
        rng = np.random.default_rng(4)
        r = rng.normal(0.0, 0.02, n)
        df = pd.DataFrame({"entry_utc": dates, "exit_utc": dates + pd.offsets.MonthBegin(1), "net_return_severe": r, "passive_net_return_severe": r})
        met = m.metrics(df, "net_return_severe", self.cfg)
        folds = m.fold_metrics(df, "net_return_severe")
        years = m.year_metrics(df, "net_return_severe")
        paired = m.paired_excess_metrics(df, self.cfg, "net_return_severe", "passive_net_return_severe")
        checks = m.reference_gate_checks(df, self.cfg, met, folds, years, paired)
        self.assertFalse(checks["all"])

    def test_collect_verifies_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = dict(self.cfg)
            cfg["output_dir"] = "reports/xauusd_final_alpha_trend"
            cfg["collect_name"] = "TEMP_XAUUSD_FINAL_ALPHA_TREND_RESULTS.zip"
            (root / "configs").mkdir()
            cp = root / "configs/xauusd_final_alpha_trend.json"
            cp.write_text(json.dumps(cfg))
            out = root / cfg["output_dir"]
            out.mkdir(parents=True)
            (out / "final_alpha_trend_summary.json").write_text("{}")
            m.write_json(out / "RESULTS_MANIFEST.json", m.output_manifest(out, {"RESULTS_MANIFEST.json"}))
            with mock.patch.object(Path, "home", return_value=root):
                dest = m.collect(root, cp)
            self.assertTrue(dest.is_file())
            dest.unlink()

    def test_no_order_authorization(self):
        a = self.cfg["execution_authorization"]
        self.assertFalse(a["paper_order_allowed"])
        self.assertFalse(a["demo_order_allowed"])
        self.assertFalse(a["live_order_allowed"])

    def test_parameter_scan_absent(self):
        self.assertIsInstance(self.cfg["lookback_months"], int)
        self.assertIsInstance(self.cfg["position"]["target_annual_volatility"], float)
        self.assertNotIn("grid", json.dumps(self.cfg).lower())


if __name__ == "__main__":
    unittest.main()
