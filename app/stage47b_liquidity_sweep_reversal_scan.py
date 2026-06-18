#!/usr/bin/env python3
"""
Stage47B Liquidity Sweep Reversal Scan
LoaderFix5: robust normalized CSV parser, exact timeframe source selection,
and numeric-only spread mapping.

This script is intentionally rule-based and research-only. It does not create
orders and does not promote candidates.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage47B_LIQUIDITY_SWEEP_REVERSAL_SCAN"
LOADERFIX = "LoaderFix5_NUMERIC_SPREAD_ONLY_NO_SPREAD_AVAILABLE_FLOAT_PARSE"

MIN_CANDLES = 200
DEFAULT_COST_BPS = 8.0

TIME_ALIASES = [
    "time_utc", "timestamp_utc", "utc_timestamp", "candle_timestamp_utc",
    "timestamp", "datetime", "date", "time", "ts", "open_time", "start_time"
]
OPEN_ALIASES = ["open", "o", "mid_o", "bid_open", "ask_open"]
HIGH_ALIASES = ["high", "h", "mid_h", "bid_high", "ask_high"]
LOW_ALIASES = ["low", "l", "mid_l", "bid_low", "ask_low"]
CLOSE_ALIASES = ["close", "c", "mid_c", "bid_close", "ask_close", "last"]
SYMBOL_ALIASES = ["symbol", "instrument", "pair", "ticker"]
TF_ALIASES = ["interval", "timeframe", "tf", "granularity"]
SESSION_ALIASES = ["session_utc", "session", "market_session"]
# Do NOT include spread_available here. It is a boolean metadata field, not a numeric cost.
NUMERIC_SPREAD_ALIASES = [
    "spread_close", "spread", "spread_points", "spread_pips", "spread_price",
    "bid_ask_spread", "ask_bid_spread", "spread_mid", "spread_bps"
]
BID_ALIASES = ["bid", "bid_close", "close_bid"]
ASK_ALIASES = ["ask", "ask_close", "close_ask"]
BOOLEAN_SPREAD_META = ["spread_available", "has_spread", "is_spread_available"]


def norm_name(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def norm_tf(value: Any) -> str:
    s = str(value or "").strip().lower().replace(" ", "")
    aliases = {
        "m1": "M1", "1m": "M1", "1min": "M1", "1minute": "M1",
        "m5": "M5", "5m": "M5", "5min": "M5", "5minute": "M5",
        "m15": "M15", "15m": "M15", "15min": "M15", "15minute": "M15",
        "h1": "H1", "1h": "H1", "60min": "H1", "1hour": "H1",
    }
    return aliases.get(s, s.upper())


def parse_ts(value: Any) -> dt.datetime:
    s = str(value or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    s = s.replace("Z", "+00:00")
    # Handle pandas-like timestamps with space before offset.
    try:
        x = dt.datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                x = dt.datetime.strptime(s, fmt)
                break
            except ValueError:
                x = None  # type: ignore
        if x is None:
            raise
    if x.tzinfo is None:
        x = x.replace(tzinfo=dt.timezone.utc)
    return x.astimezone(dt.timezone.utc)


def to_float(value: Any, field: str) -> float:
    if value is None:
        raise ValueError(f"missing {field}")
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        raise ValueError(f"missing {field}")
    # Explicitly reject boolean-like values in numeric fields.
    if s.lower() in {"true", "false", "yes", "no"}:
        raise ValueError(f"boolean string in numeric field {field}: {s}")
    x = float(s)
    if not math.isfinite(x):
        raise ValueError(f"non-finite {field}")
    return x


def safe_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "true", "false", "yes", "no"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if not math.isfinite(x) or x < 0:
        return None
    return x


def find_root() -> Path:
    p = Path.cwd().resolve()
    for cur in [p] + list(p.parents):
        if (cur / "app").exists() and (cur / "data").exists():
            return cur
        if (cur / ".git").exists():
            return cur
    return p


def choose_col(norm_to_original: Dict[str, str], aliases: List[str]) -> Optional[str]:
    for a in aliases:
        k = norm_name(a)
        if k in norm_to_original:
            return norm_to_original[k]
    return None


def choose_numeric_spread_col(norm_to_original: Dict[str, str], sample_rows: List[Dict[str, str]]) -> Optional[str]:
    # Prefer known numeric spread columns and explicitly skip boolean metadata.
    for alias in NUMERIC_SPREAD_ALIASES:
        k = norm_name(alias)
        if k not in norm_to_original:
            continue
        col = norm_to_original[k]
        usable = 0
        for row in sample_rows[:20]:
            if safe_optional_float(row.get(col)) is not None:
                usable += 1
        if usable > 0:
            return col
    return None


def choose_bid_ask(norm_to_original: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    return choose_col(norm_to_original, BID_ALIASES), choose_col(norm_to_original, ASK_ALIASES)


def timeframe_filename_score(path: Path, requested_tf: str) -> int:
    name = path.name.lower()
    tf = norm_tf(requested_tf)
    exact_tokens = {
        "M1": ["_1min_", "_m1_"],
        "M5": ["_5min_", "_m5_"],
        "M15": ["_15min_", "_m15_"],
        "H1": ["_1h_", "_h1_", "_60min_"],
    }.get(tf, [f"_{tf.lower()}_"])
    bad_tokens = {
        "M1": ["_5min_", "_15min_", "_1h_"],
        "M5": ["_1min_", "_15min_", "_1h_"],
        "M15": ["_1min_", "_5min_", "_1h_"],
        "H1": ["_1min_", "_5min_", "_15min_"],
    }.get(tf, [])
    score = 0
    if "xau" in name:
        score += 20
    if "normalized" in name:
        score += 10
    if any(tok in name for tok in exact_tokens):
        score += 100
    if any(tok in name for tok in bad_tokens):
        score -= 1000
    return score


def discover_csv(root: Path, timeframe: str) -> Tuple[Optional[Path], Dict[str, Any]]:
    norm_dir = root / "data" / "normalized"
    patterns = [
        norm_dir / f"normalized_*XAU*{timeframe.lower()}*.csv",
        norm_dir / "normalized_*XAU*5min*.csv" if norm_tf(timeframe) == "M5" else norm_dir / "__never__",
        norm_dir / "*.csv",
    ]
    candidates: List[Path] = []
    checked: List[str] = []
    for pat in patterns:
        checked.append(str(pat))
        candidates.extend(Path(x) for x in glob.glob(str(pat)))
    unique = sorted(set(candidates), key=lambda p: p.name)
    scored = []
    for p in unique:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0
        scored.append({"score": timeframe_filename_score(p, timeframe), "mtime": mtime, "path": str(p)})
    scored.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
    selected = Path(scored[0]["path"]) if scored and scored[0]["score"] > -900 else None
    return selected, {
        "checked_csv_patterns": checked,
        "csv_candidates": [str(p) for p in unique],
        "csv_candidate_scores": scored,
        "selected_csv": str(selected) if selected else None,
        "loaderfix": LOADERFIX,
    }


def discover_db(root: Path) -> Tuple[Optional[Path], Dict[str, Any]]:
    candidates = [
        root / "data" / "local" / "xauusd_local_store.sqlite",
        root / "data" / "store" / "xauusd.sqlite",
        root / "state" / "xauusd.db",
    ]
    existing = [p for p in candidates if p.exists()]
    return (existing[0] if existing else None), {"checked_db_paths": [str(p) for p in candidates], "selected_db": str(existing[0]) if existing else None}


def resolve_source(args: argparse.Namespace) -> Tuple[Optional[str], Optional[Path], Dict[str, Any]]:
    root = find_root()
    meta: Dict[str, Any] = {
        "source_type": "auto",
        "root": str(root),
        "prefer_source": args.prefer_source,
        "note": "LoaderFix5 uses bounded source discovery and numeric-only spread mapping.",
    }
    if args.csv:
        return "csv", Path(args.csv), {**meta, "source_type": "csv", "selected_by_arg": args.csv}
    if args.db:
        return "db", Path(args.db), {**meta, "source_type": "db", "selected_by_arg": args.db}
    csv_path, csv_meta = discover_csv(root, args.timeframe)
    db_path, db_meta = discover_db(root)
    meta["csv_discovery"] = csv_meta
    meta["db_discovery"] = db_meta
    if args.prefer_source == "db" and db_path:
        return "db", db_path, {**meta, "selected_by_autodiscovery": str(db_path)}
    if csv_path:
        return "csv", csv_path, {**meta, "selected_by_autodiscovery": str(csv_path)}
    if db_path:
        return "db", db_path, {**meta, "selected_by_autodiscovery": str(db_path)}
    return None, None, meta


@dataclass
class Candle:
    ts: dt.datetime
    open: float
    high: float
    low: float
    close: float
    spread: Optional[float]
    symbol: str = ""
    timeframe: str = ""
    session: str = ""


def infer_session(ts: dt.datetime) -> str:
    h = ts.hour
    if 0 <= h < 7:
        return "ASIA"
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 17:
        return "NY_OVERLAP"
    if 17 <= h < 22:
        return "NEW_YORK"
    return "ROLLOVER"


def load_csv(path: Path, requested_tf: str) -> Tuple[List[Candle], Dict[str, Any]]:
    meta: Dict[str, Any] = {"source_type": "csv", "source_path": str(path)}
    rows: List[Dict[str, str]] = []
    delimiter = ","
    dialect_detected = False
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
            dialect_detected = True
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    norm_to_original = {norm_name(c): c for c in (fieldnames or [])}
    sample_rows = rows[:20]
    mapping = {
        "ts": choose_col(norm_to_original, TIME_ALIASES),
        "open": choose_col(norm_to_original, OPEN_ALIASES),
        "high": choose_col(norm_to_original, HIGH_ALIASES),
        "low": choose_col(norm_to_original, LOW_ALIASES),
        "close": choose_col(norm_to_original, CLOSE_ALIASES),
        "spread": choose_numeric_spread_col(norm_to_original, sample_rows),
        "bid": None,
        "ask": None,
        "symbol": choose_col(norm_to_original, SYMBOL_ALIASES),
        "timeframe": choose_col(norm_to_original, TF_ALIASES),
        "session": choose_col(norm_to_original, SESSION_ALIASES),
    }
    bid_col, ask_col = choose_bid_ask(norm_to_original)
    mapping["bid"], mapping["ask"] = bid_col, ask_col

    candles: List[Candle] = []
    parse_fail_rows = 0
    symbol_filtered_rows = 0
    timeframe_filtered_rows = 0
    bad_ohlc_rows = 0
    first_parse_exception: Optional[str] = None
    first_bad_row: Optional[Dict[str, str]] = None

    required = ["ts", "open", "high", "low", "close"]
    if any(mapping.get(k) is None for k in required):
        meta.update({
            "mapping": mapping,
            "raw_rows": len(rows),
            "accepted_rows": 0,
            "loaderfix": LOADERFIX,
            "error": "MISSING_REQUIRED_CSV_COLUMNS",
            "fieldnames": fieldnames,
            "normalized_fieldnames": [norm_name(c) for c in fieldnames],
            "sample_rows_first_3_limited": rows[:3],
        })
        return [], meta

    requested_norm_tf = norm_tf(requested_tf)
    for row in rows:
        try:
            tf_val = row.get(mapping["timeframe"]) if mapping.get("timeframe") else ""
            if tf_val and norm_tf(tf_val) != requested_norm_tf:
                timeframe_filtered_rows += 1
                continue
            symbol_val = row.get(mapping["symbol"], "") if mapping.get("symbol") else ""
            if symbol_val and "XAU" not in symbol_val.upper():
                symbol_filtered_rows += 1
                continue
            ts = parse_ts(row.get(mapping["ts"]))  # type: ignore[arg-type]
            o = to_float(row.get(mapping["open"]), "open")  # type: ignore[arg-type]
            h = to_float(row.get(mapping["high"]), "high")  # type: ignore[arg-type]
            l = to_float(row.get(mapping["low"]), "low")  # type: ignore[arg-type]
            c = to_float(row.get(mapping["close"]), "close")  # type: ignore[arg-type]
            if h < max(o, c) or l > min(o, c) or h < l or o <= 0 or h <= 0 or l <= 0 or c <= 0:
                bad_ohlc_rows += 1
                continue
            spread = None
            if mapping.get("spread"):
                spread = safe_optional_float(row.get(mapping["spread"]))
            if spread is None and mapping.get("bid") and mapping.get("ask"):
                bid = safe_optional_float(row.get(mapping["bid"]))
                ask = safe_optional_float(row.get(mapping["ask"]))
                if bid is not None and ask is not None and ask >= bid:
                    spread = ask - bid
            session = row.get(mapping["session"], "") if mapping.get("session") else ""
            candles.append(Candle(ts=ts, open=o, high=h, low=l, close=c, spread=spread, symbol=symbol_val, timeframe=requested_norm_tf, session=session or infer_session(ts)))
        except Exception as e:
            parse_fail_rows += 1
            if first_parse_exception is None:
                first_parse_exception = repr(e)
                first_bad_row = dict(row)

    candles.sort(key=lambda x: x.ts)
    meta.update({
        "mapping": mapping,
        "raw_rows": len(rows),
        "accepted_rows": len(candles),
        "loaderfix": LOADERFIX,
        "parse_fail_rows": parse_fail_rows,
        "symbol_filtered_rows": symbol_filtered_rows,
        "timeframe_filtered_rows": timeframe_filtered_rows,
        "bad_ohlc_rows": bad_ohlc_rows,
        "delimiter": delimiter,
        "dialect_detected": dialect_detected,
        "fieldnames": fieldnames,
        "normalized_fieldnames": [norm_name(c) for c in fieldnames],
        "sample_rows_first_3_limited": rows[:3],
        "first_parse_exception": first_parse_exception,
        "first_bad_row_limited": first_bad_row,
        "spread_mapping_note": "spread_available is boolean metadata and is intentionally never mapped as numeric spread.",
        "numeric_spread_column_found": mapping.get("spread"),
        "spread_available_column_present": any(norm_name(c) in BOOLEAN_SPREAD_META for c in fieldnames),
    })
    if len(candles) == 0:
        meta["error"] = "CSV_ROWS_REJECTED_AFTER_PARSE_OR_FILTER"
    return candles, meta


def load_db(path: Path, requested_tf: str, table: Optional[str]) -> Tuple[List[Candle], Dict[str, Any]]:
    meta: Dict[str, Any] = {"source_type": "db", "source_path": str(path), "loaderfix": LOADERFIX}
    if not path.exists():
        meta["error"] = "DB_NOT_FOUND"
        return [], meta
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        preferred = [table] if table else ["normalized_candles", "candles", "xauusd_candles", "ohlcv"]
        selected_table = next((t for t in preferred if t and t in tables), None)
        if selected_table is None and tables:
            selected_table = tables[0]
        meta["tables"] = tables
        meta["selected_table"] = selected_table
        if selected_table is None:
            meta["error"] = "NO_TABLES"
            return [], meta
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({selected_table})").fetchall()]
        norm_to_original = {norm_name(c): c for c in cols}
        mapping = {
            "ts": choose_col(norm_to_original, TIME_ALIASES),
            "open": choose_col(norm_to_original, OPEN_ALIASES),
            "high": choose_col(norm_to_original, HIGH_ALIASES),
            "low": choose_col(norm_to_original, LOW_ALIASES),
            "close": choose_col(norm_to_original, CLOSE_ALIASES),
            "symbol": choose_col(norm_to_original, SYMBOL_ALIASES),
            "timeframe": choose_col(norm_to_original, TF_ALIASES),
        }
        meta["mapping"] = mapping
        if any(mapping.get(k) is None for k in ["ts", "open", "high", "low", "close"]):
            meta["error"] = "MISSING_REQUIRED_DB_COLUMNS"
            meta["columns"] = cols
            return [], meta
        rows = con.execute(f"SELECT * FROM {selected_table} LIMIT 200000").fetchall()
        candles: List[Candle] = []
        parse_fail_rows = 0
        timeframe_filtered_rows = 0
        requested_norm_tf = norm_tf(requested_tf)
        for r in rows:
            try:
                d = dict(r)
                tf_val = d.get(mapping["timeframe"]) if mapping.get("timeframe") else ""
                if tf_val and norm_tf(tf_val) != requested_norm_tf:
                    timeframe_filtered_rows += 1
                    continue
                ts = parse_ts(d.get(mapping["ts"]))
                o = to_float(d.get(mapping["open"]), "open")
                h = to_float(d.get(mapping["high"]), "high")
                l = to_float(d.get(mapping["low"]), "low")
                c = to_float(d.get(mapping["close"]), "close")
                if h < max(o, c) or l > min(o, c) or h < l:
                    continue
                candles.append(Candle(ts=ts, open=o, high=h, low=l, close=c, spread=None, symbol=str(d.get(mapping.get("symbol") or "", "")), timeframe=requested_norm_tf, session=infer_session(ts)))
            except Exception:
                parse_fail_rows += 1
        candles.sort(key=lambda x: x.ts)
        meta.update({"raw_rows": len(rows), "accepted_rows": len(candles), "parse_fail_rows": parse_fail_rows, "timeframe_filtered_rows": timeframe_filtered_rows})
        return candles, meta
    finally:
        con.close()


def bps_return(entry: float, exit_: float, direction: str) -> float:
    raw = (exit_ - entry) / entry * 10000.0
    return raw if direction == "long" else -raw


def run_scan(candles: List[Candle], cost_bps: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    # A compact predefined grid. No post-hoc filters are applied.
    grid = []
    for lookback in (24, 48, 72):
        for horizon in (12, 24, 48):
            for min_sweep_bps in (6.0, 10.0, 15.0):
                grid.append({"lookback": lookback, "horizon": horizon, "min_sweep_bps": min_sweep_bps})
    candidates: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    for gi, p in enumerate(grid, 1):
        this_returns: List[float] = []
        this_trades: List[Dict[str, Any]] = []
        lb = p["lookback"]
        horizon = p["horizon"]
        min_sweep_bps = p["min_sweep_bps"]
        for i in range(lb, len(candles) - horizon):
            prev = candles[i-lb:i]
            cur = candles[i]
            range_high = max(x.high for x in prev)
            range_low = min(x.low for x in prev)
            mid = (range_high + range_low) / 2.0
            # sweep high then close back inside -> short reversal
            if cur.high > range_high and cur.close < range_high:
                sweep_bps = (cur.high - range_high) / cur.close * 10000.0
                if sweep_bps >= min_sweep_bps:
                    entry = cur.close
                    exit_idx = min(i + horizon, len(candles)-1)
                    # Conservative target: midpoint if touched, else horizon close.
                    exit_price = candles[exit_idx].close
                    exit_reason = "horizon"
                    for j in range(i+1, exit_idx+1):
                        if candles[j].low <= mid:
                            exit_price = mid
                            exit_idx = j
                            exit_reason = "midpoint_touch"
                            break
                    net = bps_return(entry, exit_price, "short") - cost_bps
                    tr = {"candidate_id": f"ST47B_SHORT_LB{lb}_H{horizon}_SW{int(min_sweep_bps)}", "direction": "short", "entry_ts": cur.ts.isoformat(), "exit_ts": candles[exit_idx].ts.isoformat(), "entry": round(entry, 5), "exit": round(exit_price, 5), "net_bps": round(net, 4), "sweep_bps": round(sweep_bps, 4), "exit_reason": exit_reason, **p}
                    this_returns.append(net)
                    this_trades.append(tr)
            # sweep low then close back inside -> long reversal
            if cur.low < range_low and cur.close > range_low:
                sweep_bps = (range_low - cur.low) / cur.close * 10000.0
                if sweep_bps >= min_sweep_bps:
                    entry = cur.close
                    exit_idx = min(i + horizon, len(candles)-1)
                    exit_price = candles[exit_idx].close
                    exit_reason = "horizon"
                    for j in range(i+1, exit_idx+1):
                        if candles[j].high >= mid:
                            exit_price = mid
                            exit_idx = j
                            exit_reason = "midpoint_touch"
                            break
                    net = bps_return(entry, exit_price, "long") - cost_bps
                    tr = {"candidate_id": f"ST47B_LONG_LB{lb}_H{horizon}_SW{int(min_sweep_bps)}", "direction": "long", "entry_ts": cur.ts.isoformat(), "exit_ts": candles[exit_idx].ts.isoformat(), "entry": round(entry, 5), "exit": round(exit_price, 5), "net_bps": round(net, 4), "sweep_bps": round(sweep_bps, 4), "exit_reason": exit_reason, **p}
                    this_returns.append(net)
                    this_trades.append(tr)
        if this_returns:
            n = len(this_returns)
            mean_net = statistics.fmean(this_returns)
            median_net = statistics.median(this_returns)
            wr = sum(1 for x in this_returns if x > 0) / n
            # OOS proxy: last 30% chronological trades.
            sorted_tr = sorted(this_trades, key=lambda x: x["entry_ts"])
            split = max(1, int(len(sorted_tr) * 0.7))
            oos = [x["net_bps"] for x in sorted_tr[split:]] or []
            oos_mean = statistics.fmean(oos) if oos else None
            strict = bool(n >= 20 and mean_net > 0 and oos_mean is not None and oos_mean > 0 and wr >= 0.52)
            soft = bool(n >= 12 and mean_net > 0 and oos_mean is not None and oos_mean > -2.0 and wr >= 0.50)
        else:
            n = 0; mean_net = 0; median_net = 0; wr = 0; oos_mean = None; strict = False; soft = False
        cid_prefix = f"ST47B_GRID{gi:02d}_LB{lb}_H{horizon}_SW{int(min_sweep_bps)}"
        candidates.append({
            "candidate_id": cid_prefix,
            "lookback": lb,
            "horizon": horizon,
            "min_sweep_bps": min_sweep_bps,
            "trades": n,
            "mean_net_bps": round(mean_net, 4),
            "median_net_bps": round(median_net, 4) if n else 0,
            "win_rate": round(wr, 4) if n else 0,
            "oos_mean_net_bps": round(oos_mean, 4) if oos_mean is not None else "",
            "strict_survivor": strict,
            "soft_survivor": soft,
            "classification": "STRICT_SURVIVOR_AUDIT_REQUIRED" if strict else ("SOFT_SURVIVOR_AUDIT_REQUIRED" if soft else "FAIL_RESEARCH_ONLY_NO_PROMOTION"),
        })
        for tr in this_trades:
            tr["grid_candidate_id"] = cid_prefix
        trades.extend(this_trades)
    summary = {
        "candidate_count": len(candidates),
        "trade_count": len(trades),
        "strict_survivor_count": sum(1 for c in candidates if c["strict_survivor"]),
        "soft_survivor_count": sum(1 for c in candidates if c["soft_survivor"]),
        "cost_bps": cost_bps,
    }
    return candidates, trades, summary


def write_csv(path: Path, rows: List[Dict[str, Any]], fallback_fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fallback_fields)
    for row in rows:
        for k in row.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_outputs(out_dir: Path, status: str, load_meta: Dict[str, Any], candidates: List[Dict[str, Any]], trades: List[Dict[str, Any]], scan_summary: Dict[str, Any]) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "stage": STAGE,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "loaderfix": LOADERFIX,
        "rows_loaded": load_meta.get("accepted_rows", 0),
        "load_meta": load_meta,
        **scan_summary,
    }
    (out_dir / "stage47b_liquidity_sweep_reversal_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(out_dir / "stage47b_liquidity_sweep_reversal_candidates.csv", candidates, ["candidate_id", "classification"])
    write_csv(out_dir / "stage47b_liquidity_sweep_reversal_trades.csv", trades, ["candidate_id", "entry_ts", "exit_ts", "net_bps"])
    report = [
        "# Stage47B Liquidity Sweep Reversal Scan Report",
        "",
        f"status: `{status}`",
        f"loaderfix: `{LOADERFIX}`",
        f"rows_loaded: `{summary.get('rows_loaded')}`",
        f"candidate_count: `{summary.get('candidate_count', 0)}`",
        f"trade_count: `{summary.get('trade_count', 0)}`",
        f"strict_survivor_count: `{summary.get('strict_survivor_count', 0)}`",
        f"soft_survivor_count: `{summary.get('soft_survivor_count', 0)}`",
        "",
        "Research-only output. No EA, paper-live, or live promotion is allowed from this stage.",
    ]
    (out_dir / "stage47b_liquidity_sweep_reversal_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


def make_smoke_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    rows = []
    price = 2300.0
    for i in range(500):
        ts = start + dt.timedelta(minutes=5*i)
        drift = math.sin(i/14.0) * 1.2
        o = price
        c = price + drift
        h = max(o, c) + 2.0
        l = min(o, c) - 2.0
        if i % 73 == 0 and i > 80:
            l -= 8.0
            c = price + 1.0
        if i % 91 == 0 and i > 80:
            h += 8.0
            c = price - 1.0
        rows.append({"time_utc": ts.isoformat(), "open": f"{o:.5f}", "high": f"{h:.5f}", "low": f"{l:.5f}", "close": f"{c:.5f}", "volume": "0.0", "symbol": "XAU/USD", "interval": "5min", "spread_available": "False", "spread_close": ""})
        price = c
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--db", default="")
    ap.add_argument("--table", default="")
    ap.add_argument("--timeframe", default="M5")
    ap.add_argument("--prefer-source", choices=["csv", "db"], default="csv")
    ap.add_argument("--out", default="reports/stage47b")
    ap.add_argument("--debug-source", action="store_true")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    args = ap.parse_args()

    if args.smoke_test:
        smoke_path = Path(args.out) / "_smoke_stage47b_m5.csv"
        make_smoke_csv(smoke_path)
        args.csv = str(smoke_path)

    kind, source, auto_meta = resolve_source(args)
    if args.debug_source:
        print(json.dumps({
            "stage": STAGE,
            "debug_source": True,
            "source_kind": kind,
            "source_path": str(source) if source else None,
            "auto_meta": auto_meta,
            "cwd": str(Path.cwd()),
        }, indent=2, ensure_ascii=False))
        return 0

    out_dir = Path(args.out)
    if not kind or not source:
        load_meta = {**auto_meta, "error": "NO_SOURCE_FOUND", "accepted_rows": 0}
        summary = write_outputs(out_dir, "NO_DATA_STOP_NO_PROMOTION", load_meta, [], [], {"candidate_count": 0, "trade_count": 0, "strict_survivor_count": 0, "soft_survivor_count": 0})
        print(json.dumps({"stage": STAGE, "status": summary["status"], "rows_loaded": 0, "out": str(out_dir)}, ensure_ascii=False))
        return 0

    if kind == "csv":
        candles, load_meta = load_csv(source, args.timeframe)
        load_meta["auto_meta"] = auto_meta
    else:
        candles, load_meta = load_db(source, args.timeframe, args.table or None)
        load_meta["auto_meta"] = auto_meta

    if len(candles) < MIN_CANDLES:
        load_meta["stop_reason"] = f"INSUFFICIENT_CANDLES_MIN_{MIN_CANDLES}"
        summary = write_outputs(out_dir, "NO_DATA_STOP_NO_PROMOTION", load_meta, [], [], {"candidate_count": 0, "trade_count": 0, "strict_survivor_count": 0, "soft_survivor_count": 0})
        print(json.dumps({"stage": STAGE, "status": summary["status"], "rows_loaded": len(candles), "out": str(out_dir)}, ensure_ascii=False))
        return 0

    candidates, trades, scan_summary = run_scan(candles, args.cost_bps)
    status = "SCAN_COMPLETE_NO_PROMOTION"
    if scan_summary["strict_survivor_count"] or scan_summary["soft_survivor_count"]:
        status = "SCAN_COMPLETE_AUDIT_REQUIRED_NO_PROMOTION"
    summary = write_outputs(out_dir, status, load_meta, candidates, trades, scan_summary)
    print(json.dumps({"stage": STAGE, "status": summary["status"], "rows_loaded": len(candles), "candidate_count": scan_summary["candidate_count"], "trade_count": scan_summary["trade_count"], "strict_survivor_count": scan_summary["strict_survivor_count"], "soft_survivor_count": scan_summary["soft_survivor_count"], "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
