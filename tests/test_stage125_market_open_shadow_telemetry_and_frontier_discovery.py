from pathlib import Path
import tempfile
import pandas as pd

from app.stage125_market_open_shadow_telemetry_and_frontier_discovery import (
    read_kv_csv,
    q,
    add_forward_return_if_needed,
    build_frontier_discovery,
    snapshot_file,
)


def test_read_kv_csv_no_header():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.csv"
        p.write_text("rule_id,ABC\nstatus,PASS\nallow_trading,false\n", encoding="utf-8")
        kv = read_kv_csv(p)
        assert kv["rule_id"] == "ABC"
        assert kv["allow_trading"] == "false"


def test_bool_quantile_safe():
    s = pd.Series([True, False, True, False])
    val = q(s, 0.5)
    assert val in (0.5, 1.0, 0.0)


def test_forward_return_compute_from_close():
    df = pd.DataFrame({"utc_time": pd.date_range("2024-01-01", periods=130, freq="h"), "close": range(100, 230)})
    out, col, source = add_forward_return_if_needed(df, 120)
    assert col == "_stage125_forward_return_bps"
    assert "computed_from" in source
    assert out[col].notna().sum() > 0


def test_frontier_discovery_handles_missing_features():
    df = pd.DataFrame({
        "utc_time": pd.date_range("2024-01-01", periods=150, freq="h"),
        "close": [2000 + i for i in range(150)],
        "real_yield_10y_chg_20d": [(-1) ** i * 0.1 for i in range(150)],
        "dollar_pressure_chg_20d": [(-1) ** (i+1) * 0.1 for i in range(150)],
        "spdr_value_chg_20d": [i % 5 for i in range(150)],
    })
    metrics, selected, alternatives, ret_source = build_frontier_discovery(df, 120)
    assert len(metrics) >= 1
    assert len(alternatives) >= 3
    assert ret_source


def test_snapshot_file_kv():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "kv.csv"
        p.write_text("rule_id,R1\nstatus,PASS\n", encoding="utf-8")
        snap = snapshot_file(p)
        assert snap.exists
        assert snap.format_hint == "KEY_VALUE"
        assert snap.rule_id == "R1"
