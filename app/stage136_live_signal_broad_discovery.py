#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage136_LIVE_SIGNAL_BROAD_DISCOVERY"
STATUS = "STAGE136_COMPLETE_LIVE_SIGNAL_BROAD_DISCOVERY_READY"

DEFAULT_DATASET = "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_LIVE_SIGNAL_FILE = "unified_observer_signal.csv"

KV_FILE = "xauusd_stage136_broad_discovery_rule_state_kv.csv"
LATEST_FILE = "xauusd_stage136_broad_discovery_rule_state_latest.csv"
HISTORY_FILE = "xauusd_stage136_broad_discovery_rule_state_history.csv"

RISK_BLOCKS = [
    "DEMO_ONLY_RULE_STATE_OUTPUT",
    "NO_ORDER_SEND_IN_STAGE136",
    "NO_TRADE_CLASS_IN_STAGE136",
    "STAGE134_EXECUTES_ONLY_AFTER_MANUAL_INPUT_SWITCH",
    "LIVE_SIGNAL_FILE_REQUIRED",
    "HISTORICAL_VALIDATION_AND_TAIL_GATE_REQUIRED",
    "RESTORE_STAGE134_TO_STAGE133_AFTER_PROBE",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "true", "false"}:
        return None
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
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def read_live_signal(path: Path) -> Dict[str, str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}
    # Unified observer signal is header,row CSV. Some fallback KV files are key|value.
    if len(lines) >= 2 and ("," in lines[0]):
        header = next(csv.reader([lines[0]]))
        row = next(csv.reader([lines[1]]))
        return {h.strip(): (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
    kv: Dict[str, str] = {}
    for line in lines:
        if "|" in line:
            k, v = line.split("|", 1)
        elif "," in line:
            k, v = line.split(",", 1)
        else:
            continue
        kv[k.strip()] = v.strip()
    return kv


def find_col(cols: Iterable[str], aliases: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for a in aliases:
        if a.lower() in lower:
            return lower[a.lower()]
    for c in cols:
        lc = c.lower()
        for a in aliases:
            if a.lower() in lc:
                return c
    return None


def find_ret_col(cols: Iterable[str]) -> Optional[str]:
    return find_col(cols, ["fwd_ret_bps_h120", "forward_ret_bps_h120", "ret_bps_h120", "return_bps_h120", "fwd_ret_bps"])


def find_date_col(cols: Iterable[str]) -> Optional[str]:
    return find_col(cols, ["utc_time", "feature_date", "date", "timestamp", "time"])


def quantile(values: List[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals:
        return None
    idx = (len(vals) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return vals[int(idx)]
    return vals[lo] * (hi - idx) + vals[hi] * (idx - lo)


def split_rows(rows: List[Dict[str, str]], date_col: Optional[str]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    if date_col:
        rows = sorted(rows, key=lambda r: parse_dt(r.get(date_col)) or datetime.min.replace(tzinfo=timezone.utc))
    n = len(rows)
    a = int(n * 0.60)
    b = int(n * 0.80)
    return rows[:a], rows[a:b], rows[b:]


def numeric_feature_cols(rows: List[Dict[str, str]], live: Dict[str, str], ret_col: str, date_col: Optional[str], min_nonnull: int) -> List[str]:
    skip_terms = ["open", "high", "low", "close", "volume", "spread", "ret_bps_h120", "fwd_ret", "future", "forward", "target"]
    cols = list(rows[0].keys())
    out = []
    for c in cols:
        lc = c.lower()
        if c == ret_col or c == date_col:
            continue
        if any(t in lc for t in skip_terms):
            continue
        if c not in live or parse_float(live.get(c)) is None:
            continue
        count = 0
        for r in rows:
            if parse_float(r.get(c)) is not None:
                count += 1
        if count >= min_nonnull:
            out.append(c)
    return out


def metric_for_condition(rows: List[Dict[str, str]], ret_col: str, conds: List[Tuple[str, str, float]]) -> Dict[str, Any]:
    vals = []
    events = 0
    for r in rows:
        ok = True
        for col, op, th in conds:
            x = parse_float(r.get(col))
            if x is None:
                ok = False
                break
            if op == ">=":
                ok = ok and x >= th
            else:
                ok = ok and x <= th
            if not ok:
                break
        if ok:
            ret = parse_float(r.get(ret_col))
            if ret is not None:
                events += 1
                vals.append(ret)
    if not vals:
        return {"events": 0, "mean_bps": 0.0, "hit_rate": 0.0, "median_bps": 0.0}
    return {
        "events": events,
        "mean_bps": round(statistics.fmean(vals), 4),
        "hit_rate": round(sum(1 for x in vals if x > 0) / len(vals), 4),
        "median_bps": round(statistics.median(vals), 4),
    }


def active_now(live: Dict[str, str], conds: List[Tuple[str, str, float]]) -> bool:
    for col, op, th in conds:
        x = parse_float(live.get(col))
        if x is None:
            return False
        if op == ">=" and not x >= th:
            return False
        if op == "<=" and not x <= th:
            return False
    return True


def pass_gate(m: Dict[str, Any], min_events: int, min_mean_bps: float, min_hit: float) -> bool:
    return int(m["events"]) >= min_events and float(m["mean_bps"]) >= min_mean_bps and float(m["hit_rate"]) >= min_hit


def make_rule_id(prefix: str, conds: List[Tuple[str, str, float]], qtags: List[str]) -> str:
    parts = []
    for (col, op, _), qtag in zip(conds, qtags):
        safe = "".join(ch if ch.isalnum() else "_" for ch in col)[:22]
        parts.append(f"{safe}_{'GE' if op == '>=' else 'LE'}{qtag}")
    rid = prefix + "_" + "__".join(parts)
    return rid[:80]


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


def generate_candidates(selection: List[Dict[str, str]], features: List[str], max_pair_features: int) -> List[Tuple[str, List[Tuple[str, str, float]], str]]:
    quants = [(0.15, "15"), (0.25, "25"), (0.35, "35"), (0.50, "50"), (0.65, "65"), (0.75, "75"), (0.85, "85")]
    singles: List[Tuple[str, List[Tuple[str, str, float]], str]] = []
    values_by_col: Dict[str, List[float]] = {}
    for col in features:
        vals = [parse_float(r.get(col)) for r in selection]
        vals = [v for v in vals if v is not None]
        if len(vals) < 100:
            continue
        values_by_col[col] = vals
        for q, tag in quants:
            th = quantile(vals, q)
            if th is None:
                continue
            for op in (">=", "<="):
                conds = [(col, op, th)]
                rid = make_rule_id("D136", conds, [tag])
                label = f"{col} {op} q{q:.2f}"
                singles.append((rid, conds, label))

    # Pair candidates from a limited, diverse feature set to keep runtime fast.
    pair_features = features[:max_pair_features]
    pairs: List[Tuple[str, List[Tuple[str, str, float]], str]] = []
    pair_quants = [(0.35, "35"), (0.50, "50"), (0.65, "65")]
    for c1, c2 in itertools.combinations(pair_features, 2):
        if c1 not in values_by_col or c2 not in values_by_col:
            continue
        for q1, t1 in pair_quants:
            th1 = quantile(values_by_col[c1], q1)
            if th1 is None:
                continue
            for q2, t2 in pair_quants:
                th2 = quantile(values_by_col[c2], q2)
                if th2 is None:
                    continue
                for op1 in (">=", "<="):
                    for op2 in (">=", "<="):
                        conds = [(c1, op1, th1), (c2, op2, th2)]
                        rid = make_rule_id("D136C", conds, [t1, t2])
                        label = f"{c1} {op1} q{q1:.2f} AND {c2} {op2} q{q2:.2f}"
                        pairs.append((rid, conds, label))
    return singles + pairs


def run(root: Path, dataset: Path, mt5_files: Path, live_signal_file: str, max_rows: int, min_events: int, min_mean_bps: float, min_hit: float, max_pair_features: int, write_mt5: bool) -> Dict[str, Any]:
    root = root.expanduser()
    dataset = dataset.expanduser()
    if not dataset.is_absolute():
        dataset = root / dataset
    mt5_files = mt5_files.expanduser()
    live_path = Path(live_signal_file).expanduser()
    if not live_path.is_absolute():
        live_path = mt5_files / live_signal_file

    out = ensure_dir(root / "reports/stage136_live_signal_broad_discovery")
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    if not dataset.exists():
        summary = {"stage": STAGE, "generated_utc": generated, "status": STATUS, "decision": "STAGE136_DATASET_MISSING", "dataset": str(dataset)}
        write_json(out / "stage136_live_signal_broad_discovery_summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary

    live = read_live_signal(live_path)
    if not live:
        summary = {"stage": STAGE, "generated_utc": generated, "status": STATUS, "decision": "STAGE136_LIVE_SIGNAL_FILE_MISSING_OR_EMPTY", "live_signal_file": str(live_path)}
        write_json(out / "stage136_live_signal_broad_discovery_summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary

    rows = read_rows(dataset)
    if max_rows and len(rows) > max_rows:
        rows = rows[-max_rows:]
    if not rows:
        raise ValueError("dataset has no rows")
    cols = list(rows[0].keys())
    ret_col = find_ret_col(cols)
    date_col = find_date_col(cols)
    if not ret_col:
        raise ValueError("could not detect forward return column")

    selection, validation, tail = split_rows(rows, date_col)
    min_nonnull = max(20, min(500, int(len(rows) * 0.20)))
    features = numeric_feature_cols(rows, live, ret_col, date_col, min_nonnull=min_nonnull)

    cand_specs = generate_candidates(selection, features, max_pair_features=max_pair_features)

    score_rows: List[Dict[str, Any]] = []
    for rid, conds, label in cand_specs:
        sm = metric_for_condition(selection, ret_col, conds)
        vm = metric_for_condition(validation, ret_col, conds)
        tm = metric_for_condition(tail, ret_col, conds)
        gate = "PASS" if (
            pass_gate(vm, min_events, min_mean_bps, min_hit)
            and pass_gate(tm, max(5, min_events // 3), min_mean_bps * 0.25, min_hit * 0.90)
        ) else "WATCH_OR_REJECT"
        is_active = active_now(live, conds)
        score_rows.append({
            "rule_id": rid,
            "label": label,
            "gate": gate,
            "current_active": is_active,
            "conditions_json": json.dumps([{"col": c, "op": op, "threshold": th} for c, op, th in conds], sort_keys=True),
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

    active_pass = [r for r in score_rows if r["gate"] == "PASS" and r["current_active"] is True]
    active_pass.sort(key=lambda r: (
        float(r["validation_mean_bps"]),
        float(r["tail_mean_bps"]),
        float(r["validation_hit_rate"]),
        int(r["validation_events"]),
    ), reverse=True)

    selected = active_pass[0] if active_pass else None
    feature_date = live.get("feature_date") or live.get("utc_time") or live.get("date") or ""

    if selected:
        decision = "STAGE136_DEMO_RULE_READY_POINT_STAGE134_TO_STAGE136_FILE"
        selected_rule_id = selected["rule_id"]
        selected_label = selected["label"]
        any_active = "true"
        active_count = "1"
        reason = "selected current-active PASS candidate from live signal broad discovery"
    else:
        decision = "STAGE136_NO_CURRENT_ACTIVE_PASS_CANDIDATE_EXPAND_DISCOVERY_OR_WAIT"
        selected_rule_id = ""
        selected_label = ""
        any_active = "false"
        active_count = "0"
        reason = "no current-active candidate passed validation/tail gate"

    kv = {
        "stage": "Stage136_LIVE_SIGNAL_BROAD_DISCOVERY",
        "status": "BROAD_DISCOVERY_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE136",
        "decision": decision,
        "reason": reason,
        "mode": "DEMO_DISCOVERY_TO_STAGE134",
        "feature_date": feature_date,
        "any_signal_active": any_active,
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "execution_allowed": "false",
        "order_authorized": "false",
        "rule_count": len(score_rows),
        "active_rule_count": active_count,
        "allow_trading": "false",
        "order_send": "false",
        "note": "Stage136 writes rule-state only; Stage134 demo executor must be manually pointed to this file",
        "stage134_required_InpRuleStateKvFile": KV_FILE,
        "stage134_required_InpAllowedRules": selected_rule_id,
    }

    latest_row = {
        "time_utc": generated,
        "rule_id": selected_rule_id,
        "rule_active": any_active,
        "feature_date": feature_date,
        "selected_label": selected_label,
        "decision": decision,
        "reason": reason,
        "allow_trading": "false",
        "order_send": "false",
    }

    score_fields = ["rule_id", "label", "gate", "current_active", "conditions_json", "selection_events", "selection_mean_bps", "selection_hit_rate", "validation_events", "validation_mean_bps", "validation_hit_rate", "tail_events", "tail_mean_bps", "tail_hit_rate"]
    score_path = out / "stage136_candidate_scores.csv"
    write_csv(score_path, score_rows, score_fields)

    latest_path = data / LATEST_FILE
    hist_path = data / HISTORY_FILE
    kv_path = data / KV_FILE
    write_csv(latest_path, [latest_row], list(latest_row.keys()))
    append_csv(hist_path, [latest_row], list(latest_row.keys()))
    write_kv(kv_path, kv)
    write_csv(out / "stage136_risk_manifest.csv", [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    mt5_kv = ""
    mt5_latest = ""
    if write_mt5:
        mt5_kv = str(mt5_files / KV_FILE)
        mt5_latest = str(mt5_files / LATEST_FILE)
        write_kv(Path(mt5_kv), kv)
        write_csv(Path(mt5_latest), [latest_row], list(latest_row.keys()))
        append_csv(mt5_files / HISTORY_FILE, [latest_row], list(latest_row.keys()))

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "dataset": str(dataset),
        "dataset_rows": len(rows),
        "live_signal_file": str(live_path),
        "live_signal_keys": len(live),
        "ret_col": ret_col,
        "date_col": date_col,
        "feature_date": feature_date,
        "numeric_features_common_with_live": len(features),
        "features_scanned": features,
        "candidate_rows": len(score_rows),
        "pass_count": len([r for r in score_rows if r["gate"] == "PASS"]),
        "current_active_pass_count": len(active_pass),
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "selected_score": selected or {},
        "stage134_instruction": {
            "InpRuleStateKvFile": KV_FILE,
            "InpAllowedRules": selected_rule_id,
            "keep_InpEnableDemoOrders": "true only on demo account",
            "restore_after_probe": "xauusd_stage133_unified_observer_rule_state_kv.csv",
        },
        "score_csv": str(score_path),
        "repo_kv": str(kv_path),
        "repo_latest": str(latest_path),
        "repo_history": str(hist_path),
        "mt5_kv_written": bool(write_mt5),
        "mt5_kv": mt5_kv,
        "mt5_latest": mt5_latest,
        "summary_json": str(out / "stage136_live_signal_broad_discovery_summary.json"),
        "next": [
            "If selected_rule_id is non-empty, set Stage134 InpRuleStateKvFile to xauusd_stage136_broad_discovery_rule_state_kv.csv and InpAllowedRules to selected_rule_id.",
            "If selected_rule_id is empty, expand discovery beyond common live features or wait only while Stage134 remains armed.",
            "After any demo attempt, evaluate retcode/fill/PnL and return to discovery if negative.",
        ],
    }
    write_json(out / "stage136_live_signal_broad_discovery_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--live-signal-file", default=DEFAULT_LIVE_SIGNAL_FILE)
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--min-events", type=int, default=20)
    ap.add_argument("--min-mean-bps", type=float, default=5.0)
    ap.add_argument("--min-hit", type=float, default=0.52)
    ap.add_argument("--max-pair-features", type=int, default=8)
    ap.add_argument("--write-mt5", action="store_true")
    args = ap.parse_args()
    run(
        root=Path(args.root),
        dataset=Path(args.dataset),
        mt5_files=Path(args.mt5_files),
        live_signal_file=args.live_signal_file,
        max_rows=args.max_rows,
        min_events=args.min_events,
        min_mean_bps=args.min_mean_bps,
        min_hit=args.min_hit,
        max_pair_features=args.max_pair_features,
        write_mt5=args.write_mt5,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
