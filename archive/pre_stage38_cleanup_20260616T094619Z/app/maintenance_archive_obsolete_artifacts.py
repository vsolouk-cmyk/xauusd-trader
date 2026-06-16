#!/usr/bin/env python3
"""
Maintenance — Archive obsolete workflows/reports safely

Default mode is audit-only.
Use --apply to move files.

Policy:
- Keep active collector workflow:
  .github/workflows/xauusd_collectors.yml
- Keep workflows that look like data collectors if they exist.
- Archive probe/lab/old pipeline workflows.
- Archive old lab report directories while keeping active collector reports.

Hard rules:
- Does not delete files.
- Moves to archive/project_housekeeping/<timestamp>/...
- Writes archive manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict


TOOL_VERSION = "v1"
DEFAULT_ARCHIVE_ROOT = Path("archive/project_housekeeping")


ACTIVE_WORKFLOW_KEEP = {
    "xauusd_collectors.yml",
    "xauusd_collectors.yaml",
}

WORKFLOW_KEEP_KEYWORDS = [
    "collector",
    "collectors",
    "data_refresh",
]

WORKFLOW_ARCHIVE_KEYWORDS = [
    "gdelt_probe",
    "pipeline_runner",
    "stage4",
    "stage5",
    "stage6",
    "stage7",
    "stage8",
    "stage9",
    "stage10",
    "probe",
    "lab",
]

ACTIVE_REPORT_KEEP = {
    "stage10b_event_pipeline_update",
    "stage9b_macro_numeric_update",
    "stage9b_macro_event_calendar_update",
    "macro_numeric_update",
    "macro_event_calendar_update",
    "workflow_metadata",
}


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def classify_workflow(path: Path) -> str:
    name = path.name.lower()
    if path.name in ACTIVE_WORKFLOW_KEEP:
        return "keep_active"
    if any(k in name for k in WORKFLOW_KEEP_KEYWORDS):
        return "keep_collector_like"
    if name in {"event_pipeline_update.yml", "event_pipeline_update.yaml", "macro_numeric_update.yml", "macro_numeric_update.yaml", "macro_event_calendar_update.yml", "macro_event_calendar_update.yaml"}:
        return "archive_replaced_by_xauusd_collectors"
    if any(k in name for k in WORKFLOW_ARCHIVE_KEYWORDS):
        return "archive_obsolete_or_lab"
    return "review_keep_unknown"


def classify_report_dir(path: Path) -> str:
    name = path.name.lower()
    if name in ACTIVE_REPORT_KEEP:
        return "keep_active_collector_report"
    if name.startswith("stage") and any(name.startswith(f"stage{i}") for i in range(2, 11)):
        return "archive_completed_research_report"
    if "probe" in name or "lab" in name:
        return "archive_probe_or_lab_report"
    return "review_keep_unknown"


def move_item(src: Path, dest_root: Path, category: str, apply: bool) -> Dict:
    dest = dest_root / category / src.as_posix()
    rec = {
        "source": str(src),
        "destination": str(dest),
        "category": category,
        "action": "move" if apply else "would_move",
        "exists": src.exists(),
    }
    if apply and src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    return rec


def run(apply: bool, archive_root: Path, archive_code: bool) -> int:
    stamp = now_stamp()
    dest_root = archive_root / stamp
    manifest: List[Dict] = []

    # Workflows.
    wf_dir = Path(".github/workflows")
    if wf_dir.exists():
        for p in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))):
            cls = classify_workflow(p)
            if cls.startswith("archive"):
                manifest.append(move_item(p, dest_root, "workflows", apply))
            else:
                manifest.append({"source": str(p), "classification": cls, "action": "keep", "exists": p.exists()})

    # Reports.
    reports_dir = Path("data/reports")
    if reports_dir.exists():
        for p in sorted([x for x in reports_dir.iterdir() if x.is_dir()]):
            cls = classify_report_dir(p)
            if cls.startswith("archive"):
                manifest.append(move_item(p, dest_root, "reports", apply))
            else:
                manifest.append({"source": str(p), "classification": cls, "action": "keep", "exists": p.exists()})

    # Optional code archive: conservative, disabled by default.
    if archive_code:
        app_dir = Path("app")
        keep_code = {
            "stage9b_macro_numeric_update.py",
            "stage9b_macro_event_calendar_update.py",
            "stage10b_event_pipeline_update.py",
            "stage10c_numeric_shock_event_backfill.py",
            "stage10a_event_impact_lab.py",
            "stage10d_event_impact_validation_lab.py",
            "stage10e_event_aware_guard_simulation.py",
            "stage11a_downtrend_short_thesis_lab.py",
        }
        if app_dir.exists():
            for p in sorted(app_dir.glob("stage*.py")):
                if p.name in keep_code:
                    manifest.append({"source": str(p), "classification": "keep_required_pipeline_or_current_stage", "action": "keep", "exists": p.exists()})
                else:
                    manifest.append(move_item(p, dest_root, "app_scripts", apply))

    dest_root.mkdir(parents=True, exist_ok=True)
    meta = {
        "tool_version": TOOL_VERSION,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "apply": apply,
        "archive_code": archive_code,
        "archive_root": str(dest_root),
        "manifest": manifest,
    }
    (dest_root / "archive_manifest.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Project Housekeeping Archive Manifest",
        "",
        f"- generated_utc: `{meta['generated_utc']}`",
        f"- apply: `{apply}`",
        f"- archive_code: `{archive_code}`",
        f"- archive_root: `{dest_root}`",
        "",
        "| Action | Classification/Category | Source | Destination |",
        "|---|---|---|---|",
    ]
    for r in manifest:
        md.append(f"| {r.get('action','')} | {r.get('classification') or r.get('category','')} | {r.get('source','')} | {r.get('destination','')} |")
    (dest_root / "archive_manifest.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("Project housekeeping archive: DONE")
    print(f"apply={apply} archive_code={archive_code}")
    print(f"Manifest: {dest_root / 'archive_manifest.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually move archive candidates. Without this, audit only.")
    p.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    p.add_argument("--archive-code", action="store_true", help="Also archive old app/stage*.py scripts not in the keep list.")
    args = p.parse_args()
    return run(args.apply, Path(args.archive_root), args.archive_code)


if __name__ == "__main__":
    raise SystemExit(main())
