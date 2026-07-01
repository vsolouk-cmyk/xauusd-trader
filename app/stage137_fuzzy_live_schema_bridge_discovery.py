#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage137_FUZZY_LIVE_SCHEMA_BRIDGE_DISCOVERY"
STATUS = "STAGE137_COMPLETE_FUZZY_LIVE_SCHEMA_BRIDGE_DISCOVERY_READY"

DEFAULT_DATASET = "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_LIVE_SIGNAL_FILE = "unified_observer_signal.csv"

KV_FILE = "xauusd_stage137_fuzzy_bridge_rule_state_kv.csv"
LATEST_FILE = "xauusd_stage137_fuzzy_bridge_rule_state_latest.csv"
HISTORY_FILE = "xauusd_stage137_fuzzy_bridge_rule_state_history.csv"

RISK_BLOCKS = [
    "DEMO_ONLY_RULE_STATE_OUTPUT",
    "NO_ORDER_SEND_IN_STAGE137",
    "NO_TRADE_CLASS_IN_STAGE137",
    "STAGE134_EXECUTES_ONLY_AFTER_MANUAL_INPUT_SWITCH",
    "FUZZY_SCHEMA_MAPPING_AUDITED",
    "HISTORICAL_VALIDATION_AND_TAIL_GATE_REQUIRED",
    "RESTORE_STAGE134_TO_STAGE133_AFTER_PROBE",
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
    if s == "" or s.lower() in {"nan", "none", "null", "true", "false", "na", "n/a"}:
        return None
    s = s.replace("%", "")
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
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                pass
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
    if len(lines) >= 2 and "," in lines[0]:
        try:
            header = next(csv.reader([lines[0]]))
            row = next(csv.reader([lines[1]]))
            return {h.strip(): (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
        except Exception:
            pass
    kv: Dict[str, str] = {}
    for line in lines:
        if "|" in line:
            k, v = line.split("|", 1)
        elif "," in line:
            k, v = line.split(",", 1)
        elif "\t" in line:
            k, v = line.split("\t", 1)
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


def norm_name(s: str) -> str:
    s = s.lower()
    replacements = {
        "realyield": "real_yield",
        "real yield": "real_yield",
        "dollar_index": "dxy",
        "dollar": "dxy",
        "gold": "xau",
        "xauusd": "xau",
        "gld": "spdr",
        "sma": "sma",
        "change": "chg",
        "delta": "chg",
        "return": "ret",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def tokens(s: str) -> set:
    n = norm_name(s)
    toks = set(t for t in n.split("_") if t and t not in {"value", "current", "latest", "feature", "validated", "raw", "norm"})
    return toks


def similarity(a: str, b: str) -> float:
    na, nb = norm_name(a), norm_name(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.82
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    j = len(ta & tb) / len(ta | tb)
    # Boost for critical market tokens.
    boosts = ["dxy", "yield", "vix", "cot", "spdr", "xau", "sma", "ret", "chg", "20d", "120d"]
    common_boost = sum(1 for x in boosts if x in ta and x in tb) * 0.04
    return min(0.95, j + common_boost)


def numeric_cols(rows: List[Dict[str, str]], ret_col: str, date_col: Optional[str], min_nonnull: int) -> List[str]:
    skip = ["open", "high", "low", "close", "volume", "spread", "future", "forward", "target", "ret_bps_h120", "fwd_ret"]
    cols = list(rows[0].keys())
    out = []
    for c in cols:
        lc = c.lower()
        if c == ret_col or c == date_col or any(x in lc for x in skip):
            continue
        n = 0
        for r in rows:
            if parse_float(r.get(c)) is not None:
                n += 1
        if n >= min_nonnull:
            out.append(c)
    return out


def live_numeric_keys(live: Dict[str, str]) -> List[str]:
    bad_fragments = ["active", "allowed", "authorized", "count", "period", "login", "magic", "order", "trade", "bars"]
    out = []
    for k, v in live.items():
        if any(x in k.lower() for x in bad_fragments):
            continue
        if parse_float(v) is not None:
            out.append(k)
    return out


def build_fuzzy_mapping(hist_cols: List[str], live: Dict[str, str], min_similarity: float) -> List[Dict[str, Any]]:
    live_keys = live_numeric_keys(live)
    rows = []
    for hc in hist_cols:
        best_key = ""
        best_score = 0.0
        for lk in live_keys:
            sc = similarity(hc, lk)
            if sc > best_score:
                best_key = lk
                best_score = sc
        if best_key and best_score >= min_similarity:
            rows.append({
                "hist_col": hc,
                "live_key": best_key,
                "similarity": round(best_score, 4),
                "live_value": live.get(best_key, ""),
                "hist_norm": norm_name(hc),
                "live_norm": norm_name(best_key),
            })
    rows.sort(key=lambda r: r["similarity"], reverse=True)
    # Keep one live key mapped to strongest historical feature to avoid duplicates.
    seen_live = set()
    dedup = []
    for r in rows:
        if r["live_key"] in seen_live:
            continue
        seen_live.add(r["live_key"])
        dedup.append(r)
    return dedup


def quantile(values: List[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals:
        return None
    idx = (len(vals) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return vals[int(idx)]
    return vals[lo] * (hi - idx) + vals[hi] * (idx - lo)


def split_rows(rows: List[Dict[str, str]], date_col: Optional[str]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    if date_col:
        rows = sorted(rows, key=lambda r: parse_dt(r.get(date_col)) or datetime.min.replace(tzinfo=timezone.utc))
    n = len(rows)
    return rows[:int(n*0.60)], rows[int(n*0.60):int(n*0.80)], rows[int(n*0.80):]


def metric(rows: List[Dict[str, str]], ret_col: str, conds: List[Tuple[str, str, float]]) -> Dict[str, Any]:
    vals = []
    for r in rows:
        ok = True
        for c, op, th in conds:
            x = parse_float(r.get(c))
            if x is None:
                ok = False
                break
            if op == ">=" and x < th:
                ok = False
                break
            if op == "<=" and x > th:
                ok = False
                break
        if ok:
            ret = parse_float(r.get(ret_col))
            if ret is not None:
                vals.append(ret)
    if not vals:
        return {"events": 0, "mean_bps": 0.0, "hit_rate": 0.0, "median_bps": 0.0}
    return {
        "events": len(vals),
        "mean_bps": round(statistics.fmean(vals), 4),
        "hit_rate": round(sum(1 for x in vals if x > 0) / len(vals), 4),
        "median_bps": round(statistics.median(vals), 4),
    }


def current_active(conds: List[Tuple[str, str, float]], mapping: Dict[str, Dict[str, Any]]) -> bool:
    for c, op, th in conds:
        live_val = parse_float(mapping[c]["live_value"])
        if live_val is None:
            return False
        if op == ">=" and live_val < th:
            return False
        if op == "<=" and live_val > th:
            return False
    return True


def gate(m: Dict[str, Any], min_events: int, min_mean: float, min_hit: float) -> bool:
    return int(m["events"]) >= min_events and float(m["mean_bps"]) >= min_mean and float(m["hit_rate"]) >= min_hit


def make_rule_id(prefix: str, conds: List[Tuple[str, str, float]], qtags: List[str]) -> str:
    parts = []
    for (c, op, _), qt in zip(conds, qtags):
        safe = re.sub(r"[^A-Za-z0-9]+", "_", c)[:18]
        parts.append(f"{safe}_{'GE' if op == '>=' else 'LE'}Q{qt}")
    return (prefix + "_" + "__".join(parts))[:80]


def candidates(selection: List[Dict[str, str]], mapped_cols: List[str], max_pair_features: int) -> List[Tuple[str, str, List[Tuple[str, str, float]]]]:
    qspec_single = [(0.15, "15"), (0.25, "25"), (0.35, "35"), (0.50, "50"), (0.65, "65"), (0.75, "75"), (0.85, "85")]
    qspec_pair = [(0.35, "35"), (0.50, "50"), (0.65, "65")]
    values: Dict[str, List[float]] = {}
    out: List[Tuple[str, str, List[Tuple[str, str, float]]]] = []
    for c in mapped_cols:
        vals = [parse_float(r.get(c)) for r in selection]
        vals = [v for v in vals if v is not None]
        if len(vals) < 50:
            continue
        values[c] = vals
        for q, tag in qspec_single:
            th = quantile(vals, q)
            if th is None:
                continue
            for op in [">=", "<="]:
                conds = [(c, op, th)]
                out.append((make_rule_id("D137", conds, [tag]), f"{c} {op} q{tag}", conds))
    pair_cols = [c for c in mapped_cols if c in values][:max_pair_features]
    for c1, c2 in itertools.combinations(pair_cols, 2):
        for q1, t1 in qspec_pair:
            th1 = quantile(values[c1], q1)
            if th1 is None:
                continue
            for q2, t2 in qspec_pair:
                th2 = quantile(values[c2], q2)
                if th2 is None:
                    continue
                for op1 in [">=", "<="]:
                    for op2 in [">=", "<="]:
                        conds = [(c1, op1, th1), (c2, op2, th2)]
                        out.append((make_rule_id("D137C", conds, [t1, t2]), f"{c1} {op1} q{t1} AND {c2} {op2} q{t2}", conds))
    return out


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


def run(root: Path, dataset: Path, mt5_files: Path, live_signal_file: str, max_rows: int, min_events: int, min_mean_bps: float, min_hit: float, min_similarity: float, max_pair_features: int, write_mt5: bool) -> Dict[str, Any]:
    root = root.expanduser()
    dataset = dataset.expanduser()
    if not dataset.is_absolute():
        dataset = root / dataset
    mt5_files = mt5_files.expanduser()
    live_path = Path(live_signal_file).expanduser()
    if not live_path.is_absolute():
        live_path = mt5_files / live_signal_file

    out = ensure_dir(root / "reports/stage137_fuzzy_live_schema_bridge_discovery")
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    if not dataset.exists():
        summary = {"stage": STAGE, "generated_utc": generated, "status": STATUS, "decision": "STAGE137_DATASET_MISSING", "dataset": str(dataset)}
        write_json(out / "stage137_fuzzy_live_schema_bridge_discovery_summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary
    live = read_live_signal(live_path)
    if not live:
        summary = {"stage": STAGE, "generated_utc": generated, "status": STATUS, "decision": "STAGE137_LIVE_SIGNAL_FILE_MISSING_OR_EMPTY", "live_signal_file": str(live_path)}
        write_json(out / "stage137_fuzzy_live_schema_bridge_discovery_summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary

    rows = read_rows(dataset)
    if max_rows and len(rows) > max_rows:
        rows = rows[-max_rows:]
    cols = list(rows[0].keys())
    ret_col = find_ret_col(cols)
    date_col = find_date_col(cols)
    if not ret_col:
        raise ValueError("could not detect forward return column")

    min_nonnull = max(20, min(500, int(len(rows) * 0.20)))
    hist_features = numeric_cols(rows, ret_col, date_col, min_nonnull=min_nonnull)
    mapping_rows = build_fuzzy_mapping(hist_features, live, min_similarity=min_similarity)
    mapping_by_hist = {r["hist_col"]: r for r in mapping_rows}
    mapped_cols = list(mapping_by_hist.keys())

    selection, validation, tail = split_rows(rows, date_col)
    specs = candidates(selection, mapped_cols, max_pair_features=max_pair_features)

    score_rows: List[Dict[str, Any]] = []
    for rid, label, conds in specs:
        sm = metric(selection, ret_col, conds)
        vm = metric(validation, ret_col, conds)
        tm = metric(tail, ret_col, conds)
        g = "PASS" if gate(vm, min_events, min_mean_bps, min_hit) and gate(tm, max(5, min_events//3), min_mean_bps * 0.25, min_hit * 0.90) else "WATCH_OR_REJECT"
        active = current_active(conds, mapping_by_hist)
        score_rows.append({
            "rule_id": rid,
            "label": label,
            "gate": g,
            "current_active": active,
            "conditions_json": json.dumps([{"col": c, "op": op, "threshold": th, "live_key": mapping_by_hist[c]["live_key"], "live_value": mapping_by_hist[c]["live_value"]} for c, op, th in conds], sort_keys=True),
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
    active_pass.sort(key=lambda r: (float(r["validation_mean_bps"]), float(r["tail_mean_bps"]), float(r["validation_hit_rate"]), int(r["validation_events"])), reverse=True)
    selected = active_pass[0] if active_pass else None

    feature_date = live.get("feature_date") or live.get("utc_time") or live.get("date") or ""
    if selected:
        decision = "STAGE137_DEMO_RULE_READY_POINT_STAGE134_TO_STAGE137_FILE"
        selected_rule_id = selected["rule_id"]
        selected_label = selected["label"]
        any_signal_active = "true"
        active_count = "1"
        reason = "selected current-active PASS candidate using fuzzy live/historical schema bridge"
    elif not mapped_cols:
        decision = "STAGE137_NO_MAPPED_LIVE_NUMERIC_FEATURES_THESIS_GENERATOR_REQUIRED"
        selected_rule_id = ""
        selected_label = ""
        any_signal_active = "false"
        active_count = "0"
        reason = "no live numeric key could be mapped to historical numeric feature"
    else:
        decision = "STAGE137_NO_CURRENT_ACTIVE_PASS_CANDIDATE_THESIS_GENERATOR_REQUIRED"
        selected_rule_id = ""
        selected_label = ""
        any_signal_active = "false"
        active_count = "0"
        reason = "fuzzy mapping worked but no current-active candidate passed validation/tail gate"

    kv = {
        "stage": "Stage137_FUZZY_LIVE_SCHEMA_BRIDGE_DISCOVERY",
        "status": "FUZZY_BRIDGE_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE137",
        "decision": decision,
        "reason": reason,
        "mode": "DEMO_DISCOVERY_TO_STAGE134",
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
        "note": "Stage137 writes rule-state only; Stage134 demo executor must be manually pointed to this file",
        "stage134_required_InpRuleStateKvFile": KV_FILE,
        "stage134_required_InpAllowedRules": selected_rule_id,
    }
    latest_row = {
        "time_utc": generated,
        "rule_id": selected_rule_id,
        "rule_active": any_signal_active,
        "feature_date": feature_date,
        "selected_label": selected_label,
        "decision": decision,
        "reason": reason,
        "allow_trading": "false",
        "order_send": "false",
    }

    score_fields = ["rule_id","label","gate","current_active","conditions_json","selection_events","selection_mean_bps","selection_hit_rate","validation_events","validation_mean_bps","validation_hit_rate","tail_events","tail_mean_bps","tail_hit_rate"]
    mapping_fields = ["hist_col","live_key","similarity","live_value","hist_norm","live_norm"]

    score_path = out / "stage137_candidate_scores.csv"
    mapping_path = out / "stage137_fuzzy_schema_mapping.csv"
    write_csv(score_path, score_rows, score_fields)
    write_csv(mapping_path, mapping_rows, mapping_fields)
    write_csv(out / "stage137_risk_manifest.csv", [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    repo_kv = data / KV_FILE
    repo_latest = data / LATEST_FILE
    repo_history = data / HISTORY_FILE
    write_kv(repo_kv, kv)
    write_csv(repo_latest, [latest_row], list(latest_row.keys()))
    append_csv(repo_history, [latest_row], list(latest_row.keys()))

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
        "live_numeric_keys": len(live_numeric_keys(live)),
        "ret_col": ret_col,
        "date_col": date_col,
        "feature_date": feature_date,
        "historical_numeric_features": len(hist_features),
        "mapped_features": len(mapped_cols),
        "candidate_rows": len(score_rows),
        "pass_count": len([r for r in score_rows if r["gate"] == "PASS"]),
        "current_active_pass_count": len(active_pass),
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "selected_score": selected or {},
        "score_csv": str(score_path),
        "mapping_csv": str(mapping_path),
        "repo_kv": str(repo_kv),
        "repo_latest": str(repo_latest),
        "mt5_kv_written": bool(write_mt5),
        "mt5_kv": mt5_kv,
        "mt5_latest": mt5_latest,
        "stage134_instruction": {
            "InpRuleStateKvFile": KV_FILE,
            "InpAllowedRules": selected_rule_id,
            "keep_InpEnableDemoOrders": "true only on demo account",
            "restore_after_probe": "xauusd_stage133_unified_observer_rule_state_kv.csv",
        },
        "summary_json": str(out / "stage137_fuzzy_live_schema_bridge_discovery_summary.json"),
        "next": [
            "If selected_rule_id is non-empty, set Stage134 InpRuleStateKvFile to xauusd_stage137_fuzzy_bridge_rule_state_kv.csv and InpAllowedRules to selected_rule_id.",
            "If selected_rule_id is empty, move to thesis-family generator using historical + live feature repair; do not build more telemetry.",
        ],
    }
    write_json(out / "stage137_fuzzy_live_schema_bridge_discovery_summary.json", summary)
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
    ap.add_argument("--min-mean-bps", type=float, default=3.0)
    ap.add_argument("--min-hit", type=float, default=0.50)
    ap.add_argument("--min-similarity", type=float, default=0.42)
    ap.add_argument("--max-pair-features", type=int, default=10)
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
        min_similarity=args.min_similarity,
        max_pair_features=args.max_pair_features,
        write_mt5=args.write_mt5,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
