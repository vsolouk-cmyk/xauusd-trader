import json
import subprocess
import sys
from pathlib import Path


def test_stage171c_smoke(tmp_path):
    root = tmp_path
    app = root / "app"
    app.mkdir()
    data = root / "data/macro_regime/normalized"
    data.mkdir(parents=True)
    (data / "stage64k_full_scope_lag_safe_feature_dataset.csv").write_text(
        "time_utc,gold_sma20_over_50,dxy_ret_20d,real_yield_change_20d,etf_flow_tonnes_3m\n"
        "2026-01-01T00:00:00Z,1,-0.1,-0.2,3\n",
        encoding="utf-8",
    )
    fwd = root / "data/forward_shadow"
    fwd.mkdir(parents=True)
    (fwd / "stage65_macro_signal_ledger.csv").write_text(
        "time_utc,rule_id,signal\n2026-01-01T00:00:00Z,H64L_H1_FULL_MACRO_TAILWIND_LONG,1\n",
        encoding="utf-8",
    )
    reports = root / "reports/stage171b_h64l_exact_rule_extraction_and_shadow_start"
    reports.mkdir(parents=True)
    s = reports / "summary.json"
    s.write_text(json.dumps({"decision":"X","exact_rule_locked":False}), encoding="utf-8")
    r = reports / "rule.json"
    r.write_text(json.dumps({"exact_rule_locked":False,"conditions":["gold_sma20_over_50 > 0"]}), encoding="utf-8")
    a = reports / "asof.csv"
    a.write_text("feature,mechanical_fix_required\ngold,use completed bars\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "app" / "stage171c_h64l_evidence_shadow_checklist.py"
    out = subprocess.check_output([
        sys.executable, str(script), "--root", str(root), "--stage171b-summary", str(s),
        "--locked-rule-candidate", str(r), "--targeted-asof-plan", str(a)
    ], text=True)
    payload = json.loads(out)
    summary = json.loads(Path(payload["summary"]).read_text())
    assert summary["order_routing_allowed"] is False
    assert summary["current_shadow_checklist"]["all_pass"] is True
