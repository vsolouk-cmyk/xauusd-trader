#!/usr/bin/env python3
"""
Stage64S - Governance / Replication / No-Order Decision Fastlane

Reads Stage64R external spot transfer output and locks the survivor into a
research-only state. It does NOT run a new validation scan, does NOT create
orders, and does NOT connect to any broker.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def file_manifest(root: Path, paths: List[str]) -> List[Dict[str, Any]]:
    rows = []
    for rel in paths:
        p = root / rel
        rows.append({
            'path': rel,
            'found': p.exists(),
            'size_bytes': p.stat().st_size if p.exists() and p.is_file() else 0,
            'sha256': sha256_file(p),
        })
    return rows


def get_nested(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def csv_write_dicts(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def build(args: argparse.Namespace) -> int:
    repo = Path(args.root).expanduser().resolve()
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = repo / out
    out.mkdir(parents=True, exist_ok=True)

    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = repo / cfg_path
    cfg = read_json(cfg_path) if cfg_path.exists() else {}

    stage64r_path = repo / cfg.get('stage64r_summary', 'reports/stage64r_external_spot_d1_intake_transfer_fastlane/stage64r_external_spot_d1_intake_transfer_fastlane_summary.json')
    stage64n4_path = repo / cfg.get('stage64n4_summary', 'reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_summary.json')
    stage64k_dataset = repo / cfg.get('stage64k_dataset', 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv')
    external_d1 = repo / cfg.get('external_spot_d1', 'data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv')

    issues: List[str] = []
    if not stage64r_path.exists():
        issues.append(f'missing_stage64r_summary:{stage64r_path}')
        stage64r = {}
    else:
        stage64r = read_json(stage64r_path)

    r_decision = stage64r.get('decision')
    transfer_pass = bool(get_nested(stage64r, ['external_spot_transfer_validation', 'transfer_pass'], False))
    overall = get_nested(stage64r, ['external_spot_transfer_validation', 'overall'], {}) or {}
    split_rows = get_nested(stage64r, ['external_spot_transfer_validation', 'split_rows'], []) or []
    external_preflight_ok = bool(get_nested(stage64r, ['external_spot_preflight', 'external_preflight_ok'], False))

    expected_decision = cfg.get('required_stage64r_decision', 'EXTERNAL_SPOT_D1_TRANSFER_PASS_STAGE64S_GOVERNANCE_REPLICATION_ALLOWED_NO_ORDER')
    r_ok = (r_decision == expected_decision) and transfer_pass and external_preflight_ok

    if not r_ok:
        status = 'GOVERNANCE_REPLICATION_DECISION_BLOCKED_NO_PROMOTION'
        decision = 'STAGE64R_TRANSFER_NOT_CONFIRMED_STOP_OR_FIX_STAGE64R_NO_ORDER'
        next_step = 'FIX_STAGE64R_OR_STOP_NO_ORDER'
    else:
        status = 'GOVERNANCE_REPLICATION_NO_ORDER_DECISION_COMPLETE_NO_PROMOTION'
        decision = 'EXTERNAL_SPOT_TRANSFER_CONFIRMED_RESEARCH_SURVIVOR_STAGE65_FORWARD_SHADOW_DESIGN_ALLOWED_NO_ORDER'
        next_step = 'Stage65_FORWARD_SHADOW_AND_SIGNAL_LEDGER_FASTLANE_NO_ORDER'

    hard_blocks = [
        'NO_PAPER_ORDER',
        'NO_EA_PROMOTION',
        'NO_PAPER_LIVE',
        'NO_LIVE',
        'NO_BROKER_CONNECTION',
        'NO_ORDER_AUTHORIZATION_FROM_STAGE64S',
        'NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE',
        'NO_POST_HOC_EVENT_EXCLUSION',
        'NO_REDUCED_SCOPE_RETEST',
        'NO_RESCUE_FILTERING',
        'NO_NEW_INTRADAY_SCAN',
        'NO_COMMERCIALIZATION_WITHOUT_LATER_FORWARD_AND_BROKER_GOVERNANCE',
    ]

    target = stage64r.get('target_survivor') or {
        'hypothesis_id': 'H64L_H1_FULL_MACRO_TAILWIND_LONG',
        'horizon_days': 120,
        'primary_benchmark_id': 'EXTERNAL_SPOT_B1_TREND_ONLY_REFERENCE',
    }

    # This is a decision/gov stage, not a validation stage.
    decision_matrix = [
        {
            'path': 'External spot transfer',
            'status': 'PASS' if transfer_pass else 'BLOCKED',
            'decision': 'Hold survivor as research-only; proceed to no-order forward-shadow design.' if transfer_pass else 'Do not continue until Stage64R passes.',
            'allowed_next': next_step if transfer_pass else 'Fix Stage64R or stop',
        },
        {
            'path': 'Broker execution claim',
            'status': 'BLOCKED',
            'decision': 'External spot transfer is not a broker execution authorization. AMarkets/broker-specific execution remains blocked.',
            'allowed_next': 'Later broker governance and forward telemetry only; no broker connection now.',
        },
        {
            'path': 'Forward-only event governance',
            'status': 'RETAINED',
            'decision': 'Historical event filters remain forbidden; future blackout governance only after later gates.',
            'allowed_next': 'Ledger only, no historical validation uplift.',
        },
        {
            'path': 'Paper/live/order',
            'status': 'HARD_BLOCKED',
            'decision': 'NO_GO',
            'allowed_next': 'None',
        },
    ]

    forward_shadow_contract = {
        'contract_id': 'STAGE65_NO_ORDER_FORWARD_SHADOW_DAILY_SIGNAL_LEDGER',
        'purpose': 'Track the locked H64L_H1/h120 macro-regime survivor prospectively without orders.',
        'not_order_authorization': True,
        'locked_hypothesis': target,
        'locked_horizon_days': int(target.get('horizon_days', 120)),
        'signal_rule': 'Use the already predeclared H64L_H1_FULL_MACRO_TAILWIND_LONG rule only; no threshold tuning or new filters.',
        'allowed_outputs': [
            'daily signal state', 'as-of feature values', '120 trading day forward observation ledger',
            'event-calendar forward-only blackout annotations when known before event time'
        ],
        'forbidden_outputs': [
            'orders', 'broker connection', 'paper-live orders', 'EA promotion', 'live trading', 'historical event filtering', 'post-hoc exclusions'
        ],
        'minimum_pre_governance_forward_requirements_suggested': {
            'observed_new_signals_min': 5,
            'calendar_span_min_days': 180,
            'all_signal_rows_asof_lag_safe': True,
            'no_manual_override_backfill': True,
        },
        'reason_for_no_paper_yet': 'Stage64R validates external spot transfer, but not execution mechanics, slippage, broker-specific fills, or prospective behavior.',
    }

    replication_bundle_paths = [
        'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv',
        'data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv',
        'reports/stage64r_external_spot_d1_intake_transfer_fastlane/stage64r_external_spot_d1_intake_transfer_fastlane_summary.json',
        'reports/stage64r_external_spot_d1_intake_transfer_fastlane/stage64r_external_spot_d1_intake_transfer_fastlane_report.md',
        'reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_summary.json',
        'reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json',
        'reports/stage64l_full_scope_walk_forward_validation_design/stage64l_full_scope_walk_forward_validation_design_summary.json',
        'reports/stage64n1b_a2_nonparametric_reconciliation/stage64n1b_a2_nonparametric_reconciliation_summary.json',
        'configs/stage64r_external_spot_d1_intake_transfer_fastlane.json',
    ]
    manifest = file_manifest(repo, replication_bundle_paths)

    summary = {
        'stage': 'Stage64S_GOVERNANCE_REPLICATION_AND_NO_ORDER_DECISION_FASTLANE',
        'status': status,
        'decision': decision,
        'promotion': 'NO_GO',
        'EA': 'NO_GO',
        'paper_order': 'NO_GO',
        'paper_live': 'NO_GO',
        'live': 'NO_GO',
        'validation_allowed_for_order_or_promotion': False,
        'validation_run_performed': False,
        'order_path': 'NONE',
        'broker_connection': 'NONE',
        'generated_utc': utc_now(),
        'root': str(repo),
        'inputs': {
            'config': str(cfg_path),
            'stage64r_summary': str(stage64r_path),
            'stage64n4_summary': str(stage64n4_path),
            'stage64k_dataset': str(stage64k_dataset),
            'external_spot_d1': str(external_d1),
        },
        'input_checks': {
            'stage64r_decision': r_decision,
            'expected_stage64r_decision': expected_decision,
            'stage64r_decision_ok': r_decision == expected_decision,
            'external_preflight_ok': external_preflight_ok,
            'external_transfer_pass': transfer_pass,
            'stage64s_input_ok': r_ok,
            'issues': issues,
        },
        'target_survivor': target,
        'external_transfer_headline': overall,
        'split_rows': split_rows,
        'decision_matrix': decision_matrix,
        'forward_shadow_contract': forward_shadow_contract,
        'replication_manifest': manifest,
        'executive_conclusion': (
            'External spot D1 transfer passed. The survivor is now a research-confirmed, no-order candidate for forward-shadow design; '
            'no paper/live/broker path is authorized.' if r_ok else
            'Stage64R transfer is not confirmed; do not proceed.'
        ),
        'next_allowed_step': next_step,
        'hard_blocks': hard_blocks,
        'outputs': {
            'summary_json': str(out / 'stage64s_governance_replication_no_order_decision_summary.json'),
            'report_md': str(out / 'stage64s_governance_replication_no_order_decision_report.md'),
            'decision_matrix_csv': str(out / 'stage64s_decision_matrix.csv'),
            'forward_shadow_contract_json': str(out / 'stage64s_forward_shadow_contract.json'),
            'replication_manifest_json': str(out / 'stage64s_research_replication_manifest.json'),
        }
    }

    write_json(out / 'stage64s_governance_replication_no_order_decision_summary.json', summary)
    write_json(out / 'stage64s_forward_shadow_contract.json', forward_shadow_contract)
    write_json(out / 'stage64s_research_replication_manifest.json', {'created_utc': summary['generated_utc'], 'files': manifest})

    csv_write_dicts(out / 'stage64s_decision_matrix.csv', decision_matrix, ['path', 'status', 'decision', 'allowed_next'])

    report = []
    report.append('# Stage64S - Governance / Replication / No-Order Decision Fastlane\n')
    report.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    report.append('## Status\n')
    report.append(f"- status: `{status}`")
    report.append(f"- decision: `{decision}`")
    report.append('- promotion/paper/live: `NO_GO`')
    report.append('- validation_allowed_for_order_or_promotion: `False`')
    report.append('- validation_run_performed: `False`')
    report.append('\n## Executive conclusion\n')
    report.append(summary['executive_conclusion'])
    report.append('\n## External transfer headline\n')
    keys = ['joined_return_days','candidate_active_days','candidate_mean_bps','external_B1_active_days','external_B1_mean_bps','mean_excess_vs_external_B1_bps','one_sided_p_uncorrected_z_approx','positive_excess_splits_vs_external_B1','max_split_share_of_candidate_active_days','max_year_share_of_candidate_active_days']
    report.append('| metric | value |')
    report.append('|---|---:|')
    for k in keys:
        report.append(f"| `{k}` | `{overall.get(k)}` |")
    report.append('\n## Decision matrix\n')
    report.append('| path | status | decision | allowed_next |')
    report.append('|---|---|---|---|')
    for r in decision_matrix:
        report.append(f"| `{r['path']}` | `{r['status']}` | {r['decision']} | {r['allowed_next']} |")
    report.append('\n## Forward-shadow contract\n')
    report.append('- Locked survivor only; no new hypothesis scan, no rescue filter, no threshold tuning.')
    report.append('- Daily signal ledger is allowed; order generation is not allowed.')
    report.append('- Historical event-calendar filtering remains forbidden; future event blackout governance is annotation-only until later gates.')
    report.append('\n## Hard blocks\n')
    for b in hard_blocks:
        report.append(f'- `{b}`')
    report.append('\n## Next allowed step\n')
    report.append(f'`{next_step}`')
    (out / 'stage64s_governance_replication_no_order_decision_report.md').write_text('\n'.join(report) + '\n', encoding='utf-8')

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--config', default='configs/stage64s_governance_replication_no_order_fastlane.json')
    ap.add_argument('--out', default='reports/stage64s_governance_replication_no_order_fastlane')
    return build(ap.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
