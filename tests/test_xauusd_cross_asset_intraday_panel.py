import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app/xauusd_cross_asset_intraday_panel.py"
spec = importlib.util.spec_from_file_location("panel", MODULE_PATH)
panel = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(panel)


class CrossAssetPanelTests(unittest.TestCase):
    def make_export(self, path: Path, symbol: str, tf: str, start: str, periods: int, freq: str):
        times_utc = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
        # January dates use UTC+2 AMarkets server time.
        server = (times_utc + pd.Timedelta(hours=2)).tz_localize(None)
        epoch = server.to_numpy(dtype="datetime64[s]").astype("int64")
        base = 100 + np.arange(periods) * 0.01
        frame = pd.DataFrame({
            "program": panel.PROGRAM,
            "symbol": symbol,
            "timeframe": tf,
            "time_server_epoch": epoch,
            "open": base,
            "high": base + 0.05,
            "low": base - 0.05,
            "close": base + 0.01,
            "tick_volume": 10,
            "spread": 2,
            "real_volume": 0,
            "source": "AMARKETS_MT5",
        })
        frame.to_csv(path, index=False)

    def make_macro(self, root: Path, start="2016-01-01", periods=100):
        report = root / "reports/xauusd_macro_causal_panel"
        report.mkdir(parents=True)
        dates = pd.date_range(start, periods=periods, freq="D", tz="UTC")
        cols = {
            "decision_date_utc": dates.strftime("%Y-%m-%d"),
            "usd_broad_chg_5d": 0.1,
            "usd_broad_chg_20d": 0.2,
            "real_yield_10y": 1.0,
            "real_yield_10y_chg_5d": 0.01,
            "real_yield_10y_chg_20d": 0.02,
            "nominal_yield_10y_chg_5d": 0.03,
            "breakeven_10y_chg_5d": 0.04,
            "vix_z252": 0.0,
            "gvz_z252": 0.0,
            "gvz_vix_ratio": 1.0,
            "cftc_mm_net_z_156w": 0.0,
            "etf_flow_tonnes_3m": 1.0,
            "wgc_official_sector_purchases_tonnes": 10.0,
            "official_event_blackout_active": 0,
            "official_event_blackout_count": 0,
            "official_events_next_24h_count": 0,
        }
        pd.DataFrame(cols).to_csv(report / "macro_causal_features.csv", index=False)

    def test_dst_conversion_standard(self):
        utc = pd.Timestamp("2024-01-15T10:00:00Z")
        server = pd.Series([int((utc + pd.Timedelta(hours=2)).timestamp())])
        got = panel.server_epoch_to_utc(server).iloc[0]
        self.assertEqual(got, utc)

    def test_dst_conversion_summer(self):
        utc = pd.Timestamp("2024-07-15T10:00:00Z")
        server = pd.Series([int((utc + pd.Timedelta(hours=3)).timestamp())])
        got = panel.server_epoch_to_utc(server).iloc[0]
        self.assertEqual(got, utc)

    def test_read_export_rejects_schema(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.csv"
            pd.DataFrame({"x": [1]}).to_csv(p, index=False)
            with self.assertRaises(panel.PanelError):
                panel.read_export(p, "XAUUSD", "H1")

    def test_exact_log_return_requires_exact_gap(self):
        times = pd.Series(pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T01:00Z", "2024-01-01T03:00Z"], utc=True))
        close = pd.Series([100.0, 101.0, 102.0])
        ret = panel.exact_log_return(close, times, 1, 3600)
        self.assertTrue(np.isfinite(ret.iloc[1]))
        self.assertTrue(np.isnan(ret.iloc[2]))

    def test_features_use_completed_bar_availability(self):
        frame = pd.DataFrame({
            "timestamp_utc": pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC"),
            "available_time_utc": pd.date_range("2024-01-01T01:00Z", periods=30, freq="h", tz="UTC"),
            "open": np.arange(30) + 100,
            "high": np.arange(30) + 101,
            "low": np.arange(30) + 99,
            "close": np.arange(30) + 100.5,
            "spread": 2,
        })
        out = panel.make_symbol_features(frame, "XAUUSD", "H1")
        self.assertEqual(out.iloc[0]["decision_time_utc"], pd.Timestamp("2024-01-01T01:00Z"))
        self.assertEqual(pd.Timestamp(out.iloc[0]["xauusd_h1_source_bar_open_utc"]), pd.Timestamp("2024-01-01T00:00Z"))

    def test_targets_exact_horizon(self):
        frame = pd.DataFrame({
            "timestamp_utc": pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC"),
            "open": np.arange(30) + 100.0,
            "close": np.arange(30) + 100.5,
        })
        out = panel.make_targets(frame)
        expected = (103.5 / 100.0 - 1) * 10000
        self.assertAlmostEqual(out.iloc[0]["forward_return_4h_bps"], expected)
        self.assertEqual(pd.Timestamp(out.iloc[0]["exit_time_4h_utc"]), pd.Timestamp("2024-01-01T04:00Z"))

    def test_targets_gap_fail_closed(self):
        times = list(pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC"))
        del times[3]
        frame = pd.DataFrame({"timestamp_utc": times, "open": 100.0, "close": 101.0})
        out = panel.make_targets(frame)
        self.assertTrue(np.isnan(out.iloc[0]["forward_return_4h_bps"]))

    def test_macro_loader_required_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_macro(root)
            got = panel.load_macro_features(root)
            self.assertIn("real_yield_10y", got.columns)

    def test_static_no_execution_tokens(self):
        root = MODULE_PATH.parents[1]
        self.assertEqual(panel.static_execution_violations(root), [])

    def test_collect_creates_manifested_zip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / panel.REPORT_REL
            report.mkdir(parents=True)
            names = [
                "cross_asset_panel_summary.json", "cross_asset_panel_quality.json",
                "cross_asset_panel_contract.json", "cross_asset_panel_decision.md",
                "cross_asset_source_manifest.csv", "cross_asset_intraday_features.csv",
                "cross_asset_intraday_targets.csv",
            ]
            for name in names:
                (report / name).write_text("{}" if name.endswith(".json") else "x\n")
            output = root / "result.zip"
            result = panel.collect(root, output=output)
            self.assertTrue(result["pass"])
            self.assertTrue(output.is_file())

    def test_preflight_requires_macro_panel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app").mkdir()
            (root / "mt5").mkdir()
            (root / "app/xauusd_cross_asset_intraday_panel.py").write_text("safe")
            (root / "mt5/XAUUSD_CrossAssetHistoryExport.mq5").write_text("safe")
            result = panel.preflight(root)
            self.assertFalse(result["pass"])

    def test_synthetic_build_writes_causal_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export = root / "exports"
            export.mkdir()
            self.make_macro(root, periods=500)
            for symbol in panel.ALL_SYMBOLS:
                self.make_export(
                    panel.expected_export_path(export, symbol, "H1"),
                    symbol, "H1", "2016-01-01", 240, "h"
                )
                self.make_export(
                    panel.expected_export_path(export, symbol, "M15"),
                    symbol, "M15", "2016-01-01", 960, "15min"
                )
            report = root / "out"
            summary = panel.build(root, export_dir=export, report_dir=report)
            self.assertEqual(summary["decision"], "CROSS_ASSET_INTRADAY_PANEL_FAIL_CLOSED")
            self.assertTrue((report / "cross_asset_intraday_features.csv").is_file())
            features = pd.read_csv(report / "cross_asset_intraday_features.csv")
            quality = json.loads((report / "cross_asset_panel_quality.json").read_text())
            self.assertEqual(sum(quality["availability_leakage_counts"].values()), 0)
            self.assertNotIn("entry_open", features.columns)
            self.assertIn("real_yield_10y", features.columns)

    def test_safe_symbol_filename(self):
        self.assertEqual(panel.safe_symbol_name("S&P500"), "sandp500")

    def test_mql_resolves_symbol_specific_history_start(self):
        mql = (MODULE_PATH.parents[1] / "mt5/XAUUSD_CrossAssetHistoryExport.mq5").read_text()
        self.assertIn("SERIES_FIRSTDATE", mql)
        self.assertIn("SERIES_SERVER_FIRSTDATE", mql)
        self.assertIn("ResolveEffectiveHistoryStart", mql)
        self.assertIn("INFO_EXPORT_EFFECTIVE_START", mql)

    def test_mql_defaults_to_wti_dxy_repair_only(self):
        mql = (MODULE_PATH.parents[1] / "mt5/XAUUSD_CrossAssetHistoryExport.mq5").read_text()
        self.assertIn("InpRepairOnlyLateHistorySymbols = true", mql)
        self.assertIn("WTI_DXY_REPAIR_ONLY", mql)
        self.assertIn("expected=ArraySize(symbols)*ArraySize(timeframes)", mql)


if __name__ == "__main__":
    unittest.main()
