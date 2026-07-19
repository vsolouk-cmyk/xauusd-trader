import argparse
import importlib.util
import json
import math
import sys
import tempfile
import unittest
import re
import urllib.parse
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app/stage176_central_bank_allocation_falsification.py"
spec = importlib.util.spec_from_file_location("stage176_test_module", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def synthetic_manifest(root: Path, quarters: int = 60, original: bool = True) -> Path:
    snapshot = root / "wgc_snapshot.html"
    snapshot.write_text("original WGC quarterly report snapshots for test", encoding="utf-8")
    digest = m.sha256(snapshot)
    rows = []
    dates = pd.date_range("2010-03-31", periods=quarters, freq="QE", tz="UTC")
    for i, qend in enumerate(dates):
        q = m.quarter_label(qend)
        rows.append({
            "quarter": q,
            "quarter_end_utc": qend.isoformat(),
            "release_timestamp_utc": (qend + pd.Timedelta(days=35)).isoformat(),
            "official_sector_purchases_tonnes": 70 + 35 * math.sin(i / 3.0),
            "source_url": f"https://www.gold.org/test/{q}",
            "source_file": str(snapshot),
            "source_sha256": digest,
            "source_kind": "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_REPORT_PAGE",
            "extraction_method": "TEST_LOCKED",
            "extraction_confidence": 0.99,
            "is_original_publication": original,
            "notes": "synthetic",
        })
    path = root / "vintages.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def synthetic_gold(root: Path, start="2009-01-01", end="2026-12-31") -> Path:
    dates = pd.bdate_range(start, end, tz="UTC")
    x = np.arange(len(dates), dtype=float)
    close = 900.0 * np.exp(0.00035 * x + 0.05 * np.sin(x / 130.0))
    path = root / "gold_daily.csv"
    pd.DataFrame({"date": dates, "close": close}).to_csv(path, index=False)
    return path


class Stage176Tests(unittest.TestCase):
    def test_locked_contract_rejects_mutation(self):
        cfg = {"locked_contract": dict(m.LOCKED_CONTRACT)}
        self.assertTrue(m.contract_assertion(cfg)["pass"])
        cfg["locked_contract"]["trend_sma_trading_days"] = 199
        result = m.contract_assertion(cfg)
        self.assertFalse(result["pass"])
        self.assertEqual(result["differences"][0]["key"], "trend_sma_trading_days")

    def test_report_parser_extracts_quarter_date_and_value(self):
        raw = '''
        <html><head><title>Gold Demand Trends Q3 2022 - Central Banks</title>
        <script type="application/ld+json">{"datePublished":"2022-11-01T08:00:00Z"}</script>
        </head><body><p>Central bank demand totalled 399.3t in Q3.</p></body></html>
        '''
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "q3.html"
            snap.write_text(raw)
            row, candidates = m.extract_report_vintage(
                "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2022/central-banks",
                raw,
                snap,
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["quarter"], "2022Q3")
            self.assertAlmostEqual(row["official_sector_purchases_tonnes"], 399.3)
            self.assertGreaterEqual(candidates[0]["confidence"], 0.85)

    def test_parser_penalizes_annual_value_and_selects_quarter(self):
        text = (
            "For the full year central bank demand totalled 1080t. "
            "In Q4 central banks bought 333t on a net basis."
        )
        selected = m.choose_purchase_candidate(m.extract_purchase_candidates(text))
        self.assertEqual(selected["status"], "PASS")
        self.assertAlmostEqual(selected["best"]["value_tonnes"], 333.0)

    def test_vintage_contract_passes_original_traceable_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = synthetic_manifest(root)
            frame = m.load_vintage_manifest(path)
            status, valid, audit = m.validate_vintage_manifest(frame, root)
            self.assertEqual(status["status"], "PASS")
            self.assertEqual(len(valid), 60)
            self.assertEqual(status["earliest_quarter"], "2010Q1")
            self.assertEqual(len(audit), 60)

    def test_vintage_contract_rejects_revised_latest_series(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = synthetic_manifest(root, original=False)
            frame = m.load_vintage_manifest(path)
            status, valid, _ = m.validate_vintage_manifest(frame, root)
            self.assertEqual(status["status"], "FAIL")
            self.assertEqual(len(valid), 0)

    def test_gold_daily_and_mt5_split_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            daily_path = synthetic_gold(root)
            daily, meta = m.load_gold_prices(daily_path)
            self.assertGreater(len(daily), 4000)
            self.assertGreater(daily["sma200"].notna().sum(), 3000)

            mt5 = root / "mt5.csv"
            dates = pd.date_range("2025-01-01", periods=48, freq="h", tz="UTC")
            pd.DataFrame({
                "<DATE>": dates.strftime("%Y.%m.%d"),
                "<TIME>": dates.strftime("%H:%M:%S"),
                "<OPEN>": 2000.0,
                "<HIGH>": 2001.0,
                "<LOW>": 1999.0,
                "<CLOSE>": np.arange(48) * 0.1 + 2000,
            }).to_csv(mt5, sep="\t", index=False)
            mt5_daily, mt5_meta = m.load_gold_prices(mt5)
            self.assertEqual(len(mt5_daily), 2)
            self.assertEqual(mt5_meta["value_column"], "<CLOSE>")

    def test_decision_panel_uses_only_price_available_before_release(self):
        vintages = pd.DataFrame({
            "quarter": [f"201{i}Q{q}" for i in range(0, 4) for q in range(1, 5)][:12],
            "quarter_end_utc": pd.date_range("2010-03-31", periods=12, freq="QE", tz="UTC"),
            "release_timestamp_utc": pd.date_range("2010-05-01", periods=12, freq="QE", tz="UTC"),
            "official_sector_purchases_tonnes": np.linspace(10, 120, 12),
        })
        dates = pd.bdate_range("2009-01-01", "2014-12-31", tz="UTC")
        prices = pd.DataFrame({"date": dates, "close": np.linspace(800, 1600, len(dates))})
        prices["sma200"] = prices["close"].rolling(200, min_periods=200).mean()
        panel = m.build_decision_panel(vintages, prices)
        self.assertTrue((pd.to_datetime(panel["price_observation_date"], utc=True) <= pd.to_datetime(panel["release_timestamp_utc"], utc=True).dt.floor("D")).all())
        self.assertTrue((pd.to_datetime(panel["tradable_date"], utc=True) > pd.to_datetime(panel["release_timestamp_utc"], utc=True).dt.floor("D")).all())

    def test_state_persists_and_two_declines_exit(self):
        qends = pd.date_range("2010-03-31", periods=16, freq="QE", tz="UTC")
        # Establish high accumulation, then force two consecutive declines.
        purchases = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 115, 100, 80, 70]
        vintages = pd.DataFrame({
            "quarter": [m.quarter_label(x) for x in qends],
            "quarter_end_utc": qends,
            "release_timestamp_utc": qends + pd.Timedelta(days=35),
            "official_sector_purchases_tonnes": purchases,
        })
        dates = pd.bdate_range("2009-01-01", "2015-12-31", tz="UTC")
        prices = pd.DataFrame({"date": dates, "close": np.linspace(800, 1800, len(dates))})
        prices["sma200"] = prices["close"].rolling(200, min_periods=200).mean()
        panel = m.build_decision_panel(vintages, prices)
        self.assertIn("HIGH", set(panel["candidate_state"]))
        decline_rows = panel[panel["exit_two_quarter_decline"]]
        self.assertFalse(decline_rows.empty)
        self.assertTrue((decline_rows["candidate_state"] == "LOW").all())

    def test_nonoverlapping_two_quarter_cohorts(self):
        intervals = pd.DataFrame({
            "candidate_state": ["HIGH", "HIGH", "LOW", "LOW"] * 6,
            "gold_gross_return": [0.05, 0.03, -0.02, -0.01] * 6,
        })
        oneq, twoq = m.regime_horizon_tests(intervals)
        self.assertEqual(oneq["status"], "PASS")
        self.assertTrue(oneq["mean_difference"] > 0)
        self.assertEqual(len(twoq["cohorts"]), 2)

    def test_decision_paths(self):
        vintage = {"status": "PASS"}
        price = {"status": "PASS"}
        episode = {
            "high_episode_count": 6,
            "calendar_era_count": 3,
            "maximum_single_episode_positive_excess_share": 0.4,
        }
        dev = {"candidate": {}}
        hold_metrics = {
            "candidate": {"cumulative_return": 0.30, "max_drawdown": 0.10, "calmar": 1.5},
            "price_200d": {"cumulative_return": 0.20, "max_drawdown": 0.15, "calmar": 1.0},
            "buy_hold": {"cumulative_return": 0.32, "max_drawdown": 0.20, "calmar": 0.9},
        }
        hold = pd.DataFrame({"candidate_state": ["HIGH", "LOW"] * 5})
        loo = {"median_excess": 0.05}
        oneq = {"status": "PASS", "high_n": 10, "low_n": 10, "mean_difference": 0.03, "one_sided_permutation_pvalue": 0.05}
        twoq = {"all_cohort_effect_signs_positive": True, "cohorts": []}
        decision, gates, _ = m.evaluate_decision(vintage, price, episode, dev, hold_metrics, hold, loo, oneq, twoq)
        self.assertEqual(decision, "ALLOCATION_SHADOW_CANDIDATE")
        self.assertTrue(all(g["pass"] for g in gates))

        bad_hold = {k: dict(v) for k, v in hold_metrics.items()}
        bad_hold["candidate"]["cumulative_return"] = -0.1
        decision2, _, _ = m.evaluate_decision(vintage, price, episode, dev, bad_hold, hold, loo, oneq, twoq)
        self.assertEqual(decision2, "KILL_NO_INCREMENTAL_ALLOCATION_VALUE")

    def test_progress_reporter_writes_terminal_checkpoint_files(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "reports"
            reporter = m.ProgressReporter(out, enabled=True)
            reporter.emit("TEST_PHASE", "working", current=2, total=5)
            payload = json.loads((out / "stage176_progress.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["phase"], "TEST_PHASE")
            self.assertEqual(payload["current"], 2)
            self.assertEqual(payload["total"], 5)
            self.assertAlmostEqual(payload["percent"], 40.0)
            self.assertIn("TEST_PHASE", (out / "stage176_progress.log").read_text(encoding="utf-8"))

    def test_index_failure_circuit_breaker_stops_redundant_requests(self):
        original = m.fetch_url
        calls = []
        try:
            def always_fail(url, config, progress=None, **kwargs):
                calls.append(url)
                return False, b"", "timeout"
            m.fetch_url = always_fail
            cfg = {
                "index_url_template": "https://www.gold.org/test?page={page}",
                "max_index_pages": 16,
                "max_consecutive_index_failures": 3,
                "request_delay_seconds": 0,
            }
            urls, ledger = m.discover_report_urls(cfg)
            self.assertEqual(urls, [])
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(ledger), 3)
        finally:
            m.fetch_url = original

    def test_cached_collection_emits_progress_and_checkpoints(self):
        raw = (
            '<html><head><title>Gold Demand Trends Q3 2022</title>'
            '<script type="application/ld+json">'
            '{"datePublished":"2022-11-01T08:00:00Z"}'
            '</script></head><body>'
            'Central bank demand totalled 399.3t in Q3.'
            '</body></html>' + (' ' * 600)
        )
        original = m.discover_report_urls
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                out = root / "reports"
                cache = root / "cache"
                cache.mkdir()
                url = "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2022"
                qlabel = "2022Q3"
                safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{qlabel}_{urllib.parse.urlparse(url).path.strip('/')}")[-180:]
                (cache / f"{safe}.html").write_text(raw, encoding="utf-8")
                m.discover_report_urls = lambda config, progress=None, checkpoint_path=None: ([url], [])
                reporter = m.ProgressReporter(out, enabled=True)
                result = m.collect_wgc_vintages(root, {
                    "cache_dir": str(cache),
                    "maximum_reports": 1,
                    "canonical_manifest_output": "manifest.csv",
                    "checkpoint_every_reports": 1,
                    "max_consecutive_report_failures": 2,
                    "request_delay_seconds": 0,
                }, out, reporter)
                self.assertEqual(result["valid_quarter_rows"], 1)
                self.assertTrue((out / "stage176_wgc_online_fetch_ledger.csv").exists())
                self.assertTrue((out / "stage176_wgc_extraction_candidates.csv").exists())
                self.assertTrue((out / "stage176_progress.json").exists())
        finally:
            m.discover_report_urls = original

    def test_end_to_end_synthetic_creates_terminal_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app").mkdir()
            (root / "configs").mkdir()
            manifest = synthetic_manifest(root, quarters=60)
            gold = synthetic_gold(root)
            cfg = {
                "output_dir": "reports/stage176",
                "locked_contract": dict(m.LOCKED_CONTRACT),
                "wgc_vintages": {
                    "manifest_candidates": [str(manifest)],
                    "online_collection": {
                        "enabled": False,
                        "index_url_template": "https://invalid?page={page}",
                        "max_index_pages": 0,
                        "maximum_reports": 0,
                        "cache_dir": "cache",
                        "canonical_manifest_output": "canonical.csv",
                    },
                },
                "gold_prices": {"candidates": [str(gold)], "globs": [], "maximum_candidates": 10},
            }
            args = argparse.Namespace(vintage_manifest="", online=False)
            summary = m.run(root, cfg, args)
            self.assertIn(summary["program_decision"], {
                "ALLOCATION_SHADOW_CANDIDATE",
                "KILL_NO_INCREMENTAL_ALLOCATION_VALUE",
                "INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE",
            })
            out = root / "reports/stage176"
            self.assertTrue((out / "stage176_summary.json").exists())
            self.assertTrue((out / "stage176_decision.md").exists())
            self.assertTrue((out / "stage176_decision_panel.csv").exists())
            self.assertTrue((out / "stage176_gate_checks.csv").exists())


if __name__ == "__main__":
    unittest.main()
