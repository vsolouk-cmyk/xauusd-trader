from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.precious_metals_final_rv import (
    REGIME_FAIL,
    REF_FAIL,
    build_common_daily,
    deterministic_cluster_mask,
    eu_dst_utc,
    formation_at,
    load_mt5_h1,
    ols_y_on_x,
    preflight,
    residual_ar1_diagnostics,
    run_clustered_regime_calibration,
    server_epoch_to_utc,
    simulate_pair_trades,
    synchronize_h1,
    _pair_weights,
    static_execution_violations,
    validate_reference_history,
    CampaignError,
)


BASE_CFG = {
    "time_contract": {"standard_shift_minutes": -120, "dst_shift_minutes": -180},
    "data_contract": {"minimum_h1_rows": 10, "minimum_h1_overlap_fraction": 0.8, "minimum_post_formation_reference_years": 1},
    "selection": {"reference_start_utc": "2012-01-01T00:00:00Z", "reference_end_utc": "2025-01-01T00:00:00Z", "diagnostic_end_utc": "2027-01-01T00:00:00Z"},
    "strategy": {
        "formation_days": 60,
        "entry_abs_z": 1.5,
        "stop_abs_z": 4.0,
        "maximum_holding_days": 20,
        "normal_roundtrip_cost_bps": 4.0,
        "severe_roundtrip_cost_bps": 8.0,
    },
    "clustered_calibration": {
        "clusters": 4,
        "cluster_days": 20,
        "trials": 40,
        "seed": 123,
        "empirical_resample_block_days": 5,
        "planted_edge_sigma_fraction": 1.0,
        "bootstrap_reps": 300,
        "bootstrap_block_trades": 4,
        "minimum_positive_clusters": 3,
        "maximum_positive_cluster_profit_share": 0.5,
        "maximum_null_pass_rate": 0.25,
        "minimum_edge_detection_rate": 0.70,
    },
    "validation": {
        "bootstrap_reps": 300,
        "bootstrap_block_trades": 2,
        "bootstrap_seed": 44,
        "random_side_control": {"reps": 300, "seed": 55},
        "reference_gates": {
            "minimum_trades": 2,
            "minimum_profit_factor": 1.0,
            "minimum_annualized_return": -1.0,
            "maximum_drawdown_abs": 1.0,
            "minimum_positive_folds": 0,
            "minimum_worst_fold_annualized_return": -1.0,
            "minimum_positive_year_share": 0.0,
            "maximum_positive_year_profit_share": 1.0,
            "maximum_positive_trade_profit_share": 1.0,
            "minimum_random_side_percentile": 0.0,
        },
        "diagnostic_gates": {"minimum_trades": 1, "minimum_profit_factor": 0.0, "minimum_annualized_return": -1.0, "maximum_drawdown_abs": 1.0},
    },
    "inputs": {"mt5_export_directory": "", "xau": {"symbol": "XAUUSD", "candidates": []}, "xag": {"symbol": "XAGUSD", "candidates": []}},
    "outputs": {"report_dir": "reports/precious_metals_final_rv", "downloads_dir": "~/Downloads", "results_zip": "XAUUSD_PRECIOUS_METALS_FINAL_RV_RESULTS.zip"},
}


def synthetic_daily(n=700, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2012-01-01", periods=n, freq="D", tz="UTC")
    silver = np.cumsum(rng.normal(0.0002, 0.01, n)) + math.log(30.0)
    # Stationary AR(1) residual with occasional excursions.
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = 0.88 * e[i - 1] + rng.normal(0, 0.012)
    gold = math.log(1600.0) + 0.55 * (silver - math.log(30.0)) + e
    xau_close = np.exp(gold)
    xag_close = np.exp(silver)
    return pd.DataFrame({
        "date": dates,
        "open_time_utc": dates,
        "close_time_utc": dates + pd.Timedelta(hours=23),
        "xau_open": xau_close * np.exp(rng.normal(0, 0.001, n)),
        "xau_close": xau_close,
        "xag_open": xag_close * np.exp(rng.normal(0, 0.001, n)),
        "xag_close": xag_close,
        "common_h1_bars": 20,
        "xau_log_close": gold,
        "xag_log_close": silver,
        "naive_spread_return_bps": pd.Series(gold - silver).diff().to_numpy() * 10000,
    })


class TestPreciousMetalsFinalRV(unittest.TestCase):
    def test_dst_winter_false(self):
        self.assertFalse(eu_dst_utc(pd.Timestamp("2024-01-15T12:00:00Z").to_pydatetime()))

    def test_dst_summer_true(self):
        self.assertTrue(eu_dst_utc(pd.Timestamp("2024-07-15T12:00:00Z").to_pydatetime()))

    def test_ols_recovers_beta(self):
        x = np.linspace(1, 3, 200)
        y = 2.0 + 0.7 * x
        a, b, r, r2 = ols_y_on_x(y, x)
        self.assertAlmostEqual(a, 2.0, places=10)
        self.assertAlmostEqual(b, 0.7, places=10)
        self.assertLess(np.max(np.abs(r)), 1e-10)
        self.assertAlmostEqual(r2, 1.0, places=10)

    def test_pair_weights_gross_normalized(self):
        wx, ws = _pair_weights(1, 0.6)
        self.assertAlmostEqual(abs(wx) + abs(ws), 1.0, places=12)
        self.assertGreater(wx, 0)
        self.assertLess(ws, 0)

    def test_ar1_half_life_positive(self):
        rng = np.random.default_rng(1)
        r = np.zeros(500)
        for i in range(1, len(r)):
            r[i] = 0.8 * r[i-1] + rng.normal(0, 1)
        d = residual_ar1_diagnostics(r)
        self.assertIsNotNone(d["half_life_days"])
        self.assertGreater(d["half_life_days"], 0)

    def test_cluster_mask_count(self):
        dates = pd.Series(pd.date_range("2012-01-01", periods=1000, freq="D", tz="UTC"))
        m = deterministic_cluster_mask(dates, 4, 30)
        self.assertEqual(int(m.sum()), 120)

    def test_formation_past_only(self):
        d = synthetic_daily(500)
        f1 = formation_at(d, 300, BASE_CFG)
        d2 = d.copy()
        d2.loc[301:, "xau_log_close"] += 100.0
        f2 = formation_at(d2, 300, BASE_CFG)
        self.assertAlmostEqual(f1["beta"], f2["beta"], places=12)
        self.assertAlmostEqual(f1["z"], f2["z"], places=12)

    def test_simulation_produces_two_leg_trades(self):
        d = synthetic_daily(700)
        t = simulate_pair_trades(d, BASE_CFG, pd.Timestamp("2012-04-01T00:00:00Z"), pd.Timestamp("2013-12-31T00:00:00Z"))
        self.assertGreater(len(t), 0)
        self.assertTrue((t["beta"] > 0).all())
        self.assertTrue(np.allclose(np.abs(t["w_xau"]) + np.abs(t["w_xag"]), 1.0))

    def test_reference_boundary_exits_before_end(self):
        d = synthetic_daily(700)
        end = pd.Timestamp("2013-06-01T00:00:00Z")
        t = simulate_pair_trades(d, BASE_CFG, pd.Timestamp("2012-04-01T00:00:00Z"), end)
        if len(t):
            self.assertTrue((t["exit_date"] < end).all())

    def test_clustered_calibration_detects_strong_observable_edge(self):
        d = synthetic_daily(1800)
        curve, summary = run_clustered_regime_calibration(d, BASE_CFG)
        self.assertEqual(set(curve["control"]), {"NULL", "OBSERVABLE_CLUSTERED_EDGE"})
        self.assertGreaterEqual(summary["observable_clustered_edge_detection_rate"], 0.70)

    def test_server_epoch_exact_cross_asset_schema_winter(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "xauusd__h1.csv"
            utc_times = pd.date_range("2024-01-02T00:00:00Z", periods=10, freq="h")
            server = (utc_times + pd.Timedelta(hours=2)).tz_localize(None)
            epoch = server.to_numpy(dtype="datetime64[s]").astype("int64")
            frame = pd.DataFrame({
                "program": "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1_2_SESSION_ELIGIBILITY_CONTRACT_REPAIR",
                "symbol": "XAUUSD",
                "timeframe": "H1",
                "time_server_epoch": epoch,
                "open": 2000.0,
                "high": 2002.0,
                "low": 1999.0,
                "close": 2001.0,
                "tick_volume": 10,
                "spread": 30,
                "real_volume": 0,
                "source": "AMARKETS_MT5",
            })
            frame.to_csv(p, index=False)
            out = load_mt5_h1(p, BASE_CFG, "XAUUSD")
            self.assertEqual(len(out), 10)
            self.assertEqual(out.attrs["loader"], "CROSS_ASSET_SERVER_EPOCH_EU_DST")
            self.assertEqual(out.iloc[0]["timestamp_utc"], utc_times[0])
            self.assertEqual(out.iloc[0]["session_date"], pd.Timestamp("2024-01-02"))

    def test_server_epoch_exact_cross_asset_schema_summer(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "xagusd__h1.csv"
            utc_times = pd.date_range("2024-07-02T00:00:00Z", periods=10, freq="h")
            server = (utc_times + pd.Timedelta(hours=3)).tz_localize(None)
            epoch = server.to_numpy(dtype="datetime64[s]").astype("int64")
            frame = pd.DataFrame({
                "program": "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1",
                "symbol": "XAGUSD",
                "timeframe": "H1",
                "time_server_epoch": epoch,
                "open": 30.0,
                "high": 30.2,
                "low": 29.9,
                "close": 30.1,
                "tick_volume": 10,
                "spread": 20,
                "real_volume": 0,
                "source": "AMARKETS_MT5",
            })
            frame.to_csv(p, index=False)
            out = load_mt5_h1(p, BASE_CFG, "XAGUSD")
            self.assertEqual(len(out), 10)
            self.assertEqual(out.attrs["loader"], "CROSS_ASSET_SERVER_EPOCH_EU_DST")
            self.assertEqual(out.iloc[0]["timestamp_utc"], utc_times[0])
            self.assertEqual(out.iloc[0]["session_date"], pd.Timestamp("2024-07-02"))

    def test_server_epoch_schema_rejects_wrong_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "wrong.csv"
            utc_times = pd.date_range("2024-01-02T00:00:00Z", periods=10, freq="h")
            server = (utc_times + pd.Timedelta(hours=2)).tz_localize(None)
            epoch = server.to_numpy(dtype="datetime64[s]").astype("int64")
            pd.DataFrame({
                "program": "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1",
                "symbol": "EURUSD",
                "timeframe": "H1",
                "time_server_epoch": epoch,
                "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1,
                "tick_volume": 10, "spread": 2, "real_volume": 0, "source": "AMARKETS_MT5",
            }).to_csv(p, index=False)
            with self.assertRaises(Exception):
                load_mt5_h1(p, BASE_CFG, "XAUUSD")

    def test_loader_mt5_schema(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n2024.01.02\t10:00:00\t2000\t2002\t1999\t2001\n" * 1, encoding="utf-8")
            # Fix repeated header issue by writing multiple valid rows manually.
            lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>"]
            for h in range(10):
                lines.append(f"2024.01.02\t{h:02d}:00:00\t2000\t2002\t1999\t2001")
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            out = load_mt5_h1(p, BASE_CFG, "XAUUSD")
            self.assertEqual(len(out), 10)
            self.assertEqual(out.attrs["loader"], "MT5_DATE_TIME_EU_DST")

    def test_loader_rejects_bad_ohlc(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.csv"
            lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>"]
            for h in range(10):
                lines.append(f"2024.01.02\t{h:02d}:00:00\t2000\t1990\t1999\t2001")
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(Exception):
                load_mt5_h1(p, BASE_CFG, "XAUUSD")

    def test_sync_requires_overlap(self):
        ts = pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC")
        a = pd.DataFrame({"timestamp_utc": ts, "session_date": pd.Timestamp("2024-01-01"), "open": 1, "high": 2, "low": 0.5, "close": 1.5})
        b = a.copy()
        m = synchronize_h1(a, b, BASE_CFG)
        self.assertEqual(len(m), 10)

    def test_build_daily_uses_common_rows(self):
        ts = pd.date_range("2024-01-01", periods=48, freq="h", tz="UTC")
        session = pd.Series([pd.Timestamp("2024-01-01") if i < 24 else pd.Timestamp("2024-01-02") for i in range(48)])
        s = pd.DataFrame({
            "timestamp_utc": ts, "session_date": session,
            "xau_open": 2000.0, "xau_high": 2002.0, "xau_low": 1999.0, "xau_close": 2001.0,
            "xag_open": 25.0, "xag_high": 25.2, "xag_low": 24.9, "xag_close": 25.1,
        })
        d = build_common_daily(s)
        self.assertEqual(len(d), 2)
        self.assertEqual(int(d.iloc[0]["common_h1_bars"]), 24)

    def test_static_no_execution_network(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(static_execution_violations(root), [])

    def test_strategy_does_not_require_cointegration_threshold(self):
        self.assertNotIn("cointegration_pvalue", BASE_CFG["strategy"])

    def test_costs_reduce_returns(self):
        d = synthetic_daily(700)
        t = simulate_pair_trades(d, BASE_CFG, pd.Timestamp("2012-04-01T00:00:00Z"), pd.Timestamp("2013-12-31T00:00:00Z"))
        if len(t):
            self.assertTrue((t["gross_return"] >= t["normal_net_return"] - 1e-15).all())
            self.assertTrue((t["normal_net_return"] >= t["severe_net_return"] - 1e-15).all())

    def test_no_trade_overlap(self):
        d = synthetic_daily(700)
        t = simulate_pair_trades(d, BASE_CFG, pd.Timestamp("2012-04-01T00:00:00Z"), pd.Timestamp("2013-12-31T00:00:00Z"))
        if len(t) > 1:
            self.assertTrue((t["entry_date"].iloc[1:].reset_index(drop=True) >= t["exit_date"].iloc[:-1].reset_index(drop=True)).all())

    def test_derived_history_contract_accepts_2311_daily_rows(self):
        cfg = dict(BASE_CFG)
        cfg["selection"] = {"reference_start_utc": "2012-01-01T00:00:00Z", "reference_end_utc": "2025-01-01T00:00:00Z"}
        cfg["strategy"] = dict(BASE_CFG["strategy"])
        cfg["strategy"]["formation_days"] = 252
        cfg["data_contract"] = {"minimum_post_formation_reference_years": 6}
        daily = pd.DataFrame({"date": pd.bdate_range("2016-02-23", periods=2311, tz="UTC")})
        result = validate_reference_history(daily, cfg)
        self.assertEqual(result["effective_reference_rows_after_formation"], 2059)
        self.assertGreaterEqual(result["effective_reference_distinct_years"], 6)

    def test_derived_history_contract_rejects_too_short_reference(self):
        cfg = dict(BASE_CFG)
        cfg["selection"] = {"reference_start_utc": "2012-01-01T00:00:00Z", "reference_end_utc": "2025-01-01T00:00:00Z"}
        cfg["strategy"] = dict(BASE_CFG["strategy"])
        cfg["strategy"]["formation_days"] = 252
        cfg["data_contract"] = {"minimum_post_formation_reference_years": 6}
        daily = pd.DataFrame({"date": pd.bdate_range("2018-01-02", periods=1600, tz="UTC")})
        with self.assertRaises(CampaignError):
            validate_reference_history(daily, cfg)


if __name__ == "__main__":
    unittest.main()
