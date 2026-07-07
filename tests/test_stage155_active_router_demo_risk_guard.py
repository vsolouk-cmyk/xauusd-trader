from pathlib import Path
import sys
import json
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage154_active_shortlist_rule_router import normalize_family_key, load_blocked_demo_families, choose_active_candidate
from app.stage151_locked_mtf_rule_state_writer import compute_latest_features

def test_family_key_normalization():
    rid = "D150C_M5_ret_3h_bps_GEQ65__ret_24h_bps_GEQ35"
    assert normalize_family_key(rid) == "D150C_M5_ret_3h_bps__ret_24h_bps"


def test_load_blocked_demo_families(tmp_path):
    p = tmp_path / "risk.json"
    p.write_text(json.dumps({"per_family":[{"family_key":"A_B","closed_trade_count":1,"total_bps":-1.0,"mean_bps":-1.0,"total_net_profit":-1.0},{"family_key":"C_D","closed_trade_count":1,"total_bps":2.0,"mean_bps":2.0,"total_net_profit":1.0}]}), encoding="utf-8")
    blocked, rows = load_blocked_demo_families(p, True)
    assert blocked == {"A_B"}
    assert rows[0]["family_key"] == "A_B"


def test_choose_active_skips_blocked_family():
    latest = {"a": 10.0, "b": 10.0}
    rows = [
        {"rule_id":"A_GEQ65__B_GEQ35","gate":"PASS","excluded":"false","validation_mean_bps":"5","validation_hit_rate":"0.6","tail_mean_bps":"10","tail_hit_rate":"0.6","tail_events":"100","validation_events":"100","conditions_json":json.dumps([{"feature":"a","op":">=","threshold":1}])},
        {"rule_id":"C_GEQ65__D_GEQ35","gate":"PASS","excluded":"false","validation_mean_bps":"4","validation_hit_rate":"0.6","tail_mean_bps":"8","tail_hit_rate":"0.6","tail_events":"100","validation_events":"100","conditions_json":json.dumps([{"feature":"b","op":">=","threshold":1}])},
    ]
    selected, active, eligible, blocked_count = choose_active_candidate(rows, latest, 2, 0.53, 1, 0.5, 300, blocked_family_keys={"A__B"})
    assert blocked_count == 1
    assert selected["rule_id"] == "C_GEQ65__D_GEQ35"
