#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List


STAGE = "Stage64E_REDUCED_SCOPE_P0_PLUS_VIX_PREDECLARATION_NO_PROMOTION"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def find_cfg_path(root: Path, cfg: Dict[str, Any], key: str) -> Path:
    raw = cfg.get(key, "")
    if not raw:
        return root / "__missing__"
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    cfg = read_json(config_path)

    d5_summary_path = find_cfg_path(root, cfg, "stage64d5_summary")
    d4_summary_path = find_cfg_path(root, cfg, "stage64d4_summary")
    fetch_summary_path = find_cfg_path(root, cfg, "local_fetch_summary")

    d5 = read_json(d5_summary_path)
    d4 = read_json(d4_summary_path)
    fetch = read_json(fetch_summary_path)

    reduced_scope_id = cfg.get("reduced_scope_id", "P0_PLUS_VIX_NO_ETF_NO_CENTRAL_BANK_NO_EVENT_CALENDAR")
    reduced_features = cfg.get("reduced_scope_manifest_ids", [
        "SRC_GOLD_D1_OHLC_2011_PRESENT",
        "SRC_DXY_D1_2011_PRESENT",
        "SRC_REAL_YIELD_OR_PROXY_2011_PRESENT",
        "SRC_VIX_OR_VOL_PROXY_2011_PRESENT",
    ])

    # Build readiness map from D4 checks.
    checks = d4.get("checks", [])
    by_manifest = {c.get("manifest_id"): c for c in checks if c.get("manifest_id")}

    scope_rows: List[Dict[str, Any]] = []
    missing_or_failed = []
    for mid in reduced_features:
        c = by_manifest.get(mid, {})
        ok = bool(c.get("preflight_ok"))
        if not ok:
            missing_or_failed.append(mid)
        scope_rows.append({
            "manifest_id": mid,
            "priority": c.get("priority", ""),
            "target_file": c.get("target_file", ""),
            "source": c.get("source", ""),
            "row_count": c.get("row_count", ""),
            "first_time_utc": c.get("first_time_utc", ""),
            "last_time_utc": c.get("last_time_utc", ""),
            "preflight_ok": ok,
            "role_in_reduced_scope": {
                "SRC_GOLD_D1_OHLC_2011_PRESENT": "gold_proxy_trend_and_realized_volatility_base",
                "SRC_DXY_D1_2011_PRESENT": "usd_pressure_trend_and_acceleration",
                "SRC_REAL_YIELD_OR_PROXY_2011_PRESENT": "opportunity_cost_pressure",
                "SRC_VIX_OR_VOL_PROXY_2011_PRESENT": "cross_asset_volatility_risk_regime",
            }.get(mid, "reduced_scope_feature"),
            "lag_policy": {
                "SRC_GOLD_D1_OHLC_2011_PRESENT": "bar_close_or_next_session_available_after_utc",
                "SRC_DXY_D1_2011_PRESENT": "next_utc_day_unless_exact_provider_timestamp",
                "SRC_REAL_YIELD_OR_PROXY_2011_PRESENT": "next_session_after_publication_or_provider_availability",
                "SRC_VIX_OR_VOL_PROXY_2011_PRESENT": "next_utc_day_unless_exact_provider_timestamp",
            }.get(mid, "explicit_available_after_utc_required"),
        })

    full_scope_blockers = d5.get("scope_readiness", {}).get("full_scope_blockers", [])
    source_warnings = list(d5.get("source_warnings", []))

    reduced_ready = not missing_or_failed and bool(d5.get("scope_readiness", {}).get("p0_plus_vix_ready", False))
    predeclared = reduced_ready

    validation_protocol = {
        "design_mode": "predeclared_reduced_scope_feasibility_only",
        "not_full_macro_thesis": True,
        "excluded_features": [
            "gold_etf_holdings_or_flows",
            "central_bank_gold_demand_regime",
            "historical_event_calendar_risk",
        ],
        "exclusion_reason": "Stage64D5 showed full scope remains blocked by empty/missing P1/P2 source files.",
        "allowed_next_work": [
            "lag_safe_feature_dataset_preflight",
            "regime_label_construction_audit",
            "walk_forward_validation_specification",
        ],
        "blocked_work": [
            "historical_validation_scan_without_feature_dataset_preflight",
            "order_generation",
            "EA_promotion",
            "paper_order",
            "paper_live",
            "live",
            "claiming_full_macro_regime_thesis_validation",
        ],
        "minimum_splits_to_preserve": [
            "2011_2015",
            "2016_2019",
            "2020_2022",
            "2023_present",
        ],
        "required_before_any_validation": [
            "Stage64F lag-safe feature dataset builder/preflight",
            "Stage64G walk-forward validation design with fixed hypotheses",
            "explicit cost/slippage assumption for D1/H4 execution only if later reached",
        ],
        "scope_warning": "This is a feasibility proxy scope, not a commercialization path and not a full macro-regime validation.",
    }

    summary = {
        "stage": STAGE,
        "status": "REDUCED_SCOPE_PREDECLARATION_COMPLETE_NO_PROMOTION" if predeclared else "REDUCED_SCOPE_PREDECLARATION_BLOCKED_NO_PROMOTION",
        "decision": "PREDECLARE_REDUCED_SCOPE_P0_PLUS_VIX_FEASIBILITY_NO_VALIDATION_NO_ORDER" if predeclared else "BLOCK_REDUCED_SCOPE_PREDECLARATION_UNTIL_D5_READY",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64d5_summary": str(d5_summary_path),
            "stage64d4_summary": str(d4_summary_path),
            "local_fetch_summary": str(fetch_summary_path),
        },
        "reduced_scope": {
            "scope_id": reduced_scope_id,
            "predeclared": predeclared,
            "ready_from_stage64d5": bool(d5.get("scope_readiness", {}).get("p0_plus_vix_ready", False)),
            "manifest_ids": reduced_features,
            "feature_count": len(reduced_features),
            "failed_or_missing_manifest_ids": missing_or_failed,
            "source_warnings": source_warnings,
        },
        "full_scope": {
            "still_blocked": True,
            "blockers": full_scope_blockers,
        },
        "validation_protocol": validation_protocol,
        "next_allowed_step": "Stage64F_REDUCED_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION",
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_HISTORICAL_VALIDATION_SCAN_IN_STAGE64E",
            "NO_FULL_SCOPE_VALIDATION_CLAIM",
            "NO_REDUCED_SCOPE_VALIDATION_WITHOUT_STAGE64F_AND_STAGE64G",
        ],
    }

    write_json(out / "stage64e_reduced_scope_predeclaration_summary.json", summary)
    write_csv(
        out / "stage64e_reduced_scope_feature_contract.csv",
        scope_rows,
        [
            "manifest_id",
            "priority",
            "target_file",
            "source",
            "row_count",
            "first_time_utc",
            "last_time_utc",
            "preflight_ok",
            "role_in_reduced_scope",
            "lag_policy",
        ],
    )
    write_json(out / "stage64e_reduced_scope_feature_contract.json", {"rows": scope_rows})
    write_json(out / "stage64e_reduced_scope_validation_protocol.json", validation_protocol)

    report = out / "stage64e_reduced_scope_predeclaration_report.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Stage64E - Reduced-Scope P0+VIX Predeclaration\n\n")
        f.write(f"Generated UTC: `{summary['generated_utc']}`\n\n")
        f.write("## Status\n\n")
        f.write(f"- status: `{summary['status']}`\n")
        f.write(f"- decision: `{summary['decision']}`\n")
        f.write("- validation_allowed: `false`\n")
        f.write("- promotion/paper/live: `NO_GO`\n\n")

        f.write("## Executive conclusion\n\n")
        if predeclared:
            f.write(
                "Stage64D5 showed that P0 plus VIX source files are ready while full scope remains blocked. "
                "This stage predeclares a reduced-scope feasibility path using gold proxy OHLC, DXY, real yield, and VIX only. "
                "It does not validate the thesis and it does not authorize any order path.\n\n"
            )
        else:
            f.write(
                "Reduced-scope predeclaration is blocked because not all selected scope files passed readiness checks.\n\n"
            )

        f.write("## Reduced scope\n\n")
        f.write(f"- scope_id: `{reduced_scope_id}`\n")
        f.write(f"- feature_count: `{len(reduced_features)}`\n")
        f.write("- excluded: `ETF flows`, `central-bank gold demand`, `historical event calendar`\n")
        f.write("- status: feasibility/proxy scope only; not full macro-regime thesis validation\n\n")

        if source_warnings:
            f.write("## Source warnings\n\n")
            for w in source_warnings:
                f.write(f"- {w}\n")
            f.write("\n")

        f.write("## Feature contract\n\n")
        f.write("| manifest_id | preflight_ok | rows | first | last | source | role |\n")
        f.write("|---|---:|---:|---|---|---|---|\n")
        for r in scope_rows:
            f.write(
                f"| `{r['manifest_id']}` | {r['preflight_ok']} | {r['row_count']} | "
                f"{r['first_time_utc']} | {r['last_time_utc']} | `{r['source']}` | {r['role_in_reduced_scope']} |\n"
            )
        f.write("\n")

        f.write("## Full-scope blockers retained\n\n")
        if full_scope_blockers:
            for b in full_scope_blockers:
                f.write(f"- `{b.get('manifest_id')}`: {b.get('issues')}\n")
        else:
            f.write("- none reported\n")
        f.write("\n")

        f.write("## Validation discipline\n\n")
        f.write("- Stage64E does not run validation.\n")
        f.write("- Stage64E does not authorize paper-order, paper-live, live, EA promotion, or broker connection.\n")
        f.write("- The reduced scope must not be marketed as full macro-regime validation.\n")
        f.write("- Next step is Stage64F lag-safe feature dataset preflight, followed by Stage64G validation design before any validation scan.\n\n")

        f.write("## Next allowed step\n\n")
        f.write("`Stage64F_REDUCED_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION`\n")

    return 0 if predeclared else 2


if __name__ == "__main__":
    raise SystemExit(main())
