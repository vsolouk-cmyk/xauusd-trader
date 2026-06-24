#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_source_map(fetch_summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in fetch_summary.get("results", []) or []:
        target = str(item.get("target_file", ""))
        if target:
            out[Path(target).name] = item
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    cfg = load_json(cfg_path)

    d4_path = root / cfg["inputs"]["stage64d4_summary"]
    fetch_path = root / cfg["inputs"]["local_fetch_summary"]
    d4 = load_json(d4_path)
    fetch = load_json(fetch_path) if fetch_path.exists() else {"results": [], "errors": [{"target": "local_fetch_summary", "error": "missing"}]}
    source_by_file = build_source_map(fetch)

    checks = d4.get("checks", []) or []
    by_manifest = {c.get("manifest_id"): c for c in checks}
    full_ids = cfg["scope_rules"]["full_scope_required_manifest_ids"]
    reduced_ids = cfg["scope_rules"]["reduced_scope_required_manifest_ids"]

    readiness_rows: List[Dict[str, Any]] = []
    for mid in full_ids:
        c = by_manifest.get(mid, {})
        target = c.get("target_file", "")
        source_info = source_by_file.get(Path(target).name, {})
        row = {
            "manifest_id": mid,
            "priority": c.get("priority", ""),
            "target_file": target,
            "preflight_ok": bool(c.get("preflight_ok")),
            "row_count": c.get("row_count", 0),
            "first_time_utc": c.get("first_time_utc"),
            "last_time_utc": c.get("last_time_utc"),
            "source": source_info.get("source", ""),
            "source_url": source_info.get("url", ""),
            "issues": "; ".join(c.get("issues", []) or []),
            "warnings": "; ".join(c.get("warnings", []) or []),
        }
        readiness_rows.append(row)

    p0_ids = [mid for mid in full_ids if by_manifest.get(mid, {}).get("priority") == "P0_CRITICAL"]
    p1_ids = [mid for mid in full_ids if by_manifest.get(mid, {}).get("priority") == "P1_HIGH"]
    p2_ids = [mid for mid in full_ids if by_manifest.get(mid, {}).get("priority") == "P2_MEDIUM"]

    def count_ok(ids: List[str]) -> int:
        return sum(1 for mid in ids if bool(by_manifest.get(mid, {}).get("preflight_ok")))

    p0_ok = count_ok(p0_ids)
    p1_ok = count_ok(p1_ids)
    p2_ok = count_ok(p2_ids)
    reduced_ok = all(bool(by_manifest.get(mid, {}).get("preflight_ok")) for mid in reduced_ids)
    full_ok = all(bool(by_manifest.get(mid, {}).get("preflight_ok")) for mid in full_ids)

    gold_source = source_by_file.get("gold_d1_ohlc_2011_present.csv", {}).get("source", "")
    gold_reference_warning = ""
    if "GC_F" in gold_source or "FUTURES" in gold_source:
        gold_reference_warning = "Gold D1 source is COMEX continuous futures reference, not broker spot XAUUSD; validation must treat it as reference gold proxy unless broker/spot D1 backfill is acquired."

    decision = "FULL_SCOPE_DATA_READY_RERUN_STAGE64D_NO_VALIDATION" if full_ok else (
        "REDUCED_SCOPE_P0_PLUS_VIX_READY_FULL_SCOPE_BLOCKED_NO_VALIDATION" if reduced_ok else "DATA_NOT_READY_NO_VALIDATION"
    )

    summary = {
        "stage": "Stage64D5_SELECTED_SCOPE_DATA_READINESS_AUDIT_NO_PROMOTION",
        "status": "SELECTED_SCOPE_DATA_READINESS_AUDIT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": False,
        "generated_utc": now_utc(),
        "root": str(root),
        "inputs": {
            "stage64d4_summary": str(d4_path),
            "local_fetch_summary": str(fetch_path),
        },
        "counts": {
            "full_scope_required": len(full_ids),
            "full_scope_preflight_ok": count_ok(full_ids),
            "p0_required": len(p0_ids),
            "p0_preflight_ok": p0_ok,
            "p1_required": len(p1_ids),
            "p1_preflight_ok": p1_ok,
            "p2_required": len(p2_ids),
            "p2_preflight_ok": p2_ok,
            "reduced_scope_required": len(reduced_ids),
            "reduced_scope_preflight_ok": count_ok(reduced_ids),
        },
        "scope_readiness": {
            "p0_ready": p0_ok == len(p0_ids),
            "p0_plus_vix_ready": reduced_ok,
            "full_scope_ready": full_ok,
            "reduced_scope_candidate_id": cfg["scope_rules"]["reduced_scope_candidate_id"],
            "reduced_scope_ids": reduced_ids,
            "full_scope_blockers": [r for r in readiness_rows if not r["preflight_ok"]],
        },
        "source_warnings": [w for w in [gold_reference_warning] if w],
        "next_allowed_step": "Stage64E_REDUCED_SCOPE_PREDECLARATION_OR_STAGE64D6_P1_SOURCE_ACQUISITION_NO_ORDER" if reduced_ok and not full_ok else "RERUN_STAGE64D_FULL_SCOPE_NO_ORDER",
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_HISTORICAL_VALIDATION_SCAN_UNTIL_EXPLICIT_PREDECLARATION_AND_STAGE64D_UNLOCK",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64d5_selected_scope_data_readiness_audit_summary.json"),
            "report_md": str(out_dir / "stage64d5_selected_scope_data_readiness_audit_report.md"),
            "readiness_csv": str(out_dir / "stage64d5_selected_scope_readiness.csv"),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "stage64d5_selected_scope_data_readiness_audit_summary.json", summary)
    write_csv(
        out_dir / "stage64d5_selected_scope_readiness.csv",
        readiness_rows,
        ["manifest_id", "priority", "target_file", "preflight_ok", "row_count", "first_time_utc", "last_time_utc", "source", "source_url", "issues", "warnings"],
    )

    with (out_dir / "stage64d5_selected_scope_data_readiness_audit_report.md").open("w", encoding="utf-8") as f:
        f.write("# Stage64D5 - Selected Scope Data Readiness Audit\n\n")
        f.write(f"Generated UTC: `{summary['generated_utc']}`\n\n")
        f.write("## Status\n\n")
        f.write(f"- status: `{summary['status']}`\n")
        f.write(f"- decision: `{summary['decision']}`\n")
        f.write("- validation_allowed: `false`\n")
        f.write("- promotion/paper/live: `NO_GO`\n\n")
        f.write("## Executive conclusion\n\n")
        if full_ok:
            f.write("All full-scope raw source files passed preflight. Rerun Stage64D before any validation decision.\n\n")
        elif reduced_ok:
            f.write("P0 plus VIX source files passed preflight, but full macro-regime scope remains blocked because ETF holdings/flows, central-bank gold demand, and historical event calendar files are not populated. No validation is authorized. The next decision is whether to predeclare a reduced-scope P0+VIX feasibility validation or continue P1 source acquisition.\n\n")
        else:
            f.write("Selected source scope is not ready. Continue data acquisition before any Stage64D rerun.\n\n")
        if gold_reference_warning:
            f.write(f"**Source warning:** {gold_reference_warning}\n\n")
        f.write("## Counts\n\n")
        for k, v in summary["counts"].items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Readiness table\n\n")
        f.write("| manifest_id | priority | preflight_ok | rows | first | last | source | issues |\n")
        f.write("|---|---|---:|---:|---|---|---|---|\n")
        for r in readiness_rows:
            f.write(f"| `{r['manifest_id']}` | {r['priority']} | {r['preflight_ok']} | {r['row_count']} | {r['first_time_utc']} | {r['last_time_utc']} | `{r['source']}` | {r['issues']} |\n")
        f.write("\n## Operational decision\n\n")
        f.write("No historical validation scan, order, paper-live, live, EA promotion, or broker connection is authorized by this audit.\n\n")
        f.write("## Next allowed step\n\n")
        f.write(f"`{summary['next_allowed_step']}`\n")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
