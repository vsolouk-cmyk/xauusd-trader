"""Archive inactive XAUUSD project artifacts safely.

Default mode is dry-run. It moves files/directories to _archive/inactive_<timestamp>
only when --apply is provided. It does not delete anything.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Set

ACTIVE_APP_MODULES: Set[str] = {
    "stage16e_amarkets_csv_refresh_cycle.py",
    "stage16c_true_forward_shadow_collector.py",
    "stage17d_broker_time_forward_shadow_collector.py",
    "stage18e_shortlist_forward_shadow_collector.py",
    "stage18a_unified_shadow_ops_cycle.py",
    "stage23d_forward_shadow_candidate.py",
    "stage25c_deduped_filter_validation.py",
    "stage25d_db_first_filtered_forward_shadow.py",
    "stage27b_db_first_lineage_gate_discovery.py",
    "stage27c_db_first_h1_atr_gate_validation.py",
    "stage27d_db_first_h1_atr_filtered_forward_shadow.py",
    "stage28a_discovery_factory_batch_runner.py",
    "run_active_shadow_suite.py",
}

ACTIVE_REPORT_DIRS: Set[str] = {
    "stage16e_amarkets_csv_refresh_cycle",
    "stage16c_true_forward_shadow_collector",
    "stage17d_broker_time_forward_shadow_collector",
    "stage18e_shortlist_forward_shadow_collector",
    "stage18a_unified_shadow_ops_cycle",
    "stage23d_forward_shadow_candidate",
    "stage25c_deduped_filter_validation",
    "stage25d_db_first_filtered_forward_shadow",
    "stage27b_db_first_lineage_gate_discovery",
    "stage27c_db_first_h1_atr_gate_validation",
    "stage27d_db_first_h1_atr_filtered_forward_shadow",
    "stage28a_discovery_factory_batch_runner",
    "active_shadow_suite",
}

ACTIVE_DOC_KEYWORDS = [
    "PROJECT_RULES", "TRANSFER", "BASELINE", "STAGE25C", "STAGE27B", "STAGE27C", "STAGE27D", "STAGE28A", "ACTIVE", "README_STAGE28A",
]

ACTIVE_WORKFLOW_KEYWORDS = ["xauusd", "shadow", "refresh", "active", "stage18", "stage23", "stage25", "stage27", "stage28"]


def _archive_path(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return root / "_archive" / f"inactive_{stamp}"


def _move(src: Path, dest_root: Path, root: Path, apply: bool, actions: List[dict]) -> None:
    rel = src.relative_to(root)
    dest = dest_root / rel
    actions.append({"action": "archive", "source": str(src), "destination": str(dest), "applied": apply})
    if apply:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))


def archive(root: Path, apply: bool, include_workflows: bool) -> List[dict]:
    actions: List[dict] = []
    dest_root = _archive_path(root)

    app_dir = root / "app"
    if app_dir.exists():
        for p in sorted(app_dir.glob("stage*.py")):
            if p.name not in ACTIVE_APP_MODULES:
                _move(p, dest_root, root, apply, actions)

    reports_dir = root / "data" / "reports"
    if reports_dir.exists():
        for p in sorted(reports_dir.iterdir()):
            if p.is_dir() and p.name.startswith("stage") and p.name not in ACTIVE_REPORT_DIRS:
                _move(p, dest_root, root, apply, actions)

    docs_dir = root / "docs"
    if docs_dir.exists():
        for p in sorted(docs_dir.glob("*.md")):
            name = p.name.upper()
            if name.startswith("STAGE") and not any(k in name for k in ACTIVE_DOC_KEYWORDS):
                _move(p, dest_root, root, apply, actions)

    if include_workflows:
        wf_dir = root / ".github" / "workflows"
        if wf_dir.exists():
            for p in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
                name = p.name.lower()
                if not any(k.lower() in name for k in ACTIVE_WORKFLOW_KEYWORDS):
                    _move(p, dest_root, root, apply, actions)

    manifest = dest_root / "archive_manifest.json"
    actions.append({"action": "write_manifest", "destination": str(manifest), "applied": apply})
    if apply:
        dest_root.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(actions, indent=2, ensure_ascii=False), encoding="utf-8")
    return actions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Project root, default current directory")
    parser.add_argument("--apply", action="store_true", help="Actually move files. Default is dry-run")
    parser.add_argument("--include-workflows", action="store_true", help="Also archive inactive .github/workflows files")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    actions = archive(root, args.apply, args.include_workflows)
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", "root": str(root), "actions": actions}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
