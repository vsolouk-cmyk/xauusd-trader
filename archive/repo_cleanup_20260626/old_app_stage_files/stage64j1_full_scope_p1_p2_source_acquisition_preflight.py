#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def parse_time_any(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    # Common date-only case.
    try:
        if len(s2) == 10 and s2[4] == "-" and s2[7] == "-":
            return dt.datetime.fromisoformat(s2).replace(tzinfo=dt.UTC)
    except Exception:
        pass
    # ISO datetime.
    try:
        x = dt.datetime.fromisoformat(s2)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.UTC)
        return x.astimezone(dt.UTC)
    except Exception:
        pass
    # Period strings like 2011Q1 or 2011-01.
    try:
        if len(s) == 7 and s[4] == "-":
            return dt.datetime(int(s[:4]), int(s[5:7]), 1, tzinfo=dt.UTC)
    except Exception:
        pass
    try:
        if len(s) == 6 and s[4].upper() == "Q":
            q = int(s[5])
            month = 1 + (q - 1) * 3
            return dt.datetime(int(s[:4]), month, 1, tzinfo=dt.UTC)
    except Exception:
        pass
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in {".", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def load_csv_rows(path: Path, max_rows: Optional[int] = None) -> Tuple[List[str], List[Dict[str, str]], Optional[str]]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], [], "empty or missing header"
            cols = [c.strip() for c in reader.fieldnames]
            rows: List[Dict[str, str]] = []
            for i, row in enumerate(reader):
                clean = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None}
                rows.append(clean)
                if max_rows is not None and len(rows) >= max_rows:
                    break
            return cols, rows, None
    except Exception as e:
        return [], [], str(e)


def full_csv_row_count(path: Path) -> int:
    # Count data rows without holding whole file in memory.
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            try:
                next(reader)
            except StopIteration:
                return 0
            return sum(1 for _ in reader)
    except Exception:
        return 0


def get_time_range(path: Path, time_columns: List[str]) -> Dict[str, Any]:
    first: Optional[dt.datetime] = None
    last: Optional[dt.datetime] = None
    parseable = 0
    parse_errors = 0
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = None
            for col in time_columns:
                if col in row:
                    t = parse_time_any(row.get(col))
                    if t is not None:
                        break
            if t is None:
                parse_errors += 1
                continue
            parseable += 1
            if first is None or t < first:
                first = t
            if last is None or t > last:
                last = t
    return {
        "first_time_utc": first.isoformat().replace("+00:00", "Z") if first else None,
        "last_time_utc": last.isoformat().replace("+00:00", "Z") if last else None,
        "parseable_time_values": parseable,
        "time_parse_error_count": parse_errors,
    }


def count_missing_and_parse_errors(path: Path, required: List[str], lag_columns: List[str], numeric_columns: List[str], key_columns: List[str]) -> Dict[str, Any]:
    missing_lag = {c: 0 for c in lag_columns}
    lag_parse_errors = {c: 0 for c in lag_columns}
    numeric_missing_or_bad = {c: 0 for c in numeric_columns}
    duplicate_key_count = 0
    seen = set()
    row_count = 0
    sample_bad_rows: List[Dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            row_count += 1
            for c in lag_columns:
                val = row.get(c, "")
                if not str(val).strip():
                    missing_lag[c] += 1
                elif parse_time_any(val) is None:
                    lag_parse_errors[c] += 1
                    if len(sample_bad_rows) < 5:
                        sample_bad_rows.append({"line": idx, "column": c, "value": val, "issue": "lag_parse_error"})
            for c in numeric_columns:
                if parse_float(row.get(c)) is None:
                    numeric_missing_or_bad[c] += 1
                    if len(sample_bad_rows) < 5:
                        sample_bad_rows.append({"line": idx, "column": c, "value": row.get(c, ""), "issue": "numeric_missing_or_bad"})
            if key_columns:
                key = tuple(str(row.get(c, "")).strip() for c in key_columns)
                if key in seen:
                    duplicate_key_count += 1
                else:
                    seen.add(key)
    return {
        "row_count": row_count,
        "missing_lag": missing_lag,
        "lag_parse_errors": lag_parse_errors,
        "numeric_missing_or_bad": numeric_missing_or_bad,
        "duplicate_key_count": duplicate_key_count,
        "sample_bad_rows": sample_bad_rows,
    }


def within_start_grace(first_iso: Optional[str], required_start: Optional[str], grace_days: int) -> bool:
    if not required_start:
        return True
    if not first_iso:
        return False
    f = parse_time_any(first_iso)
    r = parse_time_any(required_start)
    if f is None or r is None:
        return False
    return f <= r + dt.timedelta(days=grace_days)


def evaluate_source(root: Path, source_cfg: Dict[str, Any]) -> Dict[str, Any]:
    rel = source_cfg["target_file"]
    path = root / rel
    required_columns = source_cfg.get("required_columns", [])
    time_columns = source_cfg.get("time_columns", [])
    lag_columns = source_cfg.get("lag_columns", [])
    numeric_columns = source_cfg.get("numeric_columns", [])
    key_columns = source_cfg.get("key_columns", [])
    min_rows = int(source_cfg.get("minimum_rows_for_preflight", 0))
    required_start = source_cfg.get("required_start_utc")
    grace_days = int(source_cfg.get("start_grace_days", 0))
    can_be_forward_only = bool(source_cfg.get("can_be_forward_only", False))
    forward_only_allowed = bool(source_cfg.get("forward_only_allowed", False))

    out: Dict[str, Any] = {
        "manifest_id": source_cfg.get("manifest_id"),
        "priority": source_cfg.get("priority"),
        "target_file": rel,
        "found": path.exists(),
        "minimum_rows_for_preflight": min_rows,
        "required_columns": required_columns,
        "missing_columns": [],
        "row_count": 0,
        "first_time_utc": None,
        "last_time_utc": None,
        "schema_ok": False,
        "row_count_ok": False,
        "time_coverage_ok": False,
        "lag_policy_ok": False,
        "numeric_quality_ok": False,
        "duplicate_key_count": 0,
        "preflight_ok": False,
        "forward_only_governance_ok": False,
        "issues": [],
        "warnings": [],
        "lag_policy": source_cfg.get("lag_policy", ""),
        "required_action": source_cfg.get("required_action", ""),
    }

    if not path.exists():
        out["issues"].append("file missing")
        if can_be_forward_only and forward_only_allowed:
            out["forward_only_governance_ok"] = True
            out["warnings"].append("historical source missing but explicit forward-only governance is allowed by config")
        return out

    cols, preview, read_error = load_csv_rows(path, max_rows=10)
    if read_error:
        out["issues"].append(f"csv read error: {read_error}")
        return out
    missing = [c for c in required_columns if c not in cols]
    out["missing_columns"] = missing
    out["schema_ok"] = len(missing) == 0
    if missing:
        out["issues"].append("missing required columns: " + ";".join(missing))
        return out

    row_count = full_csv_row_count(path)
    out["row_count"] = row_count
    out["row_count_ok"] = row_count >= min_rows
    if row_count == 0:
        out["issues"].append("no data rows")
        if can_be_forward_only and forward_only_allowed:
            out["forward_only_governance_ok"] = True
            out["warnings"].append("historical source has no rows but explicit forward-only governance is allowed by config")
        return out
    if not out["row_count_ok"]:
        out["issues"].append(f"row_count below minimum: rows={row_count} min={min_rows}")

    tr = get_time_range(path, time_columns)
    out.update(tr)
    if tr["parseable_time_values"] <= 0:
        out["issues"].append("no parseable time column values")
        return out

    out["time_coverage_ok"] = within_start_grace(out["first_time_utc"], required_start, grace_days)
    if not out["time_coverage_ok"]:
        out["issues"].append(f"coverage starts after required minimum plus grace: first={out['first_time_utc']} min={required_start} grace_days={grace_days}")
    elif required_start and out["first_time_utc"] and parse_time_any(out["first_time_utc"]) and parse_time_any(required_start) and parse_time_any(out["first_time_utc"]) > parse_time_any(required_start):
        out["warnings"].append(f"coverage starts after calendar minimum but within grace window: first={out['first_time_utc']} min={required_start} grace_days={grace_days}")

    quality = count_missing_and_parse_errors(path, required_columns, lag_columns, numeric_columns, key_columns)
    out["duplicate_key_count"] = quality["duplicate_key_count"]
    out["missing_lag"] = quality["missing_lag"]
    out["lag_parse_errors"] = quality["lag_parse_errors"]
    out["numeric_missing_or_bad"] = quality["numeric_missing_or_bad"]
    out["sample_bad_rows"] = quality["sample_bad_rows"]

    if out["duplicate_key_count"] > 0:
        out["issues"].append(f"duplicate key rows: {out['duplicate_key_count']}")

    bad_lag = sum(quality["missing_lag"].values()) + sum(quality["lag_parse_errors"].values())
    out["lag_policy_ok"] = bad_lag == 0
    if not out["lag_policy_ok"]:
        out["issues"].append(f"lag timestamp missing/parse errors: {bad_lag}")

    bad_num = sum(quality["numeric_missing_or_bad"].values())
    out["numeric_quality_ok"] = bad_num == 0
    if not out["numeric_quality_ok"]:
        out["issues"].append(f"numeric missing/bad values: {bad_num}")

    out["preflight_ok"] = bool(
        out["schema_ok"]
        and out["row_count_ok"]
        and out["time_coverage_ok"]
        and out["lag_policy_ok"]
        and out["numeric_quality_ok"]
        and out["duplicate_key_count"] == 0
    )
    return out


def make_report(summary: Dict[str, Any], checks: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# Stage64J1 - Full-Scope P1/P2 Source Acquisition Preflight (No Order)\n")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    lines.append("## Status\n")
    for k in ["status", "decision", "validation_allowed_for_order_or_promotion", "promotion", "paper_order", "paper_live", "live"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Executive conclusion\n")
    lines.append(summary["executive_conclusion"])
    lines.append("")
    lines.append("## Counts\n")
    for k, v in summary["counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Source preflight table\n")
    lines.append("| manifest_id | priority | found | rows | min_rows | preflight_ok | first | last | issues | warnings |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|---|---|")
    for c in checks:
        issues = "; ".join(c.get("issues") or [])
        warnings = "; ".join(c.get("warnings") or [])
        lines.append(
            f"| `{c.get('manifest_id')}` | `{c.get('priority')}` | {c.get('found')} | {c.get('row_count')} | {c.get('minimum_rows_for_preflight')} | {c.get('preflight_ok')} | {c.get('first_time_utc')} | {c.get('last_time_utc')} | {issues} | {warnings} |"
        )
    lines.append("")
    lines.append("## Decision matrix\n")
    lines.append("| path | status | decision | allowed_next |")
    lines.append("|---|---|---|---|")
    for row in summary["decision_matrix"]:
        lines.append(f"| `{row['path']}` | `{row['status']}` | {row['decision']} | {row['allowed_next']} |")
    lines.append("")
    lines.append("## Program stop triggers retained\n")
    for s in summary["program_stop_triggers_retained"]:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## Operational decision\n")
    lines.append("No validation scan, signal generation, paper-order, paper-live, live, EA promotion, broker connection, or full-scope validation claim is authorized by Stage64J1.")
    lines.append("")
    lines.append("## Next allowed step\n")
    lines.append(f"`{summary['next_allowed_step']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64J1 full-scope source acquisition preflight. No validation/order.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64j1_full_scope_p1_p2_source_acquisition_preflight.json")
    ap.add_argument("--out", default="reports/stage64j1_full_scope_p1_p2_source_acquisition_preflight")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = root / args.config
    cfg = read_json(cfg_path)
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    stage64j_summary_path = root / cfg["inputs"]["stage64j_summary"]
    stage64j_summary = read_json(stage64j_summary_path) if stage64j_summary_path.exists() else {}

    sources = cfg["sources"]
    checks = [evaluate_source(root, s) for s in sources]

    core_ids = set(cfg.get("core_full_scope_manifest_ids", []))
    broker_ids = set(cfg.get("broker_alignment_manifest_ids", []))
    core_checks = [c for c in checks if c["manifest_id"] in core_ids]
    broker_checks = [c for c in checks if c["manifest_id"] in broker_ids]

    core_ready = all(c.get("preflight_ok") or c.get("forward_only_governance_ok") for c in core_checks) and len(core_checks) == len(core_ids)
    broker_ready = all(c.get("preflight_ok") for c in broker_checks) and len(broker_checks) == len(broker_ids)
    full_source_ready_for_dataset_preflight = core_ready

    blocked = [c for c in checks if not (c.get("preflight_ok") or c.get("forward_only_governance_ok"))]
    preflight_ok_count = sum(1 for c in checks if c.get("preflight_ok"))

    if full_source_ready_for_dataset_preflight:
        decision = "FULL_SCOPE_CORE_SOURCES_PASS_STAGE64K_DATASET_PREFLIGHT_ALLOWED_NO_VALIDATION"
        next_step = "Stage64K_FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION"
        status_detail = "Core full-scope sources passed preflight. Broker/spot alignment is still separately required before commercialization if not already passed."
    else:
        decision = "FULL_SCOPE_SOURCE_PREFLIGHT_BLOCKED_CONTINUE_ACQUISITION_OR_PROGRAM_STOP_NO_ORDER"
        next_step = "Stage64J1_CONTINUE_SOURCE_ACQUISITION_OR_PROGRAM_STOP_NO_ORDER"
        status_detail = "Full-scope source acquisition is still blocked. Continue source acquisition under lag policy or stop the macro-regime program; do not retune reduced-scope rules."

    if not broker_ready:
        broker_decision = "BROKER_SPOT_ALIGNMENT_BLOCKED_BEFORE_COMMERCIALIZATION"
    else:
        broker_decision = "BROKER_SPOT_ALIGNMENT_PREFLIGHT_PASS"

    summary = {
        "stage": "Stage64J1_FULL_SCOPE_P1_P2_SOURCE_ACQUISITION_PREFLIGHT_OR_PROGRAM_STOP_NO_ORDER",
        "status": "FULL_SCOPE_SOURCE_ACQUISITION_PREFLIGHT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64j_summary": str(stage64j_summary_path),
        },
        "counts": {
            "sources_required": len(sources),
            "sources_found": sum(1 for c in checks if c.get("found")),
            "sources_preflight_ok": preflight_ok_count,
            "core_full_scope_required": len(core_ids),
            "core_full_scope_preflight_or_governance_ok": sum(1 for c in core_checks if c.get("preflight_ok") or c.get("forward_only_governance_ok")),
            "broker_alignment_required": len(broker_ids),
            "broker_alignment_preflight_ok": sum(1 for c in broker_checks if c.get("preflight_ok")),
            "blocked_source_count": len(blocked),
        },
        "readiness": {
            "core_full_scope_sources_ready_for_dataset_preflight": core_ready,
            "broker_alignment_ready_before_commercialization": broker_ready,
            "full_source_ready_for_dataset_preflight": full_source_ready_for_dataset_preflight,
            "broker_decision": broker_decision,
        },
        "executive_conclusion": status_detail,
        "source_checks": checks,
        "blocked_sources": blocked,
        "decision_matrix": [
            {
                "path": "Reduced-scope P0+VIX",
                "status": "KILLED",
                "decision": "Reference only; no tuning, rescue filter, intraday scan, or promotion.",
                "allowed_next": "None except archival/reference use",
            },
            {
                "path": "Full macro-regime core data",
                "status": "READY" if core_ready else "BLOCKED_BY_SOURCE_PREFLIGHT",
                "decision": "Proceed to full-scope lag-safe dataset preflight only if core sources are ready." if core_ready else "Continue source acquisition or stop the program.",
                "allowed_next": "Stage64K dataset preflight; no validation" if core_ready else "Acquire ETF, central-bank demand, and event-calendar data under lag policy or stop",
            },
            {
                "path": "Broker/spot alignment",
                "status": "READY" if broker_ready else "BLOCKED_BEFORE_COMMERCIALIZATION",
                "decision": "Alignment source passed preflight." if broker_ready else "No broker XAUUSD commercialization claim is allowed.",
                "allowed_next": "Can support later commercialization governance" if broker_ready else "Acquire broker/spot D1 backfill or run alignment audit later",
            },
            {
                "path": "Order / EA / paper-live / live",
                "status": "HARD_BLOCKED",
                "decision": "NO_GO",
                "allowed_next": "None",
            },
        ],
        "program_stop_triggers_retained": stage64j_summary.get("program_stop_triggers", []),
        "next_allowed_step": next_step,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_FULL_SCOPE_VALIDATION_CLAIM",
            "NO_REDUCED_SCOPE_PARAMETER_TWEAKING",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_VALIDATION_SCAN_IN_STAGE64J1",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64j1_full_scope_p1_p2_source_acquisition_preflight_summary.json"),
            "report_md": str(out_dir / "stage64j1_full_scope_p1_p2_source_acquisition_preflight_report.md"),
            "source_checks_csv": str(out_dir / "stage64j1_source_preflight_checks.csv"),
            "blocked_sources_csv": str(out_dir / "stage64j1_blocked_sources.csv"),
            "source_template_manifest_json": str(out_dir / "stage64j1_source_template_manifest.json"),
        },
    }

    flat_fields = [
        "manifest_id", "priority", "target_file", "found", "row_count", "minimum_rows_for_preflight",
        "schema_ok", "row_count_ok", "time_coverage_ok", "lag_policy_ok", "numeric_quality_ok",
        "duplicate_key_count", "preflight_ok", "forward_only_governance_ok", "first_time_utc", "last_time_utc",
        "lag_policy", "required_action", "issues", "warnings"
    ]
    flat_rows = []
    for c in checks:
        r = {k: c.get(k, "") for k in flat_fields}
        r["issues"] = "; ".join(c.get("issues") or [])
        r["warnings"] = "; ".join(c.get("warnings") or [])
        flat_rows.append(r)
    write_csv(out_dir / "stage64j1_source_preflight_checks.csv", flat_rows, flat_fields)
    write_csv(out_dir / "stage64j1_blocked_sources.csv", [r for r in flat_rows if not (str(r.get("preflight_ok")) == "True" or str(r.get("forward_only_governance_ok")) == "True")], flat_fields)

    template_manifest = {
        "stage": summary["stage"],
        "generated_utc": summary["generated_utc"],
        "templates": [
            {
                "manifest_id": s.get("manifest_id"),
                "target_file": s.get("target_file"),
                "required_columns": s.get("required_columns"),
                "minimum_rows_for_preflight": s.get("minimum_rows_for_preflight"),
                "lag_policy": s.get("lag_policy"),
                "required_action": s.get("required_action"),
            }
            for s in sources
        ],
        "note": "This manifest is schema guidance only. Stage64J1 does not create or fetch source data by default.",
    }
    write_json(out_dir / "stage64j1_source_template_manifest.json", template_manifest)
    write_json(out_dir / "stage64j1_full_scope_p1_p2_source_acquisition_preflight_summary.json", summary)
    (out_dir / "stage64j1_full_scope_p1_p2_source_acquisition_preflight_report.md").write_text(make_report(summary, checks), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
