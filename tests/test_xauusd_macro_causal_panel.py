from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app/xauusd_macro_causal_panel.py"
spec = importlib.util.spec_from_file_location("panel", MODULE_PATH)
panel = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(panel)

class MacroPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        cfg = {
            "program": panel.PROGRAM,
            "reference_start": "2011-01-01",
            "reference_end": "2024-12-31",
            "diagnostic_start": "2025-01-01",
            "fred_series": {"usd_broad":"DTWEXBGS","real_yield_10y":"DFII10","nominal_yield_10y":"DGS10","breakeven_10y":"T10YIE","vix":"VIXCLS","gvz":"GVZCLS"},
            "daily_availability_lag_days": 1,
            "minimum_core_start": "2012-01-01",
            "minimum_core_end": "2024-12-31",
            "minimum_core_completeness": 0.90,
            "event_blackout_before_minutes": 60,
            "event_blackout_after_minutes": 120,
            "target_horizons_trading_days": [5,20],
        }
        (self.root / "config/xauusd_macro_causal_panel_v1.json").write_text(json.dumps(cfg))
        self._make_fixture()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_fixture(self):
        dates = pd.date_range("2010-01-01", "2026-01-15", freq="B", tz="UTC")
        raw = self.root / "data/fundamental_event_inbox/raw/fred_macro"
        raw.mkdir(parents=True)
        for i, series in enumerate(["DTWEXBGS","DFII10","DGS10","T10YIE","VIXCLS","GVZCLS"]):
            pd.DataFrame({"observation_date": dates.strftime("%Y-%m-%d"), series: np.linspace(10+i,20+i,len(dates))}).to_csv(raw / f"abc{i}__{series}.csv", index=False)
        gold = self.root / "data/macro_regime/raw"
        gold.mkdir(parents=True)
        g = pd.DataFrame({"date_utc": dates, "open":100+np.arange(len(dates))*.01, "high":101, "low":99, "close":100.5+np.arange(len(dates))*.01, "volume":1, "source":"x", "spread_median":1})
        g.to_csv(gold / "broker_or_spot_gold_d1_ohlc_2011_present.csv", index=False)
        cftc = self.root / "data/external_frontiers"
        cftc.mkdir(parents=True)
        wdates = pd.date_range("2010-01-08","2026-01-09",freq="W-FRI",tz="UTC")
        pd.DataFrame({"report_date_utc":wdates-pd.Timedelta(days=3),"available_after_utc":wdates,"managed_money_net_z_156w":0.1,"managed_money_net_pct_oi":0.2,"managed_money_net_change_4w":0.3}).to_csv(cftc/"cot_positioning_normalized.csv",index=False)
        evt = self.root / "data/fundamental_event_inbox/features"
        evt.mkdir(parents=True)
        pd.DataFrame({"event_time_utc":["2020-01-02T00:30:00Z"],"source":["BLS"],"category":["CPI"],"title":["CPI"]}).to_csv(evt/"stage115_official_core_event_timestamps.csv",index=False)
        norm = self.root / "data/macro_regime/normalized"
        norm.mkdir(parents=True)
        pd.DataFrame({"date_utc":["2019-12-31"],"holdings_tonnes":[1000],"fund_sum_tonnes":[1000],"etf_flow_tonnes_3m":[12],"available_after_utc":["2020-01-05T00:00:00Z"],"source_path":["x"],"source_sha256":["a"],"semantic_contract":["x"],"availability_contract":["x"]}).to_csv(norm/"wgc_global_etf_holdings_monthly_stage173.csv",index=False)
        vint = self.root / "data/macro_regime/vintages"
        vint.mkdir(parents=True)
        pd.DataFrame({"quarter":["2019Q4"],"quarter_end_utc":["2019-12-31"],"release_timestamp_utc":["2020-02-01T00:00:00Z"],"official_sector_purchases_tonnes":[50],"is_original_publication":[True]}).to_csv(vint/"wgc_official_sector_quarterly_vintages.csv",index=False)

    def test_reject_html_masquerade(self):
        p=self.root/"bad.csv"; p.write_text("<!DOCTYPE html><html></html>")
        with self.assertRaises(panel.PanelError): panel.read_csv_checked(p)

    def test_validate_gvz_bytes(self):
        dates=pd.date_range("2008-01-01",periods=1200,freq="B")
        data=pd.DataFrame({"observation_date":dates.strftime("%Y-%m-%d"),"GVZCLS":20}).to_csv(index=False).encode()
        self.assertEqual(len(panel.validate_gvz_bytes(data)),1200)

    def test_fetch_gvz_from_local_source_file(self):
        dates=pd.date_range("2008-01-01",periods=1200,freq="B")
        source=self.root/"GVZCLS_input.csv"
        pd.DataFrame({"observation_date":dates.strftime("%Y-%m-%d"),"GVZCLS":20}).to_csv(source,index=False)
        r=panel.fetch_gvz(self.root,source)
        self.assertTrue(r["pass"])
        self.assertTrue(Path(r["repo_path"]).is_file())
        self.assertTrue(Path(r["downloads_path"]).is_file())

    def test_fred_availability_is_next_day(self):
        p=next((self.root/"data/fundamental_event_inbox/raw/fred_macro").glob("*__DTWEXBGS.csv"))
        df=panel.load_fred(p,"DTWEXBGS","usd_broad",1)
        delta=df["usd_broad_available_after_utc"]-df["usd_broad_observation_date_utc"]
        self.assertTrue((delta==pd.Timedelta(days=1)).all())

    def test_asof_never_uses_future(self):
        left=pd.DataFrame({"decision_time_utc":pd.to_datetime(["2020-01-02"],utc=True)})
        right=pd.DataFrame({"available":pd.to_datetime(["2020-01-03"],utc=True),"x":[1]})
        out=panel.asof_merge(left,right,"available")
        self.assertTrue(pd.isna(out.loc[0,"x"]))

    def test_event_blackout(self):
        p=pd.DataFrame({"decision_time_utc":pd.to_datetime(["2020-01-02T00:00:00Z"])})
        e=pd.DataFrame({"event_time_utc":pd.to_datetime(["2020-01-02T00:30:00Z"])})
        cfg={"event_blackout_before_minutes":60,"event_blackout_after_minutes":120}
        out=panel.add_event_flags(p,e,cfg)
        self.assertTrue(bool(out.loc[0,"official_event_blackout_active"]))

    def test_select_sources_full(self):
        cfg=panel.load_config(self.root)
        s=panel.select_sources(self.root,cfg,False)
        self.assertIn("gvz",s["selected"])

    def test_preflight_ready(self):
        r=panel.preflight(self.root)
        self.assertEqual(r["decision"],"PASS_MACRO_PANEL_PREFLIGHT_READY")

    def test_build_end_to_end(self):
        r=panel.build(self.root)
        self.assertTrue(r["pass"])
        self.assertTrue((self.root/panel.REPORT_DIR/"macro_causal_features.csv").is_file())
        q=json.loads((self.root/panel.REPORT_DIR/"macro_panel_quality.json").read_text())
        self.assertTrue(all(v==0 for v in q["causality_leakage_counts"].values()))

    def test_targets_separate_future_only(self):
        gold,_=panel.load_gold(self.root)
        t=panel.build_targets(gold,[5])
        self.assertTrue(t["future_target_only"].all())
        self.assertIn("gross_return_5td_bps",t)

    def test_collect_current_outputs(self):
        panel.build(self.root)
        r=panel.collect(self.root)
        self.assertTrue(Path(r["output"]).is_file())
        with panel.ZipFile(r["output"]) as z:
            self.assertIn("RESULTS_MANIFEST.json",z.namelist())
            self.assertNotIn("reports/macro_panel_failure.json",z.namelist())

    def test_no_order_authorization(self):
        r=panel.build(self.root)
        self.assertFalse(r["paper_order_allowed"])
        self.assertFalse(r["demo_order_allowed"])
        self.assertFalse(r["live_order_allowed"])

    def test_datetime_resolution_safe(self):
        s=pd.Series(pd.date_range("2020-01-01",periods=2,freq="D").astype("datetime64[us]"))
        out=panel.to_utc(s)
        self.assertEqual(out.iloc[1]-out.iloc[0],pd.Timedelta(days=1))

    def test_optional_wgc_uses_release_time(self):
        w,_=panel.load_wgc_optional(self.root)
        self.assertEqual(w.loc[0,"wgc_available_after_utc"],pd.Timestamp("2020-02-01T00:00:00Z"))

if __name__ == "__main__":
    unittest.main()
