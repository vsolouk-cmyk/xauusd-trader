import csv
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE_PATH = ROOT / "app" / "stage175_h64l_closeout_and_t1_locked_holdout_refresh.py"
spec0 = importlib.util.spec_from_file_location("stage175_for_tests", BASE_PATH)
base = importlib.util.module_from_spec(spec0)
sys.modules[spec0.name] = base
spec0.loader.exec_module(base)

MODULE_PATH = ROOT / "app" / "stage175b_dual_source_parity_repair.py"
spec = importlib.util.spec_from_file_location("stage175b", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class Stage175BTests(unittest.TestCase):
    def test_mt5_split_schema_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h1.csv"
            p.write_text(
                "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n"
                "2026.01.02\t03:00:00\t2000\t2002\t1999\t2001\n",
                encoding="utf-8",
            )
            bars = base.load_h1_csv(p)
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].close, 2001.0)

    def test_archived_sqlite_bar_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.sqlite"
            conn = sqlite3.connect(p)
            conn.execute(
                "create table bars(utc_time text, open real, high real, low real, close real, "
                "source text, symbol text, timeframe text)"
            )
            conn.execute(
                "insert into bars values(?,?,?,?,?,?,?,?)",
                ("2026-01-02T03:00:00Z", 2000, 2002, 1999, 2001, "amarkets_mt5", "XAUUSD", "1h"),
            )
            conn.commit(); conn.close()
            bars = m.load_h1_db(p, "amarkets_mt5", "XAUUSD", "1h")
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].utc_time.hour, 3)
            self.assertEqual(bars[0].close, 2001)

    def test_alignment_finds_integer_shift(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        archived = [
            base.Bar(i, start + timedelta(hours=i), 100+i, 101+i, 99+i, 100.5+i)
            for i in range(20)
        ]
        # Current file is two hours ahead; applying -2 aligns it.
        current = [
            base.Bar(i, b.utc_time + timedelta(hours=2), b.open, b.high, b.low, b.close)
            for i, b in enumerate(archived)
        ]
        scores = m.alignment_scores(current, archived, [-3,-2,-1,0,1], 0.001)
        resolved = m.resolve_alignment(scores, 10, .99, .2)
        self.assertTrue(resolved["pass"])
        self.assertEqual(resolved["resolved_shift_hours"], -2)

    def test_alignment_fails_low_match(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        archived = [
            base.Bar(i, start + timedelta(hours=i), 100, 101, 99, 100)
            for i in range(20)
        ]
        current = [
            base.Bar(i, start + timedelta(hours=i), 200, 201, 199, 200)
            for i in range(20)
        ]
        scores = m.alignment_scores(current, archived, [-1,0,1], 0.001)
        resolved = m.resolve_alignment(scores, 10, .98, .02)
        self.assertFalse(resolved["pass"])
        self.assertFalse(resolved["checks"]["min_match_share"])

    def test_alignment_fails_ambiguous_tie(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Constant OHLC makes adjacent shifts equally plausible.
        archived = [
            base.Bar(i, start + timedelta(hours=i), 100, 101, 99, 100)
            for i in range(20)
        ]
        current = [
            base.Bar(i, start + timedelta(hours=i), 100, 101, 99, 100)
            for i in range(20)
        ]
        scores = m.alignment_scores(current, archived, [-1,0,1], 0.001)
        resolved = m.resolve_alignment(scores, 10, .98, .02)
        self.assertFalse(resolved["pass"])
        self.assertFalse(resolved["checks"]["unique_lead"])

    def test_trade_set_comparison(self):
        generated = [
            {"signal_utc":"2025-01-01T00:00:00+00:00","r_stress_p90":1.0},
            {"signal_utc":"2025-01-02T00:00:00+00:00","r_stress_p90":-0.5},
        ]
        archived = [dict(r) for r in generated]
        metrics, diff = m.compare_trade_sets(generated, archived)
        self.assertEqual(metrics["jaccard"], 1.0)
        self.assertEqual(metrics["max_common_abs_r_difference"], 0.0)
        self.assertEqual(len(diff), 2)

    def test_ledger_parity_threshold(self):
        metrics = {
            "jaccard": .99,
            "missing_from_generated": 1,
            "extra_in_generated": 0,
            "max_common_abs_r_difference": 1e-8,
        }
        cfg = {
            "min_trade_jaccard": .98,
            "max_missing_trades": 1,
            "max_extra_trades": 1,
            "max_common_abs_r_difference": 1e-6,
        }
        self.assertTrue(m.ledger_parity_pass(metrics, cfg))

    def test_macro_permitted(self):
        b = base.Bar(0, datetime.now(timezone.utc), 1, 2, 0, 1)
        b.macro_regime = "neutral"
        b.macro_score_long_gold = 0
        b.d_real_yield_20d = 0.1
        b.d_usd_20d_pct = -0.1
        self.assertTrue(base.macro_permitted(b)[0])
        b.macro_regime = "hostile"
        self.assertFalse(base.macro_permitted(b)[0])

    def test_locked_filter(self):
        b = base.Bar(0, datetime.now(timezone.utc), 100, 101, 99, 100)
        b.d1_close, b.d1_ma50 = 106, 100
        b.h4_close, b.h4_ma50 = 103, 100
        b.atr_h1_14 = 0.4
        cfg = {
            "locked_d1_trend_pct_min": .05,
            "locked_h4_trend_pct_min": .02,
            "locked_atr_pct_price_min": .003,
        }
        ok, vals = base.locked_filter_permitted(b, 100, cfg)
        self.assertTrue(ok)
        self.assertGreaterEqual(vals["d1_trend_pct"], .05)

    def test_stop_first_same_bar(self):
        bars = [base.Bar(0, datetime(2026,1,1,tzinfo=timezone.utc), 100, 111, 89, 100)]
        reason, _, price = base.simulate_exit(bars, 0, 100, 90, 110, 1)
        self.assertEqual(reason, "SL")
        self.assertEqual(price, 90)

    def test_metrics(self):
        rows = [
            {"entry_utc":"2025-01-01T00:00:00+00:00","r_stress_p90":1.0},
            {"entry_utc":"2025-02-01T00:00:00+00:00","r_stress_p90":-0.5},
        ]
        x = base.metrics(rows)
        self.assertAlmostEqual(x["profit_factor"], 2.0)
        self.assertAlmostEqual(x["net_R"], .5)

    def test_parity_failure_blocks(self):
        decision, gates = base.evaluate_decision({"pass": False}, {}, {}, {})
        self.assertTrue(decision.startswith("INCONCLUSIVE_BLOCKED"))
        self.assertFalse(gates["parity"])

    def test_concentration_kills_even_when_pf_is_high(self):
        parity = {"pass": True}
        hold = {
            "trades": 30,
            "profit_factor": 2.2,
            "avg_R": .4,
            "max_drawdown_R": 6,
            "max_month_positive_contribution_share": 1.0,
            "max_year_positive_contribution_share": 1.0,
            "positive_month_count": 1,
        }
        raw = dict(hold)
        raw["profit_factor"] = 1.5
        raw["avg_R"] = .25
        cfg = {
            "min_holdout_trades":30,
            "min_holdout_profit_factor":1.1,
            "min_holdout_avg_R":0,
            "max_holdout_drawdown_R":8,
            "max_month_positive_share":.55,
            "max_year_positive_share":.7,
            "min_positive_months":3,
        }
        decision, gates = base.evaluate_decision(parity, hold, raw, cfg)
        self.assertEqual(decision, "KILL_T1_LOCKED_HOLDOUT_FAILURE_NO_ML")
        self.assertFalse(gates["month_concentration"])
        self.assertFalse(gates["year_concentration"])
        self.assertFalse(gates["positive_months"])


if __name__ == "__main__":
    unittest.main()
