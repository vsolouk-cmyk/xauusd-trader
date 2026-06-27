#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


@dataclass
class CleanupItem:
    path: str
    kind: str
    size_bytes: int
    action: str
    reason: str
    deleted: bool = False
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def path_size(p: Path) -> int:
    if not p.exists() and not p.is_symlink():
        return 0
    if p.is_file() or p.is_symlink():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for q in p.rglob("*"):
        try:
            if q.is_file() or q.is_symlink():
                total += q.stat().st_size
        except OSError:
            pass
    return total


def git_status(root: Path) -> list[str]:
    try:
        cp = subprocess.run(["git", "status", "--short"], cwd=root, text=True, capture_output=True, timeout=20)
        if cp.returncode != 0:
            return [f"GIT_STATUS_ERROR: {cp.stderr.strip()}"]
        return [line for line in cp.stdout.splitlines() if line.strip()]
    except Exception as e:
        return [f"GIT_STATUS_EXCEPTION: {e}"]


def git_ignored(root: Path, max_lines: int = 500) -> list[str]:
    try:
        cp = subprocess.run(["git", "status", "--ignored", "--short"], cwd=root, text=True, capture_output=True, timeout=30)
        if cp.returncode != 0:
            return [f"GIT_IGNORED_ERROR: {cp.stderr.strip()}"]
        lines = [line for line in cp.stdout.splitlines() if line.startswith("!! ")]
        return lines[:max_lines]
    except Exception as e:
        return [f"GIT_IGNORED_EXCEPTION: {e}"]


def resolve_targets(root: Path, patterns: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for pat in patterns:
        matches = list(root.glob(pat))
        # root.glob('*.zip') only top-level; intentional. For .DS_Store and __pycache__ use ** patterns.
        for m in matches:
            try:
                rel = safe_rel(root, m)
            except Exception:
                continue
            if rel not in seen:
                seen.add(rel)
                out.append(m)
    return sorted(out, key=lambda p: safe_rel(root, p))


def is_protected(root: Path, p: Path, protected: list[str]) -> bool:
    rel = safe_rel(root, p)
    rel_slash = rel.rstrip("/")
    for prot in protected:
        prot = prot.rstrip("/")
        if rel_slash == prot or rel_slash.startswith(prot + "/"):
            return True
    # Never allow deleting core source/control directories.
    top = rel_slash.split("/", 1)[0]
    if top in {".git", "app", "configs", "docs", "tests", "mt5"}:
        return True
    return False


def delete_item(p: Path) -> None:
    if not p.exists() and not p.is_symlink():
        return
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        p.unlink()


def write_csv(path: Path, rows: list[CleanupItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(CleanupItem("", "", 0, "", "")).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def write_md(path: Path, summary: dict, items: list[CleanupItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stage102 Repo Runtime Folder Cleaner",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Cleanup",
        f"- apply: `{summary['apply']}`",
        f"- include_generated_data: `{summary['include_generated_data']}`",
        f"- candidate_count: `{summary['candidate_count']}`",
        f"- candidate_size_bytes: `{summary['candidate_size_bytes']}`",
        f"- deleted_count: `{summary['deleted_count']}`",
        f"- deleted_size_bytes: `{summary['deleted_size_bytes']}`",
        "",
        "## Git status after",
    ]
    for line in summary.get("git_status_short_after", [])[:50]:
        lines.append(f"- `{line}`")
    if not summary.get("git_status_short_after"):
        lines.append("- clean")
    lines += ["", "## Top cleanup items"]
    for item in sorted(items, key=lambda x: x.size_bytes, reverse=True)[:20]:
        lines.append(f"- `{item.path}` kind=`{item.kind}` size=`{item.size_bytes}` action=`{item.action}` deleted=`{item.deleted}` error=`{item.error or ''}`")
    lines += ["", "## Hard blocks"]
    for hb in summary.get("hard_blocks", []):
        lines.append(f"- `{hb}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true", help="Actually delete safe runtime targets. Default is dry-run.")
    ap.add_argument("--include-generated-data", action="store_true", help="Also clean ignored generated data. Use only after confirming rebuild paths.")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    cfg = load_json(Path(args.config).expanduser().resolve())
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    patterns = list(cfg.get("safe_runtime_targets", []))
    if args.include_generated_data:
        patterns += list(cfg.get("optional_generated_data_targets", []))
    protected = list(cfg.get("protected_top_level", []))

    candidates: list[CleanupItem] = []
    for p in resolve_targets(root, patterns):
        try:
            rel = safe_rel(root, p)
        except Exception as e:
            candidates.append(CleanupItem(str(p), "unknown", 0, "SKIP", "outside_root", False, str(e)))
            continue
        kind = "dir" if p.is_dir() and not p.is_symlink() else "file"
        size = path_size(p)
        if is_protected(root, p, protected):
            candidates.append(CleanupItem(rel, kind, size, "SKIP", "protected_path"))
        else:
            candidates.append(CleanupItem(rel, kind, size, "DELETE_IF_APPLY", "runtime_or_ignored_artifact"))

    deleted_count = 0
    deleted_size = 0
    if args.apply:
        for item in candidates:
            if item.action != "DELETE_IF_APPLY":
                continue
            p = root / item.path
            try:
                delete_item(p)
                item.deleted = True
                deleted_count += 1
                deleted_size += item.size_bytes
            except Exception as e:
                item.error = str(e)

    git_after = git_status(root)
    ignored_after = git_ignored(root)
    candidate_size = sum(i.size_bytes for i in candidates if i.action == "DELETE_IF_APPLY")
    status = "STAGE102_COMPLETE_NO_PROMOTION"
    decision = "STAGE102_RUNTIME_CLEANUP_APPLIED_NO_DELETE_CORE" if args.apply else "STAGE102_RUNTIME_CLEANUP_DRY_RUN_READY_NO_DELETE"
    classification = "S102_RUNTIME_CLEANUP_APPLIED" if args.apply else "S102_DRY_RUN_READY"
    disposition = "RUNTIME_FOLDERS_CLEANED" if args.apply else "REVIEW_AND_RERUN_WITH_APPLY"

    summary = {
        "stage": "Stage102_REPO_RUNTIME_FOLDER_CLEANER",
        "root": str(root),
        "config": str(Path(args.config).expanduser().resolve()),
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "apply": bool(args.apply),
        "include_generated_data": bool(args.include_generated_data),
        "candidate_count": len([i for i in candidates if i.action == "DELETE_IF_APPLY"]),
        "candidate_size_bytes": candidate_size,
        "deleted_count": deleted_count,
        "deleted_size_bytes": deleted_size,
        "skipped_count": len([i for i in candidates if i.action == "SKIP"]),
        "git_status_short_after_count": len(git_after),
        "git_status_short_after": git_after,
        "git_ignored_short_after_count_sampled": len(ignored_after),
        "git_ignored_short_after_sample": ignored_after[:100],
        "outputs": {
            "summary_json": str(out / "stage102_repo_runtime_folder_cleaner_summary.json"),
            "report_md": str(out / "stage102_repo_runtime_folder_cleaner_report.md"),
            "cleanup_plan_csv": str(out / "stage102_cleanup_plan.csv"),
        },
        "hard_blocks": cfg.get("hard_blocks", []),
    }

    write_csv(out / "stage102_cleanup_plan.csv", candidates)
    (out / "stage102_repo_runtime_folder_cleaner_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(out / "stage102_repo_runtime_folder_cleaner_report.md", summary, candidates)
    print(json.dumps({"status": status, "decision": decision, "candidate_count": summary["candidate_count"], "deleted_count": deleted_count, "git_status_short_after_count": len(git_after)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
