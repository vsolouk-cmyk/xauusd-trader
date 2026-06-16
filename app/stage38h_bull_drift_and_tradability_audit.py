#!/usr/bin/env python3
"""
Stage38H — Bull Drift and Tradability Audit for XAUUSD H1.

Read-only diagnostic.
No strategy promotion, no Stage39, no EA, no paper/live.

Purpose:
  Detect whether positive forward returns in prior Stage38 diagnostics are
  mostly explained by naive bull drift in XAUUSD rather than alpha/context edge.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TS_CANDIDATES = [
    "bar_ts_utc", "ts_utc", "timestamp_utc", "utc_time", "time_utc",
    "datetime_utc", "datetime", "timestamp", "time", "date",
]
OPEN_CANDIDATES = ["open", "open_price", "o"]
HIGH_CANDIDATES = ["high", "high_price", "h"]
LOW_CANDIDATES = ["low", "low_price", "l"]
CLOSE_CANDIDATES = ["close", "close_price", "c"]
SOURCE_CANDIDATES = ["source", "data_source", "provider"]
SYMBOL_CANDIDATES = ["symbol", "instrument", "ticker"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "period", "bar_timeframe"]


@dataclass
class Bar:
    idx: int
    ts: datetime
    ts_iso: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class ForwardReturn:
    event_family: str
    horizon_bars: int
    event_key: str
    event_idx: int
    entry_ts: datetime
    entry_ts_iso: str
    exit_ts: datetime
    exit_ts_iso: str
    entry_close: float
    exit_close: float
    long_return_bps: float
    short_return_bps: float
    long_mfe_bps: float
    long_mae_bps: float
    net_long_return_bps: float
    year: int
    month: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage38H bull drift and tradability audit")
    p.add_argument("--db", required=True, help="SQLite DB path")
    p.add_argument("--bars-table", default="bars")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--h1-timeframes", default="H1,1h", help="comma-separated timeframe aliases")
    p.add_argument("--horizons", default="24,72,120", help="comma-separated forward horizons in H1 bars")
    p.add_argument("--cost-bps", type=float, default=2.0, help="one-trade round-trip cost in bps for net diagnostic")
    p.add_argument("--reports-dir", default="data/reports/stage38h_bull_drift_and_tradability_audit")
    return p.parse_args()


def parse_ts(value: Any) -> datetime:
    if value is None:
        raise ValueError("timestamp is None")
    if isinstance(value, (int, float)):
        # Heuristic: seconds vs milliseconds.
        v = float(value)
        if v > 10_000_000_000:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(value).strip()
    if not s:
        raise ValueError("empty timestamp")
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y",
        ]:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None  # type: ignore[assignment]
        if dt is None:
            raise
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f'pragma table_info("{table}")').fetchall()
    if not rows:
        raise RuntimeError(f"table not found or has no columns: {table}")
    return [r[1] for r in rows]


def pick_col(columns: Sequence[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    if required:
        raise RuntimeError(f"Could not find required column among candidates: {candidates}; available={columns}")
    return None


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    r = con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
    return r is not None


def load_h1_bars(
    con: sqlite3.Connection,
    table: str,
    source: str,
    symbol: str,
    h1_aliases: Sequence[str],
) -> Tuple[List[Bar], Dict[str, Any]]:
    cols = get_columns(con, table)
    ts_col = pick_col(cols, TS_CANDIDATES)
    o_col = pick_col(cols, OPEN_CANDIDATES)
    h_col = pick_col(cols, HIGH_CANDIDATES)
    l_col = pick_col(cols, LOW_CANDIDATES)
    c_col = pick_col(cols, CLOSE_CANDIDATES)
    source_col = pick_col(cols, SOURCE_CANDIDATES, required=False)
    symbol_col = pick_col(cols, SYMBOL_CANDIDATES, required=False)
    timeframe_col = pick_col(cols, TIMEFRAME_CANDIDATES, required=False)

    where: List[str] = []
    params: List[Any] = []
    if source_col:
        where.append(f'lower("{source_col}") = lower(?)')
        params.append(source)
    if symbol_col:
        where.append(f'upper("{symbol_col}") = upper(?)')
        params.append(symbol)
    if timeframe_col:
        aliases = [a.strip() for a in h1_aliases if a.strip()]
        if aliases:
            where.append("(" + " or ".join([f'lower("{timeframe_col}") = lower(?)' for _ in aliases]) + ")")
            params.extend(aliases)

    where_sql = " where " + " and ".join(where) if where else ""
    sql = f'''
        select "{ts_col}", "{o_col}", "{h_col}", "{l_col}", "{c_col}"
        from "{table}"
        {where_sql}
        order by "{ts_col}"
    '''
    rows = con.execute(sql, params).fetchall()

    bars: List[Bar] = []
    bad_rows = 0
    for r in rows:
        try:
            dt = parse_ts(r[0])
            o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
            if not all(math.isfinite(x) for x in [o, h, l, c]):
                bad_rows += 1
                continue
            if c <= 0 or h <= 0 or l <= 0:
                bad_rows += 1
                continue
            bars.append(Bar(len(bars), dt, iso_z(dt), o, h, l, c))
        except Exception:
            bad_rows += 1

    meta = {
        "table": table,
        "timestamp_column": ts_col,
        "open_column": o_col,
        "high_column": h_col,
        "low_column": l_col,
        "close_column": c_col,
        "source_column": source_col,
        "symbol_column": symbol_col,
        "timeframe_column": timeframe_col,
        "raw_rows_loaded": len(rows),
        "bad_rows_skipped": bad_rows,
    }
    if not bars:
        raise RuntimeError(f"No usable H1 bars loaded from {table}; meta={meta}")
    return bars, meta


def mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def median(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    m = n // 2
    if n % 2:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


def stdev_sample(xs: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    mu = mean(xs)
    assert mu is not None
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def t_stat_mean(xs: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    sd = stdev_sample(xs)
    if not sd or sd == 0:
        return None
    mu = mean(xs)
    assert mu is not None
    return mu / (sd / math.sqrt(len(xs)))


def max_drawdown(cumulative: Sequence[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for v in cumulative:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def cumulative_curve(xs: Sequence[float]) -> List[float]:
    out: List[float] = []
    s = 0.0
    for x in xs:
        s += x
        out.append(s)
    return out


def event_indices_daily(bars: Sequence[Bar]) -> List[Tuple[str, int]]:
    seen: set[str] = set()
    out: List[Tuple[str, int]] = []
    for b in bars:
        key = b.ts.date().isoformat()
        if key not in seen:
            seen.add(key)
            out.append((key, b.idx))
    return out


def event_indices_weekly(bars: Sequence[Bar]) -> List[Tuple[str, int]]:
    seen: set[str] = set()
    out: List[Tuple[str, int]] = []
    for b in bars:
        y, w, _ = b.ts.isocalendar()
        key = f"{y}-W{int(w):02d}"
        if key not in seen:
            seen.add(key)
            out.append((key, b.idx))
    return out


def event_indices_h1_all(bars: Sequence[Bar]) -> List[Tuple[str, int]]:
    return [(b.ts_iso, b.idx) for b in bars]


def compute_forward_returns(
    bars: Sequence[Bar],
    horizons: Sequence[int],
    cost_bps: float,
) -> List[ForwardReturn]:
    families = {
        "DAILY_ANCHOR": event_indices_daily(bars),
        "WEEKLY_ANCHOR": event_indices_weekly(bars),
        "H1_ALL": event_indices_h1_all(bars),
    }
    out: List[ForwardReturn] = []
    n = len(bars)
    for family, idxs in families.items():
        for h in horizons:
            for key, i in idxs:
                j = i + h
                if j >= n:
                    continue
                entry = bars[i]
                exitb = bars[j]
                entry_price = entry.close
                exit_price = exitb.close
                if entry_price <= 0:
                    continue
                segment = bars[i + 1 : j + 1]
                max_high = max(b.high for b in segment) if segment else exit_price
                min_low = min(b.low for b in segment) if segment else exit_price
                long_ret = (exit_price - entry_price) / entry_price * 10000.0
                short_ret = -long_ret
                mfe = (max_high - entry_price) / entry_price * 10000.0
                mae = (min_low - entry_price) / entry_price * 10000.0
                out.append(
                    ForwardReturn(
                        event_family=family,
                        horizon_bars=h,
                        event_key=key,
                        event_idx=i,
                        entry_ts=entry.ts,
                        entry_ts_iso=entry.ts_iso,
                        exit_ts=exitb.ts,
                        exit_ts_iso=exitb.ts_iso,
                        entry_close=entry_price,
                        exit_close=exit_price,
                        long_return_bps=long_ret,
                        short_return_bps=short_ret,
                        long_mfe_bps=mfe,
                        long_mae_bps=mae,
                        net_long_return_bps=long_ret - cost_bps,
                        year=entry.ts.year,
                        month=f"{entry.ts.year}-{entry.ts.month:02d}",
                    )
                )
    return out


def split_half_values(rows: Sequence[ForwardReturn]) -> Tuple[List[float], List[float]]:
    if not rows:
        return [], []
    sorted_rows = sorted(rows, key=lambda r: r.entry_ts)
    mid = len(sorted_rows) // 2
    return [r.long_return_bps for r in sorted_rows[:mid]], [r.long_return_bps for r in sorted_rows[mid:]]


def loo_worst(rows: Sequence[ForwardReturn]) -> Tuple[Optional[float], Optional[int]]:
    years = sorted({r.year for r in rows})
    if len(years) < 2:
        return None, None
    vals: List[Tuple[float, int]] = []
    for y in years:
        kept = [r.long_return_bps for r in rows if r.year != y]
        if kept:
            vals.append((mean(kept) or 0.0, y))
    if not vals:
        return None, None
    return min(vals, key=lambda x: x[0])


def concentration_counts(rows: Sequence[ForwardReturn]) -> Dict[str, Any]:
    by_year: Dict[int, float] = {}
    by_month: Dict[str, float] = {}
    for r in rows:
        by_year[r.year] = by_year.get(r.year, 0.0) + r.long_return_bps
        by_month[r.month] = by_month.get(r.month, 0.0) + r.long_return_bps
    pos_years = {y: v for y, v in by_year.items() if v > 0}
    neg_years = {y: v for y, v in by_year.items() if v < 0}
    pos_months = {m: v for m, v in by_month.items() if v > 0}
    neg_months = {m: v for m, v in by_month.items() if v < 0}
    total_pos_year = sum(pos_years.values())
    total_pos_month = sum(pos_months.values())
    max_pos_year_share = max(pos_years.values()) / total_pos_year if total_pos_year > 0 else None
    max_pos_month_share = max(pos_months.values()) / total_pos_month if total_pos_month > 0 else None
    return {
        "positive_year_count": len(pos_years),
        "negative_year_count": len(neg_years),
        "max_positive_year_share": max_pos_year_share,
        "positive_month_count": len(pos_months),
        "negative_month_count": len(neg_months),
        "max_positive_month_share": max_pos_month_share,
        "year_totals": by_year,
        "month_totals": by_month,
    }


def summarize_rows(event_family: str, horizon: int, rows: Sequence[ForwardReturn], cost_bps: float) -> Dict[str, Any]:
    vals = [r.long_return_bps for r in rows]
    net_vals = [r.net_long_return_bps for r in rows]
    short_vals = [r.short_return_bps for r in rows]
    mfe_vals = [r.long_mfe_bps for r in rows]
    mae_vals = [r.long_mae_bps for r in rows]
    abs_mae_vals = [abs(min(0.0, x)) for x in mae_vals]
    first_half, second_half = split_half_values(rows)
    worst_loo, worst_loo_year = loo_worst(rows)
    c = concentration_counts(rows)

    years = sorted({r.year for r in rows})
    pre2025 = [r.long_return_bps for r in rows if r.year < 2025]
    exclude2025 = [r.long_return_bps for r in rows if r.year != 2025]
    y2025 = [r.long_return_bps for r in rows if r.year == 2025]
    y2026 = [r.long_return_bps for r in rows if r.year == 2026]

    mu = mean(vals)
    med = median(vals)
    win_rate = sum(1 for x in vals if x > 0) / len(vals) if vals else None
    tstat = t_stat_mean(vals)
    net_mu = mean(net_vals)
    short_mu = mean(short_vals)
    dd = max_drawdown(cumulative_curve(vals))
    net_dd = max_drawdown(cumulative_curve(net_vals))

    med_abs_mae = median(abs_mae_vals)
    med_mfe = median(mfe_vals)
    p90_abs_mae = None
    if abs_mae_vals:
        s = sorted(abs_mae_vals)
        p90_abs_mae = s[min(len(s) - 1, int(math.ceil(0.90 * len(s))) - 1)]
    ret_to_mae = None
    if med_abs_mae and med_abs_mae > 0 and med is not None:
        ret_to_mae = med / med_abs_mae

    notes: List[str] = []
    decision = "DRIFT_REFERENCE"
    if event_family == "DAILY_ANCHOR":
        if mu is not None and mu > 20 and horizon >= 72:
            decision = "BULL_DRIFT_PRESENT_REQUIRES_ALPHA_ABOVE_BASELINE"
        if (
            mu is not None and mu > 20 and horizon >= 72 and
            ((c["max_positive_year_share"] is not None and c["max_positive_year_share"] > 0.55) or len([y for y in years if y >= 2025]) >= 1)
        ):
            decision = "BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION"
    if event_family == "H1_ALL":
        decision = "OVERLAPPED_H1_DRIFT_REFERENCE_ONLY"
    if event_family == "WEEKLY_ANCHOR":
        decision = "LOW_OVERLAP_WEEKLY_DRIFT_REFERENCE"

    if c["max_positive_year_share"] is not None and c["max_positive_year_share"] > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if c["max_positive_month_share"] is not None and c["max_positive_month_share"] > 0.35:
        notes.append("MONTH_CONCENTRATED_GT_35PCT")
    if c["positive_year_count"] < 4:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_4")
    if mean(exclude2025) is not None and mu is not None and mean(exclude2025) < mu * 0.5:
        notes.append("EXCLUDE_2025_MUCH_WEAKER_THAN_ALL")
    if mean(first_half) is not None and mean(second_half) is not None:
        if (mean(first_half) or 0.0) * (mean(second_half) or 0.0) < 0:
            notes.append("CHRONO_HALF_SIGN_MISMATCH")
    if med_abs_mae is not None and med_abs_mae > 0 and med is not None and med / med_abs_mae < 0.35:
        notes.append("LOW_MEDIAN_RETURN_TO_MAE")

    return {
        "event_family": event_family,
        "horizon_bars": horizon,
        "sample_count": len(vals),
        "long_mean_return_bps": mu,
        "long_median_return_bps": med,
        "long_win_rate": win_rate,
        "long_t_stat": tstat,
        "short_mean_return_bps": short_mu,
        "net_long_mean_return_bps": net_mu,
        "cost_bps": cost_bps,
        "event_clock_max_drawdown_bps": dd,
        "net_event_clock_max_drawdown_bps": net_dd,
        "median_mfe_bps": med_mfe,
        "median_mae_bps": median(mae_vals),
        "median_abs_mae_bps": med_abs_mae,
        "p90_abs_mae_bps": p90_abs_mae,
        "median_return_to_abs_mae": ret_to_mae,
        "positive_year_count": c["positive_year_count"],
        "negative_year_count": c["negative_year_count"],
        "max_positive_year_share": c["max_positive_year_share"],
        "positive_month_count": c["positive_month_count"],
        "negative_month_count": c["negative_month_count"],
        "max_positive_month_share": c["max_positive_month_share"],
        "pre2025_mean_return_bps": mean(pre2025),
        "exclude_2025_mean_return_bps": mean(exclude2025),
        "y2025_mean_return_bps": mean(y2025),
        "y2026_mean_return_bps": mean(y2026),
        "first_half_mean_return_bps": mean(first_half),
        "second_half_mean_return_bps": mean(second_half),
        "worst_loo_mean_return_bps": worst_loo,
        "worst_loo_excluded_year": worst_loo_year,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
    }


def yearly_bar_returns(bars: Sequence[Bar]) -> List[Dict[str, Any]]:
    by_year: Dict[int, List[Bar]] = {}
    for b in bars:
        by_year.setdefault(b.ts.year, []).append(b)
    out: List[Dict[str, Any]] = []
    for y, bs in sorted(by_year.items()):
        if len(bs) < 2:
            continue
        first, last = bs[0], bs[-1]
        ret_bps = (last.close - first.close) / first.close * 10000.0
        out.append({
            "year": y,
            "first_ts_utc": first.ts_iso,
            "last_ts_utc": last.ts_iso,
            "first_close": first.close,
            "last_close": last.close,
            "year_close_to_close_return_bps": ret_bps,
            "bar_count": len(bs),
        })
    return out


def recreate_tables(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    for t in [
        "stage38h_bull_drift_forward_returns",
        "stage38h_bull_drift_summary",
        "stage38h_bull_drift_year_summary",
        "stage38h_bull_drift_audit",
    ]:
        cur.execute(f'drop table if exists "{t}"')

    cur.execute('''
    create table stage38h_bull_drift_forward_returns (
        event_family text,
        horizon_bars integer,
        event_key text,
        event_idx integer,
        entry_ts_utc text,
        exit_ts_utc text,
        entry_close real,
        exit_close real,
        long_return_bps real,
        short_return_bps real,
        long_mfe_bps real,
        long_mae_bps real,
        net_long_return_bps real,
        event_year integer,
        event_month text
    )
    ''')
    cur.execute('''
    create table stage38h_bull_drift_summary (
        event_family text,
        horizon_bars integer,
        sample_count integer,
        long_mean_return_bps real,
        long_median_return_bps real,
        long_win_rate real,
        long_t_stat real,
        short_mean_return_bps real,
        net_long_mean_return_bps real,
        cost_bps real,
        event_clock_max_drawdown_bps real,
        net_event_clock_max_drawdown_bps real,
        median_mfe_bps real,
        median_mae_bps real,
        median_abs_mae_bps real,
        p90_abs_mae_bps real,
        median_return_to_abs_mae real,
        positive_year_count integer,
        negative_year_count integer,
        max_positive_year_share real,
        positive_month_count integer,
        negative_month_count integer,
        max_positive_month_share real,
        pre2025_mean_return_bps real,
        exclude_2025_mean_return_bps real,
        y2025_mean_return_bps real,
        y2026_mean_return_bps real,
        first_half_mean_return_bps real,
        second_half_mean_return_bps real,
        worst_loo_mean_return_bps real,
        worst_loo_excluded_year integer,
        decision text,
        note text
    )
    ''')
    cur.execute('''
    create table stage38h_bull_drift_year_summary (
        year integer,
        first_ts_utc text,
        last_ts_utc text,
        first_close real,
        last_close real,
        year_close_to_close_return_bps real,
        bar_count integer
    )
    ''')
    cur.execute('''
    create table stage38h_bull_drift_audit (
        audit_id integer primary key autoincrement,
        created_utc text,
        status text,
        decision text,
        bars_loaded integer,
        forward_rows_written integer,
        summary_rows_written integer,
        year_rows_written integer,
        warning_count integer,
        note_count integer,
        min_bar_ts_utc text,
        max_bar_ts_utc text,
        metadata_json text
    )
    ''')
    con.commit()


def insert_outputs(
    con: sqlite3.Connection,
    returns: Sequence[ForwardReturn],
    summaries: Sequence[Dict[str, Any]],
    year_rows: Sequence[Dict[str, Any]],
) -> None:
    cur = con.cursor()
    cur.executemany('''
    insert into stage38h_bull_drift_forward_returns values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', [
        (
            r.event_family, r.horizon_bars, r.event_key, r.event_idx,
            r.entry_ts_iso, r.exit_ts_iso, r.entry_close, r.exit_close,
            r.long_return_bps, r.short_return_bps, r.long_mfe_bps, r.long_mae_bps,
            r.net_long_return_bps, r.year, r.month,
        )
        for r in returns
    ])
    cur.executemany('''
    insert into stage38h_bull_drift_summary values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', [
        (
            s["event_family"], s["horizon_bars"], s["sample_count"],
            s["long_mean_return_bps"], s["long_median_return_bps"], s["long_win_rate"],
            s["long_t_stat"], s["short_mean_return_bps"], s["net_long_mean_return_bps"],
            s["cost_bps"], s["event_clock_max_drawdown_bps"], s["net_event_clock_max_drawdown_bps"],
            s["median_mfe_bps"], s["median_mae_bps"], s["median_abs_mae_bps"],
            s["p90_abs_mae_bps"], s["median_return_to_abs_mae"],
            s["positive_year_count"], s["negative_year_count"], s["max_positive_year_share"],
            s["positive_month_count"], s["negative_month_count"], s["max_positive_month_share"],
            s["pre2025_mean_return_bps"], s["exclude_2025_mean_return_bps"],
            s["y2025_mean_return_bps"], s["y2026_mean_return_bps"],
            s["first_half_mean_return_bps"], s["second_half_mean_return_bps"],
            s["worst_loo_mean_return_bps"], s["worst_loo_excluded_year"],
            s["decision"], s["note"],
        )
        for s in summaries
    ])
    cur.executemany('''
    insert into stage38h_bull_drift_year_summary values (?,?,?,?,?,?,?)
    ''', [
        (
            y["year"], y["first_ts_utc"], y["last_ts_utc"], y["first_close"], y["last_close"],
            y["year_close_to_close_return_bps"], y["bar_count"],
        )
        for y in year_rows
    ])
    con.commit()


def make_report(
    args: argparse.Namespace,
    bars: Sequence[Bar],
    returns: Sequence[ForwardReturn],
    summaries: Sequence[Dict[str, Any]],
    year_rows: Sequence[Dict[str, Any]],
    audit: Dict[str, Any],
    reports_dir: Path,
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "audit": audit,
        "summary": summaries,
        "year_summary": year_rows,
    }
    (reports_dir / "stage38h_bull_drift_and_tradability_audit.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    lines: List[str] = []
    lines.append("# Stage38H Bull Drift and Tradability Audit")
    lines.append("")
    lines.append("Read-only diagnostic. No Stage39, EA, paper-live, or live trading.")
    lines.append("")
    lines.append("## Audit")
    lines.append("")
    for k in ["status", "decision", "bars_loaded", "forward_rows_written", "summary_rows_written", "year_rows_written", "min_bar_ts_utc", "max_bar_ts_utc"]:
        lines.append(f"- {k}: `{audit.get(k)}`")
    lines.append("")
    lines.append("## Key summary rows")
    lines.append("")
    lines.append("| family | horizon | n | mean | median | WR | t | net mean | DD | +yrs | -yrs | max +yr share | pre2025 | excl2025 | 2025 | 2026 | decision | note |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")
    order = {"DAILY_ANCHOR": 1, "WEEKLY_ANCHOR": 2, "H1_ALL": 3}
    for s in sorted(summaries, key=lambda x: (order.get(x["event_family"], 99), x["horizon_bars"])):
        def f(x: Any, nd: int = 2) -> str:
            if x is None:
                return ""
            if isinstance(x, float):
                return f"{x:.{nd}f}"
            return str(x)
        lines.append(
            "| " + " | ".join([
                str(s["event_family"]), str(s["horizon_bars"]), str(s["sample_count"]),
                f(s["long_mean_return_bps"]), f(s["long_median_return_bps"]), f(s["long_win_rate"], 3),
                f(s["long_t_stat"]), f(s["net_long_mean_return_bps"]), f(s["event_clock_max_drawdown_bps"]),
                str(s["positive_year_count"]), str(s["negative_year_count"]), f(s["max_positive_year_share"], 3),
                f(s["pre2025_mean_return_bps"]), f(s["exclude_2025_mean_return_bps"]),
                f(s["y2025_mean_return_bps"]), f(s["y2026_mean_return_bps"]),
                str(s["decision"]), str(s["note"] or ""),
            ]) + " |"
        )
    lines.append("")
    lines.append("## Year close-to-close drift")
    lines.append("")
    lines.append("| year | first close | last close | close-to-close bps | bars |")
    lines.append("|---:|---:|---:|---:|---:|")
    for y in year_rows:
        lines.append(f"| {y['year']} | {y['first_close']:.2f} | {y['last_close']:.2f} | {y['year_close_to_close_return_bps']:.2f} | {y['bar_count']} |")
    lines.append("")
    lines.append("## Interpretation guardrail")
    lines.append("")
    lines.append("If daily or weekly always-long baselines explain most positive forward returns, prior context positives must not be treated as alpha. Any future candidate must beat these drift baselines on event-clock uplift and drawdown, not only on subset trade mean.")

    (reports_dir / "stage38h_bull_drift_and_tradability_audit.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    h1_aliases = [x.strip() for x in args.h1_timeframes.split(",") if x.strip()]
    reports_dir = Path(args.reports_dir)

    con = sqlite3.connect(args.db)
    con.execute("pragma journal_mode=wal")

    bars, meta = load_h1_bars(con, args.bars_table, args.source, args.symbol, h1_aliases)
    returns = compute_forward_returns(bars, horizons, args.cost_bps)

    summaries: List[Dict[str, Any]] = []
    for fam in ["DAILY_ANCHOR", "WEEKLY_ANCHOR", "H1_ALL"]:
        for h in horizons:
            rows = [r for r in returns if r.event_family == fam and r.horizon_bars == h]
            if rows:
                summaries.append(summarize_rows(fam, h, rows, args.cost_bps))

    year_rows = yearly_bar_returns(bars)

    recreate_tables(con)
    insert_outputs(con, returns, summaries, year_rows)

    daily_120 = next((s for s in summaries if s["event_family"] == "DAILY_ANCHOR" and s["horizon_bars"] == 120), None)
    decision = "BULL_DRIFT_RECHECK_COMPLETE_REVIEW"
    notes: List[str] = []
    warnings: List[str] = []
    if daily_120:
        m = daily_120.get("long_mean_return_bps")
        excl = daily_120.get("exclude_2025_mean_return_bps")
        max_share = daily_120.get("max_positive_year_share")
        if m is not None and m > 20:
            decision = "BULL_DRIFT_PRESENT_REQUIRES_ALPHA_ABOVE_BASELINE"
            notes.append("DAILY_120H_ALWAYS_LONG_POSITIVE")
        if m is not None and m > 20 and max_share is not None and max_share > 0.55:
            decision = "BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION"
            notes.append("DAILY_120H_YEAR_CONCENTRATED")
        if excl is not None and m is not None and excl < m * 0.55:
            notes.append("EXCLUDE_2025_WEAKER_THAN_ALL")
    else:
        warnings.append("MISSING_DAILY_120_SUMMARY")

    audit = {
        "created_utc": iso_z(datetime.now(timezone.utc)),
        "status": "PASS" if returns and summaries else "FAIL",
        "decision": decision,
        "bars_loaded": len(bars),
        "forward_rows_written": len(returns),
        "summary_rows_written": len(summaries),
        "year_rows_written": len(year_rows),
        "warning_count": len(warnings),
        "note_count": len(notes),
        "min_bar_ts_utc": bars[0].ts_iso,
        "max_bar_ts_utc": bars[-1].ts_iso,
        "metadata": {**meta, "horizons": horizons, "h1_aliases": h1_aliases, "cost_bps": args.cost_bps, "notes": notes, "warnings": warnings},
    }

    con.execute('''
    insert into stage38h_bull_drift_audit (
        created_utc, status, decision, bars_loaded, forward_rows_written,
        summary_rows_written, year_rows_written, warning_count, note_count,
        min_bar_ts_utc, max_bar_ts_utc, metadata_json
    ) values (?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        audit["created_utc"], audit["status"], audit["decision"], audit["bars_loaded"],
        audit["forward_rows_written"], audit["summary_rows_written"], audit["year_rows_written"],
        audit["warning_count"], audit["note_count"], audit["min_bar_ts_utc"], audit["max_bar_ts_utc"],
        json.dumps(audit["metadata"], default=str),
    ))
    con.commit()

    make_report(args, bars, returns, summaries, year_rows, audit, reports_dir)

    print("audit:", (
        audit["status"], audit["decision"], audit["bars_loaded"], audit["forward_rows_written"],
        audit["summary_rows_written"], audit["year_rows_written"], audit["warning_count"], audit["note_count"],
        audit["min_bar_ts_utc"], audit["max_bar_ts_utc"],
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
