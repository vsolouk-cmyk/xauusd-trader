import math
import pandas as pd

from app.stage127_rule9_deconcentration_combo_overlap_review import (
    parse_conditions,
    apply_conditions,
    spaced_events,
    path_metrics,
    overlap_row,
    decide_stage127,
)


def test_parse_and_apply_rule9_conditions():
    cond = "vix_chg_20dgt0.49;dollar_pressure_chg_20dlt0.2258"
    parsed = parse_conditions(cond)
    assert parsed == [("vix_chg_20d", "gt", 0.49), ("dollar_pressure_chg_20d", "lt", 0.2258)]
    df = pd.DataFrame({"vix_chg_20d": [0.5, 0.1], "dollar_pressure_chg_20d": [0.1, 0.1]})
    mask, missing = apply_conditions(df, parsed)
    assert missing == []
    assert mask.tolist() == [True, False]


def test_spaced_events_and_path_metrics_drawdown():
    df = pd.DataFrame({
        "utc_time": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-07", "2024-01-12"], utc=True),
        "ret": [50.0, -100.0, 40.0, 30.0],
    })
    sp = spaced_events(df, 120)
    assert len(sp) == 3
    m = path_metrics(sp, "ret", cost_bps=10)
    assert m["events"] == 3
    assert m["valid_return_events"] == 3
    assert math.isfinite(m["max_drawdown_cost10_bps"])


def test_overlap_row_jaccard():
    a = pd.DataFrame({"utc_time": pd.to_datetime(["2024-01-01 00:00", "2024-01-02 00:00"], utc=True)})
    b = pd.DataFrame({"utc_time": pd.to_datetime(["2024-01-02 00:30", "2024-01-03 00:00"], utc=True)})
    r = overlap_row("a", "b", a, b)
    assert r["intersection_events"] == 1
    assert r["union_events"] == 3
    assert abs(r["jaccard"] - 1/3) < 1e-9


def test_decide_watch_when_validation_concentrated_but_economics_positive():
    split_df = pd.DataFrame([
        {"split": "all", "events": 200, "cost10_mean_bps": 50, "cost10_hit_rate": 0.6, "max_year_concentration_pct": 40},
        {"split": "validation", "events": 50, "cost10_mean_bps": 30, "cost10_hit_rate": 0.58, "max_year_concentration_pct": 95},
        {"split": "tail", "events": 60, "cost10_mean_bps": 70, "cost10_hit_rate": 0.62, "max_year_concentration_pct": 50},
    ])
    nonov = {"events": 40, "cost10_mean_bps": 60, "max_drawdown_cost10_bps": -500}
    overlap = pd.DataFrame([{"status": "AVAILABLE", "jaccard": 0.1}])
    status, decision, reasons = decide_stage127(split_df, nonov, overlap)
    assert status == "WATCH_FORWARD_SHADOW_DECONCENTRATION_REQUIRED"
    assert any("validation_year_concentration" in r for r in reasons)
