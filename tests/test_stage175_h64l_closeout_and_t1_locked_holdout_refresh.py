import csv
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import sys
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage175_h64l_closeout_and_t1_locked_holdout_refresh.py"
spec = importlib.util.spec_from_file_location("stage175", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class Stage175Tests(unittest.TestCase):
    def test_mt5_split_schema_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h1.csv"
            p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n2026.01.02\t03:00:00\t2000\t2002\t1999\t2001\n", encoding="utf-8")
            bars = m.load_h1_csv(p)
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].close, 2001.0)

    def test_macro_permitted(self):
        b = m.Bar(0, datetime.now(timezone.utc), 1, 2, 0, 1)
        b.macro_regime = "neutral"
        b.macro_score_long_gold = 0
        b.d_real_yield_20d = 0.1
        b.d_usd_20d_pct = -0.1
        self.assertTrue(m.macro_permitted(b)[0])
        b.macro_regime = "hostile"
        self.assertFalse(m.macro_permitted(b)[0])

    def test_locked_filter(self):
        b = m.Bar(0, datetime.now(timezone.utc), 100, 101, 99, 100)
        b.d1_close, b.d1_ma50 = 106, 100
        b.h4_close, b.h4_ma50 = 103, 100
        b.atr_h1_14 = 0.4
        cfg = {"locked_d1_trend_pct_min": .05, "locked_h4_trend_pct_min": .02, "locked_atr_pct_price_min": .003}
        ok, vals = m.locked_filter_permitted(b, 100, cfg)
        self.assertTrue(ok)
        self.assertGreaterEqual(vals["d1_trend_pct"], .05)

    def test_stop_first_same_bar(self):
        bars = [m.Bar(0, datetime(2026,1,1,tzinfo=timezone.utc), 100, 111, 89, 100)]
        reason, _, price = m.simulate_exit(bars, 0, 100, 90, 110, 1)
        self.assertEqual(reason, "SL")
        self.assertEqual(price, 90)

    def test_metrics(self):
        rows = [
            {"entry_utc":"2025-01-01T00:00:00+00:00","r_stress_p90":1.0},
            {"entry_utc":"2025-02-01T00:00:00+00:00","r_stress_p90":-0.5},
        ]
        x = m.metrics(rows)
        self.assertAlmostEqual(x["profit_factor"], 2.0)
        self.assertAlmostEqual(x["net_R"], .5)

    def test_low_sample_kill(self):
        parity = {"pass": True}
        hold = {"trades": 2, "profit_factor": 2, "avg_R": .2, "max_drawdown_R": 1,
                "max_month_positive_contribution_share": .5, "max_year_positive_contribution_share": .5,
                "positive_month_count": 3}
        raw = dict(hold); raw["profit_factor"] = 1; raw["avg_R"] = 0
        cfg = {"min_holdout_trades":30,"min_holdout_profit_factor":1.1,"min_holdout_avg_R":0,
               "max_holdout_drawdown_R":8,"max_month_positive_share":.55,"max_year_positive_share":.7,
               "min_positive_months":3}
        decision, _ = m.evaluate_decision(parity, hold, raw, cfg)
        self.assertEqual(decision, "KILL_T1_COMMERCIAL_LOW_HOLDOUT_FREQUENCY_NO_WAIT")

    def test_parity_failure_blocks(self):
        decision, gates = m.evaluate_decision({"pass": False}, {}, {}, {})
        self.assertTrue(decision.startswith("INCONCLUSIVE_BLOCKED"))
        self.assertFalse(gates["parity"])

    def test_pass_decision(self):
        parity = {"pass": True}
        hold = {"trades": 35, "profit_factor": 1.3, "avg_R": .1, "max_drawdown_R": 4,
                "max_month_positive_contribution_share": .4, "max_year_positive_contribution_share": .6,
                "positive_month_count": 4}
        raw = dict(hold); raw["profit_factor"] = 1.0; raw["avg_R"] = 0
        cfg = {"min_holdout_trades":30,"min_holdout_profit_factor":1.1,"min_holdout_avg_R":0,
               "max_holdout_drawdown_R":8,"max_month_positive_share":.55,"max_year_positive_share":.7,
               "min_positive_months":3}
        decision, gates = m.evaluate_decision(parity, hold, raw, cfg)
        self.assertEqual(decision, "SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER")
        self.assertTrue(all(gates.values()))


if __name__ == "__main__":
    unittest.main()
