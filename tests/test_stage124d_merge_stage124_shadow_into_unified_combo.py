import json
from pathlib import Path
import csv

from app.stage124d_merge_stage124_shadow_into_unified_combo import run, EA_SOURCE


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def test_stage124d_merges_stage124_shadow(tmp_path):
    root = tmp_path
    rep = root / 'reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery'
    rep.mkdir(parents=True)
    overlay = root / 'data/shadow_observer/stage124c_unified_observer_signal_overlay_preview.csv'
    rows = [{'rule_id': f'OLD_{i}', 'allow_trading': 'false', 'observer_only': 'true'} for i in range(7)]
    write_csv(overlay, rows)
    kv = root / 'data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv'
    kv.parent.mkdir(parents=True, exist_ok=True)
    kv.write_text('rule_id,S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN\nrule_status,PASS_STATIC_REPLAY\nallow_trading,false\n', encoding='utf-8')
    summary = {
        'replay_status': 'PASS_STATIC_REPLAY',
        'combo_overlay_preview_repo': str(overlay),
        'mt5_shadow_kv_repo': str(kv),
        'selected_for_stage125_count': 0,
    }
    (rep / 'stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    out = run(root, root/'mt5_files', root/'mt5_experts', True, True)
    assert out['status'].startswith('STAGE124D_COMPLETE')
    assert out['stage124_rule_added_to_combo_shadow'] is True
    assert out['merged_combo_estimated_rule_count'] == 8
    assert (root/'mt5_files/xauusd_stage124d_unified_combo_plus_stage124_shadow.csv').exists()
    assert (root/'mt5_experts/XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5').exists()


def test_ea_source_no_order_terms():
    assert 'CTrade' not in EA_SOURCE
    assert 'OrderSend' not in EA_SOURCE
    assert 'Trading remains disabled' in EA_SOURCE
