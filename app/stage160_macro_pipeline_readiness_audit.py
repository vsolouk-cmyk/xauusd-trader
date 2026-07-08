#!/usr/bin/env python3
"""Stage160: Macro/fundamental pipeline readiness audit for XAUUSD.

Read-only audit. It does not create trading signals, MT5 KV files, or orders.
It verifies whether the refreshed official-data/fundamental pipeline is fresh and
usable before any macro-aware candidate classification or demo release.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

UTC = timezone.utc

KEY_FEATURES = [
    {
        "role": "macro_daily_panel",
        "file": "stage115_daily_macro_feature_panel.csv",
        "required": True,
        "min_bytes": 100_000,
        "min_rows": 100,
    },
    {
        "role": "fred_daily_wide",
        "file": "stage115_fred_macro_daily_wide.csv",
        "required": True,
        "min_bytes": 20_000,
        "min_rows": 100,
    },
    {
        "role": "cot_gold_weekly",
        "file": "stage115_cot_gold_weekly_features.csv",
        "required": True,
        "min_bytes": 20_000,
        "min_rows": 100,
    },
    {
        "role": "event_calendar",
        "file": "stage115_unified_event_calendar_features.csv",
        "required": True,
        "min_bytes": 5_000,
        "min_rows": 10,
    },
    {
        "role": "validated_dollar_pressure",
        "file": "stage116_validated_dollar_pressure.csv",
        "required": True,
        "min_bytes": 20_000,
        "min_rows": 100,
    },
    {
        "role": "validated_spdr_gld",
        "file": "stage116_validated_spdr_gld_long.csv",
        "required": False,
        "min_bytes": 20_000,
        "min_rows": 10,
    },
    {
        "role": "stage117_joined_h1_macro_dataset",
        "file": "stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        "required": True,
        "min_bytes": 100_000,
        "min_rows": 1000,
    },
    {
        "role": "validated_wgc_gold_etf",
        "file": "stage116_validated_wgc_gold_etf_long.csv",
        "required": False,
        "min_bytes": 5_000,
        "min_rows": 10,
    },
    {
        "role": "validated_wgc_central_bank",
        "file": "stage116_validated_wgc_central_bank_gold_long.csv",
        "required": False,
        "min_bytes": 5_000,
        "min_rows": 5,
    },
]

DATE_CANDIDATES = [
    "datetime", "date", "timestamp", "utc_time", "time_utc", "time", "ds",
    "observation_date", "report_date", "release_date", "event_date", "period",
]


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: Optional[datetime]) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z") if dt else ""


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def safe_read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}
    return {}


def sample_columns(path: Path, max_rows: int = 2000) -> Tuple[List[str], int, Optional[datetime], str]:
    """Return columns, row count estimate, latest parsed date, and date column used."""
    try:
        df = pd.read_csv(path, nrows=max_rows)
    except Exception as exc:
        return [], 0, None, f"READ_ERROR:{exc}"
    cols = list(df.columns)
    row_count = 0
    try:
        # Efficient enough for files in this project; avoids misleading nrows-only count.
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            row_count = max(sum(1 for _ in f) - 1, 0)
    except Exception:
        row_count = len(df)

    latest: Optional[datetime] = None
    used = ""
    lower_map = {c.lower(): c for c in cols}
    candidates: List[str] = []
    for name in DATE_CANDIDATES:
        if name in lower_map:
            candidates.append(lower_map[name])
    for c in cols:
        lc = c.lower()
        if ("date" in lc or "time" in lc) and c not in candidates:
            candidates.append(c)
    for c in candidates:
        try:
            s = pd.to_datetime(df[c], errors="coerce", utc=True)
            if s.notna().sum() >= max(1, min(5, len(df) // 20)):
                val = s.max()
                if pd.notna(val):
                    latest = val.to_pydatetime().astimezone(UTC)
                    used = c
                    break
        except Exception:
            continue
    return cols, row_count, latest, used


def mtime_utc(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except Exception:
        return None


def audit_one(feature_dir: Path, spec: Dict[str, Any], generated: datetime, max_mtime_age_hours: float) -> Dict[str, Any]:
    path = feature_dir / spec["file"]
    row: Dict[str, Any] = {
        "role": spec["role"],
        "file": spec["file"],
        "path": str(path),
        "required": bool(spec.get("required")),
        "exists": path.exists(),
        "size_bytes": 0,
        "mtime_utc": "",
        "mtime_age_hours": "",
        "row_count": 0,
        "column_count": 0,
        "latest_data_time_utc": "",
        "date_column_used": "",
        "status": "MISSING",
        "warnings": "",
    }
    warnings: List[str] = []
    if not path.exists():
        row["status"] = "MISSING_REQUIRED" if spec.get("required") else "MISSING_OPTIONAL"
        return row
    try:
        st = path.stat()
        row["size_bytes"] = st.st_size
    except Exception as exc:
        warnings.append(f"stat_error:{exc}")
    mt = mtime_utc(path)
    if mt:
        row["mtime_utc"] = iso(mt)
        age_h = (generated - mt).total_seconds() / 3600.0
        row["mtime_age_hours"] = round(age_h, 3)
        if age_h > max_mtime_age_hours:
            warnings.append(f"mtime_stale_gt_{max_mtime_age_hours:g}h")
    cols, row_count, latest, used = sample_columns(path)
    row["row_count"] = row_count
    row["column_count"] = len(cols)
    row["date_column_used"] = used
    row["latest_data_time_utc"] = iso(latest)
    if row["size_bytes"] < int(spec.get("min_bytes", 1)):
        warnings.append(f"small_file_lt_{spec.get('min_bytes')}")
    if row_count < int(spec.get("min_rows", 1)):
        warnings.append(f"few_rows_lt_{spec.get('min_rows')}")
    if used.startswith("READ_ERROR"):
        warnings.append(used)
    # Optional WGC files are known to be manual / intermittently unavailable; treat weak but not blocker.
    if warnings:
        row["status"] = "WARN_REQUIRED" if spec.get("required") else "WEAK_OPTIONAL"
    else:
        row["status"] = "READY"
    row["warnings"] = ";".join(warnings)
    return row


def make_decision(rows: List[Dict[str, Any]], stage116: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    blockers: List[str] = []
    warnings: List[str] = []
    for r in rows:
        if r["required"] and r["status"] in {"MISSING_REQUIRED", "WARN_REQUIRED"}:
            # Required files with only mtime warning are still usable, but report caution.
            warn = str(r.get("warnings", ""))
            if "small_file" in warn or "few_rows" in warn or "READ_ERROR" in warn or r["status"] == "MISSING_REQUIRED":
                blockers.append(f"{r['role']}:{r['status']}:{warn}")
            else:
                warnings.append(f"{r['role']}:{warn}")
        elif r["status"] == "WEAK_OPTIONAL":
            warnings.append(f"{r['role']}:{r.get('warnings','')}")
    # Stage116 summaries vary by stage version. Surface explicit failure-looking values if present.
    stage116_text = json.dumps(stage116, ensure_ascii=False).lower() if stage116 else ""
    if "error" in stage116_text or "fail" in stage116_text:
        warnings.append("stage116_summary_contains_error_or_fail_keyword_review_required")
    if blockers:
        return "STAGE160_MACRO_PIPELINE_BLOCKED_REPAIR_REQUIRED", "BLOCK", blockers + warnings
    if warnings:
        return "STAGE160_MACRO_CORE_READY_WITH_WARNINGS_FOR_CLASSIFICATION_ONLY", "WARN", warnings
    return "STAGE160_MACRO_PIPELINE_READY_FOR_CANDIDATE_CLASSIFICATION", "READY", []


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage160 macro/fundamental pipeline readiness audit")
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--feature-dir", default="data/fundamental_event_inbox/features")
    ap.add_argument("--pipeline-summary", default="reports/xauusd_fundamental_unify_normalize_pipeline/xauusd_fundamental_unify_normalize_pipeline_summary.json")
    ap.add_argument("--stage116-summary", default="reports/stage116_source_specific_wgc_spdr_dxy_validator/stage116_source_specific_wgc_spdr_dxy_validator_summary.json")
    ap.add_argument("--max-mtime-age-hours", type=float, default=48.0)
    ap.add_argument("--out", default="reports/stage160_macro_pipeline_readiness_audit")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    feature_dir = (root / args.feature_dir).resolve() if not Path(args.feature_dir).is_absolute() else Path(args.feature_dir).expanduser().resolve()
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).expanduser().resolve()
    generated = now_utc()

    rows = [audit_one(feature_dir, spec, generated, args.max_mtime_age_hours) for spec in KEY_FEATURES]
    pipeline_summary_path = (root / args.pipeline_summary).resolve() if not Path(args.pipeline_summary).is_absolute() else Path(args.pipeline_summary).expanduser().resolve()
    stage116_summary_path = (root / args.stage116_summary).resolve() if not Path(args.stage116_summary).is_absolute() else Path(args.stage116_summary).expanduser().resolve()
    pipeline_summary = safe_read_json(pipeline_summary_path)
    stage116_summary = safe_read_json(stage116_summary_path)
    decision, severity, issues = make_decision(rows, stage116_summary)

    required_count = sum(1 for r in rows if r["required"])
    required_ready = sum(1 for r in rows if r["required"] and r["status"] == "READY")
    optional_weak = sum(1 for r in rows if not r["required"] and r["status"] == "WEAK_OPTIONAL")

    summary = {
        "stage": "Stage160_MACRO_PIPELINE_READINESS_AUDIT",
        "generated_utc": iso(generated),
        "status": "STAGE160_COMPLETE_MACRO_PIPELINE_READINESS_AUDIT_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": (
            "RUN_STAGE161_MACRO_AWARE_CLASSIFIER_WITH_NO_DEMO_RELEASE" if severity in {"READY", "WARN"}
            else "KEEP_STAGE157_FREEZE_AND_REPAIR_MACRO_PIPELINE"
        ),
        "root": str(root),
        "feature_dir": str(feature_dir),
        "pipeline_summary": str(pipeline_summary_path),
        "stage116_summary": str(stage116_summary_path),
        "required_feature_count": required_count,
        "required_ready_count": required_ready,
        "optional_weak_count": optional_weak,
        "issue_count": len(issues),
        "issues": issues,
        "pipeline_summary_loaded": bool(pipeline_summary),
        "stage116_summary_loaded": bool(stage116_summary),
        "macro_blind_demo_release_allowed": False,
        "order_routing_allowed": False,
        "outputs": {
            "summary_json": str(out_dir / "stage160_macro_pipeline_readiness_audit_summary.json"),
            "feature_inventory_csv": str(out_dir / "stage160_macro_feature_inventory.csv"),
            "status_kv": str(out_dir / "stage160_macro_pipeline_status_kv.csv"),
        },
        "next": [
            "Keep Stage157 freeze active until macro-aware candidate classification is reviewed.",
            "Use Stage161 to classify Stage159 technical candidates by macro/regime support or conflict.",
            "Do not release demo orders from a technical-only shortlist.",
        ],
    }
    status_rows = [{"key": k, "value": v} for k, v in {
        "stage": summary["stage"],
        "decision": decision,
        "severity": severity,
        "required_ready_count": required_ready,
        "required_feature_count": required_count,
        "optional_weak_count": optional_weak,
        "order_routing_allowed": "false",
    }.items()]
    write_csv(out_dir / "stage160_macro_feature_inventory.csv", rows)
    write_csv(out_dir / "stage160_macro_pipeline_status_kv.csv", status_rows)
    write_json(out_dir / "stage160_macro_pipeline_readiness_audit_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
