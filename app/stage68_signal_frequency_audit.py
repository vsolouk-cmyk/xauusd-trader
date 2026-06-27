
#!/usr/bin/env python3
"""Stage68 signal frequency audit for Stage67D6 + Stage66J3 macro-regime rules.
Local-only. No broker, no order, no downloads.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RULES = {
    "h64l_v2": {
        "label": "H64L v2",
        "type": "primary",
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", "<", 0.0),
            ("real_yield_change_20d", "<", 0.0),
            ("etf_flow_tonnes_3m", ">", 0.0),
            ("central_bank_demand_tonnes_3m", ">", 0.0),
            ("gold_sma50_over_200", ">", 0.0),
        ],
    },
    "d3_h60": {
        "label": "D3 Dollar Relief Trend Continuation H60",
        "type": "complementary_primary",
        "horizon_trading_days": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
            ("dxy_ret_20d", "<", 0.0),
        ],
    },
    "d1_backup": {
        "label": "D1 DXY Real Yield Gold Trend H60",
        "type": "backup",
        "horizon_trading_days": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", "<", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    "d4_backup": {
        "label": "D4 Vol Risk-Off Real Yield Gold Long H60",
        "type": "backup",
        "horizon_trading_days": 60,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
}

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE68",
    "NO_THRESHOLD_TUNING_FROM_FREQUENCY_AUDIT",
]


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == '' or s.lower() in {'nan', 'none', 'null', 'na', 'n/a'}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def parse_date(v: Any) -> str:
    s = str(v).strip()
    if not s:
        return ''
    # Keep date part only; accepted input is expected ISO-like.
    return s[:10]


def condition_pass(value: Optional[float], op: str, threshold: float) -> Optional[bool]:
    if value is None:
        return None
    if op == '>':
        return value > threshold
    if op == '<':
        return value < threshold
    if op == '>=':
        return value >= threshold
    if op == '<=':
        return value <= threshold
    raise ValueError(f'unsupported operator {op}')


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def evaluate_rule(rows: List[Dict[str, str]], date_col: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    active_flags: List[bool] = []
    evaluable_flags: List[bool] = []
    missing_value_count = 0
    missing_column_names = sorted({c for c, _, _ in rule['conditions'] if c not in rows[0]}) if rows else []
    latest_condition_results = []

    for row in rows:
        all_present = True
        all_pass = True
        condition_results = []
        for col, op, threshold in rule['conditions']:
            val = parse_float(row.get(col)) if col in row else None
            passed = condition_pass(val, op, threshold) if col in row else None
            if passed is None:
                all_present = False
                all_pass = False
                missing_value_count += 1
            elif not passed:
                all_pass = False
            condition_results.append({"column": col, "operator": op, "threshold": threshold, "value": val, "passed": passed})
        evaluable_flags.append(all_present)
        active_flags.append(all_present and all_pass)
        latest_condition_results = condition_results

    dates = [parse_date(r.get(date_col, '')) for r in rows]
    active_indices = [i for i, x in enumerate(active_flags) if x]
    active_dates = [dates[i] for i in active_indices]

    episodes = []
    if active_indices:
        start_i = prev_i = active_indices[0]
        for i in active_indices[1:]:
            if i == prev_i + 1:
                prev_i = i
            else:
                episodes.append((start_i, prev_i))
                start_i = prev_i = i
        episodes.append((start_i, prev_i))

    # no-overlap count: earliest active entry, then skip horizon trading rows
    horizon = int(rule.get('horizon_trading_days', 0) or 0)
    entries = []
    next_allowed = 0
    for i, flag in enumerate(active_flags):
        if flag and i >= next_allowed:
            entries.append(i)
            next_allowed = i + max(horizon, 1)

    # year stats
    years: Dict[str, Dict[str, int]] = {}
    for i, d in enumerate(dates):
        if not d or len(d) < 4:
            continue
        y = d[:4]
        ys = years.setdefault(y, {"rows": 0, "evaluable_rows": 0, "active_days": 0, "entries": 0})
        ys['rows'] += 1
        if evaluable_flags[i]:
            ys['evaluable_rows'] += 1
        if active_flags[i]:
            ys['active_days'] += 1
    for i in entries:
        d = dates[i]
        if d and len(d) >= 4:
            years.setdefault(d[:4], {"rows": 0, "evaluable_rows": 0, "active_days": 0, "entries": 0})['entries'] += 1

    episode_lengths = [b - a + 1 for a, b in episodes]
    gap_days = []
    # approximate calendar gaps between episode end/start where ISO dates parse
    for (_, end_i), (start_j, _) in zip(episodes, episodes[1:]):
        try:
            end_dt = datetime.fromisoformat(dates[end_i]).date()
            start_dt = datetime.fromisoformat(dates[start_j]).date()
            gap_days.append((start_dt - end_dt).days)
        except Exception:
            pass

    n = len(rows)
    evaluable_count = sum(1 for x in evaluable_flags if x)
    active_count = len(active_indices)
    return {
        "label": rule['label'],
        "type": rule['type'],
        "horizon_trading_days": horizon,
        "missing_columns": missing_column_names,
        "required_columns": [c for c, _, _ in rule['conditions']],
        "total_rows": n,
        "evaluable_rows": evaluable_count,
        "active_days": active_count,
        "active_pct_of_total": round(active_count / n * 100.0, 4) if n else 0.0,
        "active_pct_of_evaluable": round(active_count / evaluable_count * 100.0, 4) if evaluable_count else 0.0,
        "contiguous_episode_count": len(episodes),
        "no_overlap_entry_count": len(entries),
        "first_active_date": active_dates[0] if active_dates else None,
        "last_active_date": active_dates[-1] if active_dates else None,
        "avg_episode_length_trading_days": round(sum(episode_lengths) / len(episode_lengths), 3) if episode_lengths else 0.0,
        "max_episode_length_trading_days": max(episode_lengths) if episode_lengths else 0,
        "max_calendar_gap_between_episodes_days": max(gap_days) if gap_days else None,
        "latest_condition_results": latest_condition_results,
        "year_stats": years,
        "entry_dates": [dates[i] for i in entries],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--config', default='configs/stage68_signal_frequency_audit.json')
    ap.add_argument('--out', default='reports/stage68_signal_frequency_audit')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve()
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))

    macro_rel = cfg.get('macro_dataset', 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv')
    macro_path = (root / macro_rel).resolve()
    out_dir = (root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    issues: List[str] = []
    status = 'STAGE68_COMPLETE_NO_PROMOTION'
    decision = 'STAGE68_SIGNAL_FREQUENCY_AUDIT_COMPLETE_NO_ORDER'
    classification = 'S68_FREQUENCY_AUDIT_COMPLETE'

    if not macro_path.exists():
        issues.append('MACRO_DATASET_MISSING')
        status = 'STAGE68_STOP_NO_PROMOTION'
        decision = 'STAGE68_STOP_MISSING_MACRO_DATASET_NO_ORDER'
        classification = 'S68_STOP'
        rows: List[Dict[str, str]] = []
        columns: List[str] = []
    else:
        columns, rows = read_csv_rows(macro_path)

    date_col = 'feature_date_utc' if 'feature_date_utc' in columns else ('date_utc' if 'date_utc' in columns else '')
    if rows and not date_col:
        issues.append('DATE_COLUMN_MISSING')
        status = 'STAGE68_STOP_NO_PROMOTION'
        decision = 'STAGE68_STOP_SCHEMA_ISSUE_NO_ORDER'
        classification = 'S68_STOP'

    rule_metrics = {}
    if rows and date_col:
        for key, rule in RULES.items():
            rule_metrics[key] = evaluate_rule(rows, date_col, rule)

    # Combined flags from reconstructed active days
    combined = {}
    if rows and date_col and rule_metrics:
        # Re-evaluate active booleans for combined metrics.
        def active_bool(row, rule):
            for col, op, thr in rule['conditions']:
                val = parse_float(row.get(col))
                p = condition_pass(val, op, thr)
                if p is not True:
                    return False
            return True
        combos = {
            'any_primary_h64l_or_d3': ['h64l_v2', 'd3_h60'],
            'any_all_four_rules': ['h64l_v2', 'd3_h60', 'd1_backup', 'd4_backup'],
            'any_backup_d1_or_d4': ['d1_backup', 'd4_backup'],
        }
        for combo_key, keys in combos.items():
            flags = [any(active_bool(row, RULES[k]) for k in keys) for row in rows]
            active_days = sum(1 for x in flags if x)
            episodes = 0
            prev = False
            for f in flags:
                if f and not prev:
                    episodes += 1
                prev = f
            combined[combo_key] = {
                'rule_keys': keys,
                'active_days': active_days,
                'active_pct_of_total': round(active_days / len(rows) * 100.0, 4) if rows else 0.0,
                'contiguous_episode_count': episodes,
            }

    # Frequency posture.
    posture = 'UNKNOWN'
    if rule_metrics:
        any_primary_entries = sum(rule_metrics[k]['no_overlap_entry_count'] for k in ['h64l_v2', 'd3_h60'])
        any_entries = sum(rule_metrics[k]['no_overlap_entry_count'] for k in rule_metrics)
        years = max(1.0, len(rows) / 252.0)
        entries_per_year_all = any_entries / years
        entries_per_year_primary = any_primary_entries / years
        if entries_per_year_primary < 1.0:
            posture = 'PRIMARY_FREQUENCY_VERY_LOW'
        elif entries_per_year_all < 3.0:
            posture = 'SYSTEM_FREQUENCY_LOW'
        else:
            posture = 'SYSTEM_FREQUENCY_MODERATE_BUT_CLUSTERED_CHECK_OVERLAP'
    else:
        entries_per_year_all = None
        entries_per_year_primary = None

    summary = {
        'stage': 'Stage68_SIGNAL_FREQUENCY_AUDIT',
        'root': str(root),
        'config': str(args.config),
        'generated_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'status': status,
        'decision': decision,
        'classification': classification,
        'macro_dataset': {
            'path': str(macro_path),
            'exists': macro_path.exists(),
            'rows': len(rows),
            'columns': columns,
            'date_col': date_col or None,
            'min_date': parse_date(rows[0].get(date_col, '')) if rows and date_col else None,
            'max_date': parse_date(rows[-1].get(date_col, '')) if rows and date_col else None,
            'sha256': sha256_path(macro_path) if macro_path.exists() else None,
        },
        'frequency_posture': posture,
        'estimated_no_overlap_entries_per_year': {
            'primary_only_h64l_plus_d3': round(entries_per_year_primary, 3) if entries_per_year_primary is not None else None,
            'all_four_naive_sum': round(entries_per_year_all, 3) if entries_per_year_all is not None else None,
            'note': 'Naive sums do not de-duplicate overlapping rules; use combined active metrics and entry dates for overlap review.',
        },
        'rule_metrics': rule_metrics,
        'combined_metrics': combined,
        'issues': issues,
        'hard_blocks': HARD_BLOCKS,
        'operator_instructions': [
            'Stage68 is diagnostic only and cannot authorize orders.',
            'Do not tune thresholds from this audit alone.',
            'If frequency is too low, add pre-registered complementary theses and audit them separately before any readiness path.',
            'Broker, EA, paper-live, and live paths remain blocked.',
        ],
        'outputs': {
            'summary_json': str(out_dir / 'stage68_signal_frequency_audit_summary.json'),
            'report_md': str(out_dir / 'stage68_signal_frequency_audit_report.md'),
            'yearly_csv': str(out_dir / 'stage68_signal_frequency_yearly.csv'),
            'entries_csv': str(out_dir / 'stage68_signal_frequency_entries.csv'),
        },
    }

    (out_dir / 'stage68_signal_frequency_audit_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    # Yearly CSV
    with (out_dir / 'stage68_signal_frequency_yearly.csv').open('w', newline='', encoding='utf-8') as f:
        fieldnames = ['rule_key', 'year', 'rows', 'evaluable_rows', 'active_days', 'entries']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rk, m in rule_metrics.items():
            for year, ys in sorted(m.get('year_stats', {}).items()):
                row = {'rule_key': rk, 'year': year}
                row.update(ys)
                w.writerow(row)

    with (out_dir / 'stage68_signal_frequency_entries.csv').open('w', newline='', encoding='utf-8') as f:
        fieldnames = ['rule_key', 'entry_date']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for rk, m in rule_metrics.items():
            for d in m.get('entry_dates', []):
                w.writerow({'rule_key': rk, 'entry_date': d})

    lines = []
    lines.append('# Stage68 Signal Frequency Audit')
    lines.append('')
    lines.append('## Decision')
    lines.append('')
    lines.append(f"- status: `{status}`")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- classification: `{classification}`")
    lines.append(f"- frequency_posture: `{posture}`")
    lines.append('')
    lines.append('## Macro dataset')
    lines.append('')
    lines.append(f"- rows: `{len(rows)}`")
    lines.append(f"- min_date: `{summary['macro_dataset']['min_date']}`")
    lines.append(f"- max_date: `{summary['macro_dataset']['max_date']}`")
    lines.append(f"- path: `{macro_path}`")
    lines.append('')
    lines.append('## Rule frequency')
    lines.append('')
    for rk, m in rule_metrics.items():
        lines.append(f"### `{rk}`")
        lines.append('')
        lines.append(f"- label: `{m['label']}`")
        lines.append(f"- type: `{m['type']}`")
        lines.append(f"- horizon_trading_days: `{m['horizon_trading_days']}`")
        lines.append(f"- evaluable_rows: `{m['evaluable_rows']}`")
        lines.append(f"- active_days: `{m['active_days']}`")
        lines.append(f"- active_pct_of_evaluable: `{m['active_pct_of_evaluable']}`")
        lines.append(f"- contiguous_episode_count: `{m['contiguous_episode_count']}`")
        lines.append(f"- no_overlap_entry_count: `{m['no_overlap_entry_count']}`")
        lines.append(f"- first_active_date: `{m['first_active_date']}`")
        lines.append(f"- last_active_date: `{m['last_active_date']}`")
        lines.append(f"- max_calendar_gap_between_episodes_days: `{m['max_calendar_gap_between_episodes_days']}`")
        if m['missing_columns']:
            lines.append(f"- missing_columns: `{';'.join(m['missing_columns'])}`")
        lines.append('')
    lines.append('## Combined metrics')
    lines.append('')
    for ck, cm in combined.items():
        lines.append(f"- `{ck}`: active_days=`{cm['active_days']}`, active_pct=`{cm['active_pct_of_total']}`, episodes=`{cm['contiguous_episode_count']}`")
    lines.append('')
    lines.append('## Issues')
    lines.append('')
    if issues:
        for i in issues:
            lines.append(f'- `{i}`')
    else:
        lines.append('- none')
    lines.append('')
    lines.append('## Hard blocks')
    lines.append('')
    for hb in HARD_BLOCKS:
        lines.append(f'- `{hb}`')
    (out_dir / 'stage68_signal_frequency_audit_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(json.dumps({
        'stage': summary['stage'],
        'status': status,
        'decision': decision,
        'classification': classification,
        'frequency_posture': posture,
        'summary_json': summary['outputs']['summary_json'],
        'report_md': summary['outputs']['report_md'],
    }, indent=2))
    return 0 if status == 'STAGE68_COMPLETE_NO_PROMOTION' else 2

if __name__ == '__main__':
    raise SystemExit(main())
