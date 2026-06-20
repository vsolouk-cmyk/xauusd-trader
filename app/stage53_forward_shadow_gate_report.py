#!/usr/bin/env python3
"""
Stage53 forward-shadow gate report and paper-order preparation.

Purpose:
- Read Stage52 true-forward state and latest summaries.
- Decide whether enough true-forward evidence exists to even design a paper-order simulator.
- Produce a paper-order skeleton configuration for later dry simulation only.

This script does not place orders, does not connect to MT5/broker, and does not authorize EA,
paper-live, live trading, or promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage53_FORWARD_SHADOW_GATES_AND_PAPER_ORDER_PREP_NO_PROMOTION"
STATUS = "FORWARD_SHADOW_GATE_REPORT_COMPLETE_NO_PROMOTION"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fmt_ts(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(value))
    except Exception:
        return default


def mean(values: Sequence[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.mean(vals) if vals else None


def median(values: Sequence[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(vals) if vals else None


def max_drawdown(vals: Sequence[float]) -> Optional[float]:
    if not vals:
        return None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in vals:
        equity += float(v)
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": repr(exc), "path": str(path)}


def read_signals_from_state_db(state_db: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(state_db), "found": state_db.exists(), "schema_ok": False}
    if not state_db.exists():
        return [], meta
    with sqlite3.connect(str(state_db)) as conn:
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        meta["tables"] = sorted(tables)
        if "signals" not in tables:
            return [], meta
        cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
        meta["columns"] = cols
        meta["schema_ok"] = True
        rows = conn.execute("SELECT * FROM signals ORDER BY entry_time_utc").fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({k: r[k] for k in r.keys()})
        meta["row_count"] = len(out)
        return out, meta


def summarize_signals(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(signals)
    backfill = [s for s in signals if safe_int(s.get("is_backfill"), 0) == 1]
    forward = [s for s in signals if safe_int(s.get("is_backfill"), 0) == 0]
    pending = [s for s in forward if str(s.get("status") or "").upper() == "PENDING"]
    evaluated = [s for s in forward if str(s.get("status") or "").upper() == "EVALUATED"]
    stress_vals = [safe_float(s.get("stress_bps")) for s in evaluated]
    stress_vals = [x for x in stress_vals if x is not None]
    entry_times = [parse_ts(s.get("entry_time_utc")) for s in forward]
    entry_times = [x for x in entry_times if x is not None]
    evaluated_times = [parse_ts(s.get("entry_time_utc")) for s in evaluated]
    evaluated_times = [x for x in evaluated_times if x is not None]
    cand_counts = Counter(str(s.get("candidate_id") or "UNKNOWN") for s in forward)
    day_counts = Counter((parse_ts(s.get("entry_time_utc")) or datetime(1970,1,1,tzinfo=timezone.utc)).strftime("%Y-%m-%d") for s in forward)
    candidate_means = {}
    neg_candidate_mean_count = 0
    for cid in cand_counts:
        vals = [safe_float(s.get("stress_bps")) for s in evaluated if str(s.get("candidate_id") or "UNKNOWN") == cid]
        vals = [x for x in vals if x is not None]
        if vals:
            m = statistics.mean(vals)
            candidate_means[cid] = m
            if m <= 0:
                neg_candidate_mean_count += 1
    return {
        "total_state_rows": total,
        "backfill_signals": len(backfill),
        "true_forward_signals": len(forward),
        "pending_signals": len(pending),
        "evaluated_signals": len(evaluated),
        "evaluated_mean_stress_bps": mean(stress_vals),
        "evaluated_median_stress_bps": median(stress_vals),
        "evaluated_win_rate": (sum(1 for x in stress_vals if x > 0) / len(stress_vals)) if stress_vals else None,
        "evaluated_total_stress_bps": sum(stress_vals) if stress_vals else None,
        "evaluated_max_drawdown_bps": max_drawdown(stress_vals),
        "distinct_candidate_ids": len(cand_counts),
        "candidate_counts": dict(cand_counts.most_common()),
        "max_candidate_share": (max(cand_counts.values()) / len(forward)) if forward and cand_counts else 0.0,
        "max_day_share": (max(day_counts.values()) / len(forward)) if forward and day_counts else 0.0,
        "pending_share": (len(pending) / len(forward)) if forward else 0.0,
        "forward_first_entry_utc": fmt_ts(min(entry_times)) if entry_times else None,
        "forward_last_entry_utc": fmt_ts(max(entry_times)) if entry_times else None,
        "forward_span_days": ((max(entry_times) - min(entry_times)).total_seconds() / 86400.0) if len(entry_times) >= 2 else 0.0,
        "evaluated_first_entry_utc": fmt_ts(min(evaluated_times)) if evaluated_times else None,
        "evaluated_last_entry_utc": fmt_ts(max(evaluated_times)) if evaluated_times else None,
        "evaluated_span_days": ((max(evaluated_times) - min(evaluated_times)).total_seconds() / 86400.0) if len(evaluated_times) >= 2 else 0.0,
        "negative_candidate_mean_count": neg_candidate_mean_count,
        "candidate_mean_stress_bps": candidate_means,
    }


def gate_check(name: str, observed: Any, operator: str, threshold: Any, passed: bool) -> Dict[str, Any]:
    return {
        "gate": name,
        "observed": observed,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
    }


def evaluate_gates(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, str, List[str]]:
    ev = cfg.get("minimum_evidence", {})
    qg = cfg.get("quality_gates", {})
    labels = cfg.get("decision_labels", {})
    gates: List[Dict[str, Any]] = []

    def ge(metric: str, threshold_key: str, group: Dict[str, Any]):
        obs = metrics.get(metric)
        th = group.get(threshold_key)
        passed = (obs is not None and th is not None and float(obs) >= float(th))
        gates.append(gate_check(metric, obs, ">=", th, passed))

    def le(metric: str, threshold_key: str, group: Dict[str, Any]):
        obs = metrics.get(metric)
        th = group.get(threshold_key)
        passed = (obs is not None and th is not None and float(obs) <= float(th))
        gates.append(gate_check(metric, obs, "<=", th, passed))

    ge("true_forward_signals", "min_true_forward_signals", ev)
    ge("evaluated_signals", "min_evaluated_signals", ev)
    # Total available evidence: pending + evaluated true-forward signals.
    pending_or_eval = metrics.get("pending_signals", 0) + metrics.get("evaluated_signals", 0)
    gates.append(gate_check("pending_or_evaluated_signals", pending_or_eval, ">=", ev.get("min_pending_or_evaluated_signals"), pending_or_eval >= ev.get("min_pending_or_evaluated_signals", 10**9)))
    ge("distinct_candidate_ids", "min_distinct_candidate_ids", ev)
    ge("forward_span_days", "min_forward_span_days", ev)
    ge("evaluated_span_days", "min_evaluated_span_days", ev)

    minimum_passed = all(g["passed"] for g in gates)

    quality_start = len(gates)
    ge("evaluated_mean_stress_bps", "min_evaluated_mean_stress_bps", qg)
    ge("evaluated_win_rate", "min_evaluated_win_rate", qg)
    ge("evaluated_median_stress_bps", "min_median_stress_bps", qg)
    le("backfill_signals", "max_backfill_signals", qg)
    le("max_candidate_share", "max_candidate_share", qg)
    le("max_day_share", "max_day_share", qg)
    le("pending_share", "max_pending_share", qg)
    le("negative_candidate_mean_count", "max_allowed_negative_candidate_mean_count", qg)
    quality_passed = all(g["passed"] for g in gates[quality_start:])

    if not minimum_passed:
        decision = labels.get("not_enough_evidence", "WAIT_FOR_TRUE_FORWARD_EVIDENCE_NO_PROMOTION")
        next_step = "CONTINUE_TRUE_FORWARD_SHADOW_UNTIL_MIN_EVIDENCE_NO_PROMOTION"
    elif not quality_passed:
        decision = labels.get("enough_but_failed", "CONTINUE_OR_REVIEW_FORWARD_SHADOW_NO_PROMOTION")
        next_step = "CONTINUE_OR_ARCHIVE_FORWARD_SHADOW_NO_PROMOTION"
    else:
        decision = labels.get("passed", "PAPER_ORDER_SIMULATION_DESIGN_ALLOWED_NO_PROMOTION")
        next_step = "PAPER_ORDER_SIMULATION_DRY_DESIGN_NO_PROMOTION"
    failed = [g["gate"] for g in gates if not g["passed"]]
    return gates, decision, next_step, failed


def build_paper_order_preview(cfg: Dict[str, Any], decision: str) -> Dict[str, Any]:
    preview = dict(cfg.get("paper_order_preview", {}))
    preview.update({
        "status": "SKELETON_ONLY_NO_ORDERS",
        "allowed_to_run_paper_order_simulation": decision == cfg.get("decision_labels", {}).get("passed", "PAPER_ORDER_SIMULATION_DESIGN_ALLOWED_NO_PROMOTION"),
        "hard_blockers": ["NO_EA", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION", "NO_ORDER_SUBMISSION"],
        "notes": "This is a preparation skeleton only. It never places orders and it is not paper-live.",
    })
    return preview


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fields})


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    metrics = summary.get("metrics", {})
    lines: List[str] = []
    lines.append("# Stage53 Forward-Shadow Gates and Paper-Order Preparation")
    lines.append("")
    lines.append(f"- status: `{summary.get('status')}`")
    lines.append(f"- decision: `{summary.get('decision')}`")
    lines.append(f"- next_allowed_step: `{summary.get('next_allowed_step')}`")
    lines.append("- promotion: `NO_GO`")
    lines.append("- EA: `NO_GO`")
    lines.append("- paper_live: `NO_GO`")
    lines.append("- live: `NO_GO`")
    lines.append("")
    lines.append("## Evidence state")
    lines.append("")
    for k in [
        "true_forward_signals", "pending_signals", "evaluated_signals", "backfill_signals",
        "evaluated_mean_stress_bps", "evaluated_median_stress_bps", "evaluated_win_rate",
        "distinct_candidate_ids", "forward_span_days", "evaluated_span_days", "max_candidate_share", "max_day_share"
    ]:
        lines.append(f"- {k}: `{metrics.get(k)}`")
    lines.append("")
    lines.append("## Gate failures")
    lines.append("")
    if summary.get("failed_gates"):
        for g in summary.get("failed_gates", []):
            lines.append(f"- `{g}`")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("This stage only decides whether Stage52 true-forward evidence is sufficient to design a dry paper-order simulator. It does not authorize EA, paper-live, live trading, or promotion.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage53 forward-shadow gate report and paper-order prep")
    ap.add_argument("--root", default=".")
    ap.add_argument("--state-db", default="data/shadow/stage52_forward_shadow.sqlite")
    ap.add_argument("--stage52-summary", default="reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_summary.json")
    ap.add_argument("--runner-summary", default="reports/stage52_forward_shadow/stage52_import_then_forward_shadow_summary.json")
    ap.add_argument("--gates", default="configs/stage53_forward_shadow_gates.json")
    ap.add_argument("--out", default="reports/stage53_forward_shadow_prep")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    state_db = (root / args.state_db).resolve() if not Path(args.state_db).is_absolute() else Path(args.state_db).resolve()
    stage52_summary_path = (root / args.stage52_summary).resolve() if not Path(args.stage52_summary).is_absolute() else Path(args.stage52_summary).resolve()
    runner_summary_path = (root / args.runner_summary).resolve() if not Path(args.runner_summary).is_absolute() else Path(args.runner_summary).resolve()
    gates_path = (root / args.gates).resolve() if not Path(args.gates).is_absolute() else Path(args.gates).resolve()

    cfg = read_json(gates_path)
    signals, state_meta = read_signals_from_state_db(state_db)
    metrics = summarize_signals(signals)
    gates, decision, next_step, failed = evaluate_gates(metrics, cfg)
    paper_preview = build_paper_order_preview(cfg, decision)

    summary = {
        "stage": STAGE,
        "status": STATUS,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "state_db": str(state_db),
        "stage52_summary": read_json(stage52_summary_path),
        "runner_summary": read_json(runner_summary_path),
        "state_meta": state_meta,
        "metrics": metrics,
        "gates": gates,
        "failed_gates": failed,
        "paper_order_preview": paper_preview,
        "generated_utc": utc_now_iso(),
    }

    (out / "stage53_forward_shadow_gate_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out / "stage53_forward_shadow_gate_report.md", summary)
    write_csv(out / "stage53_forward_shadow_gate_checks.csv", gates, ["gate", "observed", "operator", "threshold", "passed"])
    (out / "stage53_paper_order_skeleton.json").write_text(json.dumps(paper_preview, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"stage": STAGE, "status": STATUS, "decision": decision, "failed_gates": failed, "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
