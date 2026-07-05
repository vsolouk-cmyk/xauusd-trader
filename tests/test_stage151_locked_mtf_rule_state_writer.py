from pathlib import Path
import sys, json
from datetime import datetime, timezone, timedelta
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from app.stage151_locked_mtf_rule_state_writer import compute_latest_features, condition_active, hours_to_bars, load_conditions_from_summary

def make_bars(n=1300, step_minutes=5):
    start=datetime(2026,1,1,tzinfo=timezone.utc); out=[]; price=1000.0
    for i in range(n):
        price += 0.1; out.append({'utc_time':start+timedelta(minutes=i*step_minutes),'open':price,'high':price+1,'low':price-1,'close':price})
    return out

def test_hours_to_bars():
    assert hours_to_bars(100,5)==1200
    assert hours_to_bars(24,15)==96

def test_latest_feature_computation_m5():
    latest=compute_latest_features(make_bars(), timeframe_minutes=5)
    assert latest['trend_8_20_bps'] is not None
    assert latest['trend_50_100_bps'] is not None
    assert latest['range_pos_24'] is not None

def test_condition_active():
    latest={'a':10.0,'b':-2.0}
    assert condition_active(latest,[{'feature':'a','op':'>=','threshold':9},{'feature':'b','op':'<=','threshold':0}])
    assert not condition_active(latest,[{'feature':'a','op':'<=','threshold':9}])

def test_load_conditions_from_summary():
    s={'selected_score':{'conditions_json':json.dumps([{'feature':'trend_8_20_bps','op':'>=','threshold':9.2,'current':10.1},{'feature':'trend_50_100_bps','op':'>=','threshold':-14.3,'current':126.0}])}}
    conds=load_conditions_from_summary(s)
    assert conds[0]['feature']=='trend_8_20_bps'
    assert conds[1]['threshold']==-14.3
