#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage150B_FAST_CURRENT_ACTIVE_MTF_DISCOVERY"
STATUS = "STAGE150B_COMPLETE_FAST_CURRENT_ACTIVE_MTF_DISCOVERY_READY"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

BASE_FEATURE_HOURS = [1, 3, 6, 12, 24, 48]
SMA_HOURS = [8, 20, 50, 100]
FEATURES = [
    "ret_1h_bps", "ret_3h_bps", "ret_6h_bps", "ret_12h_bps", "ret_24h_bps", "ret_48h_bps",
    "trend_8_20_bps", "trend_20_50_bps", "trend_50_100_bps",
    "dist_high_24_bps", "dist_low_24_bps", "range_pos_24", "break_high_24", "break_low_24",
    "range_pos_48", "break_high_48", "break_low_48",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    s = s.replace(",", "")
    try:
        x = float(s)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    if not s:
        return None
    for fmt in (
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def clean_col(c: str) -> str:
    return str(c).strip().strip("\ufeff").strip("<>").strip().lower()


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="replace")[:4096]
    first = sample.splitlines()[0] if sample.splitlines() else ""
    if "\t" in first and first.count("\t") >= first.count(","):
        return "\t"
    if ";" in first and first.count(";") > first.count(","):
        return ";"
    return ","


def read_table(path: Path) -> List[Dict[str, str]]:
    delim = detect_delimiter(path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)
        return [{clean_col(k): ("" if v is None else str(v).strip()) for k, v in r.items() if k is not None} for r in reader]


def find_col(cols: Iterable[str], aliases: List[str]) -> Optional[str]:
    lower = {clean_col(c): c for c in cols}
    for a in aliases:
        ca = clean_col(a)
        if ca in lower:
            return lower[ca]
    for c in cols:
        lc = clean_col(c)
        for a in aliases:
            if clean_col(a) in lc:
                return c
    return None


def normalize_bars(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    cols = list(rows[0].keys())
    date_col = find_col(cols, ["date"])
    separate_time_col = find_col(cols, ["time"])
    datetime_col = find_col(cols, ["utc_time", "time_utc", "timestamp", "datetime", "date_time", "time"])

    open_col = find_col(cols, ["open"])
    high_col = find_col(cols, ["high"])
    low_col = find_col(cols, ["low"])
    close_col = find_col(cols, ["close"])
    volume_col = find_col(cols, ["volume", "tickvol", "tick_volume"])

    if not all([open_col, high_col, low_col, close_col]):
        raise ValueError(f"could not bind OHLC columns. cols={cols[:30]}")

    out: List[Dict[str, Any]] = []
    for r in rows:
        if date_col and separate_time_col and date_col != separate_time_col:
            dt = parse_dt(f"{r.get(date_col, '')} {r.get(separate_time_col, '')}")
        else:
            dt = parse_dt(r.get(datetime_col)) if datetime_col else None

        o = parse_float(r.get(open_col))
        h = parse_float(r.get(high_col))
        l = parse_float(r.get(low_col))
        c = parse_float(r.get(close_col))
        v = parse_float(r.get(volume_col)) if volume_col else None

        if dt is None or o is None or h is None or l is None or c is None or c <= 0:
            continue
        out.append({"utc_time": dt, "open": o, "high": h, "low": l, "close": c, "volume": v})
    out.sort(key=lambda r: r["utc_time"])
    return out


def mean(vals: List[float]) -> Optional[float]:
    vals = [v for v in vals if v is not None and not math.isnan(v)]
    if not vals:
        return None
    return statistics.fmean(vals)


def quantile(vals: List[float], q: float) -> Optional[float]:
    xs = sorted(v for v in vals if v is not None and not math.isnan(v))
    if not xs:
        return None
    idx = (len(xs) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return xs[int(idx)]
    return xs[lo] * (hi - idx) + xs[hi] * (idx - lo)


def bars_per_hour(timeframe_minutes: int) -> int:
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be positive")
    return max(1, int(round(60 / timeframe_minutes)))


def hours_to_bars(hours: int, timeframe_minutes: int) -> int:
    return max(1, int(round((hours * 60) / timeframe_minutes)))


def add_features(bars: List[Dict[str, Any]], horizon_hours: int, timeframe_minutes: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    horizon_bars = hours_to_bars(horizon_hours, timeframe_minutes)

    for i, b in enumerate(bars):
        r = dict(b)
        c = b["close"]

        for h in BASE_FEATURE_HOURS:
            n = hours_to_bars(h, timeframe_minutes)
            r[f"ret_{h}h_bps"] = (c / closes[i-n] - 1.0) * 10000.0 if i >= n and closes[i-n] > 0 else None

        sma_vals: Dict[int, Optional[float]] = {}
        for h in SMA_HOURS:
            n = hours_to_bars(h, timeframe_minutes)
            sma_vals[h] = mean(closes[i-n+1:i+1]) if i + 1 >= n else None
            r[f"sma_{h}h"] = sma_vals[h]

        r["trend_8_20_bps"] = (sma_vals[8] / sma_vals[20] - 1.0) * 10000.0 if sma_vals[8] and sma_vals[20] else None
        r["trend_20_50_bps"] = (sma_vals[20] / sma_vals[50] - 1.0) * 10000.0 if sma_vals[20] and sma_vals[50] else None
        r["trend_50_100_bps"] = (sma_vals[50] / sma_vals[100] - 1.0) * 10000.0 if sma_vals[50] and sma_vals[100] else None

        n24 = hours_to_bars(24, timeframe_minutes)
        if i >= n24:
            prev_hi24 = max(highs[i-n24:i])
            prev_lo24 = min(lows[i-n24:i])
            rng = prev_hi24 - prev_lo24
            r["dist_high_24_bps"] = (c / prev_hi24 - 1.0) * 10000.0 if prev_hi24 > 0 else None
            r["dist_low_24_bps"] = (c / prev_lo24 - 1.0) * 10000.0 if prev_lo24 > 0 else None
            r["range_pos_24"] = (c - prev_lo24) / rng if rng > 0 else None
            r["break_high_24"] = 1.0 if c > prev_hi24 else 0.0
            r["break_low_24"] = 1.0 if c < prev_lo24 else 0.0
        else:
            r["dist_high_24_bps"] = r["dist_low_24_bps"] = r["range_pos_24"] = None
            r["break_high_24"] = r["break_low_24"] = None

        n48 = hours_to_bars(48, timeframe_minutes)
        if i >= n48:
            prev_hi48 = max(highs[i-n48:i])
            prev_lo48 = min(lows[i-n48:i])
            rng48 = prev_hi48 - prev_lo48
            r["range_pos_48"] = (c - prev_lo48) / rng48 if rng48 > 0 else None
            r["break_high_48"] = 1.0 if c > prev_hi48 else 0.0
            r["break_low_48"] = 1.0 if c < prev_lo48 else 0.0
        else:
            r["range_pos_48"] = r["break_high_48"] = r["break_low_48"] = None

        if i + horizon_bars < len(bars):
            r[f"fwd_ret_{horizon_hours}h_bps"] = (closes[i+horizon_bars] / c - 1.0) * 10000.0
        else:
            r[f"fwd_ret_{horizon_hours}h_bps"] = None

        out.append(r)
    return out


def split_rows_with_recent_embargo(rows: List[Dict[str, Any]], recent_embargo_hours: int) -> Dict[str, Any]:
    valid = [r for r in rows if parse_float(r.get("target")) is not None]
    if not valid:
        return {"selection": [], "validation": [], "tail": [], "embargoed_recent": [], "scoring": []}
    latest = valid[-1]["utc_time"]
    cutoff = latest - timedelta(hours=max(0, recent_embargo_hours))
    scoring = [r for r in valid if r["utc_time"] < cutoff]
    embargoed = [r for r in valid if r["utc_time"] >= cutoff]
    if len(scoring) < 300:
        scoring = valid
        embargoed = []
    n = len(scoring)
    return {
        "selection": scoring[:int(n * 0.60)],
        "validation": scoring[int(n * 0.60):int(n * 0.80)],
        "tail": scoring[int(n * 0.80):],
        "embargoed_recent": embargoed,
        "scoring": scoring,
    }


def iso_or_empty(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return ""
    dt = row.get("utc_time")
    if isinstance(dt, datetime):
        return dt.isoformat().replace("+00:00", "Z")
    return str(dt or "")


def condition_active(row: Dict[str, Any], conds: List[Tuple[str, str, float]]) -> bool:
    for c, op, th in conds:
        x = parse_float(row.get(c))
        if x is None:
            return False
        if op == ">=" and x < th:
            return False
        if op == "<=" and x > th:
            return False
    return True


def metric(rows: List[Dict[str, Any]], conds: List[Tuple[str, str, float]]) -> Dict[str, Any]:
    vals = []
    for r in rows:
        if condition_active(r, conds):
            y = parse_float(r.get("target"))
            if y is not None:
                vals.append(y)
    if not vals:
        return {"events": 0, "mean_bps": 0.0, "hit_rate": 0.0, "median_bps": 0.0}
    return {
        "events": len(vals),
        "mean_bps": round(statistics.fmean(vals), 4),
        "hit_rate": round(sum(1 for x in vals if x > 0) / len(vals), 4),
        "median_bps": round(statistics.median(vals), 4),
    }


def gate(m: Dict[str, Any], min_events: int, min_mean: float, min_hit: float) -> bool:
    return int(m["events"]) >= min_events and float(m["mean_bps"]) >= min_mean and float(m["hit_rate"]) >= min_hit


def rule_is_excluded(rule_id: str, exclude_rule_ids: List[str], exclude_rule_substrings: List[str]) -> Tuple[bool, str]:
    rid = str(rule_id or "")
    exact = {str(x).strip() for x in exclude_rule_ids if str(x).strip()}
    if rid in exact:
        return True, f"exact:{rid}"
    for token in exclude_rule_substrings:
        t = str(token or "").strip()
        if t and t in rid:
            return True, f"substring:{t}"
    return False, ""


def make_rule_id(prefix: str, tf: str, conds: List[Tuple[str, str, float]], tags: List[str]) -> str:
    parts = []
    for (c, op, _), tag in zip(conds, tags):
        safe = "".join(ch if ch.isalnum() else "_" for ch in c)[:18]
        parts.append(f"{safe}_{'GE' if op == '>=' else 'LE'}Q{tag}")
    return (prefix + "_" + tf.upper() + "_" + "__".join(parts))[:95]


def generate_candidates(selection: List[Dict[str, Any]], max_pair_features: int, tf: str) -> List[Tuple[str, str, List[Tuple[str, str, float]]]]:
    qspec = [(0.15, "15"), (0.25, "25"), (0.35, "35"), (0.50, "50"), (0.65, "65"), (0.75, "75"), (0.85, "85")]
    pair_qspec = [(0.35, "35"), (0.50, "50"), (0.65, "65")]
    values: Dict[str, List[float]] = {}
    out: List[Tuple[str, str, List[Tuple[str, str, float]]]] = []
    for f in FEATURES:
        vals = [parse_float(r.get(f)) for r in selection]
        vals = [v for v in vals if v is not None]
        if len(vals) < 100:
            continue
        values[f] = vals
        for q, tag in qspec:
            th = quantile(vals, q)
            if th is None:
                continue
            for op in [">=", "<="]:
                conds = [(f, op, th)]
                out.append((make_rule_id("D150", tf, conds, [tag]), f"{tf}: {f} {op} q{tag}", conds))

    pair_features = [f for f in FEATURES if f in values][:max_pair_features]
    for f1, f2 in itertools.combinations(pair_features, 2):
        for q1, t1 in pair_qspec:
            th1 = quantile(values[f1], q1)
            if th1 is None:
                continue
            for q2, t2 in pair_qspec:
                th2 = quantile(values[f2], q2)
                if th2 is None:
                    continue
                for op1 in [">=", "<="]:
                    for op2 in [">=", "<="]:
                        conds = [(f1, op1, th1), (f2, op2, th2)]
                        out.append((make_rule_id("D150C", tf, conds, [t1, t2]), f"{tf}: {f1} {op1} q{t1} AND {f2} {op2} q{t2}", conds))
    return out


def market_logic_statement(rule_id: str, label: str) -> str:
    rid = str(rule_id or "")
    if "range_pos" in rid and "ret_" in rid:
        return "MTF range/momentum thesis: price location in the recent range is combined with recent return pressure. This is allowed only for demo-probe until separated validation and closed demo outcomes agree."
    if "trend" in rid:
        return "MTF trend thesis: intraday moving-average structure is used as directional drift proxy. This remains demo-only and must be monitored per family."
    if "break" in rid:
        return "MTF breakout thesis: recent range break is used as continuation proxy. This is session- and volatility-sensitive."
    return "MTF technical thesis: broker-bar technical pattern. Demo-only unless separated validation and live-demo outcomes agree."


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def append_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def locate_bars(explicit: str) -> Path:
    p = Path(explicit).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"bars file not found: {p}")
    return p


def run(
    root: Path,
    bars_path: Path,
    tf: str,
    timeframe_minutes: int,
    horizon_hours: int,
    min_events: int,
    min_selection_mean_bps: float,
    min_selection_hit: float,
    min_mean_bps: float,
    min_hit: float,
    min_tail_mean_bps: float,
    min_tail_hit: float,
    recent_embargo_hours: int,
    max_pair_features: int,
    exclude_rule_ids: Optional[List[str]],
    exclude_rule_substrings: Optional[List[str]],
    mt5_files: Path,
    write_mt5: bool,
    score_inactive: bool = False,
) -> Dict[str, Any]:
    root = root.expanduser()
    bars_path = locate_bars(str(bars_path))
    mt5_files = mt5_files.expanduser()
    exclude_rule_ids = exclude_rule_ids or []
    exclude_rule_substrings = exclude_rule_substrings or []

    tf_safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in tf).strip("_") or f"m{timeframe_minutes}"
    out = ensure_dir(root / "reports/stage150_mtf_separated_validation_discovery" / tf_safe)
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    raw_rows = read_table(bars_path)
    bars = normalize_bars(raw_rows)
    min_bars = max(500, hours_to_bars(150, timeframe_minutes))
    if len(bars) < min_bars:
        raise ValueError(f"not enough bars for Stage150 {tf}: {len(bars)} < {min_bars}; file={bars_path}")

    rows = add_features(bars, horizon_hours=horizon_hours, timeframe_minutes=timeframe_minutes)
    target_col = f"fwd_ret_{horizon_hours}h_bps"
    for r in rows:
        r["target"] = r.get(target_col)

    split = split_rows_with_recent_embargo(rows, recent_embargo_hours=recent_embargo_hours)
    selection, validation, tail = split["selection"], split["validation"], split["tail"]
    embargoed_recent, scoring = split["embargoed_recent"], split["scoring"]
    specs = generate_candidates(selection, max_pair_features=max_pair_features, tf=tf_safe)
    latest = rows[-1]

    # Stage150B speed fix:
    # Only current-active candidates can be selected for Stage134 execution.
    # On M5, scoring inactive candidates is the main runtime cost and does not
    # affect selected_rule_id. Use --score-inactive for full offline diagnostics.
    prefiltered_specs = []
    inactive_candidate_count = 0
    excluded_current_active_count = 0
    for rid, label, conds in specs:
        active = condition_active(latest, conds)
        excluded, exclude_reason = rule_is_excluded(rid, exclude_rule_ids, exclude_rule_substrings)
        if not active and not score_inactive:
            inactive_candidate_count += 1
            continue
        if active and excluded:
            excluded_current_active_count += 1
        prefiltered_specs.append((rid, label, conds, active, excluded, exclude_reason))

    score_rows: List[Dict[str, Any]] = []
    for rid, label, conds, active, excluded, exclude_reason in prefiltered_specs:
        sm = metric(selection, conds)
        vm = metric(validation, conds)
        tm = metric(tail, conds)
        g = "PASS" if (
            gate(sm, min_events, min_selection_mean_bps, min_selection_hit)
            and gate(vm, min_events, min_mean_bps, min_hit)
            and gate(tm, max(10, min_events // 3), min_tail_mean_bps, min_tail_hit)
        ) else "WATCH_OR_REJECT"
        if excluded and g == "PASS":
            g = "EXCLUDED_FROZEN_FAMILY"
        score_rows.append({
            "rule_id": rid,
            "label": label,
            "gate": g,
            "current_active": active,
            "excluded": excluded,
            "exclude_reason": exclude_reason,
            "conditions_json": json.dumps([{"feature": c, "op": op, "threshold": th, "current": latest.get(c)} for c, op, th in conds], sort_keys=True),
            "selection_events": sm["events"],
            "selection_mean_bps": sm["mean_bps"],
            "selection_hit_rate": sm["hit_rate"],
            "validation_events": vm["events"],
            "validation_mean_bps": vm["mean_bps"],
            "validation_hit_rate": vm["hit_rate"],
            "tail_events": tm["events"],
            "tail_mean_bps": tm["mean_bps"],
            "tail_hit_rate": tm["hit_rate"],
        })

    active_pass = [r for r in score_rows if r["gate"] == "PASS" and r["current_active"] is True and not r.get("excluded")]
    active_pass.sort(key=lambda r: (float(r["validation_mean_bps"]), float(r["tail_mean_bps"]), float(r["selection_mean_bps"]), float(r["validation_hit_rate"]), int(r["validation_events"])), reverse=True)
    selected = active_pass[0] if active_pass else None

    if selected:
        decision = "STAGE150B_FAST_MTF_RULE_READY_POINT_STAGE134_TO_STAGE150_FILE"
        selected_rule_id = selected["rule_id"]
        selected_label = selected["label"]
        any_signal_active = "true"
        active_count = "1"
        reason = "selected current-active non-excluded MTF candidate passing selection, separated validation, tail, and recent-time embargo gates"
    else:
        decision = "STAGE150B_NO_CURRENT_ACTIVE_MTF_CANDIDATE"
        selected_rule_id = ""
        selected_label = ""
        any_signal_active = "false"
        active_count = "0"
        reason = "no current-active non-excluded MTF candidate passed selection, validation, tail, and recent-time embargo gates"

    kv_file = f"xauusd_stage150_{tf_safe}_rule_state_kv.csv"
    latest_file = f"xauusd_stage150_{tf_safe}_rule_state_latest.csv"
    history_file = f"xauusd_stage150_{tf_safe}_rule_state_history.csv"
    feature_date = latest["utc_time"].isoformat().replace("+00:00", "Z")

    kv = {
        "stage": STAGE,
        "status": "MTF_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE150B",
        "decision": decision,
        "reason": reason,
        "mode": "MTF_BROKER_TECHNICAL_DISCOVERY_TO_STAGE134_WITH_RECENT_TIME_EMBARGO",
        "tf": tf_safe,
        "timeframe_minutes": timeframe_minutes,
        "horizon_hours": horizon_hours,
        "feature_date": feature_date,
        "any_signal_active": any_signal_active,
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "execution_allowed": "false",
        "order_authorized": "false",
        "rule_count": len(score_rows),
        "active_rule_count": active_count,
        "allow_trading": "false",
        "order_send": "false",
        "note": "Stage150 writes MTF rule-state only; Stage134 demo executor must be manually pointed to this file if selected.",
        "stage134_required_InpRuleStateKvFile": kv_file,
        "stage134_required_InpAllowedRules": selected_rule_id,
        "market_logic_statement": market_logic_statement(selected_rule_id, selected_label) if selected_rule_id else "",
    }

    latest_row = {
        "time_utc": generated,
        "tf": tf_safe,
        "rule_id": selected_rule_id,
        "rule_active": any_signal_active,
        "feature_date": feature_date,
        "selected_label": selected_label,
        "decision": decision,
        "reason": reason,
        "allow_trading": "false",
        "order_send": "false",
    }

    fields = ["rule_id","label","gate","current_active","excluded","exclude_reason","conditions_json","selection_events","selection_mean_bps","selection_hit_rate","validation_events","validation_mean_bps","validation_hit_rate","tail_events","tail_mean_bps","tail_hit_rate"]
    score_path = out / "stage150_candidate_scores.csv"
    write_csv(score_path, score_rows, fields)

    repo_kv = data / kv_file
    repo_latest = data / latest_file
    repo_history = data / history_file
    write_kv(repo_kv, kv)
    write_csv(repo_latest, [latest_row], list(latest_row.keys()))
    append_csv(repo_history, [latest_row], list(latest_row.keys()))

    mt5_kv = ""
    mt5_latest = ""
    if write_mt5:
        mt5_kv = str(mt5_files / kv_file)
        mt5_latest = str(mt5_files / latest_file)
        write_kv(Path(mt5_kv), kv)
        write_csv(Path(mt5_latest), [latest_row], list(latest_row.keys()))
        append_csv(mt5_files / history_file, [latest_row], list(latest_row.keys()))

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "tf": tf_safe,
        "timeframe_minutes": timeframe_minutes,
        "bars_per_hour": bars_per_hour(timeframe_minutes),
        "horizon_hours": horizon_hours,
        "contamination_guard_active": True,
        "recent_embargo_hours": recent_embargo_hours,
        "recent_embargo_row_count": len(embargoed_recent),
        "scoring_row_count": len(scoring),
        "selection_row_count": len(selection),
        "validation_row_count": len(validation),
        "tail_row_count": len(tail),
        "selection_start_utc": iso_or_empty(selection[0] if selection else None),
        "selection_end_utc": iso_or_empty(selection[-1] if selection else None),
        "validation_start_utc": iso_or_empty(validation[0] if validation else None),
        "validation_end_utc": iso_or_empty(validation[-1] if validation else None),
        "tail_start_utc": iso_or_empty(tail[0] if tail else None),
        "tail_end_utc": iso_or_empty(tail[-1] if tail else None),
        "embargo_start_utc": iso_or_empty(embargoed_recent[0] if embargoed_recent else None),
        "embargo_end_utc": iso_or_empty(embargoed_recent[-1] if embargoed_recent else None),
        "min_selection_mean_bps": min_selection_mean_bps,
        "min_selection_hit": min_selection_hit,
        "min_validation_mean_bps": min_mean_bps,
        "min_validation_hit": min_hit,
        "min_tail_mean_bps": min_tail_mean_bps,
        "min_tail_hit": min_tail_hit,
        "excluded_rule_ids": exclude_rule_ids,
        "excluded_rule_substrings": exclude_rule_substrings,
        "excluded_pass_count": len([r for r in score_rows if r.get("excluded") and str(r.get("gate")).startswith("EXCLUDED")]),
        "root": str(root),
        "bars_path": str(bars_path),
        "raw_row_count": len(raw_rows),
        "bar_count": len(bars),
        "bar_min_utc": bars[0]["utc_time"].isoformat(),
        "bar_max_utc": bars[-1]["utc_time"].isoformat(),
        "generated_candidate_spec_count": len(specs),
        "candidate_rows": len(score_rows),
        "score_inactive": score_inactive,
        "inactive_candidate_skipped_count": inactive_candidate_count,
        "excluded_current_active_count": excluded_current_active_count,
        "pass_count": len([r for r in score_rows if r["gate"] == "PASS"]),
        "current_active_pass_count": len(active_pass),
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "selected_score": selected or {},
        "selected_market_logic_statement": market_logic_statement(selected_rule_id, selected_label) if selected_rule_id else "",
        "score_csv": str(score_path),
        "repo_kv": str(repo_kv),
        "repo_latest": str(repo_latest),
        "mt5_kv_written": bool(write_mt5),
        "mt5_kv": mt5_kv,
        "mt5_latest": mt5_latest,
        "stage134_instruction": {
            "InpRuleStateKvFile": kv_file,
            "InpAllowedRules": selected_rule_id,
            "keep_InpEnableDemoOrders": "true only on demo account",
        },
        "summary_json": str(out / "stage150_mtf_separated_validation_discovery_summary.json"),
        "next": [
            "If selected_rule_id is non-empty and metrics beat the H1 Stage148 candidate, point Stage134 to this Stage150 KV for demo-probe.",
            "If no MTF candidate passes, keep H1 Stage148 as the only limited demo-probe or pivot to D1/macro discovery.",
        ],
    }
    write_json(out / "stage150_mtf_separated_validation_discovery_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--bars", required=True)
    ap.add_argument("--tf", required=True, help="Label such as m15 or m5")
    ap.add_argument("--timeframe-minutes", type=int, required=True)
    ap.add_argument("--horizon-hours", type=int, default=4)
    ap.add_argument("--min-events", type=int, default=80)
    ap.add_argument("--min-selection-mean-bps", type=float, default=0.0)
    ap.add_argument("--min-selection-hit", type=float, default=0.50)
    ap.add_argument("--min-mean-bps", type=float, default=2.0)
    ap.add_argument("--min-hit", type=float, default=0.53)
    ap.add_argument("--min-tail-mean-bps", type=float, default=1.0)
    ap.add_argument("--min-tail-hit", type=float, default=0.50)
    ap.add_argument("--recent-embargo-hours", type=int, default=720)
    ap.add_argument("--max-pair-features", type=int, default=10)
    ap.add_argument("--exclude-rule-id", action="append", default=[])
    ap.add_argument("--exclude-rule-substring", action="append", default=[])
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--write-mt5", action="store_true")
    ap.add_argument("--score-inactive", action="store_true", help="Full diagnostic scan: score inactive candidates too. Slower on M5.")
    args = ap.parse_args()
    run(
        root=Path(args.root),
        bars_path=Path(args.bars),
        tf=args.tf,
        timeframe_minutes=args.timeframe_minutes,
        horizon_hours=args.horizon_hours,
        min_events=args.min_events,
        min_selection_mean_bps=args.min_selection_mean_bps,
        min_selection_hit=args.min_selection_hit,
        min_mean_bps=args.min_mean_bps,
        min_hit=args.min_hit,
        min_tail_mean_bps=args.min_tail_mean_bps,
        min_tail_hit=args.min_tail_hit,
        recent_embargo_hours=args.recent_embargo_hours,
        max_pair_features=args.max_pair_features,
        exclude_rule_ids=args.exclude_rule_id,
        exclude_rule_substrings=args.exclude_rule_substring,
        mt5_files=Path(args.mt5_files),
        write_mt5=args.write_mt5,
        score_inactive=args.score_inactive,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
