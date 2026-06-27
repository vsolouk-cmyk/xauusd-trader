
#!/usr/bin/env python3
"""Stage90 Data Frontier Thesis Router.

Routes the next thesis-discovery step after current macro residual discovery is exhausted.
No trading, no broker connection, no threshold tuning, no EA/MT5 changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {'_read_error': str(e), '_path': str(path)}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_csv_header(path: Path) -> List[str]:
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            return next(reader, [])
    except Exception:
        try:
            with path.open('r', encoding='latin-1', newline='') as f:
                reader = csv.reader(f)
                return next(reader, [])
        except Exception:
            return []


def count_csv_rows(path: Path, max_scan: int = 500000) -> int:
    """Count data rows up to max_scan; enough for readiness without huge delays."""
    try:
        with path.open('r', encoding='utf-8-sig', errors='replace') as f:
            total = -1
            for total, _ in enumerate(f):
                if total >= max_scan:
                    return max_scan
            return max(total, 0)
    except Exception:
        return 0


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, '') for k in fieldnames})


def normalize_path(root: Path, raw: str) -> Path:
    raw = os.path.expanduser(raw)
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    return p


def find_candidate_files(root: Path, patterns: Iterable[str], max_results: int = 25) -> List[Path]:
    results: List[Path] = []
    for pattern in patterns:
        for p in root.glob(pattern):
            if p.is_file() and p not in results:
                results.append(p)
                if len(results) >= max_results:
                    return results
    return results


def inspect_macro_dataset(path: Path) -> Dict[str, Any]:
    header = load_csv_header(path) if path.exists() else []
    row_count = count_csv_rows(path, max_scan=10000) if path.exists() else 0
    lower = [h.lower() for h in header]
    def has_any(tokens: Iterable[str]) -> bool:
        return any(any(t in h for t in tokens) for h in lower)
    return {
        'path': str(path),
        'exists': path.exists(),
        'header_count': len(header),
        'row_count_sampled_or_exact': row_count,
        'columns': header,
        'has_cot_columns': has_any(['cot', 'cftc', 'managed_money', 'producer', 'swap_dealer']),
        'has_event_surprise_columns': has_any(['surprise', 'actual', 'forecast', 'previous', 'consensus']),
        'has_intraday_columns': has_any(['session', 'asia', 'london', 'ny_', 'range_breakout']),
        'has_etf_columns': has_any(['etf']),
        'has_central_bank_columns': has_any(['central_bank', 'official_sector']),
        'has_vix_columns': has_any(['vix']),
        'has_dxy_columns': has_any(['dxy']),
        'has_real_yield_columns': has_any(['real_yield']),
    }


def inspect_sqlite_db(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {'path': str(path), 'exists': path.exists(), 'read_ok': False, 'tables': [], 'bars': []}
    if not path.exists():
        return out
    try:
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        out['tables'] = tables
        if 'bars' in tables:
            cols = [r[1] for r in cur.execute('PRAGMA table_info(bars)').fetchall()]
            out['bars_columns'] = cols
            has_tf = 'timeframe' in cols
            has_src = 'source' in cols
            has_utc = 'utc_time' in cols
            row_count = cur.execute('SELECT COUNT(*) FROM bars').fetchone()[0]
            out['bars_row_count'] = int(row_count)
            out['bars_has_spread_col'] = 'spread' in cols
            out['bars_has_volume_col'] = 'volume' in cols
            if has_tf:
                q = 'SELECT timeframe, COUNT(*) FROM bars GROUP BY timeframe ORDER BY COUNT(*) DESC'
                out['bars_by_timeframe'] = [{'timeframe': r[0], 'row_count': int(r[1])} for r in cur.execute(q).fetchall()]
            if has_src:
                q = 'SELECT source, COUNT(*) FROM bars GROUP BY source ORDER BY COUNT(*) DESC'
                out['bars_by_source'] = [{'source': r[0], 'row_count': int(r[1])} for r in cur.execute(q).fetchall()]
            if has_utc:
                mn, mx = cur.execute('SELECT MIN(utc_time), MAX(utc_time) FROM bars').fetchone()
                out['bars_min_utc_time'] = mn
                out['bars_max_utc_time'] = mx
        con.close()
        out['read_ok'] = True
    except Exception as e:
        out['read_error'] = str(e)
    return out


def inspect_csv_file(path: Path) -> Dict[str, Any]:
    header = load_csv_header(path) if path.exists() else []
    lower = [h.lower() for h in header]
    return {
        'path': str(path),
        'exists': path.exists(),
        'row_count_sampled_or_exact': count_csv_rows(path, max_scan=500000) if path.exists() else 0,
        'columns': header,
        'has_time_col': any(h in ('time', 'datetime', 'date', 'utc_time', 'time_utc', 'feature_date_utc') or 'time' in h for h in lower),
        'has_price_cols': all(x in lower for x in ['open', 'high', 'low', 'close']) or 'close' in lower,
        'has_spread_col': 'spread' in lower,
        'has_volume_col': 'volume' in lower or 'tick_volume' in lower,
        'has_surprise_col': any('surprise' in h for h in lower),
        'has_actual_forecast_cols': any('actual' in h for h in lower) and any(('forecast' in h or 'consensus' in h) for h in lower),
    }


def score_frontiers(root: Path, cfg: Dict[str, Any], macro_info: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    paths_cfg = cfg.get('paths', {})
    exog_dir = normalize_path(root, paths_cfg.get('exogenous_dir', 'data/exogenous'))
    local_dir = normalize_path(root, paths_cfg.get('local_data_dir', 'data/local'))

    # COT / CFTC
    cot_patterns = paths_cfg.get('cot_file_patterns', ['data/**/*cot*.csv', 'data/**/*cftc*.csv', 'data/**/*COT*.csv'])
    cot_files = find_candidate_files(root, cot_patterns, max_results=20)
    cot_infos = [inspect_csv_file(p) for p in cot_files]
    cot_rows = max([x.get('row_count_sampled_or_exact', 0) for x in cot_infos] or [0])
    cot_has_file = bool(cot_files)

    # Event / calendar
    calendar_candidates = []
    for raw in paths_cfg.get('calendar_candidates', ['data/exogenous/calendar_events.csv', 'data/calendar_events.csv']):
        p = normalize_path(root, raw)
        if p.exists():
            calendar_candidates.append(p)
    event_infos = [inspect_csv_file(p) for p in calendar_candidates]
    event_rows = max([x.get('row_count_sampled_or_exact', 0) for x in event_infos] or [0])
    event_has_surprise = any(x.get('has_surprise_col') or x.get('has_actual_forecast_cols') for x in event_infos) or macro_info.get('has_event_surprise_columns')

    # Intraday SQLite / CSV
    db_candidates = []
    for raw in paths_cfg.get('sqlite_db_candidates', ['data/local/*.db', 'data/local/*.sqlite', 'data/**/*.db']):
        db_candidates.extend(find_candidate_files(root, [raw], max_results=10))
    seen = set(); db_candidates = [p for p in db_candidates if not (str(p) in seen or seen.add(str(p)))]
    db_infos = [inspect_sqlite_db(p) for p in db_candidates]
    bars_total = sum(int(x.get('bars_row_count', 0) or 0) for x in db_infos)
    timeframes = set()
    has_spread = False
    for x in db_infos:
        has_spread = has_spread or bool(x.get('bars_has_spread_col'))
        for r in x.get('bars_by_timeframe', []) or []:
            if r.get('timeframe'):
                timeframes.add(str(r.get('timeframe')).lower())
    csv_candidates = []
    for raw in paths_cfg.get('amarkets_csv_candidates', []):
        p = normalize_path(root, raw)
        if p.exists():
            csv_candidates.append(p)
    csv_infos = [inspect_csv_file(p) for p in csv_candidates]
    csv_rows = sum(int(x.get('row_count_sampled_or_exact', 0) or 0) for x in csv_infos)
    csv_has_spread = any(x.get('has_spread_col') for x in csv_infos)

    # ETF / CB already available but exhausted in macro-only residual search.
    macro_rows = int(macro_info.get('row_count_sampled_or_exact') or 0)

    frontier_rows: List[Dict[str, Any]] = []
    requirements: List[Dict[str, Any]] = []

    def add_requirement(frontier: str, requirement: str, status: str, detail: str = '') -> None:
        requirements.append({'frontier': frontier, 'requirement': requirement, 'status': status, 'detail': detail})

    cot_score = 0
    cot_score += 35 if cot_has_file else 0
    cot_score += 35 if macro_info.get('has_cot_columns') else 0
    cot_score += 20 if cot_rows >= 300 else (10 if cot_rows >= 100 else 0)
    cot_score += 10 if any(any(('managed' in c.lower() or 'producer' in c.lower() or 'swap' in c.lower()) for c in x.get('columns', [])) for x in cot_infos) else 0
    if not cot_has_file:
        add_requirement('COT_POSITIONING', 'gold COT/CFTC history CSV', 'MISSING', 'Need local weekly disaggregated gold COT with managed money / producer / swap fields.')
    else:
        add_requirement('COT_POSITIONING', 'gold COT/CFTC history CSV', 'PRESENT', f'{len(cot_files)} candidate file(s), max_rows={cot_rows}')
    if not macro_info.get('has_cot_columns'):
        add_requirement('COT_POSITIONING', 'lag-safe COT feature join into macro dataset', 'MISSING', 'Need cot_managed_money_z or equivalent lag-safe weekly state.')
    else:
        add_requirement('COT_POSITIONING', 'lag-safe COT feature join into macro dataset', 'PRESENT', '')

    event_score = 0
    event_score += 30 if bool(event_infos) else 0
    event_score += 35 if event_has_surprise else 0
    event_score += 20 if event_rows >= 250 else (10 if event_rows >= 50 else 0)
    event_score += 15 if any(x.get('has_time_col') for x in event_infos) else 0
    if not event_infos:
        add_requirement('EVENT_SURPRISE', 'economic event calendar history', 'MISSING', 'Need local CPI/NFP/FOMC/ISM/calendar events with dates/timestamps.')
    else:
        add_requirement('EVENT_SURPRISE', 'economic event calendar history', 'PRESENT', f'{len(event_infos)} calendar file(s), max_rows={event_rows}')
    if not event_has_surprise:
        add_requirement('EVENT_SURPRISE', 'surprise fields', 'MISSING', 'Need actual/forecast/consensus or precomputed surprise z-score.')
    else:
        add_requirement('EVENT_SURPRISE', 'surprise fields', 'PRESENT', '')

    intraday_score = 0
    intraday_score += 35 if bars_total >= 100000 else (20 if bars_total >= 10000 else 0)
    intraday_score += 20 if len(timeframes) >= 2 else (10 if len(timeframes) == 1 else 0)
    intraday_score += 15 if has_spread or csv_has_spread else 0
    intraday_score += 20 if csv_rows >= 100000 else (10 if csv_rows >= 10000 else 0)
    intraday_score += 10 if any(tf in timeframes for tf in ['m1', '1m', 'm5', '5m']) else 0
    if bars_total <= 0 and csv_rows <= 0:
        add_requirement('INTRADAY_SESSION', 'M1/M5 broker bars', 'MISSING', 'Need AMarkets M1/M5/H1 history in DB or CSV.')
    else:
        add_requirement('INTRADAY_SESSION', 'M1/M5 broker bars', 'PRESENT', f'db_bars={bars_total}, csv_rows_scanned={csv_rows}, timeframes={sorted(timeframes)}')
    if not (has_spread or csv_has_spread):
        add_requirement('INTRADAY_SESSION', 'spread/cost history', 'WEAK_OR_MISSING', 'Need spread coverage for cost-aware tests.')
    else:
        add_requirement('INTRADAY_SESSION', 'spread/cost history', 'PRESENT', '')

    flow_score = 0
    flow_score += 30 if macro_info.get('has_etf_columns') else 0
    flow_score += 30 if macro_info.get('has_central_bank_columns') else 0
    flow_score += 20 if macro_rows >= 3000 else (10 if macro_rows >= 1000 else 0)
    flow_score -= 20  # already used heavily in Stage77B/83/89; penalize repeated macro-only flow expansion.
    add_requirement('FLOW_REFINEMENT', 'ETF and central-bank columns in macro dataset', 'PRESENT' if flow_score > 0 else 'WEAK', 'Already heavily explored; only useful with new decomposition/source granularity.')

    frontiers = [
        {
            'frontier': 'INTRADAY_SESSION',
            'readiness_score': max(intraday_score, 0),
            'status': 'READY' if intraday_score >= 65 else ('PARTIAL' if intraday_score >= 35 else 'NOT_READY'),
            'primary_evidence': f'db_bars={bars_total}; csv_rows_scanned={csv_rows}; timeframes={sorted(timeframes)}; spread={has_spread or csv_has_spread}',
            'recommended_next_stage': 'Stage91_INTRADAY_SESSION_RESIDUAL_THESIS_DISCOVERY',
            'rationale': 'Best source for genuinely new orthogonal exposure after daily macro residual search is exhausted, if broker M1/M5 data is present.',
        },
        {
            'frontier': 'COT_POSITIONING',
            'readiness_score': max(cot_score, 0),
            'status': 'READY' if cot_score >= 65 else ('PARTIAL' if cot_score >= 35 else 'NOT_READY'),
            'primary_evidence': f'cot_files={len(cot_files)}; max_rows={cot_rows}; macro_has_cot={macro_info.get("has_cot_columns")}',
            'recommended_next_stage': 'Stage91_COT_POSITIONING_THESIS_DISCOVERY',
            'rationale': 'Adds investor-positioning/flow-of-funds state that is not represented in current macro-only portfolio.',
        },
        {
            'frontier': 'EVENT_SURPRISE',
            'readiness_score': max(event_score, 0),
            'status': 'READY' if event_score >= 65 else ('PARTIAL' if event_score >= 35 else 'NOT_READY'),
            'primary_evidence': f'calendar_files={len(event_infos)}; rows={event_rows}; surprise_ready={event_has_surprise}',
            'recommended_next_stage': 'Stage91_EVENT_SURPRISE_THESIS_DISCOVERY',
            'rationale': 'Could capture episodic re-pricing around CPI/NFP/FOMC that daily macro states smooth away.',
        },
        {
            'frontier': 'FLOW_REFINEMENT',
            'readiness_score': max(flow_score, 0),
            'status': 'PARTIAL' if flow_score >= 45 else 'LOW_PRIORITY',
            'primary_evidence': f'macro_has_etf={macro_info.get("has_etf_columns")}; macro_has_cb={macro_info.get("has_central_bank_columns")}',
            'recommended_next_stage': 'NO_IMMEDIATE_STAGE_UNLESS_NEW_GRANULAR_FLOW_DATA',
            'rationale': 'ETF/CB aggregates are already used; more value requires source decomposition or higher-frequency reliable updates.',
        },
    ]
    frontiers.sort(key=lambda x: (x['readiness_score'], x['frontier'] == 'INTRADAY_SESSION'), reverse=True)

    selected = frontiers[0]
    aux = {
        'cot_files': [str(p) for p in cot_files],
        'calendar_files': [str(p) for p in calendar_candidates],
        'sqlite_dbs': db_infos,
        'amarkets_csvs': csv_infos,
    }
    return frontiers, requirements, aux


def thesis_queue_for_frontier(frontier: str) -> List[Dict[str, Any]]:
    templates = {
        'INTRADAY_SESSION': [
            ('I01_MACRO_INACTIVE_LONDON_RANGE_BREAKOUT', 'London/NY range expansion only when unified macro portfolio is inactive; cost/spread gated.'),
            ('I02_PULLBACK_REVERSAL_AROUND_SESSION_OPEN', 'Gold pullback reversal around London/NY open with macro no-signal state.'),
            ('I03_ASIA_RANGE_BREAK_FAILED_BREAKOUT', 'Failed Asia range breakout as mean-reversion candidate, gated by realized vol and spread.'),
            ('I04_SESSION_VOL_REGIME_CONTINUATION', 'Intraday continuation only after realized-vol expansion and clean spread conditions.'),
        ],
        'COT_POSITIONING': [
            ('C01_MANAGED_MONEY_EXTREME_UNWIND', 'Gold long thesis after managed-money crowding unwinds while price stops falling.'),
            ('C02_PRODUCER_SWAP_DIVERGENCE', 'Producer/swap dealer divergence as slower positioning prior for gold resilience.'),
            ('C03_COT_EXTREME_WITH_DXY_RELIEF', 'COT extreme combined with DXY/real-yield relief, lag-safe weekly only.'),
        ],
        'EVENT_SURPRISE': [
            ('E01_CPI_NFP_FOMC_SURPRISE_REVERSAL', 'Gold response to USD/rate surprise after first reaction fades.'),
            ('E02_SURPRISE_CONFIRMATION_CONTINUATION', 'Continuation after event surprise aligns with DXY/real-yield move.'),
            ('E03_EVENT_CLUSTER_RISK_HEDGE', 'Pre/post cluster hedge behavior around high-impact macro events.'),
        ],
        'FLOW_REFINEMENT': [
            ('F01_ETF_FLOW_ACCELERATION_DECOMPOSITION', 'ETF flow acceleration by source/region, not aggregate only.'),
            ('F02_CB_DEMAND_SOURCE_QUALITY', 'Central-bank demand decomposition and reporting-lag sensitivity.'),
        ],
    }
    rows = []
    for rank, (rule_family, rationale) in enumerate(templates.get(frontier, []), start=1):
        rows.append({'priority': rank, 'frontier': frontier, 'thesis_family': rule_family, 'rationale': rationale, 'stage_status': 'QUEUED_NO_ORDER'})
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--config', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    ensure_dir(out_dir)

    cfg = read_json(cfg_path)
    paths_cfg = cfg.get('paths', {})
    macro_path = normalize_path(root, paths_cfg.get('macro_dataset', 'data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv'))
    stage88_summary_path = normalize_path(root, paths_cfg.get('stage88_summary', 'reports/stage88_daily_unified_observer_combo/stage88_daily_unified_observer_combo_summary.json'))
    stage89_summary_path = normalize_path(root, paths_cfg.get('stage89_summary', 'reports/stage89_residual_regime_thesis_discovery/stage89_residual_regime_thesis_discovery_summary.json'))

    macro_info = inspect_macro_dataset(macro_path)
    stage88 = read_json(stage88_summary_path) if stage88_summary_path.exists() else {}
    stage89 = read_json(stage89_summary_path) if stage89_summary_path.exists() else {}

    frontiers, requirements, aux = score_frontiers(root, cfg, macro_info)
    selected = frontiers[0]
    selected_frontier = selected['frontier'] if selected['readiness_score'] >= cfg.get('min_score_to_select_frontier', 35) else 'NONE_READY'
    queue = thesis_queue_for_frontier(selected_frontier) if selected_frontier != 'NONE_READY' else []

    if selected_frontier == 'NONE_READY':
        decision = 'STAGE90_DATA_FRONTIER_REQUIREMENTS_READY_NO_ORDER'
        classification = 'S90_NO_FRONTIER_READY'
        disposition = 'DATA_FRONTIER_REQUIREMENTS_READY'
    else:
        decision = f'STAGE90_{selected_frontier}_FRONTIER_SELECTED_FOR_STAGE91_NO_ORDER'
        classification = 'S90_DATA_FRONTIER_SELECTED'
        disposition = 'DATA_FRONTIER_SELECTED_FOR_STAGE91'

    summary = {
        'stage': 'Stage90_DATA_FRONTIER_THESIS_ROUTER',
        'root': str(root),
        'config': str(cfg_path),
        'generated_utc': utc_now(),
        'status': 'STAGE90_COMPLETE_NO_PROMOTION',
        'decision': decision,
        'classification': classification,
        'disposition': disposition,
        'principle': 'After Stage89 found no residual macro-only shortlist, route thesis discovery to new data frontiers. No orders, no broker connection, no EA/MT5 change.',
        'stage88_reference': {
            'path': str(stage88_summary_path),
            'exists': stage88_summary_path.exists(),
            'decision': stage88.get('decision'),
            'disposition': stage88.get('disposition'),
        },
        'stage89_reference': {
            'path': str(stage89_summary_path),
            'exists': stage89_summary_path.exists(),
            'decision': stage89.get('decision'),
            'disposition': stage89.get('disposition'),
            'current_union_active_days': stage89.get('current_union_active_days'),
        },
        'macro_dataset': macro_info,
        'selected_frontier': selected_frontier,
        'frontier_ranking': frontiers,
        'thesis_queue_count': len(queue),
        'thesis_queue': queue,
        'hard_blocks': [
            'NO_AUTOMATED_ORDER', 'NO_PAPER_ORDER', 'NO_BROKER_CONNECTION', 'NO_EA_PROMOTION',
            'NO_PAPER_LIVE', 'NO_LIVE', 'NO_ORDER_AUTHORIZATION_FROM_STAGE90',
            'NO_THRESHOLD_TUNING_FROM_STAGE90_ROUTER', 'NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE90'
        ],
        'outputs': {
            'summary_json': str(out_dir / 'stage90_data_frontier_thesis_router_summary.json'),
            'report_md': str(out_dir / 'stage90_data_frontier_thesis_router_report.md'),
            'frontier_readiness_csv': str(out_dir / 'stage90_frontier_readiness.csv'),
            'data_requirements_csv': str(out_dir / 'stage90_data_requirements.csv'),
            'thesis_queue_csv': str(out_dir / 'stage90_thesis_queue.csv'),
            'inventory_json': str(out_dir / 'stage90_data_inventory.json'),
        },
    }

    with (out_dir / 'stage90_data_frontier_thesis_router_summary.json').open('w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with (out_dir / 'stage90_data_inventory.json').open('w', encoding='utf-8') as f:
        json.dump(aux, f, indent=2, ensure_ascii=False)
    write_csv(out_dir / 'stage90_frontier_readiness.csv', frontiers)
    write_csv(out_dir / 'stage90_data_requirements.csv', requirements)
    write_csv(out_dir / 'stage90_thesis_queue.csv', queue, fieldnames=['priority', 'frontier', 'thesis_family', 'rationale', 'stage_status'])

    md = []
    md.append('# Stage90 Data Frontier Thesis Router\n')
    md.append('## Decision')
    md.append(f"- status: `{summary['status']}`")
    md.append(f"- decision: `{decision}`")
    md.append(f"- classification: `{classification}`")
    md.append(f"- disposition: `{disposition}`\n")
    md.append('## Selected frontier')
    md.append(f"- `{selected_frontier}`\n")
    md.append('## Frontier ranking')
    for frow in frontiers:
        md.append(f"- `{frow['frontier']}` score=`{frow['readiness_score']}` status=`{frow['status']}` next=`{frow['recommended_next_stage']}`")
    md.append('\n## Thesis queue')
    if queue:
        for row in queue:
            md.append(f"- `{row['thesis_family']}`: {row['rationale']}")
    else:
        md.append('- none')
    md.append('\n## Hard blocks')
    for block in summary['hard_blocks']:
        md.append(f'- `{block}`')
    with (out_dir / 'stage90_data_frontier_thesis_router_report.md').open('w', encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')

    print(json.dumps({'status': summary['status'], 'decision': decision, 'selected_frontier': selected_frontier, 'summary_json': summary['outputs']['summary_json']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
