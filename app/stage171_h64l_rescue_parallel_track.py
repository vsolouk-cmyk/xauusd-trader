#!/usr/bin/env python3
"""Stage171 H64L Rescue Parallel Track.

Read-only strategic/operational bridge stage. It does not create MT5 signals,
does not authorize demo/live orders, and does not optimize thresholds.

Tracks:
- Track 1.5: 30-minute triage mapping H64L feature sources to Stage170C blockers.
- Track 1: timeboxed H64L as-of safety audit (max 3 business days by policy).
- Track 2: day-one manual shadow checklist/log scaffold, in parallel with audit.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage171_H64L_RESCUE_PARALLEL_TRACK"
DECISION = "STAGE171_PARALLEL_H64L_RESCUE_READY_NO_AUDIT_FIRST_BLOCK"
RECOMMENDED_ACTION = (
    "RUN_TRIAGE_AND_START_MANUAL_SHADOW_CHECKLIST_IN_PARALLEL; "
    "TIMEBOX_ASOF_AUDIT_TO_3_BUSINESS_DAYS; NO_THRESHOLD_REOPTIMIZATION"
)

H64L_FEATURES = [
    {
        "feature_id": "gold_trend_sma20_over_50",
        "source_match": ["AMARKETS_M5_BROKER_BARS", "AMARKETS_M1_M15_M30_H1_BROKER_BARS"],
        "required_policy": "completed-bar or prior-day daily bar only; no incomplete HTF bar",
        "risk": "same-bar / incomplete higher-timeframe leakage",
    },
    {
        "feature_id": "dxy_ret_20d",
        "source_match": ["FRED_MACRO_DAILY_PANEL", "DXY", "EXOGENOUS_DXY"],
        "required_policy": "use prior completed daily close or explicit available_time_utc",
        "risk": "daily close/timezone availability leakage",
    },
    {
        "feature_id": "real_yield_change_20d",
        "source_match": ["FRED_MACRO_DAILY_PANEL", "REAL_YIELD", "US_REAL_YIELD"],
        "required_policy": "vintage/as-of or conservative one-business-day embargo",
        "risk": "revision/publication-time lookahead",
    },
    {
        "feature_id": "etf_flow_tonnes_3m",
        "source_match": ["ETF_GLD_WGC_CENTRAL_BANK_GOLD", "GLD", "ETF", "WGC"],
        "required_policy": "explicit publication lag; use only data available before signal decision",
        "risk": "using calendar date instead of publication availability date",
    },
]

@dataclass
class FileInspection:
    path: str
    exists: bool
    size_bytes: Optional[int] = None
    note: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_csv_lenient(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    # Detect separator from first line.
    with path.open("r", encoding="utf-8", errors="replace") as f:
        first = f.readline()
    sep = ","
    if "\t" in first:
        sep = "\t"
    elif ";" in first:
        sep = ";"
    elif "|" in first:
        sep = "|"
    try:
        return pd.read_csv(path, sep=sep)
    except Exception:
        return pd.read_csv(path)


def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc), "_path": str(path)}


def inspect_file(path: Optional[Path]) -> FileInspection:
    if not path:
        return FileInspection(path="", exists=False, note="not provided")
    p = path.expanduser()
    return FileInspection(path=str(p), exists=p.exists(), size_bytes=p.stat().st_size if p.exists() else None)


def discover_h64l_artifacts(root: Path, extra_paths: Iterable[Path]) -> List[Dict[str, Any]]:
    candidates: List[Path] = []
    search_roots = [root / "reports", root / "docs", root / "app", root / "data"]
    for ep in extra_paths:
        if ep:
            search_roots.append(ep.expanduser())
    patterns = ["*H64L*", "*h64l*", "*stage64*", "*Stage64*", "*64R*", "*64r*"]
    seen = set()
    for sr in search_roots:
        if not sr.exists():
            continue
        for pat in patterns:
            for p in sr.rglob(pat):
                if p.is_file() and p not in seen:
                    seen.add(p)
                    candidates.append(p)
    out = []
    for p in sorted(candidates, key=lambda x: str(x))[:200]:
        text_sample = ""
        try:
            if p.suffix.lower() in {".md", ".txt", ".json", ".csv", ".py"}:
                text_sample = p.read_text(encoding="utf-8", errors="replace")[:3000]
        except Exception:
            pass
        hit_terms = []
        for term in ["H64L", "macro", "tailwind", "dxy", "real", "yield", "etf", "GLD", "z"]:
            if term.lower() in text_sample.lower() or term.lower() in p.name.lower():
                hit_terms.append(term)
        out.append({
            "path": str(p),
            "size_bytes": p.stat().st_size,
            "suffix": p.suffix,
            "hit_terms": ";".join(hit_terms),
            "sample_mentions_h64l": "H64L" in text_sample or "h64l" in text_sample.lower(),
        })
    return out


def extract_h64l_clues(artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
    clues: Dict[str, Any] = {
        "found_artifact_count": len(artifacts),
        "candidate_paths": [a["path"] for a in artifacts[:25]],
        "exact_rule_locked": False,
        "confidence": "LOW_UNTIL_STAGE64R_RAW_ARTIFACT_REVIEWED",
        "rule_conditions_from_expert_feedback": [
            "gold_sma20_over_50 > 0",
            "dxy_ret_20d < 0",
            "real_yield_change_20d < 0",
            "etf_flow_tonnes_3m > 0",
        ],
        "do_not_optimize": True,
    }
    if artifacts:
        clues["confidence"] = "MEDIUM_PENDING_EXACT_RULE_EXTRACTION"
    return clues


def map_features_to_contract(contract_csv: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    df = read_csv_lenient(contract_csv.expanduser()) if contract_csv else pd.DataFrame()
    if df.empty:
        for feat in H64L_FEATURES:
            rows.append({
                "feature_id": feat["feature_id"],
                "matched_contract_source_id": "MISSING_CONTRACT",
                "historical_asof_status": "UNKNOWN",
                "blocking_issue": "contract file missing or empty",
                "triage_verdict": "BLOCKING_UNTIL_CONTRACT_ROW_IDENTIFIED",
                "required_policy": feat["required_policy"],
                "risk": feat["risk"],
            })
        return rows, {"contract_loaded": False, "blocking_h64l_features": len(rows)}

    cols = {c.lower(): c for c in df.columns}
    src_col = cols.get("source_id") or df.columns[0]
    status_col = cols.get("historical_asof_status")
    block_col = cols.get("blocking_issue")
    action_col = cols.get("owner_action")

    for feat in H64L_FEATURES:
        matches = []
        for _, r in df.iterrows():
            sid = str(r.get(src_col, ""))
            hay = " ".join([str(r.get(c, "")) for c in df.columns])
            if any(m.lower() in sid.lower() or m.lower() in hay.lower() for m in feat["source_match"]):
                matches.append(r)
        if not matches:
            rows.append({
                "feature_id": feat["feature_id"],
                "matched_contract_source_id": "NO_MATCH",
                "historical_asof_status": "UNKNOWN",
                "blocking_issue": "no matching source contract row found",
                "triage_verdict": "BLOCKING_UNTIL_SOURCE_CONTRACT_ADDED",
                "required_policy": feat["required_policy"],
                "risk": feat["risk"],
            })
            continue
        for r in matches:
            status = str(r.get(status_col, "UNKNOWN")) if status_col else "UNKNOWN"
            blocking = str(r.get(block_col, "")) if block_col else ""
            action = str(r.get(action_col, "")) if action_col else ""
            status_low = status.lower()
            is_blocking = any(x in status_low for x in ["low", "medium", "until", "unknown"]) or bool(blocking.strip())
            rows.append({
                "feature_id": feat["feature_id"],
                "matched_contract_source_id": str(r.get(src_col, "")),
                "historical_asof_status": status,
                "blocking_issue": blocking,
                "owner_action": action,
                "triage_verdict": "H64L_FEATURE_BLOCKED_OR_NEEDS_MECHANICAL_ASOF_FIX" if is_blocking else "H64L_FEATURE_ASOF_ACCEPTABLE",
                "required_policy": feat["required_policy"],
                "risk": feat["risk"],
            })
    block_count = sum(1 for r in rows if "BLOCK" in r.get("triage_verdict", "") or "NEEDS" in r.get("triage_verdict", ""))
    return rows, {"contract_loaded": True, "mapped_rows": len(rows), "blocking_h64l_features": block_count}


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(k for row in rows for k in row.keys()))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_shadow_template(out_csv: Path) -> None:
    rows = [{
        "check_date_utc": datetime.now(timezone.utc).date().isoformat(),
        "checked_at_utc": utc_now(),
        "gold_sma20_over_50_gt_0": "TODO",
        "dxy_ret_20d_lt_0": "TODO",
        "real_yield_change_20d_lt_0": "TODO",
        "etf_flow_tonnes_3m_gt_0": "TODO",
        "event_guard_state": "TODO",
        "simple_blackout_fomc_nfp_cpi_30m": "TODO",
        "h64l_hit": "TODO_TRUE_FALSE",
        "action": "LOG_ONLY_NO_ORDER",
        "notes": "Manual daily shadow checklist starts immediately in parallel with audit.",
    }]
    write_csv(out_csv, rows)


def decision_from_triage(triage_meta: Dict[str, Any], clues: Dict[str, Any]) -> str:
    if clues.get("found_artifact_count", 0) == 0:
        return "STAGE171_NEEDS_STAGE64R_ARTIFACTS_BUT_START_MANUAL_SHADOW_FROM_EXPERT_RULE"
    if triage_meta.get("blocking_h64l_features", 0) > 0:
        return "STAGE171_H64L_PARALLEL_TRACK_WITH_TARGETED_ASOF_FIXES_REQUIRED"
    return "STAGE171_H64L_PARALLEL_TRACK_READY_FOR_TIMEBOXED_AUDIT_AND_SHADOW"


def render_decision_md(path: Path, summary: Dict[str, Any], triage_rows: List[Dict[str, Any]], artifacts: List[Dict[str, Any]]) -> None:
    current = summary["parallel_track_policy"]
    md = []
    md.append(f"# Stage171 H64L Rescue Parallel Track\n")
    md.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    md.append(f"Decision: `{summary['decision']}`\n")
    md.append(f"Recommended action: `{summary['recommended_action']}`\n")
    md.append("## Core correction\n")
    md.append("This stage explicitly rejects audit-before-action. H64L triage/audit and manual shadow checklist must run in parallel from day one. No MT5 order signal or demo/live authorization is created by this stage.\n")
    md.append("## Timebox\n")
    md.append(f"Audit timebox: `{current['audit_timebox_business_days']}` business days. After the limit, incomplete evidence becomes `INCONCLUSIVE`, not an open-ended audit.\n")
    md.append("## Track design\n")
    md.append("- Track 1.5: 30-minute triage mapping H64L features to Stage170C blockers.\n")
    md.append("- Track 1: timeboxed as-of safety audit, no threshold changes.\n")
    md.append("- Track 2: manual shadow checklist starts immediately, log-only, no orders.\n")
    md.append("## H64L feature blocker triage\n")
    md.append("| feature | contract source | status | verdict | risk |\n|---|---|---|---|---|\n")
    for r in triage_rows:
        md.append(f"| {r.get('feature_id','')} | {r.get('matched_contract_source_id','')} | {r.get('historical_asof_status','')} | {r.get('triage_verdict','')} | {r.get('risk','')} |\n")
    md.append("\n## H64L artifacts\n")
    if artifacts:
        for a in artifacts[:20]:
            md.append(f"- `{a['path']}` ({a.get('hit_terms','')})\n")
    else:
        md.append("No Stage64R/H64L artifacts were found by automatic search. Use the expert-provided locked conditions as temporary manual checklist until raw Stage64R evidence is supplied.\n")
    md.append("\n## Decision tree after three business days\n")
    md.append("```text\n")
    md.append("Track1 PASS + at least one shadow hit -> Stage172 limited 0.01-lot demo bridge candidate review, not broad scan.\n")
    md.append("Track1 PASS + zero shadow hit -> wait for H64L signal, but start small Path B supervised quick AUC test as hedge.\n")
    md.append("Track1 FAIL -> abandon rescue and move to Path B or C; no second rescue scan.\n")
    md.append("Track1 INCONCLUSIVE -> continue shadow logging but do not promote; specialist decision required.\n")
    md.append("```\n")
    md.append("\n## Hard constraints\n")
    md.append("- No threshold re-optimization.\n- Only mechanical as-of lag fixes are allowed.\n- GDELT/news remains guard only.\n- Simple 30-minute blackout around FOMC/NFP/CPI is sufficient for this rescue track.\n- Shadow/logging can start immediately; orders cannot.\n")
    path.write_text("".join(md), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--stage170c-summary", default=None)
    ap.add_argument("--stage170c-contract-report", default=None)
    ap.add_argument("--data-asof-contract", default=None)
    ap.add_argument("--stage64-search-dir", action="append", default=[])
    ap.add_argument("--audit-timebox-business-days", type=int, default=3)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else root / "reports" / "stage171_h64l_rescue_parallel_track"
    out_dir.mkdir(parents=True, exist_ok=True)

    stage170c_summary = load_json(Path(args.stage170c_summary).expanduser()) if args.stage170c_summary else {}
    contract_path = Path(args.stage170c_contract_report).expanduser() if args.stage170c_contract_report else None
    if not contract_path or not contract_path.exists():
        contract_path = Path(args.data_asof_contract).expanduser() if args.data_asof_contract else None
    if not contract_path or not contract_path.exists():
        # default reports paths
        candidates = [
            root / "reports/stage170c_asof_join_enforcement_and_validation_framework/stage170c_data_contract_enforcement_report.csv",
            root / "reports/stage170b_data_asof_contract_validation_redesign/stage170b_data_asof_contract.csv",
        ]
        contract_path = next((p for p in candidates if p.exists()), None)

    artifacts = discover_h64l_artifacts(root, [Path(p) for p in args.stage64_search_dir])
    clues = extract_h64l_clues(artifacts)
    triage_rows, triage_meta = map_features_to_contract(contract_path)

    # Outputs
    artifacts_csv = out_dir / "stage171_h64l_artifact_inventory.csv"
    triage_csv = out_dir / "stage171_h64l_feature_blocker_triage.csv"
    shadow_csv = out_dir / "stage171_h64l_manual_shadow_checklist.csv"
    summary_json = out_dir / "stage171_h64l_rescue_parallel_track_summary.json"
    decision_md = out_dir / "stage171_decision.md"
    write_csv(artifacts_csv, artifacts)
    write_csv(triage_csv, triage_rows)
    build_shadow_template(shadow_csv)

    decision = decision_from_triage(triage_meta, clues)
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE171_COMPLETE_PARALLEL_RESCUE_FRAMEWORK_READY",
        "decision": decision,
        "severity": "HIGH",
        "recommended_action": RECOMMENDED_ACTION,
        "stage170c_verdict": {
            "decision": stage170c_summary.get("decision"),
            "new_discovery_allowed": stage170c_summary.get("methodology_gate", {}).get("new_discovery_allowed"),
            "next_required_stage": stage170c_summary.get("methodology_gate", {}).get("next_required_stage"),
        },
        "parallel_track_policy": {
            "audit_before_action_rejected": True,
            "track_1_5_triage_minutes": 30,
            "audit_timebox_business_days": args.audit_timebox_business_days,
            "manual_shadow_starts_day_one": True,
            "threshold_reoptimization_allowed": False,
            "mechanical_asof_fix_allowed": True,
            "mt5_signal_written": False,
            "demo_live_authorized": False,
        },
        "h64l_clues": clues,
        "triage_meta": triage_meta,
        "outputs": {
            "summary_json": str(summary_json),
            "decision_md": str(decision_md),
            "artifact_inventory_csv": str(artifacts_csv),
            "feature_blocker_triage_csv": str(triage_csv),
            "manual_shadow_checklist_csv": str(shadow_csv),
        },
        "next": [
            "Start manual H64L checklist logging immediately; log-only, no orders.",
            "Review feature blocker triage before spending time on C1-C7 audit.",
            "Keep audit timeboxed to 3 business days; incomplete result becomes INCONCLUSIVE.",
            "If PASS plus at least one shadow hit, prepare Stage172 limited 0.01-lot demo bridge review.",
            "If PASS plus zero hit, keep waiting for signal and start small Path B supervised quick AUC test.",
        ],
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    render_decision_md(decision_md, summary, triage_rows, artifacts)
    print(json.dumps({"decision": decision, "outputs": summary["outputs"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
