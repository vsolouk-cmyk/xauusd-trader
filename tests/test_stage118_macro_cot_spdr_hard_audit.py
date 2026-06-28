from pathlib import Path
import json
import pandas as pd

from app.stage118_macro_cot_spdr_hard_audit import make_rule_mask, RuleSpec, run


def test_rule_mask_basic():
    df = pd.DataFrame({
        "real_yield_10y_chg_20d": [-0.2, 0.1],
        "dollar_pressure_chg_20d": [-2.0, -2.0],
        "cot_mm_net_z": [0.5, 0.5],
    })
    rule = RuleSpec("x", "x", ["real_yield_10y_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"], "RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED")
    mask = make_rule_mask(df, rule, {"real_yield_10y_chg_20d_q25": -0.1, "dollar_pressure_chg_20d_q25": -1.0})
    assert mask.tolist() == [True, False]


def test_stage118_run_smoke(tmp_path: Path):
    root = tmp_path
    feature_dir = root / "data/fundamental_event_inbox/features"
    report117 = root / "reports/stage117_segmented_macro_cot_dollar_discovery"
    report116 = root / "reports/stage116_source_specific_wgc_spdr_dxy_validator"
    feature_dir.mkdir(parents=True)
    report117.mkdir(parents=True)
    report116.mkdir(parents=True)

    dates = pd.date_range("2024-01-01", periods=240, freq="h", tz="UTC")
    split = ["selection"]*120 + ["validation"]*60 + ["tail_forward_proxy"]*60
    df = pd.DataFrame({
        "utc_time": dates.astype(str),
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "fwd_ret_bps_h120": [50.0]*240,
        "split": split,
        "real_yield_10y_chg_20d": [-0.2]*240,
        "dollar_pressure_chg_20d": [-2.0]*240,
        "cot_mm_net_z": [0.0]*240,
        "spdr_value_chg_20d": [100.0]*240,
    })
    df.to_csv(feature_dir / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv", index=False)
    pd.DataFrame({"rule_id":["S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED","S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF"]}).to_csv(report117 / "stage117_selected_for_stage118.csv", index=False)
    pd.DataFrame([{"real_yield_10y_chg_20d_q25": -0.1, "dollar_pressure_chg_20d_q25": -1.0, "dollar_pressure_chg_20d_q50": 0.0, "spdr_value_chg_20d_q75": 10.0}]).to_csv(report117 / "stage117_selection_thresholds.csv", index=False)
    (report116 / "stage116_source_specific_wgc_spdr_dxy_validator_summary.json").write_text(json.dumps({"spdr_gld_status":"VALIDATED_CANDIDATE", "dxy_fallback_active": True}), encoding="utf-8")

    out = run(root, horizon_hours=120)
    assert out["audited_rule_count"] == 2
    assert Path(out["audit_metrics"]).exists()
    assert Path(out["selected_for_stage119"]).exists()
