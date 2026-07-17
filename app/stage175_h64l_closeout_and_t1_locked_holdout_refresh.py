#!/usr/bin/env python3
"""
Stage175 — H64L closeout and exact locked T1 holdout refresh.

Purpose
-------
1. Record the Stage174 H64L commercial-rescue closeout.
2. Re-evaluate exactly one previously locked Stage38A T1 formulation on a
   final 20% time holdout, without variant search or threshold optimization.

The locked formulation is:
- long only;
- macro supportive, or neutral/non-hostile under the archived rule;
- D1 close > D1 MA50 and H4 close > H4 MA50;
- locked structural-expansion filter:
    d1_trend_pct >= 5%, h4_trend_pct >= 2%, ATR(H1,14)/price >= 0.30%;
- sweep/acceptance above previous UTC-day high;
- V1 close-acceptance entry at next H1 open;
- structural stop with 0.10 ATR buffer, stop distance 0.50–2.50 ATR;
- target 1.5R;
- five-H1-bar time stop;
- conservative p90 spread penalty of 49 points × 0.01.

No order, demo, paper, live, ML, broad scan, or parameter optimization path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage175_H64L_CLOSEOUT_AND_T1_LOCKED_HOLDOUT_REFRESH"


@dataclass
class Bar:
    idx: int
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float
    atr_h1_14: Optional[float] = None
    previous_day_high: Optional[float] = None
    d1_close: Optional[float] = None
    d1_ma50: Optional[float] = None
    h4_close: Optional[float] = None
    h4_ma50: Optional[float] = None
    macro_regime: Optional[str] = None
    macro_score_long_gold: Optional[float] = None
    d_real_yield_20d: Optional[float] = None
    d_usd_20d_pct: Optional[float] = None


@dataclass
class MacroRow:
    obs_date: date
    macro_regime: str
    macro_score_long_gold: Optional[float]
    d_real_yield_20d: Optional[float]
    d_usd_20d_pct: Optional[float]


@dataclass
class D1Row:
    d: date
    high: float
    close: float
    ma50: Optional[float]


@dataclass
class H4Row:
    start: datetime
    end: datetime
    close: float
    ma50: Optional[float]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_dt(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # MT5 exports commonly use YYYY.MM.DD.
    if len(text) >= 10 and text[4] == "." and text[7] == ".":
        text = text[:4] + "-" + text[5:7] + "-" + text[8:]
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def clean(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return round(value, 10)
    return value


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        if not fieldnames:
            return
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: clean(row.get(k, "")) for k in fieldnames})


def normalize_header(name: str) -> str:
    return str(name).strip().lower().replace("<", "").replace(">", "")


def load_h1_csv(path: Path) -> List[Bar]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("H1 CSV has no header")
        header_map = {normalize_header(h): h for h in reader.fieldnames}
        required_ohlc = ["open", "high", "low", "close"]
        missing = [c for c in required_ohlc if c not in header_map]
        if missing:
            raise ValueError(f"H1 OHLC columns missing: {missing}; actual={reader.fieldnames}")

        direct_ts = next((c for c in ("timestamp", "timestamp_utc", "utc_time", "datetime", "time_utc") if c in header_map), None)
        split_ts = "date" in header_map and "time" in header_map
        if not direct_ts and not split_ts:
            raise ValueError(f"H1 timestamp missing; actual={reader.fieldnames}")

        by_time: Dict[datetime, Tuple[float, float, float, float]] = {}
        for row_num, row in enumerate(reader, start=2):
            if direct_ts:
                raw_ts = row.get(header_map[direct_ts], "")
            else:
                raw_ts = f"{row.get(header_map['date'], '')}T{row.get(header_map['time'], '')}"
            try:
                ts = parse_dt(raw_ts)
                o = float(row[header_map["open"]])
                h = float(row[header_map["high"]])
                l = float(row[header_map["low"]])
                c = float(row[header_map["close"]])
            except Exception as exc:
                raise ValueError(f"Invalid H1 row {row_num}: {exc}") from exc
            if not (l <= min(o, c) <= max(o, c) <= h):
                raise ValueError(f"H1 OHLC invariant failed at row {row_num}")
            by_time[ts] = (o, h, l, c)

    bars = [Bar(idx=i, utc_time=ts, open=v[0], high=v[1], low=v[2], close=v[3])
            for i, (ts, v) in enumerate(sorted(by_time.items()))]
    if not bars:
        raise ValueError("H1 CSV produced zero bars")
    return bars


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [str(row[1]) for row in conn.execute(f"pragma table_info({table})")]


def load_macro_db(path: Path) -> List[MacroRow]:
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        if not table_exists(conn, "macro_daily_regime"):
            raise ValueError(f"macro_daily_regime missing in {path}")
        cols = set(table_columns(conn, "macro_daily_regime"))
        required = {"obs_date", "macro_regime", "macro_score_long_gold", "d_real_yield_20d", "d_usd_20d_pct"}
        missing = sorted(required - cols)
        if missing:
            raise ValueError(f"macro_daily_regime missing columns {missing} in {path}")
        rows = conn.execute(
            """
            select obs_date, macro_regime, macro_score_long_gold,
                   d_real_yield_20d, d_usd_20d_pct
            from macro_daily_regime order by obs_date
            """
        ).fetchall()
        out = [MacroRow(parse_date(r[0]), str(r[1] or ""), safe_float(r[2]), safe_float(r[3]), safe_float(r[4])) for r in rows]
        if not out:
            raise ValueError(f"macro_daily_regime empty in {path}")
        return out
    finally:
        conn.close()


def resolve_existing(root: Path, explicit: Optional[str], candidates: Sequence[str], glob_pattern: Optional[str] = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"Explicit input not found: {p}")
    for item in candidates:
        p = Path(item).expanduser()
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p.resolve()
    if glob_pattern:
        hits = sorted(root.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if hits:
            return hits[0].resolve()
    raise FileNotFoundError(f"No input found. candidates={list(candidates)} glob={glob_pattern}")


def compute_atr(bars: List[Bar], period: int) -> None:
    trs: List[float] = []
    prev_close: Optional[float] = None
    for b in bars:
        tr = b.high - b.low if prev_close is None else max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        trs.append(tr)
        prev_close = b.close
    for i, b in enumerate(bars):
        if i + 1 >= period:
            b.atr_h1_14 = sum(trs[i - period + 1:i + 1]) / period


def derive_d1(bars: List[Bar], min_h1_count: int, ma_period: int) -> Dict[date, D1Row]:
    groups: Dict[date, List[Bar]] = defaultdict(list)
    for b in bars:
        groups[b.utc_time.date()].append(b)
    rows: List[D1Row] = []
    closes: List[float] = []
    for d in sorted(groups):
        g = groups[d]
        if len(g) < min_h1_count:
            continue
        closes.append(g[-1].close)
        ma = sum(closes[-ma_period:]) / ma_period if len(closes) >= ma_period else None
        rows.append(D1Row(d=d, high=max(x.high for x in g), close=g[-1].close, ma50=ma))
    return {r.d: r for r in rows}


def h4_floor(dt: datetime) -> datetime:
    return dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)


def derive_h4(bars: List[Bar], min_h1_count: int, ma_period: int) -> List[H4Row]:
    groups: Dict[datetime, List[Bar]] = defaultdict(list)
    for b in bars:
        groups[h4_floor(b.utc_time)].append(b)
    out: List[H4Row] = []
    closes: List[float] = []
    for start in sorted(groups):
        g = groups[start]
        if len(g) < min_h1_count:
            continue
        closes.append(g[-1].close)
        ma = sum(closes[-ma_period:]) / ma_period if len(closes) >= ma_period else None
        out.append(H4Row(start=start, end=start + timedelta(hours=4), close=g[-1].close, ma50=ma))
    return out


def attach_context(bars: List[Bar], macro_rows: List[MacroRow], cfg: Dict[str, Any]) -> Dict[str, Any]:
    d1 = derive_d1(bars, int(cfg["d1_min_h1_count"]), int(cfg["d1_ma_period"]))
    valid_dates = sorted(d1)
    h4 = derive_h4(bars, int(cfg["h4_min_h1_count"]), int(cfg["h4_ma_period"]))
    h4_ends = [r.end for r in h4]
    macro_dates = [m.obs_date for m in macro_rows]
    joined = 0

    for b in bars:
        pos = bisect_right(valid_dates, b.utc_time.date()) - 1
        while pos >= 0 and valid_dates[pos] >= b.utc_time.date():
            pos -= 1
        if pos >= 0:
            row = d1[valid_dates[pos]]
            b.previous_day_high = row.high
            b.d1_close = row.close
            b.d1_ma50 = row.ma50

        signal_close = b.utc_time + timedelta(hours=1)
        hp = bisect_right(h4_ends, signal_close) - 1
        if hp >= 0:
            b.h4_close = h4[hp].close
            b.h4_ma50 = h4[hp].ma50

        mp = bisect_right(macro_dates, b.utc_time.date()) - 1
        if mp >= 0:
            m = macro_rows[mp]
            if (b.utc_time.date() - m.obs_date).days <= int(cfg["max_macro_ffill_days"]):
                b.macro_regime = m.macro_regime
                b.macro_score_long_gold = m.macro_score_long_gold
                b.d_real_yield_20d = m.d_real_yield_20d
                b.d_usd_20d_pct = m.d_usd_20d_pct
                joined += 1
    return {
        "macro_joined_bars": joined,
        "macro_join_fraction": joined / len(bars),
        "macro_min_date": macro_rows[0].obs_date.isoformat(),
        "macro_max_date": macro_rows[-1].obs_date.isoformat(),
    }


def macro_permitted(b: Bar) -> Tuple[bool, str]:
    regime = (b.macro_regime or "").lower()
    if regime == "supportive":
        return True, "supportive"
    if regime == "neutral":
        score_ok = b.macro_score_long_gold is not None and b.macro_score_long_gold >= 0
        real_ok = b.d_real_yield_20d is not None and b.d_real_yield_20d <= 0
        usd_ok = b.d_usd_20d_pct is not None and b.d_usd_20d_pct <= 0
        if score_ok and (real_ok or usd_ok):
            return True, "neutral_non_hostile"
    return False, regime or "missing_macro"


def basic_structure_permitted(b: Bar) -> bool:
    return all(v is not None for v in (b.d1_close, b.d1_ma50, b.h4_close, b.h4_ma50)) and b.d1_close > b.d1_ma50 and b.h4_close > b.h4_ma50


def locked_filter_permitted(b: Bar, entry_price: float, cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Optional[float]]]:
    d1_pct = None if b.d1_close is None or b.d1_ma50 in (None, 0) else (b.d1_close - b.d1_ma50) / b.d1_ma50
    h4_pct = None if b.h4_close is None or b.h4_ma50 in (None, 0) else (b.h4_close - b.h4_ma50) / b.h4_ma50
    atr_pct = None if b.atr_h1_14 is None or entry_price == 0 else b.atr_h1_14 / entry_price
    ok = (
        d1_pct is not None and d1_pct >= float(cfg["locked_d1_trend_pct_min"]) and
        h4_pct is not None and h4_pct >= float(cfg["locked_h4_trend_pct_min"]) and
        atr_pct is not None and atr_pct >= float(cfg["locked_atr_pct_price_min"])
    )
    return ok, {"d1_trend_pct": d1_pct, "h4_trend_pct": h4_pct, "atr_pct_price": atr_pct}


def blocked_entry_window(dt: datetime) -> bool:
    return (dt.weekday() == 6 and dt.hour in (22, 23)) or (dt.weekday() == 0 and dt.hour in (0, 1))


def large_gap(bars: List[Bar], start: int, end: int) -> bool:
    return any(bars[i].utc_time - bars[i - 1].utc_time > timedelta(hours=3) for i in range(start + 1, end + 1))


def simulate_exit(bars: List[Bar], entry_idx: int, entry: float, stop: float, target: float, holding_bars: int) -> Tuple[str, int, float]:
    end = entry_idx + holding_bars - 1
    if end >= len(bars):
        raise RuntimeError("not enough future bars")
    for j in range(entry_idx, end + 1):
        # Conservative same-bar sequencing: stop before target.
        if bars[j].low <= stop:
            return "SL", j, stop
        if bars[j].high >= target:
            return "TP", j, target
    return "TIME", end, bars[end].close


def generate_exact_lead_trades(bars: List[Bar], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    trades: List[Dict[str, Any]] = []
    skips: Dict[str, int] = defaultdict(int)
    for i, b in enumerate(bars):
        atr = b.atr_h1_14
        level = b.previous_day_high
        if atr is None or atr <= 0 or level is None:
            continue
        if b.high <= level or b.high - level < float(cfg["min_sweep_atr"]) * atr:
            continue
        signal_range = b.high - b.low
        if signal_range / atr > float(cfg["max_signal_range_atr"]):
            skips["large_signal"] += 1
            continue
        macro_ok, macro_bucket = macro_permitted(b)
        if not macro_ok:
            skips["macro"] += 1
            continue
        if not basic_structure_permitted(b):
            skips["basic_structure"] += 1
            continue
        rng = b.high - b.low
        if rng <= 0 or b.close <= level or (b.close - b.low) / rng < 0.50:
            skips["close_acceptance"] += 1
            continue
        entry_idx = i + 1
        if entry_idx >= len(bars):
            skips["no_entry_bar"] += 1
            continue
        entry_bar = bars[entry_idx]
        if blocked_entry_window(entry_bar.utc_time):
            skips["blocked_window"] += 1
            continue
        end_idx = entry_idx + int(cfg["time_stop_h1_bars"]) - 1
        if end_idx >= len(bars):
            skips["no_exit_bars"] += 1
            continue
        if large_gap(bars, entry_idx, end_idx):
            skips["large_gap"] += 1
            continue
        entry = entry_bar.open
        stop = b.low - float(cfg["stop_buffer_atr"]) * atr
        stop_dist = entry - stop
        stop_atr = stop_dist / atr
        if stop_dist <= 0 or stop_atr < float(cfg["min_stop_atr"]) or stop_atr > float(cfg["max_stop_atr"]):
            skips["invalid_stop"] += 1
            continue
        locked_ok, locked_values = locked_filter_permitted(b, entry, cfg)
        target = entry + float(cfg["target_r"]) * stop_dist
        try:
            reason, exit_idx, exit_price = simulate_exit(bars, entry_idx, entry, stop, target, int(cfg["time_stop_h1_bars"]))
        except RuntimeError:
            skips["no_exit_bars"] += 1
            continue
        gross_r = (exit_price - entry) / stop_dist
        cost_r = float(cfg["stress_spread_points"]) * float(cfg["point_size"]) / stop_dist
        net_r = gross_r - cost_r
        trades.append({
            "trade_id": f"T1_LOCKED__{b.utc_time.strftime('%Y%m%dT%H%M%SZ')}__{len(trades)+1:05d}",
            "signal_utc": b.utc_time.isoformat(),
            "entry_utc": entry_bar.utc_time.isoformat(),
            "exit_utc": bars[exit_idx].utc_time.isoformat(),
            "macro_regime": b.macro_regime or "",
            "macro_bucket": macro_bucket,
            "macro_score_long_gold": b.macro_score_long_gold,
            "d_real_yield_20d": b.d_real_yield_20d,
            "d_usd_20d_pct": b.d_usd_20d_pct,
            "d1_close": b.d1_close,
            "d1_ma50": b.d1_ma50,
            "h4_close": b.h4_close,
            "h4_ma50": b.h4_ma50,
            "atr_h1_14": atr,
            "previous_day_high": level,
            "sweep_distance": b.high - level,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "stop_distance": stop_dist,
            "stop_distance_atr": stop_atr,
            "d1_trend_pct": locked_values["d1_trend_pct"],
            "h4_trend_pct": locked_values["h4_trend_pct"],
            "atr_pct_price": locked_values["atr_pct_price"],
            "locked_filter_pass": bool(locked_ok),
            "exit_reason": reason,
            "exit_price": exit_price,
            "r_gross": gross_r,
            "r_stress_p90": net_r,
        })
    return trades, dict(skips)


def profit_factor(values: Sequence[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def max_drawdown(values: Sequence[float]) -> float:
    equity = peak = dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return dd


def metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    values = [float(r["r_stress_p90"]) for r in rows]
    wins = [v for v in values if v > 0]
    by_month: Dict[str, List[float]] = defaultdict(list)
    by_year: Dict[str, List[float]] = defaultdict(list)
    for r, v in zip(rows, values):
        ts = parse_dt(r["entry_utc"])
        by_month[ts.strftime("%Y-%m")].append(v)
        by_year[ts.strftime("%Y")].append(v)
    positive_month = {k: sum(vs) for k, vs in by_month.items() if sum(vs) > 0}
    positive_year = {k: sum(vs) for k, vs in by_year.items() if sum(vs) > 0}
    total_positive_month = sum(positive_month.values())
    total_positive_year = sum(positive_year.values())
    return {
        "trades": len(rows),
        "profit_factor": profit_factor(values),
        "avg_R": sum(values) / len(values) if values else None,
        "median_R": sorted(values)[len(values)//2] if values else None,
        "net_R": sum(values),
        "win_rate": len(wins) / len(values) if values else None,
        "max_drawdown_R": max_drawdown(values),
        "positive_month_count": len(positive_month),
        "max_month_positive_contribution_share": max(positive_month.values()) / total_positive_month if total_positive_month > 0 else None,
        "max_year_positive_contribution_share": max(positive_year.values()) / total_positive_year if total_positive_year > 0 else None,
        "monthly": {k: {"trades": len(by_month[k]), "net_R": sum(by_month[k]), "pf": profit_factor(by_month[k])} for k in sorted(by_month)},
        "yearly": {k: {"trades": len(by_year[k]), "net_R": sum(by_year[k]), "pf": profit_factor(by_year[k])} for k in sorted(by_year)},
    }


def compare_parity(actual: Dict[str, Any], parity_cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not parity_cfg.get("enabled", True):
        return {"enabled": False, "pass": True, "checks": {}}
    expected = parity_cfg["expected"]
    tolerances = parity_cfg["tolerances"]
    checks = {
        "trades": abs(int(actual["trades"]) - int(expected["trades"])) <= int(tolerances["trades_abs"]),
        "profit_factor": abs(float(actual["profit_factor"]) - float(expected["profit_factor"])) <= float(tolerances["profit_factor_abs"]),
        "avg_R": abs(float(actual["avg_R"]) - float(expected["avg_R"])) <= float(tolerances["avg_R_abs"]),
        "net_R": abs(float(actual["net_R"]) - float(expected["net_R"])) <= float(tolerances["net_R_abs"]),
        "max_drawdown_R": abs(float(actual["max_drawdown_R"]) - float(expected["max_drawdown_R"])) <= float(tolerances["max_drawdown_R_abs"]),
    }
    return {"enabled": True, "pass": all(checks.values()), "checks": checks, "actual": actual, "expected": expected, "tolerances": tolerances}


def evaluate_decision(parity: Dict[str, Any], holdout: Dict[str, Any], raw_holdout: Dict[str, Any], gates_cfg: Dict[str, Any]) -> Tuple[str, Dict[str, bool]]:
    if not parity["pass"]:
        return "INCONCLUSIVE_BLOCKED_ARCHIVED_ENGINE_PARITY_FAILED", {"parity": False}
    gates = {
        "min_holdout_trades": holdout["trades"] >= int(gates_cfg["min_holdout_trades"]),
        "holdout_pf": holdout["profit_factor"] is not None and holdout["profit_factor"] >= float(gates_cfg["min_holdout_profit_factor"]),
        "holdout_avg_R": holdout["avg_R"] is not None and holdout["avg_R"] > float(gates_cfg["min_holdout_avg_R"]),
        "holdout_max_dd": holdout["max_drawdown_R"] <= float(gates_cfg["max_holdout_drawdown_R"]),
        "month_concentration": holdout["max_month_positive_contribution_share"] is not None and holdout["max_month_positive_contribution_share"] <= float(gates_cfg["max_month_positive_share"]),
        "year_concentration": holdout["max_year_positive_contribution_share"] is not None and holdout["max_year_positive_contribution_share"] <= float(gates_cfg["max_year_positive_share"]),
        "positive_months": holdout["positive_month_count"] >= int(gates_cfg["min_positive_months"]),
        "filter_beats_raw_pf": holdout["profit_factor"] > raw_holdout["profit_factor"],
        "filter_beats_raw_avg_R": holdout["avg_R"] is not None and raw_holdout["avg_R"] is not None and holdout["avg_R"] > raw_holdout["avg_R"],
    }
    if not gates["min_holdout_trades"]:
        return "KILL_T1_COMMERCIAL_LOW_HOLDOUT_FREQUENCY_NO_WAIT", gates
    if all(gates.values()):
        return "SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER", gates
    return "KILL_T1_LOCKED_HOLDOUT_FAILURE_NO_ML", gates


def decision_markdown(summary: Dict[str, Any]) -> str:
    t1 = summary["t1_locked_refresh"]
    lines = [
        "# Stage175 Decision", "", f"Generated: {summary['generated_utc']}", "",
        "## Hard controls", "",
        "- Orders/demo/live/paper-order: forbidden.",
        "- ML: forbidden.",
        "- Broad scan and threshold reoptimization: forbidden.", "",
        "## H64L closeout", "",
        "**`KILL_COMMERCIAL_RESCUE_CLOSE_H64L_SIGNAL_PATH`**", "",
        "Generic macro/event data ingestion may remain available, but H64L must no longer open any promotion or execution gate.", "",
        "## Exact locked T1 refresh", "",
        f"**Decision: `{t1['decision']}`**", "",
        f"Parity: `{t1['parity']['pass']}`", "",
        f"Holdout cutoff: `{t1['holdout_cutoff_utc']}`", "",
        f"Locked holdout trades: `{t1['locked_holdout_metrics']['trades']}`", "",
        f"Locked holdout PF: `{clean(t1['locked_holdout_metrics']['profit_factor'])}`", "",
        f"Locked holdout avg R: `{clean(t1['locked_holdout_metrics']['avg_R'])}`", "",
        "## Program decision", "",
        f"**`{summary['program_decision']}`**", "",
        "No execution bridge is authorized by this stage.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--h1")
    parser.add_argument("--macro-db")
    parser.add_argument("--out")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out).expanduser().resolve() if args.out else root / cfg["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_utc_iso()

    outputs = {
        "summary_json": out_dir / "stage175_summary.json",
        "decision_md": out_dir / "stage175_decision.md",
        "h64l_closeout_json": out_dir / "stage175_h64l_closeout.json",
        "locked_trades_csv": out_dir / "stage175_t1_locked_trades.csv",
        "raw_trades_csv": out_dir / "stage175_t1_raw_comparator_trades.csv",
        "period_metrics_csv": out_dir / "stage175_t1_period_metrics.csv",
        "gate_checks_csv": out_dir / "stage175_t1_gate_checks.csv",
    }

    hard = {
        "orders_allowed": False, "demo_allowed": False, "live_allowed": False,
        "paper_order_allowed": False, "ml_allowed": False,
        "broad_scan_allowed": False, "threshold_reoptimization_allowed": False,
    }
    h64l_closeout = {
        "source_stage": "Stage174",
        "decision": "KILL_COMMERCIAL_RESCUE_CLOSE_H64L_SIGNAL_PATH",
        "reason": "Five total episodes, one negative holdout episode, approximately 1.1 episodes/year, and failure versus drift/simple trend.",
        "ops_policy": "PRESERVE_GENERIC_MACRO_EVENT_DATA_PIPELINE; H64L_SIGNAL_OUTPUT_IS_INERT_AND_MUST_NOT_OPEN_PROMOTION_OR_EXECUTION_GATES",
        "orders_allowed": False,
    }
    json_dump(outputs["h64l_closeout_json"], h64l_closeout)

    try:
        h1_path = resolve_existing(root, args.h1, cfg["h1_candidates"])
        db_path = resolve_existing(root, args.macro_db, cfg["macro_db_candidates"], cfg.get("macro_db_glob"))
        bars = load_h1_csv(h1_path)
        if len(bars) < int(cfg["minimum_h1_rows"]):
            raise ValueError(f"H1 rows {len(bars)} < minimum {cfg['minimum_h1_rows']}")
        macro = load_macro_db(db_path)
        compute_atr(bars, int(cfg["atr_period"]))
        context = attach_context(bars, macro, cfg)
        all_trades, skips = generate_exact_lead_trades(bars, cfg)
        raw_trades = all_trades
        locked_trades = [t for t in all_trades if t["locked_filter_pass"]]

        split_idx = max(1, min(len(bars)-1, int(math.floor(len(bars) * (1.0 - float(cfg["holdout_fraction"]))))))
        cutoff = bars[split_idx].utc_time
        raw_dev = [t for t in raw_trades if parse_dt(t["signal_utc"]) < cutoff]
        raw_hold = [t for t in raw_trades if parse_dt(t["signal_utc"]) >= cutoff]
        locked_dev = [t for t in locked_trades if parse_dt(t["signal_utc"]) < cutoff]
        locked_hold = [t for t in locked_trades if parse_dt(t["signal_utc"]) >= cutoff]

        reference_end = parse_dt(cfg["parity"]["reference_end_utc"])
        reference_locked = [t for t in locked_trades if parse_dt(t["signal_utc"]) <= reference_end]
        parity = compare_parity(metrics(reference_locked), cfg["parity"])

        m_raw_dev = metrics(raw_dev)
        m_raw_hold = metrics(raw_hold)
        m_locked_dev = metrics(locked_dev)
        m_locked_hold = metrics(locked_hold)
        decision, gates = evaluate_decision(parity, m_locked_hold, m_raw_hold, cfg["gates"])

        write_csv(outputs["locked_trades_csv"], locked_trades)
        write_csv(outputs["raw_trades_csv"], raw_trades)
        period_rows = [
            {"population": "RAW", "period": "DEVELOPMENT", **{k: v for k, v in m_raw_dev.items() if k not in ("monthly", "yearly")}},
            {"population": "RAW", "period": "HOLDOUT", **{k: v for k, v in m_raw_hold.items() if k not in ("monthly", "yearly")}},
            {"population": "LOCKED", "period": "DEVELOPMENT", **{k: v for k, v in m_locked_dev.items() if k not in ("monthly", "yearly")}},
            {"population": "LOCKED", "period": "HOLDOUT", **{k: v for k, v in m_locked_hold.items() if k not in ("monthly", "yearly")}},
        ]
        write_csv(outputs["period_metrics_csv"], period_rows)
        write_csv(outputs["gate_checks_csv"], [{"gate": k, "pass": v} for k, v in gates.items()])

        program = (
            "CLOSE_H64L_AND_PROMOTE_T1_TO_SHADOW_LOG_ONLY_NO_ORDER" if decision == "SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER"
            else "CLOSE_H64L_AND_KILL_LOCKED_T1_NO_ML_REQUIRE_NEW_CAUSAL_THESIS"
            if decision.startswith("KILL")
            else "CLOSE_H64L_BLOCK_T1_PENDING_ENGINE_PARITY_REPAIR_NO_NEW_SCAN"
        )
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "root": str(root),
            "hard_controls": hard,
            "inputs": {
                "h1": str(h1_path), "h1_sha256": sha256_file(h1_path), "h1_rows": len(bars),
                "h1_min_utc": bars[0].utc_time.isoformat(), "h1_max_utc": bars[-1].utc_time.isoformat(),
                "macro_db": str(db_path), "macro_db_sha256": sha256_file(db_path), "macro_rows": len(macro),
            },
            "h64l_closeout": h64l_closeout,
            "t1_locked_contract": {
                "entry": "V1_CLOSE_ACCEPTANCE",
                "level": "previous_day_high",
                "target_R": cfg["target_r"],
                "time_stop_h1_bars": cfg["time_stop_h1_bars"],
                "locked_d1_trend_pct_min": cfg["locked_d1_trend_pct_min"],
                "locked_h4_trend_pct_min": cfg["locked_h4_trend_pct_min"],
                "locked_atr_pct_price_min": cfg["locked_atr_pct_price_min"],
                "stress_spread_points": cfg["stress_spread_points"],
                "point_size": cfg["point_size"],
            },
            "t1_locked_refresh": {
                "status": "COMPLETE",
                "decision": decision,
                "holdout_fraction": cfg["holdout_fraction"],
                "holdout_cutoff_utc": cutoff.isoformat(),
                "context": context,
                "skip_counts": skips,
                "raw_development_metrics": m_raw_dev,
                "raw_holdout_metrics": m_raw_hold,
                "locked_development_metrics": m_locked_dev,
                "locked_holdout_metrics": m_locked_hold,
                "parity": parity,
                "gates": gates,
            },
            "outputs": {k: str(v) for k, v in outputs.items()},
            "program_decision": program,
        }
        json_dump(outputs["summary_json"], summary)
        outputs["decision_md"].write_text(decision_markdown(summary), encoding="utf-8")
        print(json.dumps({"stage": STAGE, "decision": decision, "program_decision": program, "out": str(out_dir)}, ensure_ascii=False))
        return 0 if decision != "INCONCLUSIVE_BLOCKED_ARCHIVED_ENGINE_PARITY_FAILED" else 2
    except Exception as exc:
        summary = {
            "stage": STAGE, "generated_utc": generated, "root": str(root),
            "hard_controls": hard, "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__, "error_message": str(exc),
            "program_decision": "CLOSE_H64L_BLOCK_T1_INPUT_OR_INTEGRATION_DEFECT_NO_NEW_SCAN",
            "outputs": {k: str(v) for k, v in outputs.items()},
        }
        json_dump(outputs["summary_json"], summary)
        outputs["decision_md"].write_text(
            "# Stage175 Decision\n\n"
            "**`INCONCLUSIVE_BLOCKED`**\n\n"
            f"Error: `{type(exc).__name__}: {exc}`\n\n"
            "H64L commercial rescue remains closed. No order/demo/live/ML/broad scan is authorized.\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
