#!/usr/bin/env python3
"""Stage68E policy robustness split audit.

Diagnostic-only audit. Reads Stage68D selected-cluster entries and evaluates
static policy robustness across chronological periods and yearly splits.
No order, broker, EA, paper-live, or live path is authorized.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE68E",
    "NO_THRESHOLD_TUNING_FROM_ROBUSTNESS_AUDIT",
    "NO_PROMOTION_FROM_ROBUSTNESS_AUDIT_ONLY",
]

DEFAULT_PERIODS = [
    {"label": "P1_2011_2014", "start_year": 2011, "end_year": 2014},
    {"label": "P2_2015_2018", "start_year": 2015, "end_year": 2018},
    {"label": "P3_2019_2022", "start_year": 2019, "end_year": 2022},
    {"label": "P4_2023_2026", "start_year": 2023, "end_year": 2026},
]


def _float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, 4)


def _metrics(df: pd.DataFrame, value_col: str = "selected_net_return_bps") -> Dict[str, Any]:
    if df.empty:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
            "worst_3_entry_sum_bps": None,
        }
    vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if vals.empty:
        return {
            "entry_count": int(len(df)),
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
            "worst_3_entry_sum_bps": None,
        }
    ordered = df.copy()
    if "selected_entry_date" in ordered.columns:
        ordered = ordered.sort_values("selected_entry_date")
    seq = pd.to_numeric(ordered[value_col], errors="coerce").dropna().tolist()
    if len(seq) >= 3:
        worst3 = min(sum(seq[i:i+3]) for i in range(len(seq)-2))
    elif seq:
        worst3 = sum(seq)
    else:
        worst3 = None
    return {
        "entry_count": int(len(vals)),
        "mean_net_return_bps": _float_or_none(vals.mean()),
        "median_net_return_bps": _float_or_none(vals.median()),
        "win_rate": _float_or_none((vals > 0).mean()),
        "min_net_return_bps": _float_or_none(vals.min()),
        "max_net_return_bps": _float_or_none(vals.max()),
        "total_net_return_bps": _float_or_none(vals.sum()),
        "worst_3_entry_sum_bps": _float_or_none(worst3),
    }


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_md(summary: Dict[str, Any], out_path: Path) -> None:
    lines: List[str] = []
    lines.append("# Stage68E Policy Robustness Split Audit")
    lines.append("")
    lines.append("## Decision")
    for k in ["status", "decision", "classification", "robustness_posture", "selected_robustness_candidate"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Input")
    inp = summary.get("input", {})
    for k, v in inp.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Candidate policy")
    cand = summary.get("candidate_policy_result", {})
    for k, v in cand.items():
        if isinstance(v, (dict, list)):
            continue
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Robust policy ranking")
    for row in summary.get("robust_policy_ranking", [])[:10]:
        lines.append(
            f"- `{row.get('policy_id')}`: mean=`{row.get('mean_net_return_bps')}`, "
            f"win=`{row.get('win_rate')}`, positive_period_share=`{row.get('positive_period_share')}`, "
            f"positive_year_share=`{row.get('positive_year_share')}`, total=`{row.get('total_net_return_bps')}`"
        )
    lines.append("")
    lines.append("## Issues")
    issues = summary.get("issues") or []
    if issues:
        for issue in issues:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for block in summary.get("hard_blocks", []):
        lines.append(f"- `{block}`")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/stage68e_policy_robustness_split_audit.json")
    parser.add_argument("--out", default="reports/stage68e_policy_robustness_split_audit")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = _safe_read_json(config_path)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    entries_path = Path(config.get("selected_cluster_entries_csv", "reports/stage68d_cluster_return_selection_policy/stage68d_selected_cluster_entries.csv"))
    if not entries_path.is_absolute():
        entries_path = root / entries_path

    candidate_policy = config.get("candidate_policy", "QUALITY_FIRST_EXCLUDE_D1")
    diagnostic_prefix = config.get("diagnostic_policy_prefix", "ORACLE")
    periods = config.get("periods", DEFAULT_PERIODS)
    constraints = config.get("constraints", {})
    min_entries = int(constraints.get("min_entry_count", 20))
    min_mean = float(constraints.get("min_mean_net_return_bps", 150.0))
    min_win = float(constraints.get("min_win_rate", 0.55))
    min_positive_period_share = float(constraints.get("min_positive_period_share", 0.50))
    min_positive_year_share = float(constraints.get("min_positive_year_share", 0.50))
    max_abs_worst_loss = float(constraints.get("max_abs_worst_3_entry_sum_bps", 3500.0))
    max_recent_total_share = float(constraints.get("max_recent_period_share_of_total_return", 0.80))

    issues: List[str] = []
    if not entries_path.exists():
        summary = {
            "stage": "Stage68E_POLICY_ROBUSTNESS_SPLIT_AUDIT",
            "root": str(root),
            "config": str(config_path),
            "status": "STAGE68E_STOP_INPUT_MISSING_NO_PROMOTION",
            "decision": "STAGE68E_STOP_SELECTED_CLUSTER_ENTRIES_MISSING_NO_ORDER",
            "classification": "S68E_STOP_INPUT_MISSING",
            "issues": [f"MISSING_SELECTED_CLUSTER_ENTRIES:{entries_path}"],
            "hard_blocks": HARD_BLOCKS,
        }
        (out_dir / "stage68e_policy_robustness_split_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        _write_md(summary, out_dir / "stage68e_policy_robustness_split_audit_report.md")
        print(json.dumps({"stage": summary["stage"], "status": summary["status"], "decision": summary["decision"]}, indent=2))
        return 2

    df = pd.read_csv(entries_path)
    required = {"policy_id", "selected_entry_date", "selected_net_return_bps"}
    missing = sorted(required - set(df.columns))
    if missing:
        summary = {
            "stage": "Stage68E_POLICY_ROBUSTNESS_SPLIT_AUDIT",
            "root": str(root),
            "config": str(config_path),
            "status": "STAGE68E_STOP_SCHEMA_MISMATCH_NO_PROMOTION",
            "decision": "STAGE68E_STOP_SELECTED_ENTRIES_SCHEMA_MISMATCH_NO_ORDER",
            "classification": "S68E_STOP_SCHEMA",
            "issues": [f"MISSING_COLUMNS:{','.join(missing)}"],
            "hard_blocks": HARD_BLOCKS,
        }
        (out_dir / "stage68e_policy_robustness_split_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        _write_md(summary, out_dir / "stage68e_policy_robustness_split_audit_report.md")
        print(json.dumps({"stage": summary["stage"], "status": summary["status"], "decision": summary["decision"]}, indent=2))
        return 2

    df["selected_entry_date"] = pd.to_datetime(df["selected_entry_date"], errors="coerce")
    df["selected_net_return_bps"] = pd.to_numeric(df["selected_net_return_bps"], errors="coerce")
    df = df.dropna(subset=["selected_entry_date", "selected_net_return_bps"]).copy()
    df["year"] = df["selected_entry_date"].dt.year

    policy_ids = sorted([p for p in df["policy_id"].dropna().unique().tolist() if not str(p).startswith(diagnostic_prefix)])

    overall_rows: List[Dict[str, Any]] = []
    period_rows: List[Dict[str, Any]] = []
    year_rows: List[Dict[str, Any]] = []
    robustness_rows: List[Dict[str, Any]] = []

    for policy_id in policy_ids:
        pdf = df[df["policy_id"] == policy_id].sort_values("selected_entry_date")
        overall = _metrics(pdf)
        overall["policy_id"] = policy_id
        overall_rows.append(overall)

        positive_periods = 0
        total_periods_with_entries = 0
        recent_period_total = None
        for period in periods:
            label = period["label"]
            start_year = int(period["start_year"])
            end_year = int(period["end_year"])
            sub = pdf[(pdf["year"] >= start_year) & (pdf["year"] <= end_year)]
            met = _metrics(sub)
            met.update({"policy_id": policy_id, "period": label, "start_year": start_year, "end_year": end_year})
            period_rows.append(met)
            if met["entry_count"] > 0:
                total_periods_with_entries += 1
                if (met["mean_net_return_bps"] or 0) > 0:
                    positive_periods += 1
            if period == periods[-1]:
                recent_period_total = met.get("total_net_return_bps") or 0.0

        years = sorted(pdf["year"].unique().tolist())
        pos_years = 0
        years_with_entries = 0
        for year in years:
            sub = pdf[pdf["year"] == year]
            met = _metrics(sub)
            met.update({"policy_id": policy_id, "year": int(year)})
            year_rows.append(met)
            if met["entry_count"] > 0:
                years_with_entries += 1
                if (met["mean_net_return_bps"] or 0) > 0:
                    pos_years += 1

        positive_period_share = positive_periods / total_periods_with_entries if total_periods_with_entries else 0.0
        positive_year_share = pos_years / years_with_entries if years_with_entries else 0.0
        total_net = overall.get("total_net_return_bps") or 0.0
        recent_share = None
        if total_net > 0:
            recent_share = (recent_period_total or 0.0) / total_net

        worst3 = overall.get("worst_3_entry_sum_bps")
        passes = (
            overall.get("entry_count", 0) >= min_entries
            and (overall.get("mean_net_return_bps") or -1e9) >= min_mean
            and (overall.get("win_rate") or 0.0) >= min_win
            and positive_period_share >= min_positive_period_share
            and positive_year_share >= min_positive_year_share
            and (worst3 is not None and worst3 >= -max_abs_worst_loss)
            and (recent_share is None or recent_share <= max_recent_total_share)
        )
        robustness_rows.append({
            "policy_id": policy_id,
            "entry_count": overall.get("entry_count"),
            "mean_net_return_bps": overall.get("mean_net_return_bps"),
            "median_net_return_bps": overall.get("median_net_return_bps"),
            "win_rate": overall.get("win_rate"),
            "total_net_return_bps": overall.get("total_net_return_bps"),
            "worst_3_entry_sum_bps": overall.get("worst_3_entry_sum_bps"),
            "positive_period_count": positive_periods,
            "period_count_with_entries": total_periods_with_entries,
            "positive_period_share": round(positive_period_share, 4),
            "positive_year_count": pos_years,
            "year_count_with_entries": years_with_entries,
            "positive_year_share": round(positive_year_share, 4),
            "recent_period_total_net_return_bps": _float_or_none(recent_period_total),
            "recent_period_share_of_total_return": _float_or_none(recent_share),
            "passes_robustness_constraints": bool(passes),
        })

    overall_df = pd.DataFrame(overall_rows).sort_values(["mean_net_return_bps", "win_rate"], ascending=[False, False])
    period_df = pd.DataFrame(period_rows)
    year_df = pd.DataFrame(year_rows)
    robustness_df = pd.DataFrame(robustness_rows)
    robust_rank = robustness_df.sort_values(
        ["passes_robustness_constraints", "positive_period_share", "positive_year_share", "mean_net_return_bps", "total_net_return_bps"],
        ascending=[False, False, False, False, False],
    )

    selected_robustness_candidate = robust_rank.iloc[0]["policy_id"] if not robust_rank.empty else None
    cand_row = robustness_df[robustness_df["policy_id"] == candidate_policy]
    candidate_result = cand_row.iloc[0].to_dict() if not cand_row.empty else {"policy_id": candidate_policy, "missing": True}

    candidate_passes = bool(candidate_result.get("passes_robustness_constraints")) if candidate_result else False
    candidate_recent_share = candidate_result.get("recent_period_share_of_total_return") if candidate_result else None
    if not candidate_passes:
        posture = "CANDIDATE_POLICY_REQUIRES_CAUTION_BEFORE_READINESS"
        issues.append("SELECTED_STAGE68D_POLICY_FAILS_OR_DOES_NOT_CLEAR_ROBUSTNESS_CONSTRAINTS")
    elif candidate_recent_share is not None and candidate_recent_share > max_recent_total_share:
        posture = "CANDIDATE_POLICY_RECENT_DOMINATED_REQUIRES_CAUTION"
        issues.append("SELECTED_STAGE68D_POLICY_RECENT_RETURN_CONCENTRATION_HIGH")
    else:
        posture = "CANDIDATE_POLICY_PASSES_FIRST_ROBUSTNESS_SPLITS_NO_PROMOTION"

    if selected_robustness_candidate and selected_robustness_candidate != candidate_policy:
        issues.append(f"ROBUSTNESS_TOP_POLICY_DIFFERS_FROM_STAGE68D_CANDIDATE:{selected_robustness_candidate}")

    # Save artifacts.
    overall_df.to_csv(out_dir / "stage68e_policy_overall_metrics.csv", index=False)
    period_df.to_csv(out_dir / "stage68e_policy_period_metrics.csv", index=False)
    year_df.to_csv(out_dir / "stage68e_policy_yearly_metrics.csv", index=False)
    robust_rank.to_csv(out_dir / "stage68e_policy_robustness_ranking.csv", index=False)

    summary = {
        "stage": "Stage68E_POLICY_ROBUSTNESS_SPLIT_AUDIT",
        "root": str(root),
        "config": str(config_path),
        "status": "STAGE68E_COMPLETE_NO_PROMOTION",
        "decision": "STAGE68E_POLICY_ROBUSTNESS_SPLIT_AUDIT_COMPLETE_NO_ORDER",
        "classification": "S68E_ROBUSTNESS_SPLIT_AUDIT_COMPLETE",
        "robustness_posture": posture,
        "input": {
            "selected_cluster_entries_csv": str(entries_path),
            "row_count": int(len(df)),
            "policy_count_excluding_diagnostic": int(len(policy_ids)),
            "candidate_policy_from_stage68d": candidate_policy,
        },
        "constraints": {
            "min_entry_count": min_entries,
            "min_mean_net_return_bps": min_mean,
            "min_win_rate": min_win,
            "min_positive_period_share": min_positive_period_share,
            "min_positive_year_share": min_positive_year_share,
            "max_abs_worst_3_entry_sum_bps": max_abs_worst_loss,
            "max_recent_period_share_of_total_return": max_recent_total_share,
        },
        "candidate_policy_result": candidate_result,
        "selected_robustness_candidate": selected_robustness_candidate,
        "robust_policy_ranking": robust_rank.to_dict(orient="records"),
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage68E is diagnostic only and cannot authorize orders.",
            "Do not tune thresholds from this audit alone.",
            "A static cluster policy still requires forward no-order observation before any readiness integration.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage68e_policy_robustness_split_audit_summary.json"),
            "report_md": str(out_dir / "stage68e_policy_robustness_split_audit_report.md"),
            "overall_csv": str(out_dir / "stage68e_policy_overall_metrics.csv"),
            "period_csv": str(out_dir / "stage68e_policy_period_metrics.csv"),
            "yearly_csv": str(out_dir / "stage68e_policy_yearly_metrics.csv"),
            "ranking_csv": str(out_dir / "stage68e_policy_robustness_ranking.csv"),
        },
    }

    (out_dir / "stage68e_policy_robustness_split_audit_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _write_md(summary, out_dir / "stage68e_policy_robustness_split_audit_report.md")
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "robustness_posture": summary["robustness_posture"],
        "selected_robustness_candidate": summary["selected_robustness_candidate"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
