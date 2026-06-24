#!/usr/bin/env python3
"""
Stage64D4 source-file import preflight.

Checks only raw macro-regime files before normalization/import.
No thesis validation, no signal generation, no order path.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

UTC = dt.timezone.utc


def utc_now_iso() -> str:
    return dt.datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(value: str) -> dt.datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        try:
            d = dt.date.fromisoformat(value[:10])
            return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            return None


def read_csv_head(path: Path) -> Tuple[List[str], List[Dict[str, str]], int]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows: List[Dict[str, str]] = []
        count = 0
        for row in reader:
            count += 1
            if len(rows) < 200000:
                rows.append(row)
        return fields, rows, count


def audit_target(root: Path, target: Dict[str, Any], minimum_start: str) -> Dict[str, Any]:
    rel = target["target_file"]
    path = root / rel
    required = list(target.get("required_columns", []))
    result: Dict[str, Any] = {
        "manifest_id": target.get("manifest_id"),
        "priority": target.get("priority"),
        "target_file": rel,
        "found": path.exists(),
        "required_columns": required,
        "missing_columns": [],
        "row_count": 0,
        "first_time_utc": None,
        "last_time_utc": None,
        "duplicate_key_count": 0,
        "available_after_missing_count": None,
        "available_after_parse_error_count": None,
        "start_coverage_ok": False,
        "schema_ok": False,
        "preflight_ok": False,
        "issues": [],
    }
    if not path.exists():
        result["issues"].append("file missing")
        return result

    fields, rows, count = read_csv_head(path)
    result["row_count"] = count
    missing = [c for c in required if c not in fields]
    result["missing_columns"] = missing
    if missing:
        result["issues"].append("missing columns: " + ",".join(missing))
    result["schema_ok"] = not missing
    if count <= 0:
        result["issues"].append("no data rows")

    time_cols = [c for c in ["date_utc", "period_start", "scheduled_time_utc"] if c in fields]
    key_cols = []
    if "date_utc" in fields and "source" in fields:
        key_cols = ["date_utc", "source"]
        if "etf_id" in fields:
            key_cols = ["date_utc", "etf_id", "source"]
        if "proxy_method" in fields:
            key_cols = ["date_utc", "source", "proxy_method"]
    elif "period_start" in fields and "period_end" in fields and "source" in fields:
        key_cols = ["period_start", "period_end", "source"]
    elif "scheduled_time_utc" in fields and "event_type" in fields and "country" in fields and "source" in fields:
        key_cols = ["scheduled_time_utc", "event_type", "country", "source"]

    seen: set[tuple[str, ...]] = set()
    dup = 0
    parsed_times: List[dt.datetime] = []
    aa_missing = 0
    aa_parse_err = 0
    for row in rows:
        if key_cols:
            key = tuple(str(row.get(c, "")).strip() for c in key_cols)
            if key in seen:
                dup += 1
            seen.add(key)
        if time_cols:
            t = parse_dt(row.get(time_cols[0], ""))
            if t:
                parsed_times.append(t)
        if "available_after_utc" in fields:
            raw = str(row.get("available_after_utc", "")).strip()
            if not raw:
                aa_missing += 1
            elif parse_dt(raw) is None:
                aa_parse_err += 1

    result["duplicate_key_count"] = dup
    if "available_after_utc" in fields:
        result["available_after_missing_count"] = aa_missing
        result["available_after_parse_error_count"] = aa_parse_err
    if parsed_times:
        first = min(parsed_times)
        last = max(parsed_times)
        result["first_time_utc"] = first.isoformat().replace("+00:00", "Z")
        result["last_time_utc"] = last.isoformat().replace("+00:00", "Z")
        min_start = parse_dt(minimum_start)
        result["start_coverage_ok"] = bool(min_start and first <= min_start)
        if not result["start_coverage_ok"]:
            result["issues"].append(f"coverage starts after required minimum {minimum_start}")
    else:
        result["issues"].append("no parseable time column values")

    if dup:
        result["issues"].append(f"duplicate primary-key rows: {dup}")
    if aa_missing:
        result["issues"].append(f"available_after_utc missing rows: {aa_missing}")
    if aa_parse_err:
        result["issues"].append(f"available_after_utc parse errors: {aa_parse_err}")

    result["preflight_ok"] = bool(result["schema_ok"] and count > 0 and result["start_coverage_ok"] and dup == 0 and not aa_missing and not aa_parse_err)
    return result


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64D4 source-file import preflight")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64d4_source_file_import_preflight.json")
    ap.add_argument("--out", default="reports/stage64d4_source_file_import_preflight")
    ns = ap.parse_args()

    root = Path(ns.root).resolve()
    cfg = json.loads((root / ns.config).read_text(encoding="utf-8"))
    source_cfg = json.loads((root / cfg["source_config"]).read_text(encoding="utf-8"))
    out_dir = root / ns.out
    out_dir.mkdir(parents=True, exist_ok=True)
    minimum_start = cfg.get("minimum_start_date", "2011-01-01")

    audits = [audit_target(root, t, minimum_start) for t in source_cfg.get("targets", [])]
    p0_files = set(cfg.get("required_p0_files", []))
    p0_audits = [a for a in audits if a["target_file"] in p0_files]
    p0_ready = all(a["preflight_ok"] for a in p0_audits) and len(p0_audits) == len(p0_files)
    all_ready = all(a["preflight_ok"] for a in audits)

    validation_allowed = False
    decision = "P0_READY_FOR_STAGE64D_RERUN_NO_VALIDATION" if p0_ready else "BLOCK_STAGE64D_RERUN_UNTIL_P0_RAW_FILES_PASS_PREFLIGHT_NO_ORDER"
    if all_ready:
        decision = "ALL_RAW_FILES_PASS_PREFLIGHT_RERUN_STAGE64D_NO_VALIDATION_YET"

    csv_path = out_dir / "stage64d4_source_file_import_preflight_checks.csv"
    write_csv(csv_path, [
        "manifest_id", "priority", "target_file", "found", "schema_ok", "preflight_ok", "row_count", "first_time_utc", "last_time_utc", "duplicate_key_count", "available_after_missing_count", "available_after_parse_error_count", "issues"
    ], [{**a, "issues": "; ".join(a.get("issues", []))} for a in audits])

    summary = {
        "stage": "Stage64D4_SOURCE_FILE_IMPORT_PREFLIGHT_NO_PROMOTION",
        "status": "SOURCE_FILE_IMPORT_PREFLIGHT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": validation_allowed,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "counts": {
            "targets": len(audits),
            "found": sum(1 for a in audits if a["found"]),
            "preflight_ok": sum(1 for a in audits if a["preflight_ok"]),
            "p0_required": len(p0_files),
            "p0_preflight_ok": sum(1 for a in p0_audits if a["preflight_ok"]),
        },
        "p0_ready_for_stage64d_rerun": p0_ready,
        "all_raw_files_preflight_ok": all_ready,
        "hard_blocks": cfg.get("hard_blocks", []),
        "outputs": {
            "checks_csv": str(csv_path.relative_to(root)),
            "summary_json": str((out_dir / "stage64d4_source_file_import_preflight_summary.json").relative_to(root)),
            "report_md": str((out_dir / "stage64d4_source_file_import_preflight_report.md").relative_to(root)),
        },
        "checks": audits,
    }
    (out_dir / "stage64d4_source_file_import_preflight_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage64D4 Source File Import Preflight",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        f"Status: `{summary['status']}`",
        f"Decision: `{decision}`",
        "",
        "No validation or order path is authorized by this preflight.",
        "",
        "## Counts",
        "",
        f"- targets: {summary['counts']['targets']}",
        f"- found: {summary['counts']['found']}",
        f"- preflight_ok: {summary['counts']['preflight_ok']}",
        f"- p0_preflight_ok: {summary['counts']['p0_preflight_ok']} / {summary['counts']['p0_required']}",
        "",
        "## Failed or missing files",
        "",
    ]
    failed = [a for a in audits if not a["preflight_ok"]]
    if not failed:
        lines.append("None.")
    else:
        for a in failed:
            lines.append(f"- `{a['target_file']}`: " + "; ".join(a.get("issues", [])))
    lines += ["", "## Next", "", "If P0 is ready, rerun Stage64D to reassess data-contract readiness. Validation is still blocked until Stage64D explicitly unlocks the selected scope."]
    (out_dir / "stage64d4_source_file_import_preflight_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
