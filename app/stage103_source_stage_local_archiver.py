#!/usr/bin/env python3
"""Stage103 Source Stage Local Archiver.

Archives superseded stage source files from app/configs/docs/tests into an ignored local zip,
then removes those files from the working tree only after the zip is written and verified.
No runtime market data is touched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def append_gitignore(root: Path, block: str) -> Dict[str, Any]:
    gi = root / ".gitignore"
    exists = gi.exists()
    before = gi.read_text(encoding="utf-8") if exists else ""
    present_before = block.strip() in before
    applied = False
    if not present_before:
        with gi.open("a", encoding="utf-8") as f:
            if before and not before.endswith("\n"):
                f.write("\n")
            f.write("\n" + block.rstrip() + "\n")
        applied = True
    return {"path": str(gi), "exists_before": exists, "block_present_before_apply": present_before, "applied": applied}


def run_git_status(root: Path) -> List[str]:
    try:
        cp = subprocess.run(["git", "status", "--short"], cwd=str(root), text=True, capture_output=True, check=False)
        if cp.returncode != 0:
            return [f"GIT_STATUS_ERROR: {cp.stderr.strip()}"]
        return [line for line in cp.stdout.splitlines() if line.strip()]
    except Exception as e:
        return [f"GIT_STATUS_EXCEPTION: {e}"]


def extract_stage_number(path: Path, regex: re.Pattern[str]) -> Optional[int]:
    m = regex.search(path.name.lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def should_preserve(path: Path, stage_num: Optional[int], cfg: Dict[str, Any]) -> bool:
    name_l = path.name.lower()
    for needle in cfg.get("preserve_name_contains", []):
        if str(needle).lower() in name_l:
            return True
    if stage_num is not None and stage_num in set(int(x) for x in cfg.get("preserve_stage_numbers", [])):
        return True
    return False


def discover_candidates(root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    regex = re.compile(cfg.get("stage_filename_regex", r"stage([0-9]{1,3})"), re.IGNORECASE)
    stage_min = int(cfg.get("archive_stage_min", 1))
    stage_max = int(cfg.get("archive_stage_max", 102))
    rows: List[Dict[str, Any]] = []
    for d in cfg.get("source_dirs", []):
        base = root / d
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if ".git" in rel.parts:
                continue
            stage_num = extract_stage_number(path, regex)
            if stage_num is None:
                continue
            in_range = stage_min <= stage_num <= stage_max
            preserve = should_preserve(path, stage_num, cfg)
            archive = in_range and not preserve
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            rows.append({
                "relative_path": str(rel),
                "stage_num": stage_num,
                "size_bytes": size,
                "sha256": sha256_file(path),
                "archive_candidate": archive,
                "preserved": preserve,
                "reason": "preserved_current_operational_or_archiver" if preserve else ("archive_superseded_stage_source" if archive else "outside_archive_range"),
            })
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def create_archive_and_remove(root: Path, cfg: Dict[str, Any], candidates: List[Dict[str, Any]], apply: bool) -> Dict[str, Any]:
    archive_candidates = [r for r in candidates if r["archive_candidate"]]
    archive_root = root / cfg.get("archive_root", "_local_archive/source_stage_archives")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_root / f"stage103_superseded_source_stages_{stamp}.archive.zip"
    manifest_name = "stage103_manifest.json"

    result: Dict[str, Any] = {
        "archive_root": str(archive_root),
        "archive_path": str(archive_path),
        "apply": apply,
        "archive_candidate_count": len(archive_candidates),
        "archived_file_count": 0,
        "removed_file_count": 0,
        "archive_sha256": None,
        "verified": False,
        "errors": [],
    }
    if not apply:
        return result
    if not archive_candidates:
        archive_root.mkdir(parents=True, exist_ok=True)
        return result

    archive_root.mkdir(parents=True, exist_ok=True)
    # Build zip directly from original files; remove only after verifying zip contains all files.
    manifest = {
        "stage": "Stage103_SOURCE_STAGE_LOCAL_ARCHIVER",
        "generated_utc": utc_now(),
        "root": str(root),
        "principle": "Archive superseded stage source files locally before removing them from working tree. No runtime data deletion.",
        "files": archive_candidates,
    }
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(manifest_name, json.dumps(manifest, indent=2, ensure_ascii=False))
            for r in archive_candidates:
                src = root / r["relative_path"]
                if not src.exists():
                    result["errors"].append(f"missing_before_archive:{r['relative_path']}")
                    continue
                zf.write(src, arcname=r["relative_path"])
                result["archived_file_count"] += 1
        # Verify zip integrity and expected entries.
        with zipfile.ZipFile(archive_path, "r") as zf:
            bad = zf.testzip()
            names = set(zf.namelist())
            if bad:
                result["errors"].append(f"zip_bad_entry:{bad}")
            missing = [r["relative_path"] for r in archive_candidates if r["relative_path"] not in names]
            if missing:
                result["errors"].append("zip_missing_entries:" + ",".join(missing[:20]))
            result["verified"] = (bad is None and not missing)
        if not result["verified"]:
            return result
        result["archive_sha256"] = sha256_file(archive_path)
        # Remove source files only after successful verification.
        for r in archive_candidates:
            src = root / r["relative_path"]
            if src.exists() and src.is_file():
                src.unlink()
                result["removed_file_count"] += 1
        # Remove empty directories inside source dirs, but not the source dirs themselves.
        for d in cfg.get("source_dirs", []):
            base = root / d
            if not base.exists():
                continue
            for p in sorted(base.rglob("*"), key=lambda x: len(x.parts), reverse=True):
                if p.is_dir():
                    try:
                        p.rmdir()
                    except OSError:
                        pass
    except Exception as e:
        result["errors"].append(str(e))
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg = read_json(Path(args.config).expanduser().resolve())
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    gi_meta = append_gitignore(root, cfg.get("gitignore_block", "")) if cfg.get("append_gitignore", True) else {"applied": False}
    before_status = run_git_status(root)
    candidates = discover_candidates(root, cfg)
    archive_candidates = [r for r in candidates if r["archive_candidate"]]
    preserved = [r for r in candidates if r["preserved"]]

    write_csv(out / "stage103_source_stage_archive_plan.csv", candidates)
    archive_result = create_archive_and_remove(root, cfg, candidates, args.apply)
    after_status = run_git_status(root)

    summary = {
        "stage": "Stage103_SOURCE_STAGE_LOCAL_ARCHIVER",
        "root": str(root),
        "config": str(Path(args.config).expanduser().resolve()),
        "generated_utc": utc_now(),
        "status": "STAGE103_COMPLETE_NO_PROMOTION",
        "decision": "STAGE103_SOURCE_STAGE_ARCHIVE_APPLIED_NO_DELETE" if args.apply else "STAGE103_SOURCE_STAGE_ARCHIVE_PLAN_READY_NO_DELETE",
        "classification": "S103_SOURCE_STAGE_ARCHIVE_APPLIED" if args.apply else "S103_SOURCE_STAGE_ARCHIVE_PLAN_READY",
        "disposition": "COMMIT_ARCHIVE_CLEANUP_AFTER_REVIEW" if args.apply else "REVIEW_PLAN_THEN_RUN_WITH_APPLY",
        "principle": "Archive superseded stage source files locally before removing them from app/configs/docs/tests. Runtime data is not deleted.",
        "apply": args.apply,
        "gitignore": gi_meta,
        "candidate_count": len(candidates),
        "archive_candidate_count": len(archive_candidates),
        "preserved_count": len(preserved),
        "archive_candidate_size_bytes": sum(int(r.get("size_bytes", 0)) for r in archive_candidates),
        "preserved_stage_files_sample": preserved[:20],
        "archive_candidate_sample": archive_candidates[:30],
        "archive_result": archive_result,
        "git_status_short_before_count": len(before_status),
        "git_status_short_before_sample": before_status[:40],
        "git_status_short_after_count": len(after_status),
        "git_status_short_after_sample": after_status[:80],
        "hard_blocks": cfg.get("hard_blocks", []),
        "outputs": {
            "summary_json": str(out / "stage103_source_stage_local_archiver_summary.json"),
            "report_md": str(out / "stage103_source_stage_local_archiver_report.md"),
            "archive_plan_csv": str(out / "stage103_source_stage_archive_plan.csv"),
            "local_archive_zip": archive_result.get("archive_path"),
        },
    }
    (out / "stage103_source_stage_local_archiver_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report = [
        "# Stage103 Source Stage Local Archiver",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Counts",
        f"- candidate_count: `{summary['candidate_count']}`",
        f"- archive_candidate_count: `{summary['archive_candidate_count']}`",
        f"- preserved_count: `{summary['preserved_count']}`",
        f"- apply: `{summary['apply']}`",
        "",
        "## Archive result",
        f"- archive_path: `{archive_result.get('archive_path')}`",
        f"- archived_file_count: `{archive_result.get('archived_file_count')}`",
        f"- removed_file_count: `{archive_result.get('removed_file_count')}`",
        f"- verified: `{archive_result.get('verified')}`",
        f"- errors: `{archive_result.get('errors')}`",
        "",
        "## Hard blocks",
    ]
    report.extend([f"- `{x}`" for x in cfg.get("hard_blocks", [])])
    (out / "stage103_source_stage_local_archiver_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "decision": summary["decision"], "archive_candidate_count": len(archive_candidates), "removed_file_count": archive_result.get("removed_file_count"), "errors": archive_result.get("errors", [])}, ensure_ascii=False))
    return 0 if not archive_result.get("errors") else 2


if __name__ == "__main__":
    raise SystemExit(main())
