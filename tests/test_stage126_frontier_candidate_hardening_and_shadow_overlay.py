from pathlib import Path
import math
import pandas as pd

from app.stage126_frontier_candidate_hardening_and_shadow_overlay import (
    parse_conditions,
    apply_conditions,
    ensure_time_and_return,
    spaced_events,
    decide_candidate,
    build_kv,
)


def test_parse_stage125_compact_conditions():
    cond = "vix_chg_20dgt0.49;dollar_pressure_chg_20dlt0.2258"
    assert parse_conditions(cond) == [("vix_chg_20d", "gt", 0.49), ("dollar_pressure_chg_20d", "lt", 0.2258)]


def test_apply_conditions_numeric_bool_safe():
    df = pd.DataFrame({"vix_chg_20d": [0.5, 0.1], "dollar_pressure_chg_20d": [0.1, 0.3], "flag": [True, False]})
    mask, missing = apply_conditions(df, [("vix_chg_20d", "gt", 0.49), ("dollar_pressure_chg_20d", "lt", 0.2258)])
    assert missing == []
    assert mask.tolist() == [True, False]


def test_return_column_mapping():
    df = pd.DataFrame({"utc_time": pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC"), "fwd_ret_bps_h120": [1, 2, 3]})
    out, ret_col, warnings = ensure_time_and_return(df)
    assert ret_col == "_stage126_forward_return_bps"
    assert out[ret_col].tolist() == [1, 2, 3]
    assert "mapped_from:fwd_ret_bps_h120" in warnings


def test_spaced_events():
    df = pd.DataFrame({"utc_time": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T01:00Z", "2024-01-06T00:00Z"])})
    out = spaced_events(df, 120)
    assert len(out) == 2


def test_build_kv_contains_no_header():
    text = build_kv({"stage": "x", "allow_trading": "false", "cost10_mean_bps": 1.23456789})
    assert text.splitlines()[0] == "stage|x"
    assert "cost10_mean_bps|1.23457" in text
