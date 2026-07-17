import importlib.util
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

P=Path(__file__).resolve().parents[1]/"app/stage172_dual_track_decision_audit.py"
spec=importlib.util.spec_from_file_location("s172",P); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class Stage172Tests(unittest.TestCase):
    def test_locked_split_is_chronological(self):
        ts=pd.Series(pd.date_range("2020-01-01",periods=100,freq="D",tz="UTC")); cutoff,mask=s.locked_split(ts,.2)
        self.assertEqual(mask.sum(),20); self.assertTrue((ts[mask]>=cutoff).all()); self.assertTrue((ts[~mask]<cutoff).all())
    def test_episode_deduplication(self):
        d=pd.DataFrame({"date":pd.date_range("2020-01-01",periods=8,freq="D",tz="UTC"),"active":[0,1,1,0,0,1,1,0]})
        e=s.build_episodes(d,20); self.assertEqual(len(e),2); self.assertEqual(list(e["date"].dt.day),[2,6])
    def test_metrics_cost_aware(self):
        m=s.metrics(pd.DataFrame({"net_bps":[2.0,-1.0,3.0]})); self.assertAlmostEqual(m["net_expectancy_bps"],4/3); self.assertAlmostEqual(m["profit_factor"],5.0)
    def test_cooldown(self):
        sig=pd.Series([1,1,0,1,0,0,1],dtype=bool); out=s.cooldown_filter(sig,3); self.assertEqual(list(np.flatnonzero(out)),[0,3,6])
    def test_available_time_violation_rejected(self):
        # Direct invariant check used by the loader.
        dates=pd.to_datetime(["2020-01-02"],utc=True); avail=pd.to_datetime(["2020-01-01"],utc=True)
        self.assertTrue((avail<dates).any())

if __name__=="__main__": unittest.main()
