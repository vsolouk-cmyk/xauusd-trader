#!/usr/bin/env python3
"""Stage64C Macro-Regime Gold Thesis Specification.

Report-only stage. It defines the Daily/Weekly Macro-Regime Gold System specification,
including thesis, regimes, feature contract, lag policy, and validation framework.
It does not mutate data/state and does not authorize trading.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def md_table(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    out = []
    out.append("| " + " | ".join(fieldnames) + " |")
    out.append("|" + "|".join(["---" for _ in fieldnames]) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(row.get(k, "")).replace("\n", " ") for k in fieldnames) + " |")
    return "\n".join(out)


def build_summary(root: Path, config_path: Path, out: Path, cfg: Dict[str, Any], generated_utc: str) -> Dict[str, Any]:
    feature_contract = cfg["feature_contract"]
    regimes = cfg["regime_definitions"]
    validation = cfg["validation_framework"]

    return {
        "stage": cfg.get("stage", "Stage64C_MACRO_REGIME_GOLD_THESIS_SPEC_NO_PROMOTION"),
        "status": "MACRO_REGIME_THESIS_SPEC_COMPLETE_NO_PROMOTION",
        "decision": "START_DAILY_WEEKLY_MACRO_REGIME_GOLD_SYSTEM_NO_ORDER",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "mutation_mode": cfg.get("mutation_mode", "report_only_no_state_mutation"),
        "generated_utc": generated_utc,
        "root": str(root),
        "config": str(config_path),
        "out": str(out),
        "thesis": cfg["thesis"],
        "counts": {
            "regime_definitions": len(regimes),
            "feature_contract_rows": len(feature_contract),
            "validation_splits": len(validation.get("minimum_splits", [])),
            "stress_periods_required": len(validation.get("stress_periods_required", [])),
        },
        "central_bank_demand_policy": {
            "role": "slow_regime_prior",
            "not_allowed_as": "direct_timing_signal",
            "lookahead_policy": "official_release_lag_must_be_respected",
        },
        "validation_framework": validation,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_INTRADAY_RESCUE_FILTERING",
        ],
        "next_allowed_step": cfg.get("next_stage", "Stage64D_MACRO_REGIME_DATA_CONTRACT_AND_LOADER_AUDIT"),
        "outputs": {
            "summary_json": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_gold_thesis_spec_summary.json",
            "report_md": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_gold_thesis_spec_report.md",
            "feature_contract_csv": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_feature_contract.csv",
            "feature_contract_json": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_feature_contract.json",
            "regime_definitions_csv": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_definitions.csv",
            "regime_definitions_json": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_definitions.json",
            "validation_framework_json": "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_validation_framework.json",
        },
    }


def build_report(summary: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    thesis = cfg["thesis"]
    regimes = cfg["regime_definitions"]
    features = cfg["feature_contract"]
    validation = cfg["validation_framework"]

    feature_fields = ["feature_id", "source_type", "timeframe", "role", "minimum_history", "lag_policy"]
    regime_fields = ["regime_id", "description", "expected_behavior", "default_bias"]

    lines = [
        "# Stage64C - Daily/Weekly Macro-Regime Gold Thesis Specification",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        "## Status",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        "- promotion: `NO_GO`",
        "- paper_order: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        f"- mutation_mode: `{summary['mutation_mode']}`",
        "",
        "## Executive specification",
        "",
        f"Thesis name: `{thesis['name']}`",
        "",
        thesis["core_statement"],
        "",
        "This stage formally pivots the active program away from candidate-first intraday research. Intraday artifacts remain reference-only. Stage58B can continue as passive independent telemetry and corrected statistical reference, but it is not the commercialization path.",
        "",
        "## Central-bank demand policy",
        "",
        "Central-bank demand is a slow regime prior. It is not a timing signal. It may condition the background probability of persistent gold demand, but entries must be validated through daily/weekly market features and explicit lag rules. Any central-bank demand data must respect publication lag and must not be joined as if it were known at the event date.",
        "",
        "## Regime definitions",
        "",
        md_table(regimes, regime_fields),
        "",
        "## Data and feature contract",
        "",
        md_table(features, feature_fields),
        "",
        "## Lag policy",
        "",
        "- OHLC-derived D1/W1 features: use completed bar only.",
        "- Macro/rate data: use only after publication availability; no same-period lookahead join.",
        "- ETF flows/holdings: use next-session or later availability unless source timestamp proves earlier availability.",
        "- Central-bank demand: monthly/quarterly release lag must be explicit; use only as prior/regime label, not as entry timing.",
        "- Event calendar: only events known before the event can be used as risk filters; realized surprise is not allowed in pre-event features.",
        "",
        "## Validation framework",
        "",
        f"- design_mode: `{validation['design_mode']}`",
        f"- initial_validation_units: `{', '.join(validation['initial_validation_units'])}`",
        f"- minimum_splits: `{', '.join(validation['minimum_splits'])}`",
        f"- stress_periods_required: `{', '.join(validation['stress_periods_required'])}`",
        f"- required_outputs_before_forward: `{', '.join(validation['required_outputs_before_forward'])}`",
        f"- blocked_until_passed: `{', '.join(validation['blocked_until_passed'])}`",
        "",
        "## Kill and promotion discipline",
        "",
        "No paper-order, paper-live, live, or EA promotion is authorized by this specification. The next stage must audit data availability, source lag, join feasibility, and historical regime coverage before any validation scan is allowed.",
        "",
        "## Next allowed step",
        "",
        f"`{summary['next_allowed_step']}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_json(config_path)
    generated = utc_now()
    summary = build_summary(root, config_path, out, cfg, generated)

    feature_contract = cfg["feature_contract"]
    regimes = cfg["regime_definitions"]
    validation = cfg["validation_framework"]

    write_csv(out / "stage64c_macro_regime_feature_contract.csv", feature_contract,
              ["feature_id", "source_type", "timeframe", "role", "minimum_history", "lag_policy"])
    write_json(out / "stage64c_macro_regime_feature_contract.json", {"features": feature_contract})
    write_csv(out / "stage64c_macro_regime_definitions.csv", regimes,
              ["regime_id", "description", "expected_behavior", "default_bias"])
    write_json(out / "stage64c_macro_regime_definitions.json", {"regimes": regimes})
    write_json(out / "stage64c_macro_regime_validation_framework.json", validation)
    write_json(out / "stage64c_macro_regime_gold_thesis_spec_summary.json", summary)

    report = build_report(summary, cfg)
    (out / "stage64c_macro_regime_gold_thesis_spec_report.md").write_text(report, encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "promotion": summary["promotion"],
        "paper_order": summary["paper_order"],
        "live": summary["live"],
        "next_allowed_step": summary["next_allowed_step"],
        "out": str(out),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
