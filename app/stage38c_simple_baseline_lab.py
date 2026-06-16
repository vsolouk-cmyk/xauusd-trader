#!/usr/bin/env python3
"""
Stage38C — Simple Baseline Lab for XAUUSD H1 bars.

Read-only diagnostic only.
No orders, no paper-live, no EA, no Stage39 promotion.

The script evaluates simple post-cost baseline families over H1 bars:
- London open continuation/reversal
- NY open continuation/reversal
- Asia range breakout/fade
- ATR expansion continuation/reversal
- HTF bias + intraday entry

COT, if available, is attached only as event annotation. It is not used as a
filter or entry condition in Stage38C.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TIMESTAMP_CANDIDATES = [
    "utc_time",
    "bar_ts_utc",
    "ts_utc",
    "timestamp_utc",
    "datetime_utc",
    "time_utc",
    "open_time_utc",
    "bar_time_utc",
    "open_time",
    "source_time",
    "timestamp",
    "datetime",
    "time",
    "ts",
]

PRICE_COLS = {
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c"],
}

SOURCE_CANDIDATES = ["source", "data_source", "feed"]
SYMBOL_CANDIDATES = ["symbol", "instrument", "ticker"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "granularity"]
SPREAD_CANDIDATES = ["spread", "spread_points", "raw_spread"]

DEFAULT_HORIZONS = [3, 5, 8, 24]
DEFAULT_LONDON_HOURS = [7, 8]
DEFAULT_NY_HOURS = [13, 14]
DEFAULT_ASIA_HOURS = list(range(0, 6))
DEFAULT_ASIA_SCAN_HOURS = list(range(7, 17))
DEFAULT_ATR_SCAN_HOURS = list(range(7, 18))
DEFAULT_ATR_THRESHOLDS = [1.20, 1.50]

ROUNDTRIP_COST_PRICE_DEFAULT = 0.49


@dataclass(frozen=True)
class Bar:
    i: int
    ts: datetime
    ts_utc: str
    date: str
    year: int
    month: str
    hour: int
    open: float
    high: float
    low: float
    close: float
    spread: Optional[float]
    tr: Optional[float] = None
    atr14_prior: Optional[float] = None


@dataclass
class DailyInfo:
    date: str
    open: float
    high: float
    low: float
    close: float
    bar_count: int
    prev_close: Optional[float] = None
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    d1_ma20_prior: Optional[float] = None
    d1_ma50_prior: Optional[float] = None
    d1_trend_pct_prior: Optional[float] = None
    htf_bias: str = "NO_BIAS"


@dataclass
class Event:
    baseline_family: str
    baseline_name: str
    horizon_bars: int
    entry_i: int
    exit_i: int
    direction: int
    entry_ts_utc: str
    exit_ts_utc: str
    entry_date_utc: str
    entry_year: int
    entry_month: str
    entry_hour_utc: int
    entry_price: float
    exit_price: float
    gross_price: float
    net_price: float
    gross_bps: float
    cost_bps: float
    net_bps: float
    signal_detail: str
    cot_state: Optional[str] = None
    cot_pressure: Optional[str] = None
    cot_crowding_score: Optional[float] = None


def qident(name: str) -> str:
    if not name or any(ch in name for ch in '"\x00'):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def parse_utc(value: Any) -> datetime:
    if value is None:
        raise ValueError("timestamp is None")
    if isinstance(value, (int, float)):
        # Accept Unix seconds as a defensive fallback.
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    s = str(value).strip()
    if not s:
        raise ValueError("empty timestamp")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Common SQLite/text fallback: "YYYY-mm-dd HH:MM:SS".
        dt = datetime.strptime(str(value).strip().replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def iso_z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def list_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [r[1] for r in rows]


def pick_col(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def require_col(cols: Sequence[str], candidates: Sequence[str], table: str, role: str) -> str:
    col = pick_col(cols, candidates)
    if not col:
        raise RuntimeError(
            f"Cannot detect {role} column in table {table!r}. "
            f"Tried: {', '.join(candidates)}. Existing columns: {', '.join(cols)}"
        )
    return col


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone()
    return row is not None


def parse_int_list(s: str) -> List[int]:
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    if not out:
        raise argparse.ArgumentTypeError("empty integer list")
    return out


def parse_float_list(s: str) -> List[float]:
    out: List[float] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    if not out:
        raise argparse.ArgumentTypeError("empty float list")
    return out


def load_bars(
    con: sqlite3.Connection,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[List[Bar], Dict[str, Any]]:
    cols = list_columns(con, table)
    if not cols:
        raise RuntimeError(f"Table {table!r} does not exist or has no columns")

    ts_col = require_col(cols, TIMESTAMP_CANDIDATES, table, "bar timestamp")
    open_col = require_col(cols, PRICE_COLS["open"], table, "open price")
    high_col = require_col(cols, PRICE_COLS["high"], table, "high price")
    low_col = require_col(cols, PRICE_COLS["low"], table, "low price")
    close_col = require_col(cols, PRICE_COLS["close"], table, "close price")
    spread_col = pick_col(cols, SPREAD_CANDIDATES)
    source_col = pick_col(cols, SOURCE_CANDIDATES)
    symbol_col = pick_col(cols, SYMBOL_CANDIDATES)
    timeframe_col = pick_col(cols, TIMEFRAME_CANDIDATES)

    select_cols = [ts_col, open_col, high_col, low_col, close_col]
    if spread_col:
        select_cols.append(spread_col)

    where_parts: List[str] = []
    params: List[Any] = []
    if source_col:
        where_parts.append(f"{qident(source_col)} = ?")
        params.append(source)
    if symbol_col:
        where_parts.append(f"{qident(symbol_col)} = ?")
        params.append(symbol)
    if timeframe_col:
        where_parts.append(f"{qident(timeframe_col)} = ?")
        params.append(timeframe)

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    sql = (
        f"SELECT {', '.join(qident(c) for c in select_cols)} "
        f"FROM {qident(table)} {where_sql} ORDER BY {qident(ts_col)}"
    )

    raw_rows = con.execute(sql, params).fetchall()
    bars_tmp: List[Dict[str, Any]] = []
    last_close: Optional[float] = None
    tr_values: List[Optional[float]] = []

    for row in raw_rows:
        try:
            dt = parse_utc(row[0])
            op = float(row[1])
            hi = float(row[2])
            lo = float(row[3])
            cl = float(row[4])
            sp = float(row[5]) if spread_col and row[5] is not None else None
        except Exception:
            continue
        if not all(math.isfinite(x) for x in [op, hi, lo, cl]):
            continue
        if hi < lo:
            continue
        if last_close is None:
            tr = hi - lo
        else:
            tr = max(hi - lo, abs(hi - last_close), abs(lo - last_close))
        tr_values.append(tr)
        atr14_prior = None
        if len(tr_values) > 14:
            prior = [v for v in tr_values[-15:-1] if v is not None]
            if len(prior) == 14:
                atr14_prior = sum(prior) / 14.0
        bars_tmp.append(
            {
                "ts": dt,
                "ts_utc": iso_z(dt),
                "date": dt.date().isoformat(),
                "year": dt.year,
                "month": f"{dt.year:04d}-{dt.month:02d}",
                "hour": dt.hour,
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "spread": sp,
                "tr": tr,
                "atr14_prior": atr14_prior,
            }
        )
        last_close = cl

    bars = [Bar(i=i, **d) for i, d in enumerate(bars_tmp)]
    meta = {
        "source_table": table,
        "timestamp_col": ts_col,
        "open_col": open_col,
        "high_col": high_col,
        "low_col": low_col,
        "close_col": close_col,
        "spread_col": spread_col,
        "source_col": source_col,
        "symbol_col": symbol_col,
        "timeframe_col": timeframe_col,
        "rows_loaded": len(bars),
        "first_bar_ts_utc": bars[0].ts_utc if bars else None,
        "last_bar_ts_utc": bars[-1].ts_utc if bars else None,
    }
    return bars, meta


def build_daily_info(bars: Sequence[Bar]) -> Tuple[Dict[str, List[Bar]], Dict[str, DailyInfo]]:
    by_date: Dict[str, List[Bar]] = defaultdict(list)
    for b in bars:
        by_date[b.date].append(b)

    daily: Dict[str, DailyInfo] = {}
    sorted_dates = sorted(by_date)
    closes: List[float] = []

    for idx, d in enumerate(sorted_dates):
        bs = sorted(by_date[d], key=lambda x: x.ts)
        info = DailyInfo(
            date=d,
            open=bs[0].open,
            high=max(b.high for b in bs),
            low=min(b.low for b in bs),
            close=bs[-1].close,
            bar_count=len(bs),
        )
        if idx > 0:
            prev = daily[sorted_dates[idx - 1]]
            info.prev_close = prev.close
            info.prev_high = prev.high
            info.prev_low = prev.low
        if len(closes) >= 20:
            info.d1_ma20_prior = sum(closes[-20:]) / 20.0
        if len(closes) >= 50:
            info.d1_ma50_prior = sum(closes[-50:]) / 50.0
        if info.d1_ma50_prior and info.prev_close:
            info.d1_trend_pct_prior = (info.prev_close - info.d1_ma50_prior) / info.d1_ma50_prior
        if (
            info.prev_close is not None
            and info.d1_ma20_prior is not None
            and info.d1_ma50_prior is not None
        ):
            if info.prev_close > info.d1_ma20_prior > info.d1_ma50_prior:
                info.htf_bias = "LONG_BIAS"
            elif info.prev_close < info.d1_ma20_prior < info.d1_ma50_prior:
                info.htf_bias = "SHORT_BIAS"
            else:
                info.htf_bias = "NO_BIAS"
        daily[d] = info
        closes.append(info.close)

    return by_date, daily


def load_cot_context(
    con: sqlite3.Connection, state_table: str
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    if not state_table or not table_exists(con, state_table):
        return {}, {"cot_context_loaded": False, "reason": "state_table_missing"}
    cols = list_columns(con, state_table)
    ts_col = pick_col(cols, ["bar_ts_utc", "utc_time", "ts_utc", "timestamp_utc"])
    state_col = pick_col(cols, ["cot_state"])
    pressure_col = pick_col(cols, ["cot_pressure"])
    score_col = pick_col(cols, ["cot_crowding_score"])
    if not ts_col or not state_col:
        return {}, {"cot_context_loaded": False, "reason": "required_columns_missing", "columns": cols}
    select_cols = [ts_col, state_col]
    if pressure_col:
        select_cols.append(pressure_col)
    if score_col:
        select_cols.append(score_col)
    sql = f"SELECT {', '.join(qident(c) for c in select_cols)} FROM {qident(state_table)}"
    out: Dict[str, Dict[str, Any]] = {}
    for row in con.execute(sql).fetchall():
        try:
            ts = iso_z(parse_utc(row[0]))
        except Exception:
            continue
        pos = 2
        rec: Dict[str, Any] = {"cot_state": row[1]}
        if pressure_col:
            rec["cot_pressure"] = row[pos]
            pos += 1
        if score_col:
            rec["cot_crowding_score"] = float(row[pos]) if row[pos] is not None else None
        out[ts] = rec
    return out, {"cot_context_loaded": True, "state_table": state_table, "rows": len(out)}


def add_event(
    events: List[Event],
    bars: Sequence[Bar],
    cot_context: Dict[str, Dict[str, Any]],
    baseline_family: str,
    baseline_name: str,
    entry_i: int,
    direction: int,
    horizon: int,
    cost_price: float,
    signal_detail: str,
) -> None:
    if direction not in (-1, 1):
        return
    exit_i = entry_i + horizon
    if entry_i < 0 or exit_i >= len(bars):
        return
    entry = bars[entry_i]
    exit_bar = bars[exit_i]
    entry_price = entry.close
    exit_price = exit_bar.close
    if entry_price <= 0 or exit_price <= 0:
        return
    gross_price = direction * (exit_price - entry_price)
    net_price = gross_price - cost_price
    gross_bps = gross_price / entry_price * 10000.0
    cost_bps = cost_price / entry_price * 10000.0
    net_bps = net_price / entry_price * 10000.0
    cot = cot_context.get(entry.ts_utc, {})
    events.append(
        Event(
            baseline_family=baseline_family,
            baseline_name=baseline_name,
            horizon_bars=horizon,
            entry_i=entry_i,
            exit_i=exit_i,
            direction=direction,
            entry_ts_utc=entry.ts_utc,
            exit_ts_utc=exit_bar.ts_utc,
            entry_date_utc=entry.date,
            entry_year=entry.year,
            entry_month=entry.month,
            entry_hour_utc=entry.hour,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_price=gross_price,
            net_price=net_price,
            gross_bps=gross_bps,
            cost_bps=cost_bps,
            net_bps=net_bps,
            signal_detail=signal_detail,
            cot_state=cot.get("cot_state"),
            cot_pressure=cot.get("cot_pressure"),
            cot_crowding_score=cot.get("cot_crowding_score"),
        )
    )


def generate_events(
    bars: Sequence[Bar],
    by_date: Dict[str, List[Bar]],
    daily: Dict[str, DailyInfo],
    cot_context: Dict[str, Dict[str, Any]],
    horizons: Sequence[int],
    cost_price: float,
    london_hours: Sequence[int],
    ny_hours: Sequence[int],
    asia_hours: Sequence[int],
    asia_scan_hours: Sequence[int],
    atr_scan_hours: Sequence[int],
    atr_thresholds: Sequence[float],
) -> List[Event]:
    events: List[Event] = []
    max_horizon = max(horizons)

    def add_for_horizons(
        family: str,
        name: str,
        entry_i: int,
        direction: int,
        detail: str,
    ) -> None:
        if entry_i + max_horizon >= len(bars):
            return
        for h in horizons:
            add_event(events, bars, cot_context, family, name, entry_i, direction, h, cost_price, detail)

    for d in sorted(by_date):
        day_bars = sorted(by_date[d], key=lambda x: x.ts)
        info = daily[d]
        hour_map: Dict[int, Bar] = {b.hour: b for b in day_bars}
        if info.prev_close is not None:
            for hour in london_hours:
                b = hour_map.get(hour)
                if not b or abs(b.close - info.prev_close) < 1e-12:
                    continue
                cont_dir = 1 if b.close > info.prev_close else -1
                add_for_horizons(
                    "LONDON_OPEN",
                    f"LONDON_OPEN_CONT_H{hour:02d}",
                    b.i,
                    cont_dir,
                    f"entry_close_vs_prev_day_close:{b.close:.5f}/{info.prev_close:.5f}",
                )
                add_for_horizons(
                    "LONDON_OPEN",
                    f"LONDON_OPEN_REV_H{hour:02d}",
                    b.i,
                    -cont_dir,
                    f"opposite_entry_close_vs_prev_day_close:{b.close:.5f}/{info.prev_close:.5f}",
                )
            for hour in ny_hours:
                b = hour_map.get(hour)
                if not b or abs(b.close - info.prev_close) < 1e-12:
                    continue
                cont_dir = 1 if b.close > info.prev_close else -1
                add_for_horizons(
                    "NY_OPEN",
                    f"NY_OPEN_CONT_H{hour:02d}",
                    b.i,
                    cont_dir,
                    f"entry_close_vs_prev_day_close:{b.close:.5f}/{info.prev_close:.5f}",
                )
                add_for_horizons(
                    "NY_OPEN",
                    f"NY_OPEN_REV_H{hour:02d}",
                    b.i,
                    -cont_dir,
                    f"opposite_entry_close_vs_prev_day_close:{b.close:.5f}/{info.prev_close:.5f}",
                )

        asia_bs = [b for b in day_bars if b.hour in set(asia_hours)]
        if len(asia_bs) >= 4:
            asia_high = max(b.high for b in asia_bs)
            asia_low = min(b.low for b in asia_bs)
            for b in day_bars:
                if b.hour not in set(asia_scan_hours):
                    continue
                breakout_dir = 0
                if b.close > asia_high:
                    breakout_dir = 1
                elif b.close < asia_low:
                    breakout_dir = -1
                if breakout_dir:
                    detail = f"asia_high={asia_high:.5f};asia_low={asia_low:.5f};close={b.close:.5f}"
                    add_for_horizons("ASIA_RANGE", "ASIA_RANGE_BREAKOUT", b.i, breakout_dir, detail)
                    add_for_horizons("ASIA_RANGE", "ASIA_RANGE_FADE", b.i, -breakout_dir, detail)
                    break

        for thr in atr_thresholds:
            for b in day_bars:
                if b.hour not in set(atr_scan_hours):
                    continue
                if not b.atr14_prior or b.atr14_prior <= 0 or not b.tr:
                    continue
                ratio = b.tr / b.atr14_prior
                if ratio < thr:
                    continue
                if abs(b.close - b.open) < 1e-12:
                    continue
                body_dir = 1 if b.close > b.open else -1
                suffix = str(thr).replace(".", "P")
                detail = f"tr_atr14_prior_ratio={ratio:.4f};threshold={thr:.2f}"
                add_for_horizons("ATR_EXPANSION", f"ATR_EXP_CONT_T{suffix}", b.i, body_dir, detail)
                add_for_horizons("ATR_EXPANSION", f"ATR_EXP_REV_T{suffix}", b.i, -body_dir, detail)
                break

        if info.htf_bias in ("LONG_BIAS", "SHORT_BIAS"):
            direction = 1 if info.htf_bias == "LONG_BIAS" else -1
            detail = (
                f"htf_bias={info.htf_bias};prev_close={info.prev_close};"
                f"ma20={info.d1_ma20_prior};ma50={info.d1_ma50_prior}"
            )
            b = hour_map.get(8)
            if b:
                add_for_horizons("HTF_BIAS", "HTF_BIAS_LONDON_H08", b.i, direction, detail)
            b = hour_map.get(13)
            if b:
                add_for_horizons("HTF_BIAS", "HTF_BIAS_NY_H13", b.i, direction, detail)

    return events


def max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def t_stat(values: Sequence[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    m = mean(values)
    sd = pstdev(values)
    if sd <= 0:
        return None
    return m / (sd / math.sqrt(n))


def positive_year_share(events: Sequence[Event]) -> Tuple[int, int, Optional[float], Dict[int, float]]:
    by_year: Dict[int, float] = defaultdict(float)
    for e in events:
        by_year[e.entry_year] += e.net_bps
    pos_years = {y: v for y, v in by_year.items() if v > 0}
    neg_years = {y: v for y, v in by_year.items() if v < 0}
    if not pos_years:
        return 0, len(neg_years), None, dict(by_year)
    total_pos = sum(pos_years.values())
    share = max(pos_years.values()) / total_pos if total_pos > 0 else None
    return len(pos_years), len(neg_years), share, dict(by_year)


def summarize_events(events: Sequence[Event]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, int], List[Event]] = defaultdict(list)
    for e in events:
        grouped[(e.baseline_family, e.baseline_name, e.horizon_bars)].append(e)

    rows: List[Dict[str, Any]] = []
    for (family, name, horizon), evs_unsorted in sorted(grouped.items()):
        evs = sorted(evs_unsorted, key=lambda e: e.entry_ts_utc)
        net = [e.net_bps for e in evs]
        gross = [e.gross_bps for e in evs]
        costs = [e.cost_bps for e in evs]
        sample = len(evs)
        pos_year_count, neg_year_count, max_pos_share, year_net = positive_year_share(evs)
        m = mean(net) if net else None
        med = median(net) if net else None
        win = sum(1 for x in net if x > 0) / sample if sample else None
        dd = max_drawdown(net)
        t = t_stat(net)
        notes: List[str] = []
        if sample < 50:
            notes.append("LOW_SAMPLE_LT_50")
        if max_pos_share is not None and max_pos_share > 0.75:
            notes.append("YEAR_CONCENTRATED")
        if pos_year_count < 3:
            notes.append("LOW_POSITIVE_YEAR_COUNT")

        decision = "KILL"
        if (
            sample >= 80
            and m is not None
            and m >= 5.0
            and t is not None
            and t >= 1.20
            and pos_year_count >= 3
            and (max_pos_share is None or max_pos_share <= 0.75)
        ):
            decision = "PASS_RESEARCH_INTEREST"
        elif sample >= 50 and m is not None and m > 0 and pos_year_count >= 2:
            decision = "WATCH"

        rows.append(
            {
                "baseline_family": family,
                "baseline_name": name,
                "horizon_bars": horizon,
                "sample_count": sample,
                "mean_gross_bps": mean(gross) if gross else None,
                "mean_cost_bps": mean(costs) if costs else None,
                "mean_net_bps": m,
                "median_net_bps": med,
                "win_rate_net": win,
                "total_net_bps": sum(net),
                "max_drawdown_bps": dd,
                "t_stat_mean_net_bps": t,
                "positive_year_count": pos_year_count,
                "negative_year_count": neg_year_count,
                "max_positive_year_share": max_pos_share,
                "year_net_bps_json": json.dumps(year_net, sort_keys=True),
                "decision": decision,
                "note": ";".join(notes) if notes else None,
            }
        )
    return rows


def recreate_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS stage38c_baseline_events;
        DROP TABLE IF EXISTS stage38c_baseline_summary;
        DROP TABLE IF EXISTS stage38c_baseline_audit;

        CREATE TABLE stage38c_baseline_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            baseline_family TEXT NOT NULL,
            baseline_name TEXT NOT NULL,
            horizon_bars INTEGER NOT NULL,
            entry_ts_utc TEXT NOT NULL,
            exit_ts_utc TEXT NOT NULL,
            entry_date_utc TEXT NOT NULL,
            entry_year INTEGER NOT NULL,
            entry_month TEXT NOT NULL,
            entry_hour_utc INTEGER NOT NULL,
            direction INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            gross_price REAL NOT NULL,
            net_price REAL NOT NULL,
            gross_bps REAL NOT NULL,
            cost_bps REAL NOT NULL,
            net_bps REAL NOT NULL,
            signal_detail TEXT,
            cot_state TEXT,
            cot_pressure TEXT,
            cot_crowding_score REAL
        );

        CREATE TABLE stage38c_baseline_summary (
            summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            baseline_family TEXT NOT NULL,
            baseline_name TEXT NOT NULL,
            horizon_bars INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            mean_gross_bps REAL,
            mean_cost_bps REAL,
            mean_net_bps REAL,
            median_net_bps REAL,
            win_rate_net REAL,
            total_net_bps REAL,
            max_drawdown_bps REAL,
            t_stat_mean_net_bps REAL,
            positive_year_count INTEGER,
            negative_year_count INTEGER,
            max_positive_year_share REAL,
            year_net_bps_json TEXT,
            decision TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE stage38c_baseline_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            decision TEXT NOT NULL,
            bars_total INTEGER NOT NULL,
            events_written INTEGER NOT NULL,
            summary_rows_written INTEGER NOT NULL,
            pass_count INTEGER NOT NULL,
            watch_count INTEGER NOT NULL,
            kill_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            note_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        );
        """
    )


def write_events(con: sqlite3.Connection, events: Sequence[Event]) -> None:
    rows = [
        (
            e.baseline_family,
            e.baseline_name,
            e.horizon_bars,
            e.entry_ts_utc,
            e.exit_ts_utc,
            e.entry_date_utc,
            e.entry_year,
            e.entry_month,
            e.entry_hour_utc,
            e.direction,
            e.entry_price,
            e.exit_price,
            e.gross_price,
            e.net_price,
            e.gross_bps,
            e.cost_bps,
            e.net_bps,
            e.signal_detail,
            e.cot_state,
            e.cot_pressure,
            e.cot_crowding_score,
        )
        for e in events
    ]
    con.executemany(
        """
        INSERT INTO stage38c_baseline_events (
            baseline_family, baseline_name, horizon_bars,
            entry_ts_utc, exit_ts_utc, entry_date_utc, entry_year, entry_month,
            entry_hour_utc, direction, entry_price, exit_price,
            gross_price, net_price, gross_bps, cost_bps, net_bps,
            signal_detail, cot_state, cot_pressure, cot_crowding_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def write_summary(con: sqlite3.Connection, summary: Sequence[Dict[str, Any]]) -> None:
    cols = [
        "baseline_family",
        "baseline_name",
        "horizon_bars",
        "sample_count",
        "mean_gross_bps",
        "mean_cost_bps",
        "mean_net_bps",
        "median_net_bps",
        "win_rate_net",
        "total_net_bps",
        "max_drawdown_bps",
        "t_stat_mean_net_bps",
        "positive_year_count",
        "negative_year_count",
        "max_positive_year_share",
        "year_net_bps_json",
        "decision",
        "note",
    ]
    con.executemany(
        f"INSERT INTO stage38c_baseline_summary ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [[r.get(c) for c in cols] for r in summary],
    )


def write_reports(
    reports_dir: Path,
    audit: Dict[str, Any],
    summary: Sequence[Dict[str, Any]],
) -> Tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38c_simple_baseline_lab.json"
    md_path = reports_dir / "stage38c_simple_baseline_lab.md"

    payload = {"audit": audit, "summary": list(summary)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    ranked = sorted(
        summary,
        key=lambda r: (
            0 if r["decision"] == "PASS_RESEARCH_INTEREST" else 1 if r["decision"] == "WATCH" else 2,
            -(r["mean_net_bps"] or -999999),
            r["baseline_name"],
            r["horizon_bars"],
        ),
    )

    lines = [
        "# Stage38C Simple Baseline Lab Report",
        "",
        "## Audit",
        "",
        "```json",
        json.dumps(audit, indent=2, sort_keys=True),
        "```",
        "",
        "## Top summary rows",
        "",
        "| decision | baseline | horizon | n | mean net bps | median net bps | win rate | t-stat | pos years | max pos year share | note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in ranked[:40]:
        lines.append(
            "| {decision} | {name} | {horizon} | {n} | {mean_net} | {median_net} | {win} | {tstat} | {pos_years} | {share} | {note} |".format(
                decision=r["decision"],
                name=r["baseline_name"],
                horizon=r["horizon_bars"],
                n=r["sample_count"],
                mean_net="" if r["mean_net_bps"] is None else f"{r['mean_net_bps']:.2f}",
                median_net="" if r["median_net_bps"] is None else f"{r['median_net_bps']:.2f}",
                win="" if r["win_rate_net"] is None else f"{r['win_rate_net']:.3f}",
                tstat="" if r["t_stat_mean_net_bps"] is None else f"{r['t_stat_mean_net_bps']:.2f}",
                pos_years=r["positive_year_count"],
                share="" if r["max_positive_year_share"] is None else f"{r['max_positive_year_share']:.3f}",
                note=r["note"] or "",
            )
        )
    lines += [
        "",
        "## Interpretation rule",
        "",
        "A PASS_RESEARCH_INTEREST row is not permission for Stage39, EA, paper-live, or live orders. It only permits deeper read-only diagnostics.",
        "",
        "COT is annotation only in this Stage38C diagnostic.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)


def make_audit_decision(summary: Sequence[Dict[str, Any]]) -> str:
    pass_count = sum(1 for r in summary if r["decision"] == "PASS_RESEARCH_INTEREST")
    watch_count = sum(1 for r in summary if r["decision"] == "WATCH")
    if pass_count > 0:
        return "PROCEED_TO_DEEP_DIAGNOSTICS_READ_ONLY"
    if watch_count > 0:
        return "WATCH_ONLY_REVIEW_BEFORE_DEEP_DIAGNOSTICS"
    return "NO_BASELINE_EDGE_STOP_OR_REDESIGN"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38C simple XAUUSD baseline lab")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--bars-table", default="bars")
    ap.add_argument("--cot-state-table", default="cot_gold_t3_feature_states")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--reports-dir", default="data/reports/stage38c_simple_baseline_lab")
    ap.add_argument("--horizons", type=parse_int_list, default=DEFAULT_HORIZONS)
    ap.add_argument("--cost-price", type=float, default=ROUNDTRIP_COST_PRICE_DEFAULT)
    ap.add_argument("--london-hours", type=parse_int_list, default=DEFAULT_LONDON_HOURS)
    ap.add_argument("--ny-hours", type=parse_int_list, default=DEFAULT_NY_HOURS)
    ap.add_argument("--asia-hours", type=parse_int_list, default=DEFAULT_ASIA_HOURS)
    ap.add_argument("--asia-scan-hours", type=parse_int_list, default=DEFAULT_ASIA_SCAN_HOURS)
    ap.add_argument("--atr-scan-hours", type=parse_int_list, default=DEFAULT_ATR_SCAN_HOURS)
    ap.add_argument("--atr-thresholds", type=parse_float_list, default=DEFAULT_ATR_THRESHOLDS)
    args = ap.parse_args(argv)

    warnings: List[str] = []
    notes: List[str] = []

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    bars, bars_meta = load_bars(con, args.bars_table, args.source, args.symbol, args.timeframe)
    if not bars:
        raise RuntimeError("No bars loaded; cannot run Stage38C baseline lab")
    if len(bars) < 1000:
        warnings.append(f"LOW_BAR_COUNT:{len(bars)}")

    by_date, daily = build_daily_info(bars)
    cot_context, cot_meta = load_cot_context(con, args.cot_state_table)
    if not cot_meta.get("cot_context_loaded"):
        notes.append(f"COT_CONTEXT_NOT_LOADED:{cot_meta.get('reason')}")
    else:
        notes.append(f"COT_CONTEXT_ANNOTATION_ONLY_ROWS:{cot_meta.get('rows')}")

    events = generate_events(
        bars=bars,
        by_date=by_date,
        daily=daily,
        cot_context=cot_context,
        horizons=args.horizons,
        cost_price=args.cost_price,
        london_hours=args.london_hours,
        ny_hours=args.ny_hours,
        asia_hours=args.asia_hours,
        asia_scan_hours=args.asia_scan_hours,
        atr_scan_hours=args.atr_scan_hours,
        atr_thresholds=args.atr_thresholds,
    )

    if not events:
        warnings.append("NO_EVENTS_GENERATED")

    summary = summarize_events(events)
    pass_count = sum(1 for r in summary if r["decision"] == "PASS_RESEARCH_INTEREST")
    watch_count = sum(1 for r in summary if r["decision"] == "WATCH")
    kill_count = sum(1 for r in summary if r["decision"] == "KILL")
    decision = make_audit_decision(summary)

    recreate_tables(con)
    write_events(con, events)
    write_summary(con, summary)

    audit: Dict[str, Any] = {
        "created_utc": iso_z(datetime.utcnow()),
        "status": "PASS" if not warnings else "PASS_WITH_WARNINGS",
        "decision": decision,
        "bars_total": len(bars),
        "events_written": len(events),
        "summary_rows_written": len(summary),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "kill_count": kill_count,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
        "metadata": {
            "bars": bars_meta,
            "cot": cot_meta,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "horizons": args.horizons,
            "cost_price": args.cost_price,
            "london_hours": args.london_hours,
            "ny_hours": args.ny_hours,
            "asia_hours": args.asia_hours,
            "asia_scan_hours": args.asia_scan_hours,
            "atr_scan_hours": args.atr_scan_hours,
            "atr_thresholds": args.atr_thresholds,
        },
    }
    json_report, md_report = write_reports(Path(args.reports_dir), audit, summary)
    audit["json_report"] = json_report
    audit["md_report"] = md_report

    con.execute(
        """
        INSERT INTO stage38c_baseline_audit (
            created_utc, status, decision, bars_total, events_written,
            summary_rows_written, pass_count, watch_count, kill_count,
            warning_count, note_count, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit["created_utc"],
            audit["status"],
            audit["decision"],
            audit["bars_total"],
            audit["events_written"],
            audit["summary_rows_written"],
            audit["pass_count"],
            audit["watch_count"],
            audit["kill_count"],
            audit["warning_count"],
            audit["note_count"],
            json.dumps(audit["metadata"], sort_keys=True),
        ),
    )
    con.commit()

    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
