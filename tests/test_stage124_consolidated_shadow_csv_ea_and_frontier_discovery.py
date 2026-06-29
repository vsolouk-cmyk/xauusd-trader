from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import stage124_consolidated_shadow_csv_ea_and_frontier_discovery as s


def test_detect_return_col_alias():
    df = pd.DataFrame({"utc_time": ["2024-01-01"], "forward_h120_bps": [12.5]})
    assert s.detect_return_col(df, 120) == "forward_h120_bps"


def test_join_events_to_returns_exact_match():
    events = pd.DataFrame({"utc_time": ["2024-01-01T00:00:00Z", "2024-01-06T00:00:00Z"]})
    ds = pd.DataFrame({"utc_time": ["2024-01-01T00:00:00Z", "2024-01-06T00:00:00Z"], "fwd_ret_bps_h120": [25.0, -5.0]})
    joined, col, warnings = s.join_events_to_returns(events, ds, 120)
    assert col == "_stage124_forward_return_bps"
    assert joined[col].notna().sum() == 2


def test_compute_replay_metrics_pass():
    times = pd.date_range("2021-01-01", periods=35, freq="20D")
    events = pd.DataFrame({"utc_time": times, "ret_bps_h120": [30.0] * 35})
    metrics = s.compute_replay_metrics("R1", events, "ret_bps_h120", 120)
    assert metrics["static_replay_status"] == "PASS_STATIC_REPLAY"
    assert metrics["cost10_mean_bps"] == 20.0


def test_ea_source_has_no_trade_tokens():
    src = s.EA_SAFE_MQL5
    assert "CTrade" not in src
    assert "OrderSend" not in src
    assert "allow_trading=false" not in src  # no signal semantics in source; it is observer-only


def test_build_next_discovery_skips_missing_bool_proxy_without_quantile_crash():
    n = 120
    ds = pd.DataFrame({
        "utc_time": pd.date_range("2022-01-01", periods=n, freq="h"),
        "fwd_ret_bps_h120": [20.0] * n,
        "real_yield_10y": [float(i % 10) for i in range(n)],
        "dollar_pressure_index": [float(10 - (i % 10)) for i in range(n)],
        # bool column used to reproduce numpy boolean subtract quantile crash.
        "cot_z": [(i % 2) == 0 for i in range(n)],
    })
    metrics, selected, feature_plan = s.build_next_discovery(ds, 120)
    assert isinstance(metrics, pd.DataFrame)
    assert isinstance(selected, pd.DataFrame)
    assert isinstance(feature_plan, pd.DataFrame)


def test_stage124c_mt5_experts_default_uses_advisors_xauusd_path():
    assert s.MT5_EXPERTS_DEFAULT.endswith("MQL5/Experts/Advisors/XAUUSD")


def test_build_mt5_shadow_kv_rows_has_key_value_contract():
    row = s.build_shadow_csv_row(
        {"generated_utc": "2026-01-01T00:00:00Z"},
        {"rule_id": "R", "static_replay_status": "PASS_STATIC_REPLAY", "cost10_mean_bps": 1.2, "cost10_hit_rate": 0.6, "horizon_hours": 120},
        {"source_rule_id": "SRC", "candidate_only": True},
        "2026-01-01T00:00:00Z",
    )
    kv = s.build_mt5_shadow_kv_rows(row)
    assert {r["key"] for r in kv} >= {"rule_id", "allow_trading", "combo_integration_mode"}
    assert all(set(r) == {"key", "value"} for r in kv)


def test_ea_source_reads_key_value_csv_and_has_no_trade_tokens():
    src = s.EA_SAFE_MQL5
    assert "CaptureKeyValue" in src
    assert "OrderSend" not in src
    assert "CTrade" not in src
