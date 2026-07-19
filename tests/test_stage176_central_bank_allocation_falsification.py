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


    def test_fetch_url_does_not_retry_permanent_404(self):
        original_urlopen = m.urllib.request.urlopen
        original_sleep = m.time.sleep
        calls = []
        sleeps = []
        try:
            def raise_404(req, timeout=None, context=None):
                calls.append(req.full_url)
                raise m.urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs=None, fp=None)
            m.urllib.request.urlopen = raise_404
            m.time.sleep = lambda seconds: sleeps.append(seconds)
            ok, content, error = m.fetch_url(
                "https://www.gold.org/missing",
                {"max_retries": 3, "timeout_seconds": 35, "retry_backoff_seconds": 4},
            )
            self.assertFalse(ok)
            self.assertEqual(content, b"")
            self.assertIn("404", error)
            self.assertEqual(len(calls), 1)
            self.assertEqual(sleeps, [])
        finally:
            m.urllib.request.urlopen = original_urlopen
            m.time.sleep = original_sleep

    def test_report_discovery_excludes_pre_2010_quarters(self):
        original_fetch = m.fetch_url
        html = ("<html><body>"
                "<a href='/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2007'>old</a>"
                "<a href='/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2010'>start</a>"
                "<a href='/goldhub/research/gold-demand-trends/gold-demand-trends-q4-2025'>new</a>"
                "</body></html>").encode("utf-8")
        calls = []
        try:
            def fake_fetch(url, config, progress=None, **kwargs):
                calls.append(url)
                return True, html, ""
            m.fetch_url = fake_fetch
            cfg = {
                "index_url_template": "https://www.gold.org/test?page={page}",
                "max_index_pages": 3,
                "max_consecutive_index_failures": 3,
                "request_delay_seconds": 0,
            }
            urls, _ = m.discover_report_urls(cfg)
            self.assertEqual(len(calls), 3)
            self.assertFalse(any("2007" in url for url in urls))
            self.assertTrue(any("q1-2010" in url for url in urls))
            self.assertTrue(any("q4-2025" in url for url in urls))
        finally:
            m.fetch_url = original_fetch




    def test_section_recovery_prefers_quarter_value_over_ytd(self):
        root_html = """
        <html><head><title>Gold Demand Trends Q3 2016</title></head><body>
        <p>8 November, 2016</p>
        <a href="/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2016/12858">Central banks and other institutions</a>
        <p>Year-to-date central banks purchased 271.1t.</p>
        </body></html>
        """ + (" " * 600)
        section_html = """
        <html><head><title>Gold Demand Trends Q3 2016 - Central banks</title></head><body>
        <p>8 November, 2016</p>
        <p>In Q3 2016 central bank net purchases fell to 81.7t.</p>
        <p>Year-to-date central banks purchased 271.1t.</p>
        </body></html>
        """ + (" " * 600)
        original_fetch = m.fetch_url
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                m.fetch_url = lambda url, config, progress=None, **kwargs: (True, section_html.encode("utf-8"), "")
                row, candidates, ledger = m.recover_vintage_from_sections(
                    "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2016",
                    root_html,
                    {"timeout_seconds": 5},
                    root,
                )
                self.assertIsNotNone(row)
                self.assertAlmostEqual(row["official_sector_purchases_tonnes"], 81.7)
                self.assertEqual(row["source_kind"], "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_CENTRAL_BANK_SECTION")
                self.assertTrue(candidates)
                self.assertTrue(ledger[0]["success"])
        finally:
            m.fetch_url = original_fetch

    def test_pdf_layout_alignment_selects_report_quarter_column(self):
        original = m.extract_pdf_text
        try:
            m.extract_pdf_text = lambda path: (
                "                              Q1'09        Q1'10       YoY\n"
                "Official sector net purchases   10.0         22.7       127%\n"
            )
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "report.pdf"
                path.write_bytes(b"fake")
                selected = m.choose_purchase_candidate(m.extract_pdf_purchase_candidates(path, "2010Q1"))
                self.assertEqual(selected["status"], "PASS")
                self.assertAlmostEqual(selected["best"]["value_tonnes"], 22.7)
                self.assertEqual(selected["best"]["method"], "WGC_ATTACHMENT_PDF_ALIGNED_TABLE")
        finally:
            m.extract_pdf_text = original

    def test_quarter_specific_text_beats_ytd_summary(self):
        text = (
            "In Q3 2016 central bank net purchases fell 56% year-on-year to 81.7t. "
            "Year-to-date, central banks purchased 271.1t."
        )
        selected = m.choose_purchase_candidate(m.extract_purchase_candidates(text, "2016Q3"))
        self.assertEqual(selected["status"], "PASS")
        self.assertAlmostEqual(selected["best"]["value_tonnes"], 81.7)

    def test_central_bank_section_link_discovery(self):
        raw = """
        <html><body>
        <a href="/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2016/12858">Central banks and other institutions</a>
        <a href="/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2016/jewellery">Jewellery</a>
        </body></html>
        """
        links = m.extract_central_bank_section_links(
            raw,
            "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2016",
        )
        self.assertEqual(len(links), 1)
        self.assertTrue(links[0].endswith("/12858"))

    def test_report_discovery_excludes_regional_duplicates(self):
        original_fetch = m.fetch_url
        html = ("<html><body>"
                "<a href='/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2025'>global</a>"
                "<a href='/ja/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2025'>jp</a>"
                "<a href='/goldhub/research/gold-demand-trends/us-gold-demand-trends-q1-2025'>us</a>"
                "<a href='/goldhub/research/gold-demand-trends/gold-demand-trends-india-focus-q1-2025'>india</a>"
                "</body></html>").encode("utf-8")
        try:
            m.fetch_url = lambda url, config, progress=None, **kwargs: (True, html, "")
            urls, _ = m.discover_report_urls({
                "index_url_template": "https://www.gold.org/test?page={page}",
                "max_index_pages": 3,
                "max_consecutive_index_failures": 3,
                "request_delay_seconds": 0,
            })
            self.assertEqual(urls, ["https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2025"])
        finally:
            m.fetch_url = original_fetch

    def test_visible_publication_date_fallback(self):
        raw = """
        <html><head><title>Gold Demand Trends Q1 2022</title></head>
        <body><h1>Gold Demand Trends Q1 2022</h1><p>28 April, 2022</p>
        <p>Central banks added 84t to global official reserves.</p></body></html>
        """
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "q1.html"
            snap.write_text(raw, encoding="utf-8")
            row, _ = m.extract_report_vintage(
                "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2022",
                raw,
                snap,
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["release_timestamp_utc"], "2022-04-28T12:00:00+00:00")
            self.assertAlmostEqual(row["official_sector_purchases_tonnes"], 84.0)

    def test_excel_attachment_table_extracts_exact_quarter(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "gdt.xlsx"
            frame = pd.DataFrame([
                ["Sector", "Q4 2021", "Q1 2022", "Full year 2022"],
                ["Central banks and other institutions", 48.0, 84.0, 1136.0],
            ])
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame.to_excel(writer, index=False, header=False, sheet_name="Supply and demand")
            candidates = m.extract_excel_purchase_candidates(path, "2022Q1")
            selected = m.choose_purchase_candidate(candidates)
            self.assertEqual(selected["status"], "PASS")
            self.assertAlmostEqual(selected["best"]["value_tonnes"], 84.0)

    def test_attachment_recovery_uses_original_xlsx_and_visible_date(self):
        raw = """
        <html><head><title>Gold Demand Trends Q1 2016</title></head>
        <body><h1>Gold Demand Trends Q1 2016</h1><p>11 May, 2016</p>
        <a href="https://www.gold.org/download/file/10270/GDT_Q1_16_tables.xlsx">Statistics XLSX</a>
        </body></html>
        """ + (" " * 600)
        original_fetch = m.fetch_url
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                workbook = root / "source.xlsx"
                pd.DataFrame([
                    ["Sector", "Q4 2015", "Q1 2016"],
                    ["Central banks and other institutions", 45.0, 109.4],
                ]).to_excel(workbook, index=False, header=False)
                payload = workbook.read_bytes()
                def fake_fetch(url, config, progress=None, **kwargs):
                    return True, payload, ""
                m.fetch_url = fake_fetch
                snap = root / "report.html"
                snap.write_text(raw, encoding="utf-8")
                row, candidates, ledger = m.recover_vintage_from_attachments(
                    "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2016",
                    raw,
                    snap,
                    {"maximum_attachments_per_report": 5},
                    root / "attachments",
                )
                self.assertIsNotNone(row)
                self.assertAlmostEqual(row["official_sector_purchases_tonnes"], 109.4)
                self.assertEqual(row["source_kind"], "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_ATTACHMENT")
                self.assertTrue(candidates)
                self.assertTrue(ledger[0]["success"])
        finally:
            m.fetch_url = original_fetch


    def test_invalid_existing_manifest_is_rebuilt_online(self):
        original_collect = m.collect_wgc_vintages
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                invalid_tmp = synthetic_manifest(root, quarters=10)
                invalid = root / "invalid.csv"
                invalid_tmp.replace(invalid)
                valid_tmp = synthetic_manifest(root, quarters=60)
                valid = root / "valid.csv"
                valid_tmp.replace(valid)
                gold = synthetic_gold(root)

                def fake_collect(root_arg, config_arg, out_dir, progress=None):
                    Path(config_arg["canonical_manifest_output"]).write_bytes(valid.read_bytes())
                    return {"status": "COLLECTED", "valid_quarter_rows": 60}

                m.collect_wgc_vintages = fake_collect
                cfg = {
                    "output_dir": "reports/stage176",
                    "locked_contract": dict(m.LOCKED_CONTRACT),
                    "wgc_vintages": {
                        "manifest_candidates": [str(invalid)],
                        "online_collection": {
                            "enabled": True,
                            "index_url_template": "https://invalid?page={page}",
                            "max_index_pages": 0,
                            "maximum_reports": 0,
                            "cache_dir": "cache",
                            "canonical_manifest_output": str(invalid),
                        },
                    },
                    "gold_prices": {"candidates": [str(gold)], "globs": [], "maximum_candidates": 10},
                }
                args = argparse.Namespace(vintage_manifest="", online=False, no_progress=True)
                summary = m.run(root, cfg, args)
                self.assertEqual(summary["wgc_vintage_preflight"]["status"], "PASS")
                self.assertNotEqual(summary["program_decision"], "KILL_ASOF_DATA_CONTRACT_UNAVAILABLE")
        finally:
            m.collect_wgc_vintages = original_collect

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


class Stage176AttachmentForbiddenRegression(unittest.TestCase):
    def test_fetch_url_treats_attachment_403_as_permanent_when_requested(self):
        original_urlopen = m.urllib.request.urlopen
        original_sleep = m.time.sleep
        calls = []
        sleeps = []
        try:
            def raise_403(req, timeout=None, context=None):
                calls.append(req.full_url)
                raise m.urllib.error.HTTPError(req.full_url, 403, "Forbidden", hdrs=None, fp=None)
            m.urllib.request.urlopen = raise_403
            m.time.sleep = lambda seconds: sleeps.append(seconds)
            ok, content, error = m.fetch_url(
                "https://www.gold.org/download/file/test.pdf",
                {"max_retries": 3, "timeout_seconds": 35, "retry_backoff_seconds": 4},
                permanent_http_statuses={403},
            )
            self.assertFalse(ok)
            self.assertEqual(content, b"")
            self.assertIn("403", error)
            self.assertEqual(len(calls), 1)
            self.assertEqual(sleeps, [])
        finally:
            m.urllib.request.urlopen = original_urlopen
            m.time.sleep = original_sleep

    def test_attachment_403_circuit_breaker_disables_uncached_downloads(self):
        raw = """
        <html><head><title>Gold Demand Trends Q1 2016</title></head>
        <body><p>11 May, 2016</p>
        <a href="https://www.gold.org/download/file/1/a.pdf">A</a>
        <a href="https://www.gold.org/download/file/2/b.pdf">B</a>
        <a href="https://www.gold.org/download/file/3/c.pdf">C</a>
        </body></html>
        """ + (" " * 600)
        original_fetch = m.fetch_url
        original_curl = m.fetch_attachment_with_curl
        fetch_calls = []
        curl_calls = []
        try:
            def fake_fetch(url, config, progress=None, **kwargs):
                fetch_calls.append(url)
                return False, b"", "HTTPError:HTTP Error 403: Forbidden"
            def fake_curl(*args, **kwargs):
                curl_calls.append(args[0])
                return False, b"", "should-not-run"
            m.fetch_url = fake_fetch
            m.fetch_attachment_with_curl = fake_curl
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                snap = root / "report.html"
                snap.write_text(raw, encoding="utf-8")
                cfg = {"maximum_attachments_per_report": 5, "attachment_forbidden_circuit_breaker": 2}
                row, candidates, ledger = m.recover_vintage_from_attachments(
                    "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2016",
                    raw,
                    snap,
                    cfg,
                    root / "attachments",
                )
                self.assertIsNone(row)
                self.assertEqual(candidates, [])
                self.assertEqual(len(fetch_calls), 2)
                self.assertEqual(curl_calls, [])
                self.assertTrue(cfg["_runtime_attachment_fetch_state"]["disabled"])
                self.assertEqual(sum(1 for r in ledger if r["kind"] == "ATTACHMENT_SKIPPED"), 1)
        finally:
            m.fetch_url = original_fetch
            m.fetch_attachment_with_curl = original_curl


if __name__ == "__main__":
    unittest.main()
