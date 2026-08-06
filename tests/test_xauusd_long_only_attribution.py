import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_long_only_attribution.py"
spec = importlib.util.spec_from_file_location("audit", MODULE_PATH)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)


def create_h1_db(path: Path, table: str, *, m5=False, perturb=0.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(path)
    extra=", m5_bar_count INTEGER NOT NULL" if m5 else ""
    con.execute(f"CREATE TABLE {table}(timestamp INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, volume REAL{extra})")
    dt=pd.DatetimeIndex(np.concatenate([pd.date_range(f"{year}-01-01", periods=24*35, freq="h", tz="UTC").to_numpy() for year in range(2015, 2025)]))
    price=1200.0
    rows=[]
    for i,t in enumerate(dt):
        # Slow positive drift plus periodic large bullish expansion candles.
        base=0.03 + 0.02*np.sin(i/37)
        o=price
        if i%240==50:
            c=o+5.0
            h=c+0.4
            l=o-0.2
        elif i%240==170:
            c=o-4.0
            h=o+0.2
            l=c-0.4
        else:
            c=o+base
            h=max(o,c)+0.12
            l=min(o,c)-0.12
        if perturb:
            o*=1+perturb*np.sin(i/17)
            c*=1+perturb*np.sin(i/17)
            h*=1+perturb*np.sin(i/17)
            l*=1+perturb*np.sin(i/17)
        row=[int(t.value//1_000_000),float(o),float(h),float(l),float(c),1.0]
        if m5: row.append(12)
        rows.append(tuple(row))
        price=c
    placeholders=",".join(["?"]*len(rows[0]))
    con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    con.commit(); con.close()


def create_event_db(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path)
    con.execute("CREATE TABLE official_events(event_time_utc TEXT, blackout_before_minutes REAL, blackout_after_minutes REAL)")
    con.executemany("INSERT INTO official_events VALUES (?,?,?)", [("2018-01-10T12:00:00Z",60,60),("2022-05-05T14:00:00Z",60,60)])
    con.commit(); con.close()


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        create_h1_db(self.root/"am.sqlite","am_h1",m5=True)
        create_h1_db(self.root/"du.sqlite","du_h1",perturb=1e-7)
        create_event_db(self.root/"events.sqlite")
        cfg={
            "amarkets_db":"am.sqlite","amarkets_table":"am_h1","dukascopy_db":"du.sqlite","dukascopy_table":"du_h1","event_db":"events.sqlite","minimum_m5_bar_count":12,
            "reference_start":"2015-01-02T07:00:00Z","reference_end":"2025-01-01T00:00:00Z","severe_cost_bps":4.5,"maximum_notional_to_equity":0.1570396406876166,"control_max_lookback_days":120,
            "bootstrap":{"block_length":5,"replications":100,"random_state":1},
            "folds":[
                {"name":"a","start":"2015-01-02T07:00:00Z","end":"2017-01-01T00:00:00Z"},
                {"name":"b","start":"2017-01-01T00:00:00Z","end":"2019-01-01T00:00:00Z"},
                {"name":"c","start":"2019-01-01T00:00:00Z","end":"2021-01-01T00:00:00Z"},
                {"name":"d","start":"2021-01-01T00:00:00Z","end":"2023-01-01T00:00:00Z"},
                {"name":"e","start":"2023-01-01T00:00:00Z","end":"2025-01-01T00:00:00Z"}],
            "gates":{"minimum_trades":5,"minimum_profit_factor":0.1,"minimum_positive_fold_share":0.0,"minimum_control_pairs":1,"minimum_signal_jaccard":0.5,"minimum_return_correlation":0.5}
        }
        self.config=self.root/"config.json"; self.config.write_text(json.dumps(cfg))
    def tearDown(self): self.tmp.cleanup()

    def test_to_ms_resolution_invariant(self):
        a=pd.Timestamp("2024-01-01T00:00:00Z")
        self.assertEqual(audit.to_ms(a),1704067200000)

    def test_bounded_loader_never_reads_2025(self):
        f=audit.load_h1_bounded(self.root/"am.sqlite","am_h1",audit.to_ms("2015-01-02"),audit.to_ms("2025-01-01"),12)
        self.assertLess(int(f.timestamp.max()),audit.to_ms("2025-01-01"))

    def test_features_create_expansion_signals(self):
        raw=audit.load_h1_bounded(self.root/"am.sqlite","am_h1",audit.to_ms("2015-01-02"),audit.to_ms("2025-01-01"),12)
        feat=audit.build_features(raw,pd.DataFrame(columns=["event_dt","before","after"]))
        self.assertGreater(int(audit.signal_series(feat,1).sum()),5)

    def test_exact_horizon_and_non_overlap(self):
        raw=audit.load_h1_bounded(self.root/"am.sqlite","am_h1",audit.to_ms("2015-01-02"),audit.to_ms("2025-01-01"),12)
        tr=audit.make_trades(audit.build_features(raw,pd.DataFrame(columns=["event_dt","before","after"])),1,4.5)
        self.assertGreater(len(tr),5)
        self.assertTrue(((tr.exit_utc-tr.entry_utc).dt.total_seconds()==48*3600).all())
        self.assertTrue((tr.entry_utc.iloc[1:].reset_index(drop=True)>=tr.exit_utc.iloc[:-1].reset_index(drop=True)).all())

    def test_control_matching(self):
        raw=audit.load_h1_bounded(self.root/"am.sqlite","am_h1",audit.to_ms("2015-01-02"),audit.to_ms("2025-01-01"),12)
        feat=audit.build_features(raw,pd.DataFrame(columns=["event_dt","before","after"]))
        tr=audit.make_trades(feat,1,4.5); pool=audit.eligible_control_pool(feat,4.5)
        pairs=audit.match_controls(tr,pool,read_json(self.config)["folds"] if False else json.loads(self.config.read_text())["folds"],120)
        self.assertGreater(len(pairs),0)
        self.assertIn("paired_excess_bps",pairs)

    def test_crossfeed_agreement(self):
        start=audit.to_ms("2015-01-02"); end=audit.to_ms("2025-01-01")
        a=audit.make_trades(audit.build_features(audit.load_h1_bounded(self.root/"am.sqlite","am_h1",start,end,12),pd.DataFrame(columns=["event_dt","before","after"])),1,4.5)
        d=audit.make_trades(audit.build_features(audit.load_h1_bounded(self.root/"du.sqlite","du_h1",start,end,None),pd.DataFrame(columns=["event_dt","before","after"])),1,4.5)
        c=audit.crossfeed(a,d)
        self.assertGreater(c["signal_jaccard"],0.8)
        self.assertGreater(c["return_correlation"],0.9)

    def test_preflight(self):
        out=audit.preflight(self.root,self.config)
        self.assertTrue(out["pass"])
        self.assertFalse(out["selection_used_2025_plus"])

    def test_run_end_to_end(self):
        outdir=self.root/"out"; result=audit.run(self.root,self.config,outdir)
        self.assertIn(result["decision"],{audit.PASS_DECISION,audit.FAIL_DECISION})
        self.assertTrue((outdir/"long_only_attribution_summary.json").is_file())
        self.assertFalse(result["live_order_allowed"])

    def test_collect(self):
        outdir=self.root/"out"; audit.run(self.root,self.config,outdir)
        dest=self.root/"result.zip"; result=audit.collect(self.root,self.config,outdir,dest)
        self.assertTrue(dest.is_file()); self.assertTrue(result["pass"])

    def test_no_order_authorization_strings(self):
        text=MODULE_PATH.read_text()
        self.assertNotIn("order_send",text.lower())
        self.assertNotIn("metatrader",text.lower())


def read_json(path): return json.loads(path.read_text())

if __name__=="__main__": unittest.main()
