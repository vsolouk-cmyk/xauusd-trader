#!/usr/bin/env python3
"""
Stage52 LoaderFix1: true forward-only volatility squeeze shadow runner.

Default behaviour is intentionally conservative:
- The first run initializes a forward watermark at the latest available M15 bar and does NOT backfill historical signals.
- Later runs only generate signals whose entry time is newer than the saved watermark.
- Existing pending signals are evaluated after their horizon matures.
- Historical backfill is available only with --allow-historical-backfill for debugging, not for forward evidence.

No trading order, EA, paper-live, live action, or promotion is authorized by this script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
STAGE = "Stage52_VOLATILITY_SQUEEZE_TRUE_FORWARD_SHADOW_NO_PROMOTION"
STATUS_UPDATED = "TRUE_FORWARD_SHADOW_UPDATED_NO_PROMOTION"
STATUS_INIT = "TRUE_FORWARD_SHADOW_INITIALIZED_NO_BACKFILL_NO_PROMOTION"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FMT)


def parse_ts(s: str) -> datetime:
    s = str(s).strip()
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(ISO_FMT)


def safe_float(v, default=None):
    try:
        if v is None or str(v).strip() == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def safe_int(v, default=None):
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(v))
    except Exception:
        return default


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    spread_points: float = 0.0
    tick_volume: float = 0.0


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    compression_window_m15: int
    compression_percentile: float
    breakout_buffer_bps: float
    m30_sma_window: int
    horizon_m5_bars: int


def ensure_state_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            entry_time_utc TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            horizon_m5_bars INTEGER NOT NULL,
            stress_cost_bps REAL NOT NULL,
            spread_cost_bps REAL,
            status TEXT NOT NULL,
            planned_exit_time_utc TEXT,
            exit_time_utc TEXT,
            exit_price REAL,
            gross_bps REAL,
            stress_bps REAL,
            created_utc TEXT NOT NULL,
            evaluated_utc TEXT,
            is_backfill INTEGER NOT NULL DEFAULT 0,
            source_run_id TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_entry ON signals(entry_time_utc)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            generated_utc TEXT NOT NULL,
            mode TEXT NOT NULL,
            latest_m15_time_utc TEXT,
            previous_watermark_utc TEXT,
            new_watermark_utc TEXT,
            candidates_loaded INTEGER,
            generated_signals INTEGER,
            inserted_new_signals INTEGER,
            newly_evaluated_signals INTEGER,
            notes TEXT
        )
        """
    )
    conn.commit()


def kv_get(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, value))


def load_bars(db: Path, timeframe: str, limit: Optional[int] = None) -> List[Bar]:
    tf = timeframe.upper()
    with sqlite3.connect(str(db)) as conn:
        # New importer table is amarkets_bars. Keep a tiny amount of schema tolerance.
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "amarkets_bars" not in tables:
            raise RuntimeError("Expected table amarkets_bars in broker normalized SQLite")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(amarkets_bars)").fetchall()]
        need = ["time_utc", "open", "high", "low", "close", "timeframe"]
        missing = [c for c in need if c not in cols]
        if missing:
            raise RuntimeError(f"amarkets_bars missing required columns: {missing}")
        spread_col = "spread_points" if "spread_points" in cols else None
        volume_col = "tick_volume" if "tick_volume" in cols else ("volume" if "volume" in cols else None)
        select_cols = ["time_utc", "open", "high", "low", "close"]
        select_cols.append(spread_col if spread_col else "0 AS spread_points")
        select_cols.append(volume_col if volume_col else "0 AS tick_volume")
        sql = f"SELECT {', '.join(select_cols)} FROM amarkets_bars WHERE UPPER(timeframe)=? ORDER BY time_utc"
        if limit:
            sql = f"SELECT * FROM ({sql} DESC LIMIT {int(limit)}) ORDER BY time_utc"  # not used; kept defensive
        rows = conn.execute(sql, (tf,)).fetchall()
    out: List[Bar] = []
    for row in rows:
        try:
            ts = parse_ts(row[0])
            o, h, l, c = map(float, row[1:5])
            sp = safe_float(row[5], 0.0) or 0.0
            tv = safe_float(row[6], 0.0) or 0.0
            if h < l or min(o, h, l, c) <= 0:
                continue
            out.append(Bar(ts, o, h, l, c, sp, tv))
        except Exception:
            continue
    return out


def load_cost_model(path: Path) -> Dict:
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def percentile(vals: Sequence[float], p: float) -> float:
    vals = sorted(float(x) for x in vals if x is not None and not math.isnan(float(x)))
    if not vals:
        return float('nan')
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (p / 100.0)
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def load_candidates(candidates_csv: Optional[Path], config_json: Path) -> List[Candidate]:
    candidates: List[Candidate] = []

    def add_from_mapping(d: Dict):
        cid = str(d.get('candidate_id') or '').strip()
        if not cid:
            return
        cw = safe_int(d.get('compression_window_m15'), None)
        cp = safe_float(d.get('compression_percentile'), None)
        bb = safe_float(d.get('breakout_buffer_bps'), None)
        m30 = safe_int(d.get('m30_sma_window'), None)
        hz = safe_int(d.get('horizon_m5_bars'), None)
        if all(v is not None for v in [cw, cp, bb, m30, hz]):
            candidates.append(Candidate(cid, int(cw), float(cp), float(bb), int(m30), int(hz)))

    if candidates_csv and candidates_csv.exists():
        with candidates_csv.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                decision = str(row.get('decision') or '').upper()
                # Keep only actual pass rows; avoid matching HARD_AUDIT_NO_PASS.
                if 'PASS' in decision and 'NO_PASS' not in decision:
                    add_from_mapping(row)

    if not candidates and config_json.exists():
        with config_json.open('r', encoding='utf-8') as f:
            obj = json.load(f)
        rows = obj.get('candidates') if isinstance(obj, dict) else obj
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict):
                    add_from_mapping(r)

    # Deduplicate by candidate_id.
    seen = set(); unique = []
    for c in candidates:
        if c.candidate_id not in seen:
            seen.add(c.candidate_id); unique.append(c)
    return unique


def m30_trend_at(m30_bars: List[Bar], ts: datetime, window: int) -> int:
    times = [b.ts for b in m30_bars]
    idx = bisect_right(times, ts) - 1
    if idx < window or idx <= 0:
        return 0
    closes = [b.close for b in m30_bars[idx-window+1:idx+1]]
    sma = sum(closes) / len(closes)
    prev_closes = [b.close for b in m30_bars[idx-window:idx]]
    prev_sma = sum(prev_closes) / len(prev_closes) if prev_closes else sma
    if m30_bars[idx].close > sma and sma >= prev_sma:
        return 1
    if m30_bars[idx].close < sma and sma <= prev_sma:
        return -1
    return 0


def find_m5_entry(m5_bars: List[Bar], start_ts: datetime, end_ts: datetime, upper: float, lower: float, trend: int) -> Optional[Bar]:
    times = [b.ts for b in m5_bars]
    start_i = bisect_right(times, start_ts)
    end_i = bisect_right(times, end_ts)
    for b in m5_bars[start_i:end_i]:
        if trend > 0 and b.close > upper:
            return b
        if trend < 0 and b.close < lower:
            return b
    return None


def compute_signal_id(candidate_id: str, entry_time: str, direction: str, horizon: int) -> str:
    s = f"{candidate_id}|{entry_time}|{direction}|{horizon}"
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:24]


def generate_signals(
    m5: List[Bar],
    m15: List[Bar],
    m30: List[Bar],
    candidates: List[Candidate],
    lower_bound_exclusive: datetime,
    upper_bound_inclusive: datetime,
    stress_cost_bps: float,
    extreme_spread_gate_bps: float,
    point_size: float,
    run_id: str,
    is_backfill: bool,
) -> List[Dict]:
    if not m5 or not m15 or not m30:
        return []
    signals = []
    m15_times = [b.ts for b in m15]
    # Scan a little context before lower bound so compression windows are valid.
    start_idx = max(0, bisect_right(m15_times, lower_bound_exclusive) - max((c.compression_window_m15 for c in candidates), default=0) - 5)
    for c in candidates:
        for i in range(max(start_idx, c.compression_window_m15), len(m15)):
            bar = m15[i]
            if not (bar.ts > lower_bound_exclusive and bar.ts <= upper_bound_inclusive):
                continue
            prior = m15[i-c.compression_window_m15:i]
            ranges = [x.high - x.low for x in prior]
            thr = percentile(ranges, c.compression_percentile)
            if not math.isfinite(thr):
                continue
            current_range = bar.high - bar.low
            if current_range > thr:
                continue
            trend = m30_trend_at(m30, bar.ts, c.m30_sma_window)
            if trend == 0:
                continue
            mid_price = bar.close
            buffer_price = mid_price * (c.breakout_buffer_bps / 10000.0)
            upper = bar.high + buffer_price
            lower = bar.low - buffer_price
            # Allow breakout during the next three M15 bars; this mirrors a short forward signal window.
            breakout_deadline = m15[min(len(m15)-1, i+3)].ts
            entry = find_m5_entry(m5, bar.ts, breakout_deadline, upper, lower, trend)
            if not entry:
                continue
            spread_price = (entry.spread_points or 0.0) * point_size
            spread_cost_bps = (spread_price / entry.close) * 10000.0 if entry.close else 999.0
            if spread_cost_bps > extreme_spread_gate_bps:
                continue
            direction = 'LONG' if trend > 0 else 'SHORT'
            entry_ts = fmt_ts(entry.ts)
            signal_id = compute_signal_id(c.candidate_id, entry_ts, direction, c.horizon_m5_bars)
            # planned exit timestamp based on available m5 index if possible.
            m5_times = [b.ts for b in m5]
            ei = bisect_left(m5_times, entry.ts)
            planned_exit = None
            if ei + c.horizon_m5_bars < len(m5):
                planned_exit = fmt_ts(m5[ei + c.horizon_m5_bars].ts)
            signals.append({
                'signal_id': signal_id,
                'candidate_id': c.candidate_id,
                'entry_time_utc': entry_ts,
                'direction': direction,
                'entry_price': entry.close,
                'horizon_m5_bars': c.horizon_m5_bars,
                'stress_cost_bps': stress_cost_bps,
                'spread_cost_bps': spread_cost_bps,
                'status': 'PENDING',
                'planned_exit_time_utc': planned_exit,
                'created_utc': utc_now(),
                'is_backfill': 1 if is_backfill else 0,
                'source_run_id': run_id,
            })
    # Deduplicate within run.
    uniq = {}
    for s in signals:
        uniq[s['signal_id']] = s
    return list(uniq.values())


def insert_signals(conn: sqlite3.Connection, signals: List[Dict]) -> int:
    inserted = 0
    for s in signals:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO signals(
                signal_id,candidate_id,entry_time_utc,direction,entry_price,horizon_m5_bars,
                stress_cost_bps,spread_cost_bps,status,planned_exit_time_utc,created_utc,is_backfill,source_run_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                s['signal_id'], s['candidate_id'], s['entry_time_utc'], s['direction'], s['entry_price'],
                s['horizon_m5_bars'], s['stress_cost_bps'], s.get('spread_cost_bps'), s['status'],
                s.get('planned_exit_time_utc'), s['created_utc'], s['is_backfill'], s['source_run_id']
            )
        )
        inserted += cur.rowcount if cur.rowcount else 0
    conn.commit()
    return inserted


def evaluate_pending(conn: sqlite3.Connection, m5: List[Bar]) -> int:
    if not m5:
        return 0
    times = [b.ts for b in m5]
    rows = conn.execute("SELECT signal_id, entry_time_utc, direction, entry_price, horizon_m5_bars, stress_cost_bps FROM signals WHERE status='PENDING'").fetchall()
    updated = 0
    for signal_id, entry_s, direction, entry_price, horizon, stress_cost in rows:
        try:
            entry_dt = parse_ts(entry_s)
            idx = bisect_left(times, entry_dt)
            if idx >= len(m5) or times[idx] < entry_dt:
                continue
            exit_idx = idx + int(horizon)
            if exit_idx >= len(m5):
                continue
            exit_bar = m5[exit_idx]
            if direction == 'LONG':
                gross = (exit_bar.close - float(entry_price)) / float(entry_price) * 10000.0
            else:
                gross = (float(entry_price) - exit_bar.close) / float(entry_price) * 10000.0
            stress = gross - float(stress_cost)
            conn.execute(
                """
                UPDATE signals SET status='EVALUATED', exit_time_utc=?, exit_price=?, gross_bps=?, stress_bps=?, evaluated_utc=?
                WHERE signal_id=? AND status='PENDING'
                """,
                (fmt_ts(exit_bar.ts), exit_bar.close, gross, stress, utc_now(), signal_id)
            )
            updated += 1
        except Exception:
            continue
    conn.commit()
    return updated


def summarize_state(conn: sqlite3.Connection) -> Dict:
    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM signals WHERE status='PENDING'").fetchone()[0]
    eval_count = conn.execute("SELECT COUNT(*) FROM signals WHERE status='EVALUATED'").fetchone()[0]
    backfill = conn.execute("SELECT COUNT(*) FROM signals WHERE is_backfill=1").fetchone()[0]
    live_forward = conn.execute("SELECT COUNT(*) FROM signals WHERE is_backfill=0").fetchone()[0]
    vals = [r[0] for r in conn.execute("SELECT stress_bps FROM signals WHERE status='EVALUATED' AND stress_bps IS NOT NULL").fetchall()]
    return {
        'total_signals': total,
        'pending_signals': pending,
        'evaluated_signals': eval_count,
        'backfill_signals': backfill,
        'true_forward_signals': live_forward,
        'evaluated_mean_stress_bps': statistics.mean(vals) if vals else None,
        'evaluated_win_rate': (sum(1 for x in vals if x > 0) / len(vals)) if vals else None,
    }


def write_outputs(out_dir: Path, summary: Dict, signals_rows: List[sqlite3.Row]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / 'stage52_volatility_squeeze_forward_shadow_summary.json'
    report_path = out_dir / 'stage52_volatility_squeeze_forward_shadow_report.md'
    csv_path = out_dir / 'stage52_volatility_squeeze_forward_shadow_signals.csv'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = []
    lines.append('# Stage52 Volatility Squeeze True Forward Shadow')
    lines.append('')
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- next_allowed_step: `{summary['next_allowed_step']}`")
    lines.append('- promotion: `NO_GO`')
    lines.append('- EA: `NO_GO`')
    lines.append('- paper_live: `NO_GO`')
    lines.append('- live: `NO_GO`')
    lines.append('')
    lines.append('## This run')
    lines.append('')
    lines.append(f"- mode: `{summary['mode']}`")
    lines.append(f"- candidates_loaded: `{summary['candidates_loaded']}`")
    lines.append(f"- previous_watermark_utc: `{summary.get('previous_watermark_utc')}`")
    lines.append(f"- new_watermark_utc: `{summary.get('new_watermark_utc')}`")
    lines.append(f"- generated_signals_this_run: `{summary['generated_signals_this_run']}`")
    lines.append(f"- inserted_new_signals: `{summary['inserted_new_signals']}`")
    lines.append(f"- newly_evaluated_signals: `{summary['newly_evaluated_signals']}`")
    lines.append('')
    lines.append('## Cumulative true-forward state')
    lines.append('')
    st = summary['state']
    for k in ['total_signals','pending_signals','evaluated_signals','true_forward_signals','backfill_signals','evaluated_mean_stress_bps','evaluated_win_rate']:
        lines.append(f"- {k}: `{st.get(k)}`")
    lines.append('')
    lines.append('## Interpretation')
    lines.append('')
    lines.append('LoaderFix1 prevents first-run historical backfill from being counted as forward evidence. The first normal run initializes the watermark only. Subsequent runs collect true forward signals after new AMarkets bars arrive. No EA, paper-live, live trading, or promotion is authorized.')
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    fields = ['signal_id','candidate_id','entry_time_utc','direction','entry_price','horizon_m5_bars','stress_cost_bps','spread_cost_bps','status','planned_exit_time_utc','exit_time_utc','exit_price','gross_bps','stress_bps','is_backfill']
    with csv_path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in signals_rows:
            w.writerow([r[i] for i in fields])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='Stage52 true forward-only volatility squeeze shadow runner')
    ap.add_argument('--root', default='.', help='Repo root')
    ap.add_argument('--db', default='data/broker_normalized/amarkets_multitf.sqlite')
    ap.add_argument('--cost-model', default='reports/stage48f/stage48f_cost_model.json')
    ap.add_argument('--candidates', default='reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv')
    ap.add_argument('--config', default='configs/stage52_forward_shadow_candidates.json')
    ap.add_argument('--state-db', default='data/shadow/stage52_forward_shadow.sqlite')
    ap.add_argument('--out', default='reports/stage52_forward_shadow')
    ap.add_argument('--point-size', type=float, default=0.01)
    ap.add_argument('--allow-historical-backfill', action='store_true', help='Debug only: generate historical signals instead of watermark-only first run')
    ap.add_argument('--reset-forward-state', action='store_true', help='Delete Stage52 state DB before running. Use once after LoaderFix1 to remove accidental historical pseudo-forward signals.')
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    db = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db)
    cost_model_path = (root / args.cost_model).resolve() if not Path(args.cost_model).is_absolute() else Path(args.cost_model)
    candidates_path = (root / args.candidates).resolve() if args.candidates else None
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    state_db = (root / args.state_db).resolve() if not Path(args.state_db).is_absolute() else Path(args.state_db)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    state_db.parent.mkdir(parents=True, exist_ok=True)
    if args.reset_forward_state and state_db.exists():
        state_db.unlink()

    m5 = load_bars(db, 'M5')
    m15 = load_bars(db, 'M15')
    m30 = load_bars(db, 'M30')
    if not (m5 and m15 and m30):
        raise SystemExit('Missing M5/M15/M30 data in broker DB')
    cost = load_cost_model(cost_model_path)
    stress_cost_bps = float(cost.get('stress_cost_bps') or cost.get('recommended_usage', {}).get('stress_scan_cost_bps') or 2.982003733153722)
    extreme_cost_bps = float(cost.get('extreme_cost_bps') or cost.get('recommended_usage', {}).get('extreme_spread_filter_reference_bps') or 3.0380209087577326)
    candidates = load_candidates(candidates_path, config_path)
    if not candidates:
        raise SystemExit('No hard-audit-pass candidates found in CSV or frozen config')

    latest_m15 = m15[-1].ts
    run_id = hashlib.sha1(f"{utc_now()}|{latest_m15}".encode()).hexdigest()[:16]

    with sqlite3.connect(str(state_db)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_state_schema(conn)
        previous_watermark_s = kv_get(conn, 'forward_watermark_m15_utc')
        previous_watermark = parse_ts(previous_watermark_s) if previous_watermark_s else None
        mode = 'true_forward_update'
        generated: List[Dict] = []
        inserted = 0
        notes = []

        if previous_watermark is None and not args.allow_historical_backfill:
            # This is the key fix: no historical pseudo-forward evidence on first run.
            kv_set(conn, 'forward_watermark_m15_utc', fmt_ts(latest_m15))
            kv_set(conn, 'initialized_utc', utc_now())
            kv_set(conn, 'loaderfix1_true_forward_no_backfill', '1')
            mode = 'initialize_watermark_no_backfill'
            notes.append('first normal run initialized watermark only; no historical signals generated')
        else:
            if previous_watermark is None:
                # explicit backfill mode; use earliest possible scan date.
                lower = m15[max(0, max(c.compression_window_m15 for c in candidates))].ts
                is_backfill = True
                mode = 'explicit_historical_backfill'
            else:
                lower = previous_watermark
                is_backfill = False
            if latest_m15 > lower:
                generated = generate_signals(m5, m15, m30, candidates, lower, latest_m15, stress_cost_bps, extreme_cost_bps, args.point_size, run_id, is_backfill)
                inserted = insert_signals(conn, generated)
                kv_set(conn, 'forward_watermark_m15_utc', fmt_ts(latest_m15))
            else:
                notes.append('no new M15 bars beyond forward watermark')

        evaluated = evaluate_pending(conn, m5)
        state = summarize_state(conn)
        new_watermark = kv_get(conn, 'forward_watermark_m15_utc')
        status = STATUS_INIT if mode == 'initialize_watermark_no_backfill' else STATUS_UPDATED
        next_step = 'CONTINUE_TRUE_FORWARD_SHADOW_UNTIL_MIN_EVIDENCE_NO_PROMOTION'
        summary = {
            'stage': STAGE,
            'patch': 'Stage52_LOADERFIX1_TRUE_FORWARD_NO_INITIAL_BACKFILL',
            'status': status,
            'promotion': 'NO_GO',
            'EA': 'NO_GO',
            'paper_live': 'NO_GO',
            'live': 'NO_GO',
            'next_allowed_step': next_step,
            'root': str(root),
            'db': str(db),
            'cost_model': str(cost_model_path),
            'state_db': str(state_db),
            'candidates_loaded': len(candidates),
            'rows': {'M5': len(m5), 'M15': len(m15), 'M30': len(m30)},
            'costs': {'stress_cost_bps': stress_cost_bps, 'extreme_cost_bps': extreme_cost_bps},
            'mode': mode,
            'previous_watermark_utc': previous_watermark_s,
            'latest_m15_time_utc': fmt_ts(latest_m15),
            'new_watermark_utc': new_watermark,
            'generated_signals_this_run': len(generated),
            'inserted_new_signals': inserted,
            'newly_evaluated_signals': evaluated,
            'state': state,
            'notes': notes,
            'generated_utc': utc_now(),
        }
        conn.execute(
            "INSERT OR REPLACE INTO runs(run_id,generated_utc,mode,latest_m15_time_utc,previous_watermark_utc,new_watermark_utc,candidates_loaded,generated_signals,inserted_new_signals,newly_evaluated_signals,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, summary['generated_utc'], mode, summary['latest_m15_time_utc'], previous_watermark_s, new_watermark, len(candidates), len(generated), inserted, evaluated, ';'.join(notes))
        )
        conn.commit()
        rows = conn.execute("SELECT signal_id,candidate_id,entry_time_utc,direction,entry_price,horizon_m5_bars,stress_cost_bps,spread_cost_bps,status,planned_exit_time_utc,exit_time_utc,exit_price,gross_bps,stress_bps,is_backfill FROM signals ORDER BY entry_time_utc DESC LIMIT 5000").fetchall()
    write_outputs(out_dir, summary, rows)
    print(json.dumps({'stage': STAGE, 'status': summary['status'], 'mode': mode, 'inserted_new_signals': inserted, 'newly_evaluated_signals': evaluated, 'state': state, 'out': str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
