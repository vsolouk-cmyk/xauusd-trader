#!/usr/bin/env python3
"""
Stage122_SHADOW_OBSERVER_PACKAGE_REVIEW

Data-only / report-only review of Stage121 dry-run observer preflight outputs.
This stage prepares a shadow-observer package candidate under reports only.
It does not update active observer files, bridges, MT5, MQL5/Files, EA, broker,
paper-live, or live-order surfaces.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STAGE = "Stage122_SHADOW_OBSERVER_PACKAGE_REVIEW"
OUT_DIR_NAME = "stage122_shadow_observer_package_review"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE122",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE122",
    "NO_OBSERVER_BRIDGE_WRITE",
    "NO_MT5_MQL5_FILES_WRITE",
    "NO_ACTIVE_OBSERVER_FILE_WRITE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

ACTIVE_WRITE_PATTERNS = [
    "MQL5/Files",
    "active_observer",
    "observer_bridge",
    "signals_to_mt5",
    "paper_order",
    "live_order",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_dicts(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        s = str(v).strip()
        if s == "" or s.lower() in {"nan", "none", "null"}:
            return default
        return float(s)
    except Exception:
        return default


def to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "pass"}


def load_rule_specs(path: Path) -> Dict[str, Dict[str, Any]]:
    data = read_json(path)
    if isinstance(data, dict):
        if "rules" in data and isinstance(data["rules"], list):
            out: Dict[str, Dict[str, Any]] = {}
            for row in data["rules"]:
                if isinstance(row, dict):
                    rid = str(row.get("observer_design_rule_id") or row.get("rule_id") or row.get("source_rule_id") or "")
                    if rid:
                        out[rid] = row
            return out
        # Could already be keyed by rule id.
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    if isinstance(data, list):
        out = {}
        for row in data:
            if isinstance(row, dict):
                rid = str(row.get("observer_design_rule_id") or row.get("rule_id") or row.get("source_rule_id") or "")
                if rid:
                    out[rid] = row
        return out
    return {}


def validate_report_only_paths(root: Path, out_dir: Path) -> Tuple[bool, List[str]]:
    """Verify planned output path is safely inside reports/stage122... and not active surfaces."""
    warnings: List[str] = []
    resolved = out_dir.resolve()
    reports_root = (root / "reports").resolve()
    ok = str(resolved).startswith(str(reports_root))
    if not ok:
        warnings.append(f"OUT_DIR_NOT_UNDER_REPORTS: {out_dir}")
    s = str(resolved)
    for pat in ACTIVE_WRITE_PATTERNS:
        if pat in s:
            warnings.append(f"ACTIVE_SURFACE_PATTERN_IN_OUT_DIR: {pat}")
            ok = False
    return ok, warnings


def build_shadow_spec(row: Dict[str, str], rule_spec: Dict[str, Any]) -> Dict[str, Any]:
    rid = row.get("observer_design_rule_id", "")
    source_rule_id = row.get("source_rule_id", "")
    candidate_only = to_bool(row.get("candidate_only", ""))
    return {
        "shadow_observer_rule_id": rid.replace("S120_", "S122_SHADOW_") if rid else f"S122_SHADOW_{source_rule_id}",
        "observer_design_rule_id": rid,
        "source_rule_id": source_rule_id,
        "bucket": row.get("bucket", ""),
        "readiness_score": to_float(row.get("readiness_score")),
        "candidate_only": candidate_only,
        "source_validation": {
            "stage116_dxy_fallback_active": to_bool(row.get("stage116_dxy_fallback_active", "")),
            "stage116_direct_dxy_valid": to_bool(row.get("stage116_direct_dxy_valid", "")),
            "stage116_spdr_status": row.get("stage116_spdr_status", ""),
        },
        "dry_run_preflight": {
            "preflight_status": row.get("preflight_status", ""),
            "raw_signal_rows": int(to_float(row.get("raw_signal_rows"))),
            "spaced_signal_rows": int(to_float(row.get("spaced_signal_rows"))),
            "expected_raw_all_events": int(to_float(row.get("expected_raw_all_events"))),
            "raw_event_count_delta_pct": to_float(row.get("raw_event_count_delta_pct")),
            "condition_parse_count": int(to_float(row.get("condition_parse_count"))),
            "event_spacing_hours": to_float(row.get("event_spacing_hours")),
            "missing_required_features": row.get("missing_required_features", ""),
        },
        "observer_contract": {
            "mode": "SHADOW_REPORT_ONLY",
            "write_scope": "reports_only",
            "active_observer_update_allowed": False,
            "mt5_or_mql5_write_allowed": False,
            "order_allowed": False,
            "requires_extra_source_confirmation": bool(candidate_only),
        },
        "design_spec_from_stage120": rule_spec or {},
    }


def assess_candidate(row: Dict[str, str]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    status = row.get("preflight_status", "")
    spaced = int(to_float(row.get("spaced_signal_rows")))
    raw_delta = abs(to_float(row.get("raw_event_count_delta_pct")))
    missing = str(row.get("missing_required_features", "")).strip()
    parse_count = int(to_float(row.get("condition_parse_count")))
    spacing = to_float(row.get("event_spacing_hours"))
    readiness = to_float(row.get("readiness_score"))
    bucket = row.get("bucket", "")
    spdr_status = row.get("stage116_spdr_status", "")

    if status != "PASS_DRY_RUN_PREFLIGHT":
        reasons.append(f"PREFLIGHT_STATUS_NOT_PASS:{status}")
    if spaced < 20:
        reasons.append(f"LOW_SPACED_SIGNAL_ROWS:{spaced}")
    if raw_delta > 1.0:
        reasons.append(f"RAW_EVENT_COUNT_DELTA_GT_1PCT:{raw_delta}")
    if missing and missing.lower() not in {"nan", "none", "null"}:
        reasons.append(f"MISSING_REQUIRED_FEATURES:{missing}")
    if parse_count < 1:
        reasons.append("NO_PARSED_CONDITIONS")
    if spacing < 120:
        reasons.append(f"EVENT_SPACING_LT_120H:{spacing}")
    if readiness < 70:
        reasons.append(f"READINESS_SCORE_LT_70:{readiness}")
    if bucket != "PRIMARY_DESIGN":
        reasons.append(f"NOT_PRIMARY_DESIGN:{bucket}")
    if spdr_status and spdr_status != "VALIDATED_CANDIDATE":
        reasons.append(f"SPDR_NOT_VALIDATED_CANDIDATE:{spdr_status}")

    # candidate-only source can proceed to shadow package, but not activation.
    decision = "STAGE123_STATIC_REPLAY_QUEUE"
    if reasons:
        decision = "WATCH_OR_BLOCK_BEFORE_STAGE123"
    return decision, reasons


def run(root: Path) -> Dict[str, Any]:
    stage121_dir = root / "reports" / "stage121_dry_run_observer_preflight"
    stage120_dir = root / "reports" / "stage120_observer_design_review"
    out_dir = ensure_dir(root / "reports" / OUT_DIR_NAME)

    report_path_ok, path_warnings = validate_report_only_paths(root, out_dir)

    summary121 = read_json(stage121_dir / "stage121_dry_run_observer_preflight_summary.json")
    metrics = read_csv_dicts(stage121_dir / "stage121_preflight_metrics.csv")
    selected121 = read_csv_dicts(stage121_dir / "stage121_selected_for_stage122.csv")
    stage120_specs = load_rule_specs(stage120_dir / "stage120_observer_rule_specs_draft.json")

    # Prefer selected rows if available; merge metrics by observer_design_rule_id for complete columns.
    metric_by_id = {r.get("observer_design_rule_id", ""): r for r in metrics}
    candidate_ids: List[str] = []
    for r in selected121:
        rid = r.get("observer_design_rule_id") or r.get("rule_id") or r.get("source_rule_id")
        if rid and rid not in candidate_ids:
            candidate_ids.append(rid)
    if not candidate_ids:
        candidate_ids = [r.get("observer_design_rule_id", "") for r in metrics if r.get("preflight_status") == "PASS_DRY_RUN_PREFLIGHT"]

    review_rows: List[Dict[str, Any]] = []
    shadow_specs: List[Dict[str, Any]] = []
    stage123_queue: List[Dict[str, Any]] = []
    watch_rows: List[Dict[str, Any]] = []

    for rid in candidate_ids:
        row = dict(metric_by_id.get(rid, {}))
        if not row and selected121:
            row = next((r for r in selected121 if (r.get("observer_design_rule_id") or r.get("rule_id")) == rid), {})
        spec = stage120_specs.get(rid, {})
        decision, reasons = assess_candidate(row)
        shadow_spec = build_shadow_spec(row, spec)
        shadow_specs.append(shadow_spec)

        review_row = {
            "observer_design_rule_id": row.get("observer_design_rule_id", rid),
            "source_rule_id": row.get("source_rule_id", ""),
            "stage122_decision": decision,
            "stage122_reasons": ";".join(reasons),
            "shadow_observer_rule_id": shadow_spec["shadow_observer_rule_id"],
            "bucket": row.get("bucket", ""),
            "readiness_score": row.get("readiness_score", ""),
            "candidate_only": row.get("candidate_only", ""),
            "raw_signal_rows": row.get("raw_signal_rows", ""),
            "spaced_signal_rows": row.get("spaced_signal_rows", ""),
            "event_spacing_hours": row.get("event_spacing_hours", ""),
            "stage116_dxy_fallback_active": row.get("stage116_dxy_fallback_active", ""),
            "stage116_direct_dxy_valid": row.get("stage116_direct_dxy_valid", ""),
            "stage116_spdr_status": row.get("stage116_spdr_status", ""),
            "active_update_allowed": "False",
            "report_only_shadow_package": "True",
        }
        review_rows.append(review_row)

        if decision == "STAGE123_STATIC_REPLAY_QUEUE":
            stage123_queue.append({
                **review_row,
                "stage123_task": "STATIC_REPLAY_SHADOW_OBSERVER_PACKAGE_ONLY",
                "min_spacing_hours": "120",
                "allowed_output_scope": "reports_only",
                "blocked_outputs": "active_observer;observer_bridge;MQL5/Files;paper_order;live_order",
            })
        else:
            watch_rows.append(review_row)

    governance_rows = [
        {"gate": "automated_order", "status": "BLOCKED", "detail": "No automated order from Stage122"},
        {"gate": "paper_order", "status": "BLOCKED", "detail": "No paper order from Stage122"},
        {"gate": "broker_connection", "status": "BLOCKED", "detail": "No broker connection from Stage122"},
        {"gate": "mt5_or_ea_change", "status": "BLOCKED", "detail": "No MT5/EA/MQL5 write from Stage122"},
        {"gate": "active_observer_update", "status": "BLOCKED", "detail": "No active observer update from Stage122"},
        {"gate": "observer_bridge_write", "status": "BLOCKED", "detail": "No observer bridge write from Stage122"},
        {"gate": "report_only_path", "status": "PASS" if report_path_ok else "BLOCKED", "detail": ";".join(path_warnings)},
    ]

    no_write_rows = [
        {"path_or_surface": "active observer files", "write_allowed": "False"},
        {"path_or_surface": "observer bridge", "write_allowed": "False"},
        {"path_or_surface": "MT5 MQL5/Files", "write_allowed": "False"},
        {"path_or_surface": "EA source or compiled files", "write_allowed": "False"},
        {"path_or_surface": "broker/order files", "write_allowed": "False"},
        {"path_or_surface": str(out_dir), "write_allowed": "True", "scope": "reports_only"},
    ]

    out_paths = {
        "shadow_package_manifest": out_dir / "stage122_shadow_package_manifest.csv",
        "shadow_observer_rule_specs_review": out_dir / "stage122_shadow_observer_rule_specs_review.json",
        "stage123_static_replay_queue": out_dir / "stage122_stage123_static_replay_queue.csv",
        "watch_or_block": out_dir / "stage122_watch_or_block.csv",
        "governance_gate": out_dir / "stage122_governance_gate.csv",
        "no_write_manifest": out_dir / "stage122_no_write_manifest.csv",
        "report_md": out_dir / "stage122_shadow_observer_package_review_report.md",
        "summary_json": out_dir / "stage122_shadow_observer_package_review_summary.json",
    }

    write_csv_dicts(out_paths["shadow_package_manifest"], review_rows)
    write_json(out_paths["shadow_observer_rule_specs_review"], {"stage": STAGE, "rules": shadow_specs, "hard_blocks": HARD_BLOCKS})
    write_csv_dicts(out_paths["stage123_static_replay_queue"], stage123_queue)
    write_csv_dicts(out_paths["watch_or_block"], watch_rows)
    write_csv_dicts(out_paths["governance_gate"], governance_rows)
    write_csv_dicts(out_paths["no_write_manifest"], no_write_rows)

    stage123_count = len(stage123_queue)
    decision = "STAGE122_STAGE123_STATIC_REPLAY_QUEUE_READY_NO_UPDATE" if stage123_count else "STAGE122_NO_STAGE123_QUEUE_NO_UPDATE"
    status = "STAGE122_COMPLETE_SHADOW_OBSERVER_PACKAGE_REVIEW_READY_NO_UPDATE"

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": "SHADOW_OBSERVER_PACKAGE_REVIEW_ONLY_NO_UPDATE",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage121_dir": str(stage121_dir),
        "stage120_dir": str(stage120_dir),
        "stage121_status": summary121.get("status", ""),
        "stage121_decision": summary121.get("decision", ""),
        "stage121_pass_preflight_count": summary121.get("pass_preflight_count", 0),
        "metrics_rows_seen": len(metrics),
        "candidate_rows_reviewed": len(review_rows),
        "stage123_static_replay_candidate_count": stage123_count,
        "watch_or_block_count": len(watch_rows),
        "report_only_path_ok": report_path_ok,
        "path_warnings": path_warnings,
        "shadow_package_manifest": str(out_paths["shadow_package_manifest"]),
        "shadow_observer_rule_specs_review": str(out_paths["shadow_observer_rule_specs_review"]),
        "stage123_static_replay_queue": str(out_paths["stage123_static_replay_queue"]),
        "watch_or_block": str(out_paths["watch_or_block"]),
        "governance_gate": str(out_paths["governance_gate"]),
        "no_write_manifest": str(out_paths["no_write_manifest"]),
        "summary_json": str(out_paths["summary_json"]),
        "report_md": str(out_paths["report_md"]),
        "next": [
            "If stage123_static_replay_candidate_count > 0, create Stage123 static replay of the shadow observer package only.",
            "Do not update active observer, observer bridge, MT5, EA, paper-order, or live-order files from Stage122.",
            "Candidate-only SPDR-based rules remain shadow-only until further static replay and governance checks pass.",
        ],
    }

    report = f"""# {STAGE}

Generated UTC: {summary['generated_utc']}

Status: `{status}`
Decision: `{decision}`

## Interpretation

Stage122 reviews the Stage121 dry-run preflight candidate and prepares a report-only shadow-observer package. It does not update any active observer, observer bridge, MT5, EA, paper-order, or live-order surface.

## Counts

- Stage121 pass preflight count: `{summary['stage121_pass_preflight_count']}`
- Candidate rows reviewed: `{len(review_rows)}`
- Stage123 static replay candidates: `{stage123_count}`
- Watch/block rows: `{len(watch_rows)}`

## Governance

All active trading and active observer write surfaces remain blocked. Outputs are limited to this reports directory:

```text
{out_dir}
```

## Next use

Use `stage122_stage123_static_replay_queue.csv` as input for Stage123 static replay of the shadow observer package only.
"""

    out_paths["report_md"].write_text(report, encoding="utf-8")
    write_json(out_paths["summary_json"], summary)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Stage122 shadow-observer package review.")
    p.add_argument("--root", required=True, help="Repository root, e.g. /Users/vahid/Desktop/xauusd-trader")
    args = p.parse_args(argv)
    summary = run(Path(args.root).expanduser().resolve())
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
