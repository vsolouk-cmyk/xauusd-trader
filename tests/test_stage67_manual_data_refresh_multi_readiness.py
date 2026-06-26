#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'app' / 'stage67_manual_data_refresh_multi_readiness.py'

spec = importlib.util.spec_from_file_location('stage67', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore


def test_parse_date_any():
    assert mod.parse_date_any('2026-06-24T00:00:00Z').isoformat() == '2026-06-24'
    assert mod.parse_date_any('2026/06/24').isoformat() == '2026-06-24'


def test_resample_ohlc_to_d1():
    import datetime as dt
    rows = [
        {'dt': dt.datetime(2026,1,1,0,0,tzinfo=dt.timezone.utc), 'date': dt.date(2026,1,1), 'open': 1.0, 'high': 2.0, 'low': 0.5, 'close': 1.5, 'volume': 10},
        {'dt': dt.datetime(2026,1,1,0,5,tzinfo=dt.timezone.utc), 'date': dt.date(2026,1,1), 'open': 1.5, 'high': 2.5, 'low': 1.0, 'close': 2.0, 'volume': 20},
    ]
    out = mod.resample_ohlc_to_d1(rows)
    assert len(out) == 1
    assert out[0]['open'] == 1.0
    assert out[0]['high'] == 2.5
    assert out[0]['low'] == 0.5
    assert out[0]['close'] == 2.0


def test_merge_d1_prefers_new():
    existing = [{'date_utc':'2026-01-01','open':1,'high':1,'low':1,'close':1,'volume':'','source':'old'}]
    new = [{'date_utc':'2026-01-01','open':2,'high':2,'low':2,'close':2,'volume':'','source':'new'}]
    out = mod.merge_d1(existing, new)
    assert out[0]['close'] == 2


if __name__ == '__main__':
    test_parse_date_any()
    test_resample_ohlc_to_d1()
    test_merge_d1_prefers_new()
    print('Stage67 tests passed')
