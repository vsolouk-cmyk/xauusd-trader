#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys
import re

# Allow direct execution as: python3 app/stage154_active_shortlist_rule_router.py
# without requiring PYTHONPATH=. in launchd or terminal.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.stage151_locked_mtf_rule_state_writer import (
    append_csv,
    compute_latest_features,
    condition_active,
    ensure_dir,
    normalize_bars,
    parse_float,
    read_table,
    write_csv,
    write_json,
    write_kv,
)

STAGE = "Stage157_GLOBAL_GATE_SAFE_ROUTER"
STATUS = "STAGE157_COMPLETE_GLOBAL_GATE_SAFE_ROUTER_READY"
DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "pass"}


def parse_conditions(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    try:
        val = json.loads(str(raw))
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    if not isinstance(val, list):
        return out
    for c in val:
        if not isinstance(c, dict):
            continue
        feature = c.get("feature")
        op = c.get("op")
        threshold = parse_float(c.get("threshold"))
        if feature and op in {">=", "<="} and threshold is not None:
            out.append({"feature": str(feature), "op": op, "threshold": threshold})
    return out




def normalize_family_key(rule_id: str) -> str:
    """Collapse threshold tokens so Stage145 family keys match candidate rule IDs."""
    s = str(rule_id or "").strip()
    # Handles tokens like _GEQ65, _LEQ35, _GEQ50P5 if later introduced.
    s = re.sub(r"_(GEQ|LEQ)[0-9]+(?:P[0-9]+)?", "", s)
    return s


def load_blocked_demo_families(risk_summary_path: Optional[Path], block_negative_demo_families: bool) -> Tuple[set, List[Dict[str, Any]]]:
    if not block_negative_demo_families or risk_summary_path is None:
        return set(), []
    p = Path(risk_summary_path).expanduser()
    if not p.exists():
        return set(), []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return set(), []
    blocked = set()
    rows: List[Dict[str, Any]] = []
    for fam in data.get("per_family", []) or []:
        if not isinstance(fam, dict):
            continue
        key = str(fam.get("family_key") or "").strip()
        if not key:
            continue
        closed = int(parse_float(fam.get("closed_trade_count")) or 0)
        total_bps = parse_float(fam.get("total_bps"))
        mean_bps = parse_float(fam.get("mean_bps"))
        total_profit = parse_float(fam.get("total_net_profit"))
        # Commercially defensive: once a demo-tested family is net negative, do not route it again
        # until the operator deliberately refreshes/replaces the rule cache or disables this guard.
        negative = closed >= 1 and ((total_bps is not None and total_bps < 0) or (mean_bps is not None and mean_bps < 0) or (total_profit is not None and total_profit < 0))
        if negative:
            blocked.add(key)
            rows.append({
                "family_key": key,
                "closed_trade_count": closed,
                "total_bps": total_bps,
                "mean_bps": mean_bps,
                "total_net_profit": total_profit,
                "last_rule_id": fam.get("last_rule_id", ""),
                "last_outcome": fam.get("last_outcome", ""),
            })
    return blocked, rows



def load_risk_summary_data(risk_summary_path: Optional[Path]) -> Dict[str, Any]:
    if risk_summary_path is None:
        return {}
    p = Path(risk_summary_path).expanduser()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def global_freeze_triggered(risk_data: Dict[str, Any], min_global_gate_trades: int) -> Tuple[bool, Dict[str, Any]]:
    """Return whether aggregate demo performance has triggered a circuit breaker.

    The guard is intentionally driven by Stage145's aggregate decision, not by
    a single candidate rule. Once Stage145 says freeze/repair on the clean demo
    ledger, this router should stop writing active signals until discovery is
    repaired or the operator explicitly disables the guard.
    """
    if not risk_data:
        return False, {
            "global_gate_freeze_active": False,
            "global_gate_reason": "risk summary missing or unreadable",
        }
    closed = int(parse_float(risk_data.get("closed_trade_count")) or 0)
    gate_decision = str(risk_data.get("gate_decision") or "")
    recommended_action = str(risk_data.get("recommended_action") or "")
    severity = str(risk_data.get("severity") or "")
    total_bps = parse_float(risk_data.get("total_bps"))
    mean_bps = parse_float(risk_data.get("mean_bps"))
    win_rate = parse_float(risk_data.get("win_rate"))
    decision_blob = " ".join([gate_decision, recommended_action, severity]).upper()
    stage145_freeze = any(tok in decision_blob for tok in ["FREEZE", "REPAIR", "NEGATIVE_EXPECTANCY"])
    high_severity_negative = severity.upper() == "HIGH" and closed >= min_global_gate_trades and (
        (total_bps is not None and total_bps < 0) or (mean_bps is not None and mean_bps < 0)
    )
    active = closed >= min_global_gate_trades and (stage145_freeze or high_severity_negative)
    reason = (
        f"Stage145 aggregate gate requires freeze/repair: gate_decision={gate_decision}; "
        f"recommended_action={recommended_action}; severity={severity}; closed_trade_count={closed}; "
        f"total_bps={total_bps}; mean_bps={mean_bps}; win_rate={win_rate}"
    ) if active else (
        f"Stage145 aggregate gate not frozen: gate_decision={gate_decision}; severity={severity}; closed_trade_count={closed}"
    )
    return active, {
        "global_gate_freeze_active": active,
        "global_gate_reason": reason,
        "global_gate_decision": gate_decision,
        "global_recommended_action": recommended_action,
        "global_severity": severity,
        "global_closed_trade_count": closed,
        "global_total_bps": total_bps,
        "global_mean_bps": mean_bps,
        "global_win_rate": win_rate,
        "min_global_gate_trades": min_global_gate_trades,
    }

def choose_active_candidate(
    score_rows: List[Dict[str, str]],
    latest: Dict[str, Any],
    min_validation_mean_bps: float,
    min_validation_hit: float,
    min_tail_mean_bps: float,
    min_tail_hit: float,
    max_candidates: int,
    blocked_family_keys: Optional[set] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], int, int]:
    candidates: List[Dict[str, Any]] = []
    eligible_count = 0
    risk_blocked_count = 0
    blocked_family_keys = blocked_family_keys or set()
    for r in score_rows:
        rule_id = str(r.get("rule_id") or "").strip()
        if not rule_id:
            continue
        family_key = normalize_family_key(rule_id)
        if family_key in blocked_family_keys:
            risk_blocked_count += 1
            continue
        gate = str(r.get("gate") or "").strip().upper()
        excluded = as_bool(r.get("excluded"))
        if gate != "PASS" or excluded:
            continue
        validation_mean = parse_float(r.get("validation_mean_bps"))
        validation_hit = parse_float(r.get("validation_hit_rate"))
        tail_mean = parse_float(r.get("tail_mean_bps"))
        tail_hit = parse_float(r.get("tail_hit_rate"))
        if validation_mean is None or validation_hit is None or tail_mean is None or tail_hit is None:
            continue
        if validation_mean < min_validation_mean_bps or validation_hit < min_validation_hit:
            continue
        if tail_mean < min_tail_mean_bps or tail_hit < min_tail_hit:
            continue
        conds = parse_conditions(r.get("conditions_json"))
        if not conds:
            continue
        eligible_count += 1
        if len(candidates) >= max_candidates:
            continue
        active = condition_active(latest, conds)
        row: Dict[str, Any] = dict(r)
        row["family_key"] = family_key
        row["conditions"] = conds
        row["router_active"] = active
        row["router_sort_key"] = (
            tail_mean,
            validation_mean,
            tail_hit,
            validation_hit,
            parse_float(r.get("tail_events")) or 0.0,
            parse_float(r.get("validation_events")) or 0.0,
        )
        row["router_condition_snapshot"] = json.dumps(
            [
                {
                    "feature": c["feature"],
                    "op": c["op"],
                    "threshold": c["threshold"],
                    "current": latest.get(c["feature"]),
                }
                for c in conds
            ],
            sort_keys=True,
        )
        if active:
            candidates.append(row)
    candidates.sort(key=lambda x: x["router_sort_key"], reverse=True)
    selected = candidates[0] if candidates else None
    return selected, candidates, eligible_count, risk_blocked_count


def run(
    root: Path,
    bars_path: Path,
    score_csv: Path,
    tf: str,
    timeframe_minutes: int,
    mt5_files: Path,
    write_mt5: bool,
    max_feature_age_sec: int,
    timestamp_shift_hours: float,
    min_validation_mean_bps: float,
    min_validation_hit: float,
    min_tail_mean_bps: float,
    min_tail_hit: float,
    max_candidates: int,
    risk_summary: Optional[Path],
    block_negative_demo_families: bool,
    global_freeze_guard: bool,
    min_global_gate_trades: int,
) -> Dict[str, Any]:
    root = root.expanduser()
    bars_path = bars_path.expanduser()
    score_csv = score_csv.expanduser()
    mt5_files = mt5_files.expanduser()
    generated = utc_now()

    raw_bars = read_table(bars_path)
    bars = normalize_bars(raw_bars)
    if len(bars) < 1300:
        raise ValueError(f"not enough bars for MTF features: {len(bars)}")
    latest = compute_latest_features(bars, timeframe_minutes)
    raw_feature_time = latest["utc_time"]
    normalized_feature_time = raw_feature_time + timedelta(hours=float(timestamp_shift_hours))
    now_utc = datetime.now(timezone.utc)
    feature_age_sec = int((now_utc - normalized_feature_time).total_seconds())
    feature_fresh = feature_age_sec >= 0 and feature_age_sec <= max_feature_age_sec
    feature_date = normalized_feature_time.isoformat().replace("+00:00", "Z")
    raw_feature_date = raw_feature_time.isoformat().replace("+00:00", "Z")

    rows = read_table(score_csv)
    risk_data = load_risk_summary_data(risk_summary)
    global_freeze_active, global_gate_info = global_freeze_triggered(risk_data, min_global_gate_trades)
    global_freeze_active = bool(global_freeze_guard and global_freeze_active)
    blocked_family_keys, blocked_family_rows = load_blocked_demo_families(risk_summary, block_negative_demo_families)
    selected, active_candidates, eligible_count, risk_blocked_count = choose_active_candidate(
        rows,
        latest,
        min_validation_mean_bps=min_validation_mean_bps,
        min_validation_hit=min_validation_hit,
        min_tail_mean_bps=min_tail_mean_bps,
        min_tail_hit=min_tail_hit,
        max_candidates=max_candidates,
        blocked_family_keys=blocked_family_keys,
    )

    tf_safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in tf).strip("_") or f"m{timeframe_minutes}"
    kv_file = f"xauusd_stage155_{tf_safe}_active_router_rule_state_kv.csv"
    latest_file = f"xauusd_stage155_{tf_safe}_active_router_rule_state_latest.csv"
    history_file = f"xauusd_stage155_{tf_safe}_active_router_rule_state_history.csv"

    raw_selected_rule_id = str(selected.get("rule_id") if selected else "")
    raw_selected_label = str(selected.get("label") if selected else "")
    if global_freeze_active:
        selected_rule_id = ""
        selected_label = ""
        active_and_fresh = False
        decision = "STAGE157_GLOBAL_PERFORMANCE_FREEZE_NO_ORDER"
        reason = str(global_gate_info.get("global_gate_reason") or "Stage145 aggregate freeze active")
    else:
        selected_rule_id = raw_selected_rule_id
        selected_label = raw_selected_label
        active_and_fresh = bool(selected_rule_id and feature_fresh)
        if selected_rule_id and feature_fresh:
            decision = "STAGE157_ACTIVE_RISK_GUARDED_RULE_READY_POINT_STAGE134_TO_STAGE155_FILE"
            reason = "active shortlist candidate selected and feature_date is fresh; aggregate global freeze guard is not active"
        elif selected_rule_id and not feature_fresh:
            decision = "STAGE157_ACTIVE_ROUTER_STALE_NO_ORDER"
            reason = "active shortlist candidate exists but feature_date is stale or future"
        else:
            decision = "STAGE157_NO_ACTIVE_RISK_GUARDED_RULE_NO_ORDER"
            reason = "no active candidate from cached Stage150 score shortlist after family/global guards"

    selected_condition_snapshot = selected.get("router_condition_snapshot") if selected else "[]"
    kv: Dict[str, Any] = {
        "stage": STAGE,
        "status": "ACTIVE_ROUTER_DEMO_RISK_GUARD_ALIVE_NO_ORDER_SEND_IN_STAGE155",
        "decision": decision,
        "reason": reason,
        "mode": "CACHED_SCORE_SHORTLIST_ACTIVE_ROUTER_WITH_DEMO_RISK_GUARD_TO_STAGE134",
        "tf": tf_safe,
        "timeframe_minutes": timeframe_minutes,
        "feature_date": feature_date,
        "raw_feature_date": raw_feature_date,
        "timestamp_shift_hours": timestamp_shift_hours,
        "feature_age_sec": feature_age_sec,
        "max_feature_age_sec": max_feature_age_sec,
        "feature_fresh": "true" if feature_fresh else "false",
        "any_signal_active": "true" if active_and_fresh else "false",
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "selected_family_key": normalize_family_key(selected_rule_id) if selected_rule_id else "",
        "active_rule_count": 1 if active_and_fresh else 0,
        "active_shortlist_count": len(active_candidates),
        "eligible_shortlist_count": eligible_count,
        "risk_blocked_family_count": len(blocked_family_keys),
        "risk_blocked_candidate_count": risk_blocked_count,
        "risk_summary": str(risk_summary) if risk_summary else "",
        "block_negative_demo_families": "true" if block_negative_demo_families else "false",
        "blocked_family_keys": ";".join(sorted(blocked_family_keys)),
        "global_freeze_guard": "true" if global_freeze_guard else "false",
        "global_gate_freeze_active": "true" if global_freeze_active else "false",
        "global_gate_decision": global_gate_info.get("global_gate_decision", ""),
        "global_recommended_action": global_gate_info.get("global_recommended_action", ""),
        "global_severity": global_gate_info.get("global_severity", ""),
        "global_gate_reason": global_gate_info.get("global_gate_reason", ""),
        "raw_selected_rule_id_before_global_gate": raw_selected_rule_id,
        "score_csv": str(score_csv),
        "selected_condition_snapshot": selected_condition_snapshot,
        "execution_allowed": "false",
        "order_authorized": "false",
        "allow_trading": "false",
        "order_send": "false",
        "note": "Stage155 routes among cached Stage150 PASS candidates and blocks demo-negative families; it does not rescan discovery and does not send orders.",
        "stage134_required_InpRuleStateKvFile": kv_file,
        "stage134_required_InpAllowedRules": "all",
    }

    latest_row = {
        "time_utc": generated,
        "tf": tf_safe,
        "rule_id": selected_rule_id,
        "rule_active": "true" if active_and_fresh else "false",
        "feature_date": feature_date,
        "raw_feature_date": raw_feature_date,
        "timestamp_shift_hours": timestamp_shift_hours,
        "decision": decision,
        "reason": reason,
        "active_shortlist_count": len(active_candidates),
        "eligible_shortlist_count": eligible_count,
        "risk_blocked_family_count": len(blocked_family_keys),
        "risk_blocked_candidate_count": risk_blocked_count,
        "global_gate_freeze_active": "true" if global_freeze_active else "false",
        "global_gate_decision": global_gate_info.get("global_gate_decision", ""),
        "raw_selected_rule_id_before_global_gate": raw_selected_rule_id,
        "allow_trading": "false",
        "order_send": "false",
    }

    data = ensure_dir(root / "data/demo_execution")
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

    out_dir = ensure_dir(root / "reports/stage155_active_router_demo_risk_guard" / tf_safe)
    active_rows: List[Dict[str, Any]] = []
    for i, r in enumerate(active_candidates[: max_candidates], start=1):
        active_rows.append(
            {
                "rank": i,
                "rule_id": r.get("rule_id", ""),
                "family_key": r.get("family_key", ""),
                "label": r.get("label", ""),
                "selection_mean_bps": r.get("selection_mean_bps", ""),
                "validation_mean_bps": r.get("validation_mean_bps", ""),
                "tail_mean_bps": r.get("tail_mean_bps", ""),
                "validation_hit_rate": r.get("validation_hit_rate", ""),
                "tail_hit_rate": r.get("tail_hit_rate", ""),
                "condition_snapshot": r.get("router_condition_snapshot", ""),
            }
        )
    write_csv(
        out_dir / "stage155_active_router_candidates.csv",
        active_rows,
        [
            "rank",
            "rule_id",
            "family_key",
            "label",
            "selection_mean_bps",
            "validation_mean_bps",
            "tail_mean_bps",
            "validation_hit_rate",
            "tail_hit_rate",
            "condition_snapshot",
        ],
    )

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "bars_path": str(bars_path),
        "score_csv": str(score_csv),
        "tf": tf_safe,
        "timeframe_minutes": timeframe_minutes,
        "raw_row_count": len(raw_bars),
        "bar_count": len(bars),
        "raw_feature_date": raw_feature_date,
        "timestamp_shift_hours": timestamp_shift_hours,
        "feature_date": feature_date,
        "feature_age_sec": feature_age_sec,
        "max_feature_age_sec": max_feature_age_sec,
        "feature_fresh": feature_fresh,
        "score_rows": len(rows),
        "eligible_shortlist_count": eligible_count,
        "active_shortlist_count": len(active_candidates),
        "selected_rule_id": selected_rule_id,
        "selected_label": selected_label,
        "selected_family_key": normalize_family_key(selected_rule_id) if selected_rule_id else "",
        "selected_condition_snapshot": selected_condition_snapshot,
        "raw_selected_rule_id_before_global_gate": raw_selected_rule_id,
        "raw_selected_label_before_global_gate": raw_selected_label,
        "risk_summary": str(risk_summary) if risk_summary else "",
        "global_freeze_guard": global_freeze_guard,
        "global_gate_freeze_active": global_freeze_active,
        "global_gate_info": global_gate_info,
        "block_negative_demo_families": block_negative_demo_families,
        "risk_blocked_family_count": len(blocked_family_keys),
        "risk_blocked_candidate_count": risk_blocked_count,
        "blocked_family_keys": sorted(blocked_family_keys),
        "blocked_family_rows": blocked_family_rows,
        "repo_kv": str(repo_kv),
        "repo_latest": str(repo_latest),
        "mt5_kv_written": bool(write_mt5),
        "mt5_kv": mt5_kv,
        "mt5_latest": mt5_latest,
        "stage134_instruction": {
            "InpRuleStateKvFile": kv_file,
            "InpAllowedRules": "all",
            "keep_InpEnableDemoOrders": "true only on demo account",
        },
        "summary_json": str(out_dir / "stage155_active_router_demo_risk_guard_summary.json"),
        "next": [
            "Use this Stage157-hardened router behind Stage156; it preserves Stage155 KV filename so Stage134 input does not need to change.",
            "If global_gate_freeze_active is true, keep demo orders blocked and repair discovery before re-enabling routing.",
        ],
    }
    write_json(out_dir / "stage155_active_router_demo_risk_guard_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--bars", required=True)
    ap.add_argument("--score-csv", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--timeframe-minutes", type=int, required=True)
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--write-mt5", action="store_true")
    ap.add_argument("--max-feature-age-sec", type=int, default=7200)
    ap.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    ap.add_argument("--min-validation-mean-bps", type=float, default=2.0)
    ap.add_argument("--min-validation-hit", type=float, default=0.53)
    ap.add_argument("--min-tail-mean-bps", type=float, default=1.0)
    ap.add_argument("--min-tail-hit", type=float, default=0.50)
    ap.add_argument("--max-candidates", type=int, default=300)
    ap.add_argument("--risk-summary", default="/Users/vahid/Desktop/xauusd-trader/reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json")
    ap.add_argument("--allow-negative-demo-families", action="store_true")
    ap.add_argument("--disable-global-freeze-guard", action="store_true")
    ap.add_argument("--min-global-gate-trades", type=int, default=10)
    args = ap.parse_args()
    run(
        root=Path(args.root),
        bars_path=Path(args.bars),
        score_csv=Path(args.score_csv),
        tf=args.tf,
        timeframe_minutes=args.timeframe_minutes,
        mt5_files=Path(args.mt5_files),
        write_mt5=args.write_mt5,
        max_feature_age_sec=args.max_feature_age_sec,
        timestamp_shift_hours=args.timestamp_shift_hours,
        min_validation_mean_bps=args.min_validation_mean_bps,
        min_validation_hit=args.min_validation_hit,
        min_tail_mean_bps=args.min_tail_mean_bps,
        min_tail_hit=args.min_tail_hit,
        max_candidates=args.max_candidates,
        risk_summary=Path(args.risk_summary) if args.risk_summary else None,
        block_negative_demo_families=not args.allow_negative_demo_families,
        global_freeze_guard=not args.disable_global_freeze_guard,
        min_global_gate_trades=args.min_global_gate_trades,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
