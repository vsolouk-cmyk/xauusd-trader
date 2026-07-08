from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage156_operational_unifier import parse_dt, read_kv, infer_status, build_router_cmd

class Args:
    root='/repo'
    bars_m5='/bars/m5.csv'
    score_csv='/reports/scores.csv'
    risk_summary='/reports/risk.json'
    tf='m5'
    timeframe_minutes=5
    max_feature_age_sec=7200
    timestamp_shift_hours=-3
    write_mt5=True

def test_parse_amarkets_datetime():
    dt = parse_dt('2026.07.07 21:35:00')
    assert dt is not None
    assert dt.year == 2026
    assert dt.tzinfo is not None

def test_infer_status_stale():
    cls, reason = infer_status({}, {'decision':'BLOCKED_SIGNAL_STALE'}, True)
    assert cls == 'BLOCKED_STALE'

def test_build_router_cmd_contains_risk_summary_and_shift():
    cmd = build_router_cmd(Args())
    assert '--risk-summary' in cmd
    assert '--timestamp-shift-hours -3' in cmd
    assert '--write-mt5' in cmd

def test_read_kv(tmp_path):
    p = tmp_path / 'x.csv'
    p.write_text('a|1\nb|two\n', encoding='utf-8')
    assert read_kv(p) == {'a':'1','b':'two'}
