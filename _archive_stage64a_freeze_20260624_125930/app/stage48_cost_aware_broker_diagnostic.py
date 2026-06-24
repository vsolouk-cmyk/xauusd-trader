#!/usr/bin/env python3
"""
Stage48 Cost-Aware Broker Diagnostic

Purpose:
- Use broker-real AMarkets/MT5 M5 export and Stage48F calibrated cost model.
- Run a frozen, small, cost-aware liquidity-sweep reversal diagnostic on broker data.
- This is NOT a promotion gate to EA/paper/live and does not rescue archived candidates.

Inputs:
- MT5/AMarkets tab export with <DATE>, <TIME>, <OPEN>, <HIGH>, <LOW>, <CLOSE>, <SPREAD>
- Stage48F cost model JSON with recommended/stress/extreme costs.

Outputs:
- summary JSON
- report MD
- candidates CSV
- trades CSV
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = timezone.utc


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    spread_points: Optional[float]
    tick_volume: Optional[float] = None
    real_volume: Optional[float] = None


@dataclass
class Trade:
    candidate_id: str
    direction: str
    entry_ts_utc: str
    exit_ts_utc: str
    entry_price: float
    exit_price: float
    horizon_bars: int
    lookback_bars: int
    sweep_points: float
    gross_bps: float
    recommended_net_bps: float
    stress_net_bps: float
    extreme_net_bps: float
    spread_points_at_entry: Optional[float]
    session_utc: str
    year: int


def clean_header(h: str) -> str:
    return h.strip().strip('\ufeff').strip().strip('<>').lower().replace(' ', '_')


def parse_dt(date_s: str, time_s: str) -> Optional[datetime]:
    ds = (date_s or '').strip()
    ts = (time_s or '').strip()
    if not ds or not ts:
        return None
    candidates = [
        f"{ds} {ts}",
        f"{ds}T{ts}",
    ]
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%dT%H:%M:%S",
    ]
    for value in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
    # Try ISO parser last.
    try:
        return datetime.fromisoformat(f"{ds}T{ts}".replace('Z', '+00:00')).astimezone(UTC)
    except Exception:
        return None


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == '' or s.lower() in {'nan', 'none', 'null'}:
        return None
    try:
        return float(s.replace(',', ''))
    except Exception:
        return None


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text(encoding='utf-8-sig', errors='replace')[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=',\t;')
    except Exception:
        class Tab(csv.Dialect):
            delimiter = '\t'
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = False
            lineterminator = '\n'
            quoting = csv.QUOTE_MINIMAL
        return Tab


def load_broker_mt5(path: Path, offset_hours: float = 0.0) -> Tuple[List[Bar], Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    dialect = sniff_dialect(path)
    bars: List[Bar] = []
    raw_rows = 0
    parse_fail = 0
    bad_ohlc = 0
    bad_ts = 0
    with path.open('r', newline='', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f, dialect=dialect)
        if reader.fieldnames is None:
            raise ValueError('CSV has no header row')
        original_fields = list(reader.fieldnames)
        field_map = {clean_header(h): h for h in original_fields}
        date_col = field_map.get('date') or field_map.get('datetime_date')
        time_col = field_map.get('time') or field_map.get('datetime_time')
        ts_col = field_map.get('time_utc') or field_map.get('timestamp') or field_map.get('datetime') or field_map.get('timeutc')
        open_col = field_map.get('open')
        high_col = field_map.get('high')
        low_col = field_map.get('low')
        close_col = field_map.get('close')
        spread_col = field_map.get('spread') or field_map.get('spread_points')
        tick_col = field_map.get('tickvol') or field_map.get('tick_volume') or field_map.get('tick_volume')
        real_col = field_map.get('vol') or field_map.get('real_volume') or field_map.get('volume')
        required = [open_col, high_col, low_col, close_col, spread_col]
        if not all(required):
            raise ValueError(f'Missing required OHLC/spread columns. fieldnames={original_fields}')
        if not ts_col and not (date_col and time_col):
            raise ValueError(f'Missing timestamp or date/time columns. fieldnames={original_fields}')
        for row in reader:
            raw_rows += 1
            try:
                if ts_col:
                    ts_raw = str(row.get(ts_col, '')).replace('Z', '+00:00')
                    dt = datetime.fromisoformat(ts_raw).astimezone(UTC)
                else:
                    dt = parse_dt(str(row.get(date_col, '')), str(row.get(time_col, '')))
                if dt is None:
                    bad_ts += 1
                    continue
                if offset_hours:
                    dt = dt - timedelta(hours=offset_hours)
                o = to_float(row.get(open_col))
                h = to_float(row.get(high_col))
                l = to_float(row.get(low_col))
                c = to_float(row.get(close_col))
                sp = to_float(row.get(spread_col))
                if o is None or h is None or l is None or c is None:
                    bad_ohlc += 1
                    continue
                if not (l <= min(o, c) <= max(o, c) <= h):
                    # MT5 files should satisfy this; tolerate small malformed rows by skipping.
                    bad_ohlc += 1
                    continue
                bars.append(Bar(dt, o, h, l, c, sp, to_float(row.get(tick_col)) if tick_col else None, to_float(row.get(real_col)) if real_col else None))
            except Exception:
                parse_fail += 1
    bars.sort(key=lambda b: b.ts)
    deduped: List[Bar] = []
    seen = set()
    for b in bars:
        if b.ts not in seen:
            deduped.append(b)
            seen.add(b.ts)
    meta = {
        'path': str(path),
        'delimiter': dialect.delimiter,
        'raw_rows': raw_rows,
        'accepted_rows': len(deduped),
        'duplicates_removed': len(bars) - len(deduped),
        'parse_fail_rows': parse_fail,
        'bad_timestamp_rows': bad_ts,
        'bad_ohlc_rows': bad_ohlc,
        'numeric_spread_rows': sum(1 for b in deduped if b.spread_points is not None),
        'fieldnames': original_fields,
        'offset_hours_applied': offset_hours,
        'start_utc': deduped[0].ts.isoformat().replace('+00:00', 'Z') if deduped else None,
        'end_utc': deduped[-1].ts.isoformat().replace('+00:00', 'Z') if deduped else None,
    }
    if deduped:
        meta['coverage_days'] = (deduped[-1].ts - deduped[0].ts).total_seconds() / 86400.0
    else:
        meta['coverage_days'] = 0.0
    return deduped, meta


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    clean = sorted(v for v in values if v is not None and not math.isnan(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[int(pos)]
    return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)


def bps_return(entry: float, exit_: float, direction: int) -> float:
    return direction * ((exit_ - entry) / entry) * 10000.0


def session_utc(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 7:
        return 'asia'
    if 7 <= h < 12:
        return 'london'
    if 12 <= h < 16:
        return 'london_ny_overlap'
    if 16 <= h < 21:
        return 'new_york'
    return 'late_us'


def load_cost_model(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def cost_values(cost: Dict[str, Any]) -> Dict[str, float]:
    # Accept both direct and recommended_usage schema.
    rec = cost.get('recommended_cost_bps')
    stress = cost.get('stress_cost_bps')
    extreme = cost.get('extreme_cost_bps')
    usage = cost.get('recommended_usage', {}) if isinstance(cost.get('recommended_usage'), dict) else {}
    rec = rec if rec is not None else usage.get('default_scan_cost_bps')
    stress = stress if stress is not None else usage.get('stress_scan_cost_bps')
    extreme = extreme if extreme is not None else usage.get('extreme_spread_filter_reference_bps')
    if rec is None or stress is None or extreme is None:
        raise ValueError('Cost model missing recommended/stress/extreme cost bps')
    offset = cost.get('selected_broker_time_offset_hours', 0)
    return {
        'recommended_cost_bps': float(rec),
        'stress_cost_bps': float(stress),
        'extreme_cost_bps': float(extreme),
        'selected_broker_time_offset_hours': float(offset),
    }


def detect_liquidity_sweep_trades(
    bars: List[Bar],
    lookback_bars: int,
    horizon_bars: int,
    sweep_points: float,
    point_size: float,
    costs: Dict[str, float],
) -> List[Trade]:
    trades: List[Trade] = []
    if len(bars) < lookback_bars + horizon_bars + 2:
        return trades
    sweep_price = sweep_points * point_size
    cid = f"S48_COST_LB{lookback_bars}_H{horizon_bars}_SW{int(sweep_points)}"
    for i in range(lookback_bars, len(bars) - horizon_bars):
        b = bars[i]
        prev = bars[i - lookback_bars:i]
        prior_low = min(x.low for x in prev)
        prior_high = max(x.high for x in prev)
        direction = 0
        # Frozen structural definition: sweep outside a prior range and close back inside.
        if b.low < prior_low - sweep_price and b.close > prior_low:
            direction = 1
            direction_label = 'LONG_SWEEP_REVERSAL'
        elif b.high > prior_high + sweep_price and b.close < prior_high:
            direction = -1
            direction_label = 'SHORT_SWEEP_REVERSAL'
        else:
            continue
        entry = b.close
        exit_bar = bars[i + horizon_bars]
        gross = bps_return(entry, exit_bar.close, direction)
        trades.append(Trade(
            candidate_id=cid,
            direction=direction_label,
            entry_ts_utc=b.ts.isoformat().replace('+00:00', 'Z'),
            exit_ts_utc=exit_bar.ts.isoformat().replace('+00:00', 'Z'),
            entry_price=entry,
            exit_price=exit_bar.close,
            horizon_bars=horizon_bars,
            lookback_bars=lookback_bars,
            sweep_points=sweep_points,
            gross_bps=gross,
            recommended_net_bps=gross - costs['recommended_cost_bps'],
            stress_net_bps=gross - costs['stress_cost_bps'],
            extreme_net_bps=gross - costs['extreme_cost_bps'],
            spread_points_at_entry=b.spread_points,
            session_utc=session_utc(b.ts),
            year=b.ts.year,
        ))
    return trades


def split_sample(ts_s: str) -> str:
    dt = datetime.fromisoformat(ts_s.replace('Z', '+00:00')).astimezone(UTC)
    # Keep a simple forward-style split: recent 2026 segment is OOS.
    return 'OOS_2026' if dt >= datetime(2026, 1, 1, tzinfo=UTC) else 'IS_PRE_2026'


def summarize_values(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {'count': 0}
    return {
        'count': len(vals),
        'mean': mean(vals),
        'median': median(vals),
        'p10': percentile(vals, 0.10),
        'p25': percentile(vals, 0.25),
        'p75': percentile(vals, 0.75),
        'p90': percentile(vals, 0.90),
        'min': min(vals),
        'max': max(vals),
        'win_rate': sum(1 for v in vals if v > 0) / len(vals),
        'stdev': pstdev(vals) if len(vals) > 1 else 0.0,
        't_stat': (mean(vals) / (pstdev(vals) / math.sqrt(len(vals)))) if len(vals) > 1 and pstdev(vals) > 0 else None,
    }


def max_drawdown(vals: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for v in vals:
        equity += v
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    return mdd


def summarize_candidate(trades: List[Trade], candidate_id: str) -> Dict[str, Any]:
    rows = [t for t in trades if t.candidate_id == candidate_id]
    rec = [t.recommended_net_bps for t in rows]
    stress = [t.stress_net_bps for t in rows]
    extreme = [t.extreme_net_bps for t in rows]
    oos = [t for t in rows if split_sample(t.entry_ts_utc) == 'OOS_2026']
    is_ = [t for t in rows if split_sample(t.entry_ts_utc) == 'IS_PRE_2026']
    oos_stress = [t.stress_net_bps for t in oos]
    is_stress = [t.stress_net_bps for t in is_]
    year_counts: Dict[int, int] = {}
    year_sum: Dict[int, float] = {}
    for t in rows:
        year_counts[t.year] = year_counts.get(t.year, 0) + 1
        year_sum[t.year] = year_sum.get(t.year, 0.0) + t.stress_net_bps
    pos_years = sum(1 for v in year_sum.values() if v > 0)
    neg_years = sum(1 for v in year_sum.values() if v < 0)
    max_year_share = max(year_counts.values()) / len(rows) if rows else 0.0
    decision = 'NO_PASS'
    notes: List[str] = []
    if len(rows) < 100:
        notes.append('trade_count_lt_100')
    if len(oos) < 30:
        notes.append('oos_trade_count_lt_30')
    if oos_stress and mean(oos_stress) <= 0:
        notes.append('oos_stress_mean_not_positive')
    if oos_stress and (sum(1 for v in oos_stress if v > 0) / len(oos_stress)) < 0.52:
        notes.append('oos_stress_win_rate_lt_52pct')
    if max_year_share > 0.60:
        notes.append('year_concentration_gt_60pct')
    if not notes:
        decision = 'DIAGNOSTIC_SURVIVOR_REQUIRES_AUDIT_NO_PROMOTION'
    return {
        'candidate_id': candidate_id,
        'lookback_bars': rows[0].lookback_bars if rows else None,
        'horizon_bars': rows[0].horizon_bars if rows else None,
        'sweep_points': rows[0].sweep_points if rows else None,
        'trade_count': len(rows),
        'is_trade_count': len(is_),
        'oos_trade_count': len(oos),
        'recommended': summarize_values(rec),
        'stress': summarize_values(stress),
        'extreme': summarize_values(extreme),
        'is_stress': summarize_values(is_stress),
        'oos_stress': summarize_values(oos_stress),
        'stress_total_bps': sum(stress),
        'stress_max_drawdown_bps': max_drawdown(stress),
        'positive_year_count': pos_years,
        'negative_year_count': neg_years,
        'max_year_share': max_year_share,
        'year_stress_total_bps': {str(k): v for k, v in sorted(year_sum.items())},
        'decision': decision,
        'notes': ';'.join(notes),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        seen: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.append(k)
        fieldnames = seen
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def flatten_summary_row(s: Dict[str, Any]) -> Dict[str, Any]:
    def get(path: str) -> Any:
        cur: Any = s
        for p in path.split('.'):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(p)
        return cur
    return {
        'candidate_id': s.get('candidate_id'),
        'lookback_bars': s.get('lookback_bars'),
        'horizon_bars': s.get('horizon_bars'),
        'sweep_points': s.get('sweep_points'),
        'trade_count': s.get('trade_count'),
        'is_trade_count': s.get('is_trade_count'),
        'oos_trade_count': s.get('oos_trade_count'),
        'stress_mean_bps': get('stress.mean'),
        'stress_median_bps': get('stress.median'),
        'stress_win_rate': get('stress.win_rate'),
        'stress_t_stat': get('stress.t_stat'),
        'stress_total_bps': s.get('stress_total_bps'),
        'stress_max_drawdown_bps': s.get('stress_max_drawdown_bps'),
        'is_stress_mean_bps': get('is_stress.mean'),
        'is_stress_win_rate': get('is_stress.win_rate'),
        'oos_stress_mean_bps': get('oos_stress.mean'),
        'oos_stress_win_rate': get('oos_stress.win_rate'),
        'positive_year_count': s.get('positive_year_count'),
        'negative_year_count': s.get('negative_year_count'),
        'max_year_share': s.get('max_year_share'),
        'decision': s.get('decision'),
        'notes': s.get('notes'),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--broker-csv', required=True)
    ap.add_argument('--cost-model', default='reports/stage48f/stage48f_cost_model.json')
    ap.add_argument('--timeframe', default='M5')
    ap.add_argument('--point-size', type=float, default=0.01)
    ap.add_argument('--out', default='reports/stage48_cost_aware')
    ap.add_argument('--lookbacks', default='24,48,72')
    ap.add_argument('--horizons', default='12,24,48')
    ap.add_argument('--sweeps', default='10,20,30')
    ap.add_argument('--max-trades-csv', type=int, default=250000)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cost_model = load_cost_model(Path(args.cost_model))
    costs = cost_values(cost_model)
    bars, broker_meta = load_broker_mt5(Path(args.broker_csv).expanduser(), offset_hours=costs.get('selected_broker_time_offset_hours', 0.0))

    lookbacks = [int(x) for x in args.lookbacks.split(',') if x.strip()]
    horizons = [int(x) for x in args.horizons.split(',') if x.strip()]
    sweeps = [float(x) for x in args.sweeps.split(',') if x.strip()]

    all_trades: List[Trade] = []
    for lb in lookbacks:
        for hz in horizons:
            for sw in sweeps:
                all_trades.extend(detect_liquidity_sweep_trades(bars, lb, hz, sw, args.point_size, costs))

    candidate_ids = sorted(set(t.candidate_id for t in all_trades))
    candidate_summaries = [summarize_candidate(all_trades, cid) for cid in candidate_ids]
    flat = [flatten_summary_row(s) for s in candidate_summaries]
    flat.sort(key=lambda r: (r.get('decision') != 'DIAGNOSTIC_SURVIVOR_REQUIRES_AUDIT_NO_PROMOTION', -(r.get('oos_stress_mean_bps') or -1e9), -(r.get('trade_count') or 0)))

    survivor_count = sum(1 for r in flat if r['decision'] == 'DIAGNOSTIC_SURVIVOR_REQUIRES_AUDIT_NO_PROMOTION')
    status = 'COST_AWARE_DIAGNOSTIC_COMPLETE_NO_PROMOTION'
    next_step = 'AUDIT_DIAGNOSTIC_SURVIVORS_OR_ARCHIVE_NO_PROMOTION' if survivor_count else 'ARCHIVE_COST_AWARE_DIAGNOSTIC_NO_PROMOTION'

    summary = {
        'stage': 'Stage48_COST_AWARE_BROKER_DIAGNOSTIC',
        'patch': 'STAGE48_COST_AWARE_BROKER_DIAGNOSTIC_NO_PROMOTION',
        'status': status,
        'promotion': 'NO_GO',
        'EA': 'NO_GO',
        'paper_live': 'NO_GO',
        'live': 'NO_GO',
        'broker_csv': str(Path(args.broker_csv).expanduser()),
        'cost_model': str(Path(args.cost_model)),
        'timeframe': args.timeframe,
        'broker_rows': len(bars),
        'broker_start_utc': broker_meta.get('start_utc'),
        'broker_end_utc': broker_meta.get('end_utc'),
        'broker_coverage_days': broker_meta.get('coverage_days'),
        'costs': costs,
        'grid': {'lookbacks': lookbacks, 'horizons': horizons, 'sweeps': sweeps, 'candidate_count': len(candidate_ids)},
        'trade_count': len(all_trades),
        'diagnostic_survivor_count': survivor_count,
        'next_allowed_step': next_step,
        'broker_load_meta': broker_meta,
        'top_candidates': flat[:10],
        'note': 'Diagnostic only. No EA, paper-live, live, or promotion is authorized.',
    }

    summary_path = out_dir / 'stage48_cost_aware_broker_diagnostic_summary.json'
    report_path = out_dir / 'stage48_cost_aware_broker_diagnostic_report.md'
    candidates_path = out_dir / 'stage48_cost_aware_broker_diagnostic_candidates.csv'
    trades_path = out_dir / 'stage48_cost_aware_broker_diagnostic_trades.csv'

    with summary_path.open('w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    write_csv(candidates_path, flat)
    trade_rows = [asdict(t) for t in all_trades[:args.max_trades_csv]]
    write_csv(trades_path, trade_rows)

    with report_path.open('w', encoding='utf-8') as f:
        f.write('# Stage48 Cost-Aware Broker Diagnostic\n\n')
        f.write(f"- status: `{status}`\n")
        f.write(f"- next_allowed_step: `{next_step}`\n")
        f.write('- promotion: `NO_GO`\n- EA: `NO_GO`\n- paper_live: `NO_GO`\n- live: `NO_GO`\n\n')
        f.write('## Inputs\n\n')
        f.write(f"- broker_csv: `{summary['broker_csv']}`\n")
        f.write(f"- cost_model: `{summary['cost_model']}`\n")
        f.write(f"- selected_broker_time_offset_hours: `{costs['selected_broker_time_offset_hours']}`\n")
        f.write(f"- recommended_cost_bps: `{costs['recommended_cost_bps']:.4f}`\n")
        f.write(f"- stress_cost_bps: `{costs['stress_cost_bps']:.4f}`\n")
        f.write(f"- extreme_cost_bps: `{costs['extreme_cost_bps']:.4f}`\n\n")
        f.write('## Coverage\n\n')
        f.write(f"- broker_rows: `{len(bars)}`\n")
        f.write(f"- broker_coverage_days: `{broker_meta.get('coverage_days')}`\n")
        f.write(f"- trade_count: `{len(all_trades)}`\n")
        f.write(f"- candidate_count: `{len(candidate_ids)}`\n")
        f.write(f"- diagnostic_survivor_count: `{survivor_count}`\n\n")
        f.write('## Top candidates\n\n')
        for r in flat[:10]:
            f.write(f"- `{r['candidate_id']}` trades={r['trade_count']} oos_trades={r['oos_trade_count']} ")
            f.write(f"stress_mean={r.get('stress_mean_bps'):.4f} oos_stress_mean={r.get('oos_stress_mean_bps') if r.get('oos_stress_mean_bps') is not None else 'NA'} ")
            f.write(f"decision=`{r['decision']}` notes=`{r['notes']}`\n")
        f.write('\n## Interpretation\n\n')
        f.write('This is a broker-real, cost-aware diagnostic using the Stage48F cost model. It does not authorize promotion, EA, paper-live, or live trading. If survivors exist, they require a separate hard audit; if none exist, archive this diagnostic.\n')

    print(json.dumps({
        'stage': summary['stage'],
        'status': status,
        'trade_count': len(all_trades),
        'candidate_count': len(candidate_ids),
        'diagnostic_survivor_count': survivor_count,
        'out': str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
