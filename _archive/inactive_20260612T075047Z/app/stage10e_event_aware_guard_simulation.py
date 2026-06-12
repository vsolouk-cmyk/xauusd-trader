#!/usr/bin/env python3
"""
Stage 10E v2 — Event-Aware Guard / Report Simulation with Input Audit

Purpose:
- Test whether validated event classes improve the Stage 8B/8D candidate as a report/guard layer.
- Audit inputs explicitly, so missing Stage 10C numeric events cannot silently produce "no_effect".
- Do NOT modify EA logic.
- Do NOT authorize orders.

Inputs:
- Stage 8B trades:
  data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv
- Numeric shock events:
  data/macro/events/stage10c_numeric_shock_events.csv
- GDELT/event pipeline events:
  data/macro/events/stage10b_detected_shock_events.csv
- Config:
  data/config/stage10e_validated_event_classes.csv

Outputs:
- data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md
- data/reports/stage10e_event_aware_guard_simulation/stage10e_candidate_trades_event_annotated.csv
- data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv
- data/reports/stage10e_event_aware_guard_simulation/stage10e_recent_event_dashboard.csv
- data/reports/stage10e_event_aware_guard_simulation/stage10e_input_audit.json
- data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.json

Hard rules:
- Research/report/guard simulation only.
- No EA change.
- No automatic news trading.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v2_input_audit"
DEFAULT_STAGE8B_TRADES = Path("data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv")
DEFAULT_NUMERIC_EVENTS = Path("data/macro/events/stage10c_numeric_shock_events.csv")
DEFAULT_GDELT_EVENTS = Path("data/macro/events/stage10b_detected_shock_events.csv")
DEFAULT_CONFIG = Path("data/config/stage10e_validated_event_classes.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage10e_event_aware_guard_simulation")


@dataclass
class EventRule:
    event_class: str
    event_channel: str
    role: str
    window_before_hours: float
    window_after_hours: float
    action: str
    notes: str


@dataclass
class Event:
    event_id: str
    event_time_utc: datetime
    event_class: str
    event_channel: str
    expected_gold_direction: int
    initial_importance: float
    confidence: float
    source_name: str
    source_kind: str
    title: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(v: str) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def safe_int(v, default=0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).strip()))
    except Exception:
        return default


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def first_existing(row: dict, aliases: Sequence[str], default: str = "") -> str:
    for a in aliases:
        if a in row and str(row.get(a, "")).strip() != "":
            return str(row.get(a, "")).strip()
    return default


def load_rules(path: Path) -> List[EventRule]:
    rows = read_csv(path)
    rules: List[EventRule] = []
    for r in rows:
        cls = (r.get("event_class") or "").strip()
        channel = (r.get("event_channel") or "").strip()
        if not cls or cls.upper().startswith("EXAMPLE"):
            continue
        rules.append(EventRule(
            event_class=cls,
            event_channel=channel,
            role=(r.get("role") or "monitoring_only").strip(),
            window_before_hours=safe_float(r.get("window_before_hours"), 0.0),
            window_after_hours=safe_float(r.get("window_after_hours"), 24.0),
            action=(r.get("action") or "report_only").strip(),
            notes=(r.get("notes") or "").strip(),
        ))
    return rules


def load_events_from_path(path: Path, source_kind_default: str) -> List[Event]:
    out: List[Event] = []
    seen = set()
    for r in read_csv(path):
        eid = (r.get("event_id") or "").strip()
        if not eid:
            eid = f"{r.get('event_time_utc','')}|{r.get('title','')}"
        if eid in seen:
            continue
        t = parse_time(r.get("event_time_utc") or "")
        if t is None:
            continue
        seen.add(eid)
        out.append(Event(
            event_id=eid,
            event_time_utc=t,
            event_class=(r.get("event_class") or "unknown").strip(),
            event_channel=(r.get("event_channel") or "unknown").strip(),
            expected_gold_direction=safe_int(r.get("expected_gold_direction"), 0),
            initial_importance=safe_float(r.get("initial_importance"), 1.0),
            confidence=safe_float(r.get("confidence"), 0.5),
            source_name=(r.get("source_name") or "").strip(),
            source_kind=(r.get("source_kind") or source_kind_default).strip(),
            title=(r.get("title") or "").strip(),
        ))
    return out


def load_events(numeric_path: Path, gdelt_path: Path) -> Tuple[List[Event], List[Event], List[Event]]:
    numeric = load_events_from_path(numeric_path, "numeric")
    gdelt = load_events_from_path(gdelt_path, "gdelt")
    seen = set()
    all_events = []
    for e in sorted(numeric + gdelt, key=lambda x: x.event_time_utc):
        if e.event_id in seen:
            continue
        seen.add(e.event_id)
        all_events.append(e)
    return numeric, gdelt, all_events


def rule_for_event(e: Event, rules: Sequence[EventRule]) -> Optional[EventRule]:
    for r in rules:
        if e.event_class == r.event_class and (not r.event_channel or e.event_channel == r.event_channel):
            return r
    return None


def is_event_active_for_time(e: Event, rule: EventRule, t: datetime) -> bool:
    start = e.event_time_utc - timedelta(hours=rule.window_before_hours)
    end = e.event_time_utc + timedelta(hours=rule.window_after_hours)
    return start <= t <= end


def normalize_trade(row: dict) -> Optional[dict]:
    entry_str = first_existing(row, ["entry_utc", "planned_entry_utc", "entry_time", "entry_ts", "signal_closed_h1_utc", "signal_utc"])
    entry_dt = parse_time(entry_str)
    if entry_dt is None:
        return None

    definition = first_existing(row, ["definition", "candidate_definition", "family", "name", "candidate"])
    guard = first_existing(row, ["guard_variant", "variant", "guard", "execution_variant"])
    geometry = first_existing(row, ["geometry", "exit_geometry", "exit_rule", "exit_name"])

    net = None
    for col in ["net_x4", "net_usd_x4", "net_after_cost_x4", "pnl_x4", "ret_x4", "net"]:
        if col in row and str(row.get(col, "")).strip() != "":
            net = safe_float(row.get(col))
            break
    if net is None:
        return None

    out = dict(row)
    out["_entry_dt"] = entry_dt
    out["_entry_utc"] = entry_dt.isoformat()
    out["_definition_norm"] = definition
    out["_guard_norm"] = guard
    out["_geometry_norm"] = geometry
    out["_net_x4"] = net
    return out


def is_stage8d_candidate_trade(t: dict) -> bool:
    definition = str(t.get("_definition_norm", "")).lower()
    guard = str(t.get("_guard_norm", "")).lower()
    geometry = str(t.get("_geometry_norm", "")).lower()
    return (
        "liquidity_session" in definition
        and "nonoverlap" in guard
        and "time_exit_12h" in geometry
    )


def drawdown(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        maxdd = min(maxdd, eq - peak)
    return round(maxdd, 6)


def pf(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def summarize(vals: Sequence[float]) -> dict:
    vals = list(vals)
    wins = [v for v in vals if v > 0]
    return {
        "trades": len(vals),
        "total_x4": round(sum(vals), 6),
        "median_x4": round(median(vals), 6) if vals else 0.0,
        "pf_x4": pf(vals),
        "wr_x4": round(len(wins) / len(vals), 6) if vals else 0.0,
        "dd_x4": drawdown(vals),
    }


def annotated_event_counts(events: Sequence[Event], rules: Sequence[EventRule]) -> Dict[str, int]:
    counts = {}
    for e in events:
        r = rule_for_event(e, rules)
        key = "unmatched"
        if r:
            key = f"{e.event_class}|{e.event_channel}|{r.role}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def audit_inputs(numeric_path: Path, gdelt_path: Path, rules: Sequence[EventRule], numeric_events: Sequence[Event], gdelt_events: Sequence[Event], all_events: Sequence[Event]) -> Tuple[dict, List[str]]:
    warnings: List[str] = []

    guard_rules = [r for r in rules if r.role in {"directional_or_guard_candidate", "guard_candidate"}]
    guard_classes = {(r.event_class, r.event_channel) for r in guard_rules}
    guard_events = [e for e in all_events if (e.event_class, e.event_channel) in guard_classes]

    numeric_guard_events = [e for e in numeric_events if (e.event_class, e.event_channel) in guard_classes]

    if guard_rules and not numeric_path.exists():
        warnings.append(f"Numeric event file missing: {numeric_path}. Run Stage 10C before Stage 10E.")
    if guard_rules and len(numeric_guard_events) == 0:
        warnings.append("No numeric events matched directional/guard rules. Yield-guard simulation will have no effect. Run Stage 10C again after copying Stage 10B artifacts.")
    if len(gdelt_events) > 0 and len(numeric_events) == 0:
        warnings.append("Only GDELT events are loaded. Current GDELT classes are monitoring-only, so guard policies will likely show no_effect.")

    audit = {
        "numeric_events_path": str(numeric_path),
        "numeric_events_path_exists": numeric_path.exists(),
        "gdelt_events_path": str(gdelt_path),
        "gdelt_events_path_exists": gdelt_path.exists(),
        "numeric_events_loaded": len(numeric_events),
        "gdelt_events_loaded": len(gdelt_events),
        "all_events_loaded": len(all_events),
        "rules_loaded": len(rules),
        "guard_rules_loaded": len(guard_rules),
        "guard_event_classes": [f"{c}|{ch}" for c, ch in sorted(guard_classes)],
        "guard_events_loaded": len(guard_events),
        "numeric_guard_events_loaded": len(numeric_guard_events),
        "event_counts_by_rule": annotated_event_counts(all_events, rules),
        "warnings": warnings,
    }
    return audit, warnings


def annotate_trades(trades: Sequence[dict], events: Sequence[Event], rules: Sequence[EventRule]) -> List[dict]:
    relevant_events = [(e, rule_for_event(e, rules)) for e in events]
    relevant_events = [(e, r) for e, r in relevant_events if r is not None]

    out = []
    for t in trades:
        entry_dt = t["_entry_dt"]
        active = []
        monitoring = []
        guard = []
        expected_dirs = []

        for e, r in relevant_events:
            if r is None:
                continue
            if is_event_active_for_time(e, r, entry_dt):
                label = f"{e.event_class}:{e.event_channel}:{e.expected_gold_direction}:{e.event_time_utc.isoformat()}"
                active.append(label)
                expected_dirs.append(e.expected_gold_direction)
                if r.role in {"directional_or_guard_candidate", "guard_candidate"}:
                    guard.append(label)
                else:
                    monitoring.append(label)

        rr = dict(t)
        rr.pop("_entry_dt", None)
        rr["entry_utc_norm"] = t["_entry_utc"]
        rr["net_x4_norm"] = t["_net_x4"]
        rr["event_active_count"] = len(active)
        rr["guard_event_active"] = 1 if guard else 0
        rr["monitoring_event_active"] = 1 if monitoring else 0
        rr["active_event_labels"] = ";".join(active)
        rr["guard_event_labels"] = ";".join(guard)
        rr["monitoring_event_labels"] = ";".join(monitoring)
        rr["hostile_event_active"] = 1 if any(x < 0 for x in expected_dirs) else 0
        rr["supportive_event_active"] = 1 if any(x > 0 for x in expected_dirs) else 0
        out.append(rr)

    return out


def simulate_policies(annotated: Sequence[dict]) -> List[dict]:
    base_vals = [safe_float(r["net_x4_norm"]) for r in annotated]

    policies = []
    baseline = summarize(base_vals)
    policies.append({"policy": "baseline_all_trades", "description": "No event filter", **baseline, "blocked_trades": 0, "kept_trades": baseline["trades"], "blocked_pct": 0.0})

    def policy(name: str, desc: str, keep_fn):
        kept = [r for r in annotated if keep_fn(r)]
        vals = [safe_float(r["net_x4_norm"]) for r in kept]
        s = summarize(vals)
        policies.append({
            "policy": name,
            "description": desc,
            **s,
            "blocked_trades": len(annotated) - len(kept),
            "kept_trades": len(kept),
            "blocked_pct": round((len(annotated) - len(kept)) / len(annotated), 6) if annotated else 0.0,
        })

    policy("block_any_validated_yield_event_window", "Block trades during any validated yield-shock event window", lambda r: safe_int(r.get("guard_event_active"), 0) == 0)
    policy("block_hostile_yield_event_window_only", "Block trades only when validated event is hostile to long gold", lambda r: safe_int(r.get("hostile_event_active"), 0) == 0)
    policy("take_only_supportive_yield_event_window", "Take trades only when validated event is supportive to long gold", lambda r: safe_int(r.get("supportive_event_active"), 0) == 1)
    policy("take_only_no_validated_event_window", "Take trades only when no validated event window is active", lambda r: safe_int(r.get("guard_event_active"), 0) == 0)

    b = policies[0]
    for p in policies:
        p["delta_total_vs_baseline"] = round(p["total_x4"] - b["total_x4"], 6)
        p["delta_pf_vs_baseline"] = round(p["pf_x4"] - b["pf_x4"], 6)
        p["delta_dd_vs_baseline"] = round(p["dd_x4"] - b["dd_x4"], 6)
        if p["policy"] == "baseline_all_trades":
            p["decision_hint"] = "baseline"
        elif p["blocked_trades"] == 0:
            p["decision_hint"] = "no_effect_check_input_audit"
        elif p["trades"] < 20:
            p["decision_hint"] = "insufficient_remaining_sample"
        elif p["total_x4"] > b["total_x4"] and p["pf_x4"] >= b["pf_x4"] and p["dd_x4"] >= b["dd_x4"]:
            p["decision_hint"] = "candidate_guard"
        elif p["pf_x4"] > b["pf_x4"] and p["dd_x4"] >= b["dd_x4"] and p["blocked_pct"] < 0.35:
            p["decision_hint"] = "weak_candidate_guard"
        else:
            p["decision_hint"] = "reject_as_guard_or_report_only"
    return policies


def recent_event_dashboard(events: Sequence[Event], rules: Sequence[EventRule], days_back: int = 21) -> List[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for e in events:
        if e.event_time_utc < now - timedelta(days=days_back):
            continue
        r = rule_for_event(e, rules)
        out.append({
            "event_time_utc": e.event_time_utc.isoformat(),
            "event_class": e.event_class,
            "event_channel": e.event_channel,
            "expected_gold_direction": e.expected_gold_direction,
            "source_kind": e.source_kind,
            "source_name": e.source_name,
            "role": r.role if r else "unvalidated_or_monitoring",
            "window_before_hours": r.window_before_hours if r else "",
            "window_after_hours": r.window_after_hours if r else "",
            "title": e.title,
        })
    return sorted(out, key=lambda x: x["event_time_utc"], reverse=True)


def write_report(out_dir: Path, payload: dict, policies: Sequence[dict], dashboard: Sequence[dict], audit: dict, warnings: Sequence[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage10e_event_aware_guard_simulation.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage10e_input_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 10E Event-Aware Guard / Report Simulation",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: simulation only. This does not authorize demo, paper, or live orders.",
        "",
        "## Input audit",
        f"- numeric_events_path_exists: `{audit['numeric_events_path_exists']}`",
        f"- numeric_events_loaded: `{audit['numeric_events_loaded']}`",
        f"- gdelt_events_loaded: `{audit['gdelt_events_loaded']}`",
        f"- all_events_loaded: `{audit['all_events_loaded']}`",
        f"- guard_rules_loaded: `{audit['guard_rules_loaded']}`",
        f"- guard_events_loaded: `{audit['guard_events_loaded']}`",
        f"- numeric_guard_events_loaded: `{audit['numeric_guard_events_loaded']}`",
    ]

    if warnings:
        lines += ["", "## Input warnings"]
        for w in warnings:
            lines.append(f"- `{w}`")

    lines += [
        "",
        "## Inputs",
        f"- stage8b_trades: `{payload['stage8b_trades']}`",
        f"- numeric_events: `{payload['numeric_events']}`",
        f"- gdelt_events: `{payload['gdelt_events']}`",
        f"- rules_config: `{payload['rules_config']}`",
        f"- raw_stage8b_trades_loaded: `{payload['raw_stage8b_trades_loaded']}`",
        f"- candidate_trades_loaded: `{payload['candidate_trades_loaded']}`",
        f"- rules_loaded: `{payload['rules_loaded']}`",
        "",
        "## Guard policy simulation",
        "| Policy | Trades | Blocked | Blocked % | Total x4 | Median x4 | PF x4 | WR x4 | DD x4 | ΔTotal | ΔPF | ΔDD | Decision hint |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for p in policies:
        lines.append(
            f"| {p['policy']} | {p['trades']} | {p.get('blocked_trades',0)} | {p.get('blocked_pct',0)} | "
            f"{p['total_x4']} | {p['median_x4']} | {p['pf_x4']} | {p['wr_x4']} | {p['dd_x4']} | "
            f"{p['delta_total_vs_baseline']} | {p['delta_pf_vs_baseline']} | {p['delta_dd_vs_baseline']} | {p['decision_hint']} |"
        )

    lines += [
        "",
        "## Recent event dashboard",
        "| Time UTC | Class | Channel | Expected | Source | Role | Title |",
        "|---|---|---|---:|---|---|---|",
    ]
    if dashboard:
        for r in dashboard[:50]:
            title = str(r["title"]).replace("|", "/")[:160]
            lines.append(
                f"| {r['event_time_utc']} | {r['event_class']} | {r['event_channel']} | {r['expected_gold_direction']} | "
                f"{r['source_kind']} | {r['role']} | {title} |"
            )
    else:
        lines.append("| none | none | none | 0 | none | none | none |")

    lines += [
        "",
        "## Interpretation",
        "- If `numeric_guard_events_loaded` is zero, yield-guard simulation is invalid and Stage 10C must be rerun.",
        "- A policy is useful only if it improves PF/drawdown without destroying trade count.",
        "- GDELT central-bank demand is monitoring-only until it has enough independent clusters.",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- If a guard policy passes here, the next step is forward-shadow reporting only.",
    ]

    (out_dir / "stage10e_event_aware_guard_simulation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(stage8b_trades: Path, numeric_events: Path, gdelt_events: Path, rules_config: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    raw_trades = read_csv(stage8b_trades)
    norm_trades = [normalize_trade(r) for r in raw_trades]
    norm_trades = [r for r in norm_trades if r is not None]
    candidate_trades = [r for r in norm_trades if is_stage8d_candidate_trade(r)]

    rules = load_rules(rules_config)
    numeric_loaded, gdelt_loaded, events = load_events(numeric_events, gdelt_events)
    audit, warnings = audit_inputs(numeric_events, gdelt_events, rules, numeric_loaded, gdelt_loaded, events)

    annotated = annotate_trades(candidate_trades, events, rules)
    policies = simulate_policies(annotated)
    dashboard = recent_event_dashboard(events, rules)

    write_csv(out_dir / "stage10e_candidate_trades_event_annotated.csv", annotated)
    write_csv(out_dir / "stage10e_guard_policy_simulation.csv", policies)
    write_csv(out_dir / "stage10e_recent_event_dashboard.csv", dashboard)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "stage8b_trades": str(stage8b_trades),
        "numeric_events": str(numeric_events),
        "gdelt_events": str(gdelt_events),
        "rules_config": str(rules_config),
        "raw_stage8b_trades_loaded": len(raw_trades),
        "normalized_trades_loaded": len(norm_trades),
        "candidate_trades_loaded": len(candidate_trades),
        "numeric_events_loaded": len(numeric_loaded),
        "gdelt_events_loaded": len(gdelt_loaded),
        "events_loaded": len(events),
        "rules_loaded": len(rules),
        "audit": audit,
        "policies": policies,
        "recent_event_dashboard_rows": len(dashboard),
    }
    write_report(out_dir, payload, policies, dashboard, audit, warnings)

    print("Stage 10E event-aware guard simulation: DONE")
    print(f"candidate_trades={len(candidate_trades)} numeric_events={len(numeric_loaded)} gdelt_events={len(gdelt_loaded)} guard_events={audit['guard_events_loaded']} policies={len(policies)}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"- {w}")
    print(f"Report: {out_dir / 'stage10e_event_aware_guard_simulation.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stage8b-trades", default=str(DEFAULT_STAGE8B_TRADES))
    p.add_argument("--numeric-events", default=str(DEFAULT_NUMERIC_EVENTS))
    p.add_argument("--gdelt-events", default=str(DEFAULT_GDELT_EVENTS))
    p.add_argument("--rules-config", default=str(DEFAULT_CONFIG))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(
        Path(args.stage8b_trades),
        Path(args.numeric_events),
        Path(args.gdelt_events),
        Path(args.rules_config),
        Path(args.out_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
