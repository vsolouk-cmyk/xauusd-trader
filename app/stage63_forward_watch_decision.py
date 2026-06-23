#!/usr/bin/env python3
"""Stage63 forward-watch decision pack.

Classifies Stage52 raw forward-shadow and Stage58B context-aware forward-shadow
without placing orders and without changing state DBs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def load_json(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def classify_quality(metrics: Dict[str, Any], gates: List[Dict[str, Any]], *, min_mean: float, min_wr: float, min_median: float, max_neg: int) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    mean = metrics.get('evaluated_mean_stress_bps')
    wr = metrics.get('evaluated_win_rate')
    median = metrics.get('evaluated_median_stress_bps')
    neg = metrics.get('negative_candidate_mean_count')
    if mean is None or mean < min_mean:
        reasons.append('evaluated_mean_stress_bps')
    if wr is None or wr < min_wr:
        reasons.append('evaluated_win_rate')
    if median is None or median < min_median:
        reasons.append('evaluated_median_stress_bps')
    if neg is None or neg > max_neg:
        reasons.append('negative_candidate_mean_count')
    for g in gates:
        if g.get('gate') in {'evaluated_mean_stress_bps','evaluated_win_rate','evaluated_median_stress_bps','negative_candidate_mean_count'} and not g.get('passed'):
            if g.get('gate') not in reasons:
                reasons.append(str(g.get('gate')))
    return (len(reasons) == 0, reasons)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.', help='repo root')
    ap.add_argument('--stage52-runner', default='reports/stage52_forward_shadow/stage52_import_then_forward_shadow_summary.json')
    ap.add_argument('--stage53-gates', default='reports/stage53_forward_shadow_prep/stage53_forward_shadow_gate_summary.json')
    ap.add_argument('--stage58b-summary', default='reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json')
    ap.add_argument('--stage59-gates', default='reports/stage59_context_forward_gates/stage59_context_forward_gate_summary.json')
    ap.add_argument('--config', default='configs/stage63_forward_watch_decision.json')
    ap.add_argument('--out', default='reports/stage63_forward_watch_decision')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = (root / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    cfg_path = root / args.config
    if cfg_path.exists():
        cfg = load_json(cfg_path)
    else:
        cfg = {}
    th = cfg.get('thresholds', {})
    min_mean = float(th.get('min_mean_stress_bps', 2.0))
    min_wr = float(th.get('min_win_rate', 0.53))
    min_median = float(th.get('min_median_stress_bps', 0.0))
    max_neg = int(th.get('max_negative_candidate_mean_count', 1))

    stage52_runner = load_json(root / args.stage52_runner)
    stage53 = load_json(root / args.stage53_gates)
    stage58b = load_json(root / args.stage58b_summary)
    stage59 = load_json(root / args.stage59_gates)

    s52_metrics = stage53.get('metrics') or {}
    s52_gates = stage53.get('gates') or []
    s58_metrics = stage59.get('metrics') or {}
    s58_gates = stage59.get('gates') or []

    s52_quality_ok, s52_quality_fail = classify_quality(s52_metrics, s52_gates, min_mean=min_mean, min_wr=min_wr, min_median=min_median, max_neg=max_neg)
    s58_quality_ok, s58_quality_fail = classify_quality(s58_metrics, s58_gates, min_mean=min_mean, min_wr=min_wr, min_median=min_median, max_neg=max_neg)

    s52_failed = stage53.get('failed_gates') or []
    s58_failed = stage59.get('failed_gates') or []

    # Stage52 has enough count but now fails quality: demote from promotion path.
    s52_count_ready = bool(s52_metrics.get('true_forward_signals', 0) >= 100 and s52_metrics.get('evaluated_signals', 0) >= 60)
    if s52_count_ready and not s52_quality_ok:
        s52_decision = 'DEMOTE_TO_PASSIVE_REFERENCE_NO_PROMOTION'
    elif s52_quality_ok:
        s52_decision = 'CONTINUE_RAW_FORWARD_WATCH_NO_PROMOTION'
    else:
        s52_decision = 'CONTINUE_RAW_FORWARD_WATCH_LOW_CONFIDENCE_NO_PROMOTION'

    if s58_quality_ok:
        s58_decision = 'PRIMARY_CONTEXT_FORWARD_WATCH_NO_PROMOTION'
    else:
        s58_decision = 'CONTINUE_CONTEXT_FORWARD_WATCH_LOW_CONFIDENCE_NO_PROMOTION'

    overall = 'STAGE52_RAW_DEMOTED_STAGE58B_PRIMARY_CONTEXT_WATCH_NO_PROMOTION'
    next_allowed = 'CONTINUE_STAGE58B_CONTEXT_FORWARD_AND_KEEP_STAGE52_REFERENCE_NO_PROMOTION'

    summary = {
        'stage': 'Stage63_FORWARD_WATCH_DECISION_NO_PROMOTION',
        'status': 'DECISION_REPORT_COMPLETE_NO_PROMOTION',
        'promotion': 'NO_GO',
        'EA': 'NO_GO',
        'paper_live': 'NO_GO',
        'live': 'NO_GO',
        'paper_order': 'NO_GO',
        'decision': overall,
        'next_allowed_step': next_allowed,
        'generated_utc': utc_now(),
        'root': str(root),
        'inputs': {
            'stage52_runner': str(root / args.stage52_runner),
            'stage53_gates': str(root / args.stage53_gates),
            'stage58b_summary': str(root / args.stage58b_summary),
            'stage59_gates': str(root / args.stage59_gates),
        },
        'stage52_raw': {
            'decision': s52_decision,
            'quality_ok': s52_quality_ok,
            'quality_failed_fields': s52_quality_fail,
            'failed_gates': s52_failed,
            'metrics': {
                k: s52_metrics.get(k) for k in [
                    'true_forward_signals','evaluated_signals','pending_signals','backfill_signals',
                    'evaluated_mean_stress_bps','evaluated_median_stress_bps','evaluated_win_rate',
                    'negative_candidate_mean_count','forward_span_days','evaluated_span_days','max_day_share',
                    'max_candidate_share','distinct_candidate_ids'
                ]
            },
        },
        'stage58b_context': {
            'decision': s58_decision,
            'quality_ok': s58_quality_ok,
            'quality_failed_fields': s58_quality_fail,
            'failed_gates': s58_failed,
            'metrics': {
                k: s58_metrics.get(k) for k in [
                    'true_forward_signals','evaluated_signals','pending_signals','backfill_signals',
                    'evaluated_mean_stress_bps','evaluated_median_stress_bps','evaluated_win_rate',
                    'negative_candidate_mean_count','forward_span_days','evaluated_span_days','max_day_share',
                    'max_candidate_share','distinct_candidate_ids'
                ]
            },
        },
        'hard_blocks': ['NO_PAPER_ORDER','NO_EA_PROMOTION','NO_PAPER_LIVE','NO_LIVE','NO_BROKER_CONNECTION'],
    }

    (out / 'stage63_forward_watch_decision_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    def fmt(v: Any) -> str:
        return 'null' if v is None else str(v)

    s52m = summary['stage52_raw']['metrics']
    s58m = summary['stage58b_context']['metrics']
    report = f"""# Stage63 Forward Watch Decision - No Promotion

- status: `DECISION_REPORT_COMPLETE_NO_PROMOTION`
- decision: `{overall}`
- next_allowed_step: `{next_allowed}`
- promotion: `NO_GO`
- paper_order: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Stage52 raw decision

Decision: `{s52_decision}`

Stage52 raw has enough forward count, but it is not a promotion candidate because its quality gates are not stable enough.

| metric | value |
|---|---:|
| true_forward_signals | {fmt(s52m.get('true_forward_signals'))} |
| evaluated_signals | {fmt(s52m.get('evaluated_signals'))} |
| pending_signals | {fmt(s52m.get('pending_signals'))} |
| backfill_signals | {fmt(s52m.get('backfill_signals'))} |
| evaluated_mean_stress_bps | {fmt(s52m.get('evaluated_mean_stress_bps'))} |
| evaluated_median_stress_bps | {fmt(s52m.get('evaluated_median_stress_bps'))} |
| evaluated_win_rate | {fmt(s52m.get('evaluated_win_rate'))} |
| negative_candidate_mean_count | {fmt(s52m.get('negative_candidate_mean_count'))} |
| forward_span_days | {fmt(s52m.get('forward_span_days'))} |
| evaluated_span_days | {fmt(s52m.get('evaluated_span_days'))} |
| max_day_share | {fmt(s52m.get('max_day_share'))} |

Failed quality fields: `{', '.join(s52_quality_fail) if s52_quality_fail else 'none'}`

## Stage58B context decision

Decision: `{s58_decision}`

Stage58B is the primary context-aware watch path. It is not promoted because sample count and time span are still insufficient, but its current quality profile remains stronger than Stage52 raw.

| metric | value |
|---|---:|
| true_forward_signals | {fmt(s58m.get('true_forward_signals'))} |
| evaluated_signals | {fmt(s58m.get('evaluated_signals'))} |
| pending_signals | {fmt(s58m.get('pending_signals'))} |
| backfill_signals | {fmt(s58m.get('backfill_signals'))} |
| evaluated_mean_stress_bps | {fmt(s58m.get('evaluated_mean_stress_bps'))} |
| evaluated_median_stress_bps | {fmt(s58m.get('evaluated_median_stress_bps'))} |
| evaluated_win_rate | {fmt(s58m.get('evaluated_win_rate'))} |
| negative_candidate_mean_count | {fmt(s58m.get('negative_candidate_mean_count'))} |
| forward_span_days | {fmt(s58m.get('forward_span_days'))} |
| evaluated_span_days | {fmt(s58m.get('evaluated_span_days'))} |
| max_day_share | {fmt(s58m.get('max_day_share'))} |

## Operational constraints

No order path is authorized by this decision pack. Stage61 demo execution only proved plumbing and does not prove edge. Continue Stage58B context forward shadow. Keep Stage52 raw only as a reference/control stream.
"""
    (out / 'stage63_forward_watch_decision_report.md').write_text(report, encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
