from pathlib import Path
import csv
import json

from app.stage119_portfolio_observer_readiness_review import run


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys=[]
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open('w', newline='', encoding='utf-8') as fh:
        w=csv.DictWriter(fh, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def test_stage119_smoke(tmp_path: Path):
    root=tmp_path
    d=root/'reports'/'stage118_macro_cot_spdr_hard_audit'
    write_csv(d/'stage118_selected_for_stage119.csv', [
        {'rule_id':'A','description':'a','audit_decision':'HARD_PASS_STAGE119_AUDIT_QUEUE','candidate_only':'False','stage116_dxy_fallback_active':'True','stage116_direct_dxy_valid':'False','stage116_spdr_status':'VALIDATED_CANDIDATE'},
        {'rule_id':'B','description':'b','audit_decision':'WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION','candidate_only':'True','stage116_dxy_fallback_active':'True','stage116_direct_dxy_valid':'False','stage116_spdr_status':'VALIDATED_CANDIDATE'},
    ])
    write_csv(d/'stage118_rule_audit_metrics.csv', [])
    write_csv(d/'stage118_cost_stress_summary.csv', [
        {'rule_id':'A','split':'validation','cost_bps':'10','raw_mean_bps':'50','raw_hit_rate':'0.6','nonoverlap_mean_bps':'40'},
        {'rule_id':'A','split':'tail_forward_proxy','cost_bps':'10','raw_mean_bps':'80','raw_hit_rate':'0.7','nonoverlap_mean_bps':'70'},
        {'rule_id':'B','split':'validation','cost_bps':'10','raw_mean_bps':'10','raw_hit_rate':'0.5','nonoverlap_mean_bps':'10'},
        {'rule_id':'B','split':'tail_forward_proxy','cost_bps':'10','raw_mean_bps':'5','raw_hit_rate':'0.5','nonoverlap_mean_bps':'5'},
    ])
    write_csv(d/'stage118_overlap_matrix.csv', [{'rule_id_a':'A','rule_id_b':'B','raw_hourly_jaccard':'0.1','raw_hourly_intersection':'1','raw_hourly_union':'10'}])
    write_csv(d/'stage118_feature_coverage_by_rule.csv', [{'rule_id':'A','feature':'x','full_coverage_pct':'100','event_coverage_pct':'100'}])
    sdir=root/'reports'/'stage116_source_specific_wgc_spdr_dxy_validator'
    sdir.mkdir(parents=True)
    (sdir/'stage116_source_specific_wgc_spdr_dxy_validator_summary.json').write_text(json.dumps({'direct_dxy_valid':False,'dxy_fallback_active':True,'spdr_gld_status':'VALIDATED_CANDIDATE'}))
    summary=run(root)
    assert summary['primary_count'] == 1
    assert (root/'reports'/'stage119_portfolio_observer_readiness_review'/'stage119_rule_readiness_scores.csv').exists()
    assert 'NO_ORDER' not in summary['decision'] or summary['decision'].endswith('NO_UPDATE')
