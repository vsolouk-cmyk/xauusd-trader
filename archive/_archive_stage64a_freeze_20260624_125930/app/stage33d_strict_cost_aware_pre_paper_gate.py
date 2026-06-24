"""
XAUUSD Stage33D — Strict Cost-Aware Pre-Paper Gate

Purpose:
    Stress-test the repaired h13+h14 handoff family from Stage33C before any
    pre-paper planning. This is a research-only gate. It does not authorize EA,
    paper-live, or order routing.

Inputs:
    data/reports/stage33c_handoff_repaired_family_gate/stage33c_summary.json
    data/reports/stage33c_handoff_repaired_family_gate/repaired_family_diagnostics.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_member_split_summary.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_cost_sensitivity_summary.csv
    data/reports/stage33c_handoff_repaired_family_gate/repaired_tail_batch_summary.csv

Outputs:
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/stage33d_strict_cost_aware_pre_paper_gate.md
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/stage33d_summary.json
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/gate_checks.csv
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/prepaper_candidate_snapshot.csv
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/recent_degradation_diagnostics.csv
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/cost_guard_summary.csv
    data/reports/stage33d_strict_cost_aware_pre_paper_gate/next_action_plan.csv

No EA, paper-live, or order authorization is produced by this stage.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

DEFAULT_STAGE33C_DIR = Path("data/reports/stage33c_handoff_repaired_family_gate")
DEFAULT_OUT_DIR = Path("data/reports/stage33d_strict_cost_aware_pre_paper_gate")


@dataclass
class Thresholds:
    # Do not lower these casually: this stage decides whether a family is worth
    # pre-paper research planning. It still does NOT authorize paper/live/orders.
    min_effective_events: int = 24
    min_good_members: int = 2
    max_weak_members: int = 0
    min_family_pf_x4: float = 1.75
    min_family_win_rate_x4: float = 0.65
    min_family_avg_net_x4: float = 0.75
    min_family_tail_pf_x4: float = 1.25
    max_family_drawdown_x4: float = -25.0
    min_cost_1_pf_x4: float = 1.25
    min_cost_1_avg_net_x4: float = 0.25
    min_cost_1_win_rate_x4: float = 0.58
    min_last_batch_pf_x4: float = 1.0
    min_last_batch_avg_net_x4: float = 0.0
    min_last_batch_win_rate_x4: float = 0.55
    min_last_batch_signal_count: int = 5
    max_recent_degradation_ratio: float = 0.65  # last_batch_pf / prior_batch_median_pf must be >= this


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def fnum(value: Any, default: float = math.nan) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}:
            return default
        return float(value)
    except Exception:
        return default


def inum(value: Any, default: int = 0) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return int(float(value))
    except Exception:
        return default


def finite_for_json(value: Any) -> Any:
    try:
        if isinstance(value, float):
            if math.isnan(value):
                return None
            if math.isinf(value):
                return "inf" if value > 0 else "-inf"
        return value
    except Exception:
        return value


def gate_row(name: str, value: Any, threshold: str, passed: bool, severity: str, implication: str) -> Dict[str, Any]:
    return {
        "gate": name,
        "value": value,
        "threshold": threshold,
        "passed": bool(passed),
        "severity": severity,
        "implication": implication,
    }


def md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No rows."
    show = df.copy()
    for col in show.columns:
        if pd.api.types.is_float_dtype(show[col]):
            def fmt(x: Any) -> Any:
                if pd.isna(x):
                    return ""
                try:
                    xf = float(x)
                    if math.isinf(xf):
                        return "inf" if xf > 0 else "-inf"
                    return round(xf, 6)
                except Exception:
                    return x
            show[col] = show[col].map(fmt)
    return show.to_markdown(index=False)


def derive_prior_median_tail_pf(tail_df: pd.DataFrame) -> Dict[str, Any]:
    if tail_df.empty or "pf_x4" not in tail_df.columns:
        return {
            "last_batch_pf_x4": math.nan,
            "prior_batch_median_pf_x4": math.nan,
            "recent_degradation_ratio": math.nan,
            "last_batch_signal_count": 0,
            "last_batch_avg_net_x4": math.nan,
            "last_batch_win_rate_x4": math.nan,
            "last_batch_start_ts": None,
            "last_batch_end_ts": None,
        }
    t = tail_df.copy()
    t["pf_x4"] = pd.to_numeric(t["pf_x4"], errors="coerce")
    t["avg_net_x4"] = pd.to_numeric(t.get("avg_net_x4"), errors="coerce") if "avg_net_x4" in t.columns else math.nan
    t["win_rate_x4"] = pd.to_numeric(t.get("win_rate_x4"), errors="coerce") if "win_rate_x4" in t.columns else math.nan
    t["signal_count"] = pd.to_numeric(t.get("signal_count"), errors="coerce") if "signal_count" in t.columns else 0
    last = t.iloc[-1].to_dict()
    prior = t.iloc[:-1]
    prior_pf = pd.to_numeric(prior["pf_x4"], errors="coerce").replace([math.inf, -math.inf], pd.NA).dropna()
    prior_median = float(prior_pf.median()) if len(prior_pf) else math.nan
    last_pf = fnum(last.get("pf_x4"))
    ratio = last_pf / prior_median if prior_median and not math.isnan(prior_median) and prior_median > 0 and not math.isnan(last_pf) else math.nan
    return {
        "last_batch_pf_x4": last_pf,
        "prior_batch_median_pf_x4": prior_median,
        "recent_degradation_ratio": ratio,
        "last_batch_signal_count": inum(last.get("signal_count")),
        "last_batch_avg_net_x4": fnum(last.get("avg_net_x4")),
        "last_batch_win_rate_x4": fnum(last.get("win_rate_x4")),
        "last_batch_start_ts": last.get("start_ts"),
        "last_batch_end_ts": last.get("end_ts"),
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    th = Thresholds(
        min_effective_events=args.min_effective_events,
        min_family_pf_x4=args.min_family_pf_x4,
        min_cost_1_pf_x4=args.min_cost_1_pf_x4,
        min_last_batch_pf_x4=args.min_last_batch_pf_x4,
    )
    stage33c_dir = Path(args.stage33c_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_c = read_json(stage33c_dir / "stage33c_summary.json")
    diag_df = read_csv(stage33c_dir / "repaired_family_diagnostics.csv")
    member_df = read_csv(stage33c_dir / "repaired_member_split_summary.csv")
    cost_df = read_csv(stage33c_dir / "repaired_cost_sensitivity_summary.csv")
    tail_df = read_csv(stage33c_dir / "repaired_tail_batch_summary.csv")

    c_decision = str(summary_c.get("decision", ""))
    stage33c_passed = c_decision == "STAGE33C_REPAIRED_FAMILY_PRE_PAPER_RESEARCH_CANDIDATE_ONLY"

    # Prefer explicit Stage33C summary values; fall back to diagnostics CSV.
    diag_row = diag_df.iloc[0].to_dict() if not diag_df.empty else {}
    effective_event_count = inum(summary_c.get("effective_event_count", diag_row.get("effective_event_count")))
    good_member_count = inum(summary_c.get("good_member_count", diag_row.get("good_member_count")))
    weak_member_count = inum(summary_c.get("weak_member_count", diag_row.get("weak_member_count")))
    family_pf_x4 = fnum(summary_c.get("family_pf_x4", diag_row.get("family_pf_x4")))
    family_win_rate_x4 = fnum(summary_c.get("family_win_rate_x4", diag_row.get("family_win_rate_x4")))
    family_avg_net_x4 = fnum(diag_row.get("family_avg_net_x4"), fnum(summary_c.get("family_avg_net_x4")))
    family_tail_pf_x4 = fnum(summary_c.get("family_tail_pf_x4", diag_row.get("family_tail_pf_x4")))
    family_max_drawdown_x4 = fnum(summary_c.get("family_max_drawdown_x4", diag_row.get("family_max_drawdown_x4")))

    cost_1_row = {}
    if not cost_df.empty and "cost_penalty_x4" in cost_df.columns:
        tmp = cost_df[pd.to_numeric(cost_df["cost_penalty_x4"], errors="coerce") == 1.0]
        if not tmp.empty:
            cost_1_row = tmp.iloc[0].to_dict()
    cost_1_pf_x4 = fnum(summary_c.get("cost_1_pf_x4", cost_1_row.get("pf_x4")))
    cost_1_avg_net_x4 = fnum(cost_1_row.get("avg_net_x4"), fnum(summary_c.get("cost_1_avg_net_x4")))
    cost_1_win_rate_x4 = fnum(cost_1_row.get("win_rate_x4"), fnum(summary_c.get("cost_1_win_rate_x4")))

    recent = derive_prior_median_tail_pf(tail_df)
    last_batch_pf_x4 = fnum(summary_c.get("last_batch_pf_x4", recent.get("last_batch_pf_x4")))
    last_batch_avg_net_x4 = fnum(recent.get("last_batch_avg_net_x4"))
    last_batch_win_rate_x4 = fnum(recent.get("last_batch_win_rate_x4"))
    last_batch_signal_count = inum(recent.get("last_batch_signal_count"))
    recent_ratio = fnum(recent.get("recent_degradation_ratio"))

    checks: List[Dict[str, Any]] = []
    checks.append(gate_row("stage33c_repaired_candidate", c_decision, "Stage33C must promote repaired family", stage33c_passed, "fatal", "Do not continue if Stage33C did not pass."))
    checks.append(gate_row("effective_event_count", effective_event_count, f">= {th.min_effective_events}", effective_event_count >= th.min_effective_events, "fatal", "Sample count must be enough for a pre-paper research gate."))
    checks.append(gate_row("member_quality", f"good={good_member_count}, weak={weak_member_count}", f"good >= {th.min_good_members}, weak <= {th.max_weak_members}", good_member_count >= th.min_good_members and weak_member_count <= th.max_weak_members, "fatal", "Both h13 and h14 must remain good; no weak sibling allowed."))
    checks.append(gate_row("core_pf", family_pf_x4, f">= {th.min_family_pf_x4}", family_pf_x4 >= th.min_family_pf_x4, "fatal", "Core PF must be strong before any pre-paper planning."))
    checks.append(gate_row("core_win_rate", family_win_rate_x4, f">= {th.min_family_win_rate_x4}", family_win_rate_x4 >= th.min_family_win_rate_x4, "fatal", "Win-rate must remain robust."))
    checks.append(gate_row("core_avg_net", family_avg_net_x4, f">= {th.min_family_avg_net_x4}", family_avg_net_x4 >= th.min_family_avg_net_x4, "fatal", "Average net must remain positive after conservative filtering."))
    checks.append(gate_row("family_tail_pf", family_tail_pf_x4, f">= {th.min_family_tail_pf_x4}", family_tail_pf_x4 >= th.min_family_tail_pf_x4, "fatal", "Overall tail window must be robust."))
    checks.append(gate_row("drawdown_guard", family_max_drawdown_x4, f">= {th.max_family_drawdown_x4}", family_max_drawdown_x4 >= th.max_family_drawdown_x4, "fatal", "Family drawdown proxy must not be too deep."))
    checks.append(gate_row("cost_1_pf", cost_1_pf_x4, f">= {th.min_cost_1_pf_x4}", cost_1_pf_x4 >= th.min_cost_1_pf_x4, "fatal", "Family must survive a severe cost/slippage stress."))
    checks.append(gate_row("cost_1_avg", cost_1_avg_net_x4, f">= {th.min_cost_1_avg_net_x4}", cost_1_avg_net_x4 >= th.min_cost_1_avg_net_x4, "fatal", "Cost-stressed average net must stay positive."))
    checks.append(gate_row("cost_1_win_rate", cost_1_win_rate_x4, f">= {th.min_cost_1_win_rate_x4}", cost_1_win_rate_x4 >= th.min_cost_1_win_rate_x4, "warning", "Cost-stressed win rate should not collapse."))
    checks.append(gate_row("last_batch_pf", last_batch_pf_x4, f">= {th.min_last_batch_pf_x4}", last_batch_pf_x4 >= th.min_last_batch_pf_x4, "fatal", "Most recent batch cannot be losing before pre-paper planning."))
    checks.append(gate_row("last_batch_avg", last_batch_avg_net_x4, f">= {th.min_last_batch_avg_net_x4}", last_batch_avg_net_x4 >= th.min_last_batch_avg_net_x4, "fatal", "Most recent batch average must not be negative."))
    checks.append(gate_row("last_batch_win_rate", last_batch_win_rate_x4, f">= {th.min_last_batch_win_rate_x4}", last_batch_win_rate_x4 >= th.min_last_batch_win_rate_x4, "warning", "Most recent batch win rate should be adequate."))
    checks.append(gate_row("last_batch_sample_count", last_batch_signal_count, f">= {th.min_last_batch_signal_count}", last_batch_signal_count >= th.min_last_batch_signal_count, "warning", "Latest batch should be large enough to interpret."))
    checks.append(gate_row("recent_degradation_ratio", recent_ratio, f">= {th.max_recent_degradation_ratio}", (not math.isnan(recent_ratio)) and recent_ratio >= th.max_recent_degradation_ratio, "fatal", "Do not promote if recent PF collapsed versus earlier batches."))

    gate_df = pd.DataFrame(checks)
    fatal_failures = gate_df[(gate_df["severity"] == "fatal") & (~gate_df["passed"])]
    warning_failures = gate_df[(gate_df["severity"] == "warning") & (~gate_df["passed"])]

    if not stage33c_passed:
        decision = "STAGE33D_BLOCKED_STAGE33C_NOT_PASSED_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE33C_OR_STAGE32B_REPAIR"
    elif fatal_failures.empty:
        decision = "STAGE33D_STRICT_COST_AWARE_PRE_PAPER_RESEARCH_READY_NO_EXECUTION"
        next_stage = "RUN_STAGE33E_PRE_PAPER_DESIGN_WITH_NO_ORDER_AUTHORIZATION"
    elif set(fatal_failures["gate"]).intersection({"last_batch_pf", "last_batch_avg", "recent_degradation_ratio"}) and len(fatal_failures) <= 3:
        decision = "STAGE33D_BLOCKED_RECENT_DEGRADATION_SHORT_SHADOW_RESEARCH_ONLY"
        next_stage = "COLLECT_SHORT_CONFIRMATION_BATCH_OR_ADD_RECENCY_FILTER_NO_EA_NO_PAPER_LIVE"
    else:
        decision = "STAGE33D_REPAIR_OR_KILL_RESEARCH_ONLY"
        next_stage = "RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_REPAIR"

    snapshot = pd.DataFrame([
        {
            "sibling_group": "session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065",
            "included_candidates": ";".join(summary_c.get("included_candidates", [])) if isinstance(summary_c.get("included_candidates"), list) else summary_c.get("included_candidates"),
            "effective_event_count": effective_event_count,
            "family_pf_x4": family_pf_x4,
            "family_avg_net_x4": family_avg_net_x4,
            "family_win_rate_x4": family_win_rate_x4,
            "family_tail_pf_x4": family_tail_pf_x4,
            "family_max_drawdown_x4": family_max_drawdown_x4,
            "cost_1_pf_x4": cost_1_pf_x4,
            "cost_1_avg_net_x4": cost_1_avg_net_x4,
            "cost_1_win_rate_x4": cost_1_win_rate_x4,
            "last_batch_pf_x4": last_batch_pf_x4,
            "last_batch_avg_net_x4": last_batch_avg_net_x4,
            "last_batch_win_rate_x4": last_batch_win_rate_x4,
            "recent_degradation_ratio": recent_ratio,
            "fatal_failure_count": int(len(fatal_failures)),
            "warning_failure_count": int(len(warning_failures)),
            "stage33d_decision": decision,
            "next_stage": next_stage,
            "commercial_status": "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER",
        }
    ])

    recent_df = pd.DataFrame([{**recent, "sibling_group": "session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065"}])
    cost_guard = pd.DataFrame([
        {
            "cost_penalty_x4": 1.0,
            "pf_x4": cost_1_pf_x4,
            "avg_net_x4": cost_1_avg_net_x4,
            "win_rate_x4": cost_1_win_rate_x4,
            "passes_cost_guard": bool(cost_1_pf_x4 >= th.min_cost_1_pf_x4 and cost_1_avg_net_x4 >= th.min_cost_1_avg_net_x4),
        }
    ])
    if decision == "STAGE33D_STRICT_COST_AWARE_PRE_PAPER_RESEARCH_READY_NO_EXECUTION":
        action = "PREPARE_PRE_PAPER_RESEARCH_DESIGN_WITH_ZERO_ORDER_ROUTING"
        rationale = "All strict gates passed. Still no EA/paper-live/order authorization."
    elif decision == "STAGE33D_BLOCKED_RECENT_DEGRADATION_SHORT_SHADOW_RESEARCH_ONLY":
        action = "KEEP_H13_H14_AS_SHORT_CONFIRMATION_SHADOW_AND_TEST_RECENCY_FILTER"
        rationale = "Core/cost metrics are strong, but the latest batch is weak; do not promote to paper planning yet."
    else:
        action = "REPAIR_OR_KILL_AND_RETURN_TO_INTAKE_EXPANSION"
        rationale = "Strict pre-paper research gate failed beyond acceptable recency-only weakness."
    action_df = pd.DataFrame([{"action": action, "rationale": rationale, "next_stage": next_stage}])

    gate_df.to_csv(out_dir / "gate_checks.csv", index=False)
    snapshot.to_csv(out_dir / "prepaper_candidate_snapshot.csv", index=False)
    recent_df.to_csv(out_dir / "recent_degradation_diagnostics.csv", index=False)
    cost_guard.to_csv(out_dir / "cost_guard_summary.csv", index=False)
    action_df.to_csv(out_dir / "next_action_plan.csv", index=False)

    summary = {
        "generated_utc": now_utc(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "STRICT_COST_AWARE_PRE_PAPER_GATE_TO_PROTECT_COMMERCIAL_FAST_PATH",
        "recommended_next_stage": next_stage,
        "stage33c_decision": c_decision,
        "effective_event_count": effective_event_count,
        "good_member_count": good_member_count,
        "weak_member_count": weak_member_count,
        "family_pf_x4": family_pf_x4,
        "family_avg_net_x4": family_avg_net_x4,
        "family_win_rate_x4": family_win_rate_x4,
        "family_tail_pf_x4": family_tail_pf_x4,
        "family_max_drawdown_x4": family_max_drawdown_x4,
        "cost_1_pf_x4": cost_1_pf_x4,
        "cost_1_avg_net_x4": cost_1_avg_net_x4,
        "cost_1_win_rate_x4": cost_1_win_rate_x4,
        "last_batch_pf_x4": last_batch_pf_x4,
        "last_batch_avg_net_x4": last_batch_avg_net_x4,
        "last_batch_win_rate_x4": last_batch_win_rate_x4,
        "recent_degradation_ratio": recent_ratio,
        "fatal_failure_count": int(len(fatal_failures)),
        "warning_failure_count": int(len(warning_failures)),
        "fatal_failed_gates": fatal_failures["gate"].tolist(),
        "warning_failed_gates": warning_failures["gate"].tolist(),
        "thresholds": asdict(th),
    }
    (out_dir / "stage33d_summary.json").write_text(json.dumps(summary, indent=2, default=finite_for_json))

    md = f"""# XAUUSD Stage33D — Strict Cost-Aware Pre-Paper Gate

Generated UTC: {summary['generated_utc']}

## Decision

```text
DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = STRICT_COST_AWARE_PRE_PAPER_GATE_TO_PROTECT_COMMERCIAL_FAST_PATH
RECOMMENDED_NEXT_STAGE = {next_stage}
```

## Why this stage exists

Stage33C repaired the handoff family by excluding h15 and keeping h13+h14 only. Stage33D is stricter: it blocks premature pre-paper planning if the repaired family has recent degradation, fails cost stress, or shows unacceptable drawdown. This stage still does not authorize EA, paper-live, or orders.

## Summary

```text
stage33c_decision = {summary['stage33c_decision']}
effective_event_count = {effective_event_count}
good_member_count = {good_member_count}
weak_member_count = {weak_member_count}
family_pf_x4 = {round(family_pf_x4, 6) if not math.isnan(family_pf_x4) else 'nan'}
family_avg_net_x4 = {round(family_avg_net_x4, 6) if not math.isnan(family_avg_net_x4) else 'nan'}
family_win_rate_x4 = {round(family_win_rate_x4, 6) if not math.isnan(family_win_rate_x4) else 'nan'}
family_tail_pf_x4 = {round(family_tail_pf_x4, 6) if not math.isnan(family_tail_pf_x4) else 'nan'}
family_max_drawdown_x4 = {round(family_max_drawdown_x4, 6) if not math.isnan(family_max_drawdown_x4) else 'nan'}
cost_1_pf_x4 = {round(cost_1_pf_x4, 6) if not math.isnan(cost_1_pf_x4) else 'nan'}
last_batch_pf_x4 = {round(last_batch_pf_x4, 6) if not math.isnan(last_batch_pf_x4) else 'nan'}
last_batch_avg_net_x4 = {round(last_batch_avg_net_x4, 6) if not math.isnan(last_batch_avg_net_x4) else 'nan'}
recent_degradation_ratio = {round(recent_ratio, 6) if not math.isnan(recent_ratio) else 'nan'}
fatal_failed_gates = {', '.join(summary['fatal_failed_gates']) if summary['fatal_failed_gates'] else 'none'}
warning_failed_gates = {', '.join(summary['warning_failed_gates']) if summary['warning_failed_gates'] else 'none'}
```

## Pre-paper candidate snapshot

{md_table(snapshot)}

## Gate checks

{md_table(gate_df)}

## Recent degradation diagnostics

{md_table(recent_df)}

## Cost guard summary

{md_table(cost_guard)}

## Next action plan

{md_table(action_df)}

## Operational interpretation

```text
1. Passing Stage33C is not enough for paper planning.
2. Stage33D blocks if the most recent batch has degraded, even when aggregate PF/WR look strong.
3. A pass here still only permits pre-paper research design, not EA/paper-live/orders.
4. Stage32F remains background collection; Stage33D protects the commercial fast path from premature promotion.
```

## Output files

- `{out_dir / 'stage33d_strict_cost_aware_pre_paper_gate.md'}`
- `{out_dir / 'stage33d_summary.json'}`
- `{out_dir / 'gate_checks.csv'}`
- `{out_dir / 'prepaper_candidate_snapshot.csv'}`
- `{out_dir / 'recent_degradation_diagnostics.csv'}`
- `{out_dir / 'cost_guard_summary.csv'}`
- `{out_dir / 'next_action_plan.csv'}`
"""
    (out_dir / "stage33d_strict_cost_aware_pre_paper_gate.md").write_text(md)
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={next_stage}")
    print(f"REPORT={out_dir / 'stage33d_strict_cost_aware_pre_paper_gate.md'}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage33D strict cost-aware pre-paper gate")
    parser.add_argument("--stage33c-dir", default=str(DEFAULT_STAGE33C_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--min-effective-events", type=int, default=24)
    parser.add_argument("--min-family-pf-x4", type=float, default=1.75)
    parser.add_argument("--min-cost-1-pf-x4", type=float, default=1.25)
    parser.add_argument("--min-last-batch-pf-x4", type=float, default=1.0)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
