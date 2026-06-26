#!/usr/bin/env python3
"""
Stage66G controlled paper-order readiness designer.
Design-only: no broker, no order, no EA promotion, no paper-live/live authorization.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66G",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_READINESS_DESIGN_ONLY",
]

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)

def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

def find_stress_mean(summary: Dict[str, Any], penalty_bps: float) -> Optional[float]:
    for row in summary.get("metrics", {}).get("stress_cost_stats", []):
        if as_float(row.get("round_trip_total_penalty_bps")) == float(penalty_bps):
            return as_float(row.get("mean_net_return_bps"))
    return None

def get_base_band_drawdown(summary: Dict[str, Any], base_band_name: str) -> Optional[float]:
    for row in summary.get("metrics", {}).get("sizing_band_stats", []):
        if row.get("band") == base_band_name:
            return abs(as_float(row.get("max_drawdown_pct"), 999.0) or 999.0)
    return None

def load_latest_signal_state(root: Path, stage65_summary_path: str) -> Dict[str, Any]:
    p = root / stage65_summary_path
    if not p.exists():
        return {"state_found": False, "signal_active": None, "reason": "stage65 summary not found"}
    try:
        s = load_json(p)
        state = s.get("stage65_run", {}).get("stage65_summary", {}).get("latest_signal_state")
        if state is None:
            state = s.get("latest_signal_state", {})
        return {
            "state_found": True,
            "signal_active": str(state.get("signal_active")).lower() == "true",
            "benchmark_active": str(state.get("benchmark_active")).lower() == "true",
            "feature_date_utc": state.get("feature_date_utc"),
            "rule_failures": state.get("rule_failures"),
            "hypothesis_id": state.get("hypothesis_id"),
            "sample_available_after_utc": state.get("sample_available_after_utc"),
        }
    except Exception as exc:
        return {"state_found": False, "signal_active": None, "reason": f"stage65 summary parse error: {exc}"}

def evaluate_stage66c(summary: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    t = cfg["thresholds"]
    allowed = set(cfg["allowed_stage66c_decisions"])
    decision = summary.get("decision")
    pos = summary.get("metrics", {}).get("position_stats", {})
    trade_count = as_int(pos.get("trade_count"))
    win_rate = as_float(pos.get("win_rate"), 0.0) or 0.0
    mean_net = as_float(pos.get("mean_net_return_bps"), 0.0) or 0.0
    min_net = as_float(pos.get("min_net_return_bps"), 0.0) or 0.0
    max_year_share = as_float(pos.get("max_year_trade_share"), 1.0) or 1.0
    base_dd = get_base_band_drawdown(summary, t["base_band_name"])
    stress_mean = find_stress_mean(summary, t["stress_gate_penalty_bps"])
    checks = {
        "stage66c_decision_allowed": decision in allowed,
        "trade_count_gate": trade_count >= int(t["min_closed_positions"]),
        "win_rate_gate": win_rate >= float(t["pass_fast_min_win_rate"]),
        "mean_net_bps_gate": mean_net >= float(t["pass_fast_min_mean_net_bps"]),
        "stress_mean_gate": stress_mean is not None and stress_mean >= float(t["pass_fast_min_stress_mean_net_bps"]),
        "base_band_drawdown_gate": base_dd is not None and base_dd <= float(t["pass_fast_max_base_band_drawdown_pct"]),
        "single_trade_loss_gate": min_net >= float(t["kill_if_single_trade_loss_bps_lt"]),
        "year_concentration_gate": max_year_share <= float(t["max_year_trade_share"]),
    }
    all_fast = all(checks.values())
    small = (decision in allowed and trade_count >= int(t["min_closed_positions"]) and
             win_rate >= float(t["small_size_min_win_rate"]) and
             mean_net >= float(t["small_size_min_mean_net_bps"]) and
             min_net >= float(t["kill_if_single_trade_loss_bps_lt"]))
    if all_fast:
        classification = "G_PASS_FAST_DESIGN_READY"
        decision_out = "CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER"
    elif small:
        classification = "G_PASS_SMALL_SIZE_ONLY"
        decision_out = "CONTROLLED_PAPER_ORDER_READINESS_SMALL_SIZE_ONLY_NO_ORDER"
    else:
        classification = "G_FAIL_OR_INSUFFICIENT"
        decision_out = "STOP_OR_STAGE66D_REQUIRED_NO_ORDER"
    return {"decision_out": decision_out, "classification": classification, "checks": checks,
            "metrics_used": {"stage66c_decision": decision, "trade_count": trade_count, "win_rate": win_rate,
            "mean_net_return_bps": mean_net, "min_net_return_bps": min_net,
            "base_band_abs_drawdown_pct": base_dd, "stress_mean_net_bps_at_gate_penalty": stress_mean,
            "max_year_trade_share": max_year_share}}

def build_readiness_design(cfg: Dict[str, Any], ev: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    sizing = cfg["paper_design"]["sizing"]
    gates = cfg["paper_design"]["operational_gates"]
    cls = ev["classification"]
    if cls == "G_PASS_FAST_DESIGN_READY":
        initial_band, max_band = "B_conservative", "B_base"
        initial_fraction, max_fraction = sizing["B_conservative"], sizing["B_base"]
    elif cls == "G_PASS_SMALL_SIZE_ONLY":
        initial_band, max_band = "A_micro", "B_conservative"
        initial_fraction, max_fraction = sizing["A_micro"], sizing["B_conservative"]
    else:
        initial_band, max_band, initial_fraction, max_fraction = "NONE", "NONE", 0.0, 0.0
    armed_now = bool(signal.get("signal_active")) and cls in {"G_PASS_FAST_DESIGN_READY", "G_PASS_SMALL_SIZE_ONLY"}
    return {
        "readiness_mode": "DESIGN_ONLY_NO_ORDER",
        "arming_status": "ARMED_DESIGN_ONLY_SIGNAL_ACTIVE" if armed_now else "NOT_ARMED_WAIT_FOR_VALID_FORWARD_SIGNAL",
        "armed_now": armed_now,
        "paper_order_is_authorized": False,
        "broker_connection_authorized": False,
        "ea_promotion_authorized": False,
        "live_or_paper_live_authorized": False,
        "initial_band": initial_band,
        "max_design_band_before_new_forward_evidence": max_band,
        "initial_notional_fraction": initial_fraction,
        "max_notional_fraction_before_new_forward_evidence": max_fraction,
        "required_before_any_future_paper_order_authorization": gates,
        "current_signal_state": signal,
        "operator_instructions": [
            "Do not place any order from this package.",
            "Use this output only as a readiness design and manual review checklist.",
            "A future paper-order authorization package must re-check a fresh H64L v2 active signal.",
            "No live path is allowed from Stage66G.",
        ],
    }

def render_report(summary: Dict[str, Any]) -> str:
    return "\n".join([
        "# Stage66G Controlled Paper-Order Readiness Design", "", "## Decision", "",
        f"- status: `{summary['status']}`", f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`", "", "## Key gate metrics", "", "```json",
        json.dumps(summary.get("stage66c_gate_evaluation", {}).get("metrics_used", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```", "", "## Gate checks", "", "```json",
        json.dumps(summary.get("stage66c_gate_evaluation", {}).get("checks", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```", "", "## Readiness design", "", "```json",
        json.dumps(summary.get("readiness_design", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```", "", "## Hard blocks", "", *[f"- `{b}`" for b in summary.get("hard_blocks", [])], ""])

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cfg_path = Path(args.config)
    cfg = load_json(cfg_path if cfg_path.is_absolute() else root / cfg_path)
    out = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out.mkdir(parents=True, exist_ok=True)
    stage66c_path = root / cfg["stage66c_summary_path"]
    if not stage66c_path.exists():
        summary = {"stage": "Stage66G_CONTROLLED_PAPER_ORDER_READINESS", "status": "STAGE66G_INPUT_FAIL_NO_ORDER",
                   "decision": "STOP_MISSING_STAGE66C_SUMMARY_NO_ORDER", "classification": "G_INPUT_FAIL",
                   "generated_utc": utc_now(), "root": str(root), "issues": [f"missing Stage66C summary: {stage66c_path}"],
                   "hard_blocks": HARD_BLOCKS, "stage66c_gate_evaluation": {"metrics_used": {}, "checks": {}}, "readiness_design": {}}
        write_json(out / "stage66g_controlled_paper_order_readiness_summary.json", summary)
        (out / "stage66g_controlled_paper_order_readiness_report.md").write_text(render_report(summary), encoding="utf-8")
        return 2
    stage66c = load_json(stage66c_path)
    ev = evaluate_stage66c(stage66c, cfg)
    signal = load_latest_signal_state(root, cfg.get("stage65_summary_path", "reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json"))
    readiness = build_readiness_design(cfg, ev, signal)
    summary = {"stage": "Stage66G_CONTROLLED_PAPER_ORDER_READINESS", "status": "STAGE66G_COMPLETE_NO_PROMOTION",
               "decision": ev["decision_out"], "classification": ev["classification"], "generated_utc": utc_now(),
               "root": str(root), "config": str(root / args.config), "input_paths": {"stage66c_summary_path": cfg["stage66c_summary_path"],
               "stage65_summary_path": cfg.get("stage65_summary_path"), "rule_lock_path": cfg.get("rule_lock_path")},
               "stage66c_gate_evaluation": ev, "readiness_design": readiness, "hard_blocks": HARD_BLOCKS,
               "next_step": "If Band B, build Stage66H no-broker paper-order dry-run ticket generator. Real paper order remains blocked until a fresh H64L v2 active signal and explicit user authorization."}
    write_json(out / "stage66g_controlled_paper_order_readiness_summary.json", summary)
    (out / "stage66g_controlled_paper_order_readiness_report.md").write_text(render_report(summary), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
