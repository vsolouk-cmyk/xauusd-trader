#!/usr/bin/env python3
"""Stage59 context-forward gate report.

Reads Stage58B true-forward state and applies explicit gates before any paper-order
simulator design is allowed. This script never places orders and never connects to
a broker.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage59_CONTEXT_FORWARD_GATES_NO_PROMOTION"
STATUS = "CONTEXT_FORWARD_GATE_REPORT_COMPLETE_NO_PROMOTION"
NO_GO = "NO_GO"

DEFAULT_CONFIG = {
    "min_true_forward_signals": 100,
    "min_evaluated_signals": 60,
    "min_pending_or_evaluated_signals": 100,
    "min_distinct_candidate_ids": 2,
    "min_forward_span_days": 10.0,
    "min_evaluated_span_days": 5.0,
    "min_evaluated_mean_stress_bps": 2.0,
    "min_evaluated_median_stress_bps": 0.0,
    "min_evaluated_win_rate": 0.53,
    "max_backfill_signals": 0,
    "max_candidate_share": 0.65,
    "max_day_share": 0.35,
    "max_pending_share": 0.85,
    "max_negative_candidate_mean_count": 1,
    "paper_order_preview": {
        "starting_balance_usd": 1000.0,
        "risk_per_signal_pct": 0.10,
        "max_daily_orders": 3,
        "max_concurrent_orders": 2,
        "max_notional_usd": 1000.0,
        "order_type": "SIMULATED_MARKET_WITH_SPREAD_AND_STRESS_COST_ONLY",
        "kill_switch": {
            "max_daily_loss_bps": -60.0,
            "max_rolling_20_signal_loss_bps": -120.0,
            "stop_if_spread_cost_bps_gt": 3.0380209087577326,
        },
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_utc(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        x = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if x.tzinfo is None:
        x = x.replace(tzinfo=dt.timezone.utc)
    return x.astimezone(dt.timezone.utc)


def iso_z(x: Optional[dt.datetime]) -> Optional[str]:
    if x is None:
        return None
    return x.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def span_days(times: Iterable[Optional[str]]) -> float:
    parsed = [p for p in (parse_utc(t) for t in times) if p is not None]
    if len(parsed) < 2:
        return 0.0
    return (max(parsed) - min(parsed)).total_seconds() / 86400.0


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def load_candidates(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"path": str(path), "found": path.exists(), "rows": 0, "pass_rows": 0, "candidate_ids": [], "error": None}
    if not path.exists():
        return meta
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as exc:  # pragma: no cover
        meta["error"] = repr(exc)
        return meta
    pass_rows = []
    for row in rows:
        status = str(row.get("status", ""))
        cid = row.get("candidate_id") or row.get("id")
        if "PASS" in status and cid:
            pass_rows.append(row)
    meta["rows"] = len(rows)
    meta["pass_rows"] = len(pass_rows)
    meta["candidate_ids"] = [r.get("candidate_id") or r.get("id") for r in pass_rows if (r.get("candidate_id") or r.get("id"))]
    return meta


def inspect_state_db(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "found": path.exists(),
        "schema_ok": False,
        "tables": [],
        "signal_columns": [],
        "watermark_utc": None,
        "error": None,
    }
    if not path.exists():
        return meta, []
    try:
        con = sqlite3.connect(str(path))
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        meta["tables"] = tables
        if "signals" not in tables:
            meta["error"] = "missing signals table"
            con.close()
            return meta, []
        cols = [r[1] for r in con.execute("PRAGMA table_info(signals)")]
        meta["signal_columns"] = cols
        required = {"candidate_id", "entry_time_utc", "status", "stress_bps", "is_backfill"}
        meta["schema_ok"] = required.issubset(set(cols))
        if "kv" in tables:
            # support either key/value or k/v schemas
            kv_cols = [r[1] for r in con.execute("PRAGMA table_info(kv)")]
            key_col = "key" if "key" in kv_cols else ("k" if "k" in kv_cols else None)
            val_col = "value" if "value" in kv_cols else ("v" if "v" in kv_cols else None)
            if key_col and val_col:
                for row in con.execute(f"SELECT {key_col} AS k, {val_col} AS v FROM kv"):
                    if "watermark" in str(row["k"]).lower():
                        meta["watermark_utc"] = row["v"]
                        break
        rows = [dict(r) for r in con.execute("SELECT * FROM signals")]
        con.close()
        return meta, rows
    except Exception as exc:  # pragma: no cover
        meta["error"] = repr(exc)
        return meta, []


def compute_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    backfill_rows = [r for r in rows if int(r.get("is_backfill") or 0) == 1]
    true_rows = [r for r in rows if int(r.get("is_backfill") or 0) == 0]
    pending = [r for r in true_rows if str(r.get("status", "")).lower() == "pending"]
    evaluated = [r for r in true_rows if str(r.get("status", "")).lower() == "evaluated"]
    eval_stress = [safe_float(r.get("stress_bps")) for r in evaluated]
    eval_stress = [x for x in eval_stress if x is not None]
    eval_mean = sum(eval_stress) / len(eval_stress) if eval_stress else None
    eval_median = median(eval_stress) if eval_stress else None
    eval_wr = (sum(1 for x in eval_stress if x > 0) / len(eval_stress)) if eval_stress else None
    eval_total = sum(eval_stress) if eval_stress else None
    # cumulative max drawdown in bps in chronological order
    max_dd = None
    if evaluated:
        ev_sorted = sorted(evaluated, key=lambda r: str(r.get("entry_time_utc") or ""))
        equity = 0.0
        peak = 0.0
        worst = 0.0
        for r in ev_sorted:
            x = safe_float(r.get("stress_bps")) or 0.0
            equity += x
            peak = max(peak, equity)
            worst = min(worst, equity - peak)
        max_dd = worst
    candidate_counts = Counter(str(r.get("candidate_id") or "UNKNOWN") for r in true_rows)
    day_counts = Counter(str(r.get("entry_time_utc") or "")[:10] for r in true_rows if r.get("entry_time_utc"))
    max_candidate_share = (max(candidate_counts.values()) / len(true_rows)) if true_rows and candidate_counts else 0.0
    max_day_share = (max(day_counts.values()) / len(true_rows)) if true_rows and day_counts else 0.0
    pending_share = (len(pending) / len(true_rows)) if true_rows else 0.0
    cand_stress: Dict[str, List[float]] = defaultdict(list)
    for r in evaluated:
        x = safe_float(r.get("stress_bps"))
        if x is not None:
            cand_stress[str(r.get("candidate_id") or "UNKNOWN")].append(x)
    cand_mean = {k: sum(v) / len(v) for k, v in cand_stress.items() if v}
    neg_cand_mean = sum(1 for v in cand_mean.values() if v < 0)
    return {
        "total_state_rows": total,
        "backfill_signals": len(backfill_rows),
        "true_forward_signals": len(true_rows),
        "pending_signals": len(pending),
        "evaluated_signals": len(evaluated),
        "evaluated_mean_stress_bps": eval_mean,
        "evaluated_median_stress_bps": eval_median,
        "evaluated_win_rate": eval_wr,
        "evaluated_total_stress_bps": eval_total,
        "evaluated_max_drawdown_bps": max_dd,
        "distinct_candidate_ids": len(candidate_counts),
        "candidate_counts": dict(candidate_counts),
        "candidate_mean_stress_bps": cand_mean,
        "negative_candidate_mean_count": neg_cand_mean,
        "max_candidate_share": max_candidate_share,
        "max_day_share": max_day_share,
        "pending_share": pending_share,
        "forward_first_entry_utc": min((r.get("entry_time_utc") for r in true_rows if r.get("entry_time_utc")), default=None),
        "forward_last_entry_utc": max((r.get("entry_time_utc") for r in true_rows if r.get("entry_time_utc")), default=None),
        "forward_span_days": span_days(r.get("entry_time_utc") for r in true_rows),
        "evaluated_first_entry_utc": min((r.get("entry_time_utc") for r in evaluated if r.get("entry_time_utc")), default=None),
        "evaluated_last_entry_utc": max((r.get("entry_time_utc") for r in evaluated if r.get("entry_time_utc")), default=None),
        "evaluated_span_days": span_days(r.get("entry_time_utc") for r in evaluated),
    }


def gate_row(name: str, observed: Any, op: str, threshold: Any, passed: bool) -> Dict[str, Any]:
    return {"gate": name, "observed": observed, "operator": op, "threshold": threshold, "passed": bool(passed)}


def apply_gates(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    g = []
    g.append(gate_row("true_forward_signals", metrics["true_forward_signals"], ">=", cfg["min_true_forward_signals"], metrics["true_forward_signals"] >= cfg["min_true_forward_signals"]))
    g.append(gate_row("evaluated_signals", metrics["evaluated_signals"], ">=", cfg["min_evaluated_signals"], metrics["evaluated_signals"] >= cfg["min_evaluated_signals"]))
    pe = metrics["pending_signals"] + metrics["evaluated_signals"]
    g.append(gate_row("pending_or_evaluated_signals", pe, ">=", cfg["min_pending_or_evaluated_signals"], pe >= cfg["min_pending_or_evaluated_signals"]))
    g.append(gate_row("distinct_candidate_ids", metrics["distinct_candidate_ids"], ">=", cfg["min_distinct_candidate_ids"], metrics["distinct_candidate_ids"] >= cfg["min_distinct_candidate_ids"]))
    g.append(gate_row("forward_span_days", metrics["forward_span_days"], ">=", cfg["min_forward_span_days"], metrics["forward_span_days"] >= cfg["min_forward_span_days"]))
    g.append(gate_row("evaluated_span_days", metrics["evaluated_span_days"], ">=", cfg["min_evaluated_span_days"], metrics["evaluated_span_days"] >= cfg["min_evaluated_span_days"]))
    mean_v = metrics["evaluated_mean_stress_bps"]
    med_v = metrics["evaluated_median_stress_bps"]
    wr_v = metrics["evaluated_win_rate"]
    g.append(gate_row("evaluated_mean_stress_bps", mean_v, ">=", cfg["min_evaluated_mean_stress_bps"], mean_v is not None and mean_v >= cfg["min_evaluated_mean_stress_bps"]))
    g.append(gate_row("evaluated_median_stress_bps", med_v, ">=", cfg["min_evaluated_median_stress_bps"], med_v is not None and med_v >= cfg["min_evaluated_median_stress_bps"]))
    g.append(gate_row("evaluated_win_rate", wr_v, ">=", cfg["min_evaluated_win_rate"], wr_v is not None and wr_v >= cfg["min_evaluated_win_rate"]))
    g.append(gate_row("backfill_signals", metrics["backfill_signals"], "<=", cfg["max_backfill_signals"], metrics["backfill_signals"] <= cfg["max_backfill_signals"]))
    g.append(gate_row("max_candidate_share", metrics["max_candidate_share"], "<=", cfg["max_candidate_share"], metrics["max_candidate_share"] <= cfg["max_candidate_share"]))
    g.append(gate_row("max_day_share", metrics["max_day_share"], "<=", cfg["max_day_share"], metrics["max_day_share"] <= cfg["max_day_share"]))
    g.append(gate_row("pending_share", metrics["pending_share"], "<=", cfg["max_pending_share"], metrics["pending_share"] <= cfg["max_pending_share"]))
    g.append(gate_row("negative_candidate_mean_count", metrics["negative_candidate_mean_count"], "<=", cfg["max_negative_candidate_mean_count"], metrics["negative_candidate_mean_count"] <= cfg["max_negative_candidate_mean_count"]))
    return g


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    metrics = summary["metrics"]
    failed = summary["failed_gates"]
    lines = [
        "# Stage59 Context-Forward Gate Report",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        f"- promotion: `{NO_GO}`",
        f"- EA: `{NO_GO}`",
        f"- paper_live: `{NO_GO}`",
        f"- live: `{NO_GO}`",
        "",
        "## Evidence state",
        "",
        f"- true_forward_signals: `{metrics['true_forward_signals']}`",
        f"- pending_signals: `{metrics['pending_signals']}`",
        f"- evaluated_signals: `{metrics['evaluated_signals']}`",
        f"- backfill_signals: `{metrics['backfill_signals']}`",
        f"- evaluated_mean_stress_bps: `{metrics['evaluated_mean_stress_bps']}`",
        f"- evaluated_median_stress_bps: `{metrics['evaluated_median_stress_bps']}`",
        f"- evaluated_win_rate: `{metrics['evaluated_win_rate']}`",
        f"- distinct_candidate_ids: `{metrics['distinct_candidate_ids']}`",
        f"- forward_span_days: `{metrics['forward_span_days']}`",
        f"- evaluated_span_days: `{metrics['evaluated_span_days']}`",
        f"- max_candidate_share: `{metrics['max_candidate_share']}`",
        f"- max_day_share: `{metrics['max_day_share']}`",
        "",
        "## Gate failures",
        "",
    ]
    if failed:
        for f in failed:
            lines.append(f"- `{f}`")
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Paper-order preview",
        "",
        f"- allowed_to_design_paper_order_simulation: `{summary['allowed_to_design_paper_order_simulation']}`",
        f"- orders_created: `0`",
        f"- broker_connection: `DISABLED`",
        "",
        "## Interpretation",
        "",
        "Stage59 only decides whether Stage58B true-forward context evidence is sufficient to design a dry paper-order simulator. It does not authorize EA, paper-live, live trading, or order submission.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--state-db", default="data/shadow/stage58b_context_forward_shadow.sqlite")
    ap.add_argument("--stage58b-summary", default="reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json")
    ap.add_argument("--stage58a-candidates", default="reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv")
    ap.add_argument("--gates", default="configs/stage59_context_forward_gates.json")
    ap.add_argument("--out", default="reports/stage59_context_forward_gates")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    state_db = (root / args.state_db).resolve() if not Path(args.state_db).is_absolute() else Path(args.state_db)
    stage58b_summary_path = (root / args.stage58b_summary).resolve() if not Path(args.stage58b_summary).is_absolute() else Path(args.stage58b_summary)
    candidates_path = (root / args.stage58a_candidates).resolve() if not Path(args.stage58a_candidates).is_absolute() else Path(args.stage58a_candidates)
    gates_path = (root / args.gates).resolve() if not Path(args.gates).is_absolute() else Path(args.gates)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = DEFAULT_CONFIG.copy()
    user_cfg = read_json(gates_path)
    cfg.update({k: v for k, v in user_cfg.items() if k in cfg})
    if "paper_order_preview" in user_cfg:
        cfg["paper_order_preview"] = user_cfg["paper_order_preview"]

    state_meta, rows = inspect_state_db(state_db)
    metrics = compute_metrics(rows)
    gates = apply_gates(metrics, cfg)
    failed_gates = [g["gate"] for g in gates if not g["passed"]]
    all_passed = not failed_gates and state_meta.get("schema_ok", False)
    if metrics["backfill_signals"] > 0:
        decision = "BLOCK_BACKFILL_CONTAMINATION_NO_PROMOTION"
        next_step = "RESET_OR_ARCHIVE_CONTEXT_FORWARD_STATE_NO_PROMOTION"
    elif all_passed:
        decision = "CONTEXT_FORWARD_GATES_PASS_DESIGN_DRY_PAPER_ORDER_SIM_NO_PROMOTION"
        next_step = "DESIGN_CONTEXT_DRY_PAPER_ORDER_SIMULATOR_NO_PROMOTION"
    else:
        decision = "WAIT_FOR_CONTEXT_TRUE_FORWARD_EVIDENCE_NO_PROMOTION"
        next_step = "CONTINUE_STAGE58B_CONTEXT_FORWARD_SHADOW_UNTIL_MIN_EVIDENCE_NO_PROMOTION"

    allowed_design = decision.startswith("CONTEXT_FORWARD_GATES_PASS")
    paper_preview = dict(cfg.get("paper_order_preview", {}))
    paper_preview.update({
        "status": "DESIGN_ALLOWED_NO_ORDERS" if allowed_design else "GATES_NOT_PASSED_NO_ORDERS",
        "allowed_to_design_paper_order_simulation": allowed_design,
        "orders_created": 0,
        "broker_connection": "DISABLED",
        "paper_live_connection": "DISABLED",
        "hard_blockers": ["NO_EA", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION", "NO_ORDER_SUBMISSION"],
    })

    summary = {
        "stage": STAGE,
        "status": STATUS,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "state_db": str(state_db),
        "stage58b_summary": read_json(stage58b_summary_path),
        "stage58a_candidates_meta": load_candidates(candidates_path),
        "state_meta": state_meta,
        "metrics": metrics,
        "gates": gates,
        "failed_gates": failed_gates,
        "paper_order_preview": paper_preview,
        "allowed_to_design_paper_order_simulation": allowed_design,
        "generated_utc": utc_now(),
    }

    summary_path = out_dir / "stage59_context_forward_gate_summary.json"
    report_path = out_dir / "stage59_context_forward_gate_report.md"
    checks_path = out_dir / "stage59_context_forward_gate_checks.csv"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(report_path, summary)
    write_csv(checks_path, gates)
    print(json.dumps({"stage": STAGE, "status": STATUS, "decision": decision, "failed_gates": failed_gates, "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
