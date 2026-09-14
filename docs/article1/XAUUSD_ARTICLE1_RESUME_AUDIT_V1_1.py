#!/usr/bin/env python3
"""Safely resume and audit the Article 1 JIFMIM package installation.

The script is intentionally non-destructive.  It never overwrites an existing
destination and never commits, pulls, pushes, resets, or stashes Git content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import zipfile


ARCHIVE_NAME = "XAUUSD_ARTICLE1_JIFMIM_COMPLETE_SUBMISSION_PACKAGE_V1_1_20260905.zip"
PACKAGE_DIR_NAME = "XAUUSD_ARTICLE1_JIFMIM_SUBMISSION_V1_1_20260905"
DESTINATION_RELATIVE = Path("docs/publications") / PACKAGE_DIR_NAME
EXPECTED_ARCHIVE_SHA256 = "13767f32e4bc8ec7725bb1bc7a6a574020d9465a37cb5d1b3e27fb8e87ab855e"
EXPECTED_MANIFEST_ENTRIES = 59
REQUIRED_FILES = (
    "PACKAGE_MANIFEST_SHA256.txt",
    "README.md",
    "author_metadata.tex",
    "manuscript.pdf",
    "manuscript_anonymized.pdf",
    "supplementary_material.pdf",
    "title_page.pdf",
    "cover_letter.pdf",
    "JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip",
    "supplementary_data.zip",
    "validation_report.json",
    "github_repository_audit.sh",
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def run(command: list[str], cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def git_value(repo: Path, *args: str) -> tuple[int, str, str]:
    result = run(["git", *args], repo)
    return (
        int(result["returncode"]),
        str(result["stdout"]).strip(),
        str(result["stderr"]).strip(),
    )


def verify_zip(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip()
    except (OSError, zipfile.BadZipFile) as exc:
        return f"{type(exc).__name__}: {exc}"


def parse_manifest(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"Malformed manifest line {line_number}: {raw!r}")
        entries.append((parts[0].lower(), parts[1].strip()))
    return entries


def verify_destination(destination: Path) -> dict[str, object]:
    missing_required = [name for name in REQUIRED_FILES if not (destination / name).is_file()]
    manifest_path = destination / "PACKAGE_MANIFEST_SHA256.txt"
    result: dict[str, object] = {
        "destination": str(destination),
        "missing_required_files": missing_required,
        "manifest_entries": 0,
        "missing_manifest_files": [],
        "hash_mismatches": [],
        "unsafe_manifest_paths": [],
        "nested_zip_checks": {},
        "pdf_signature_checks": {},
        "validation_report": {},
        "pass": False,
    }
    if missing_required or not manifest_path.is_file():
        return result

    try:
        entries = parse_manifest(manifest_path)
    except Exception as exc:  # diagnostic boundary
        result["manifest_error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["manifest_entries"] = len(entries)
    missing: list[str] = []
    mismatches: list[dict[str, str]] = []
    unsafe: list[str] = []
    destination_resolved = destination.resolve()

    for expected, relative_name in entries:
        candidate = (destination / relative_name).resolve()
        try:
            candidate.relative_to(destination_resolved)
        except ValueError:
            unsafe.append(relative_name)
            continue
        if not candidate.is_file():
            missing.append(relative_name)
            continue
        actual = sha256_file(candidate)
        if actual != expected:
            mismatches.append({"file": relative_name, "expected": expected, "actual": actual})

    result["missing_manifest_files"] = missing
    result["hash_mismatches"] = mismatches
    result["unsafe_manifest_paths"] = unsafe

    nested: dict[str, object] = {}
    for name in ("JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip", "supplementary_data.zip"):
        failure = verify_zip(destination / name)
        nested[name] = {"pass": failure is None, "first_bad_member_or_error": failure}
    result["nested_zip_checks"] = nested

    pdf_checks: dict[str, bool] = {}
    for name in (
        "manuscript.pdf",
        "manuscript_anonymized.pdf",
        "supplementary_material.pdf",
        "title_page.pdf",
        "cover_letter.pdf",
    ):
        path = destination / name
        pdf_checks[name] = path.is_file() and path.stat().st_size > 1000 and path.read_bytes()[:5] == b"%PDF-"
    result["pdf_signature_checks"] = pdf_checks

    try:
        validation = json.loads((destination / "validation_report.json").read_text(encoding="utf-8"))
        result["validation_report"] = {
            "decision": validation.get("decision"),
            "technical_validation_pass": validation.get("technical_validation_pass"),
            "submission_ready": validation.get("submission_ready"),
            "pending_author_metadata_markers": validation.get("pending_author_metadata_markers", []),
        }
    except Exception as exc:  # diagnostic boundary
        result["validation_report_error"] = f"{type(exc).__name__}: {exc}"

    result["pass"] = bool(
        len(entries) == EXPECTED_MANIFEST_ENTRIES
        and not missing
        and not mismatches
        and not unsafe
        and all(bool(item["pass"]) for item in nested.values())
        and all(pdf_checks.values())
        and result.get("validation_report", {}).get("technical_validation_pass") is True
    )
    return result


def install_if_absent(repo: Path, downloads: Path, destination: Path) -> tuple[str, dict[str, object]]:
    if destination.exists():
        return "reused_existing_destination", {"archive_checked": False}

    archive_path = downloads / ARCHIVE_NAME
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    actual_sha = sha256_file(archive_path)
    if actual_sha != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(
            "Outer archive SHA-256 mismatch: "
            f"expected {EXPECTED_ARCHIVE_SHA256}, got {actual_sha}"
        )
    bad_member = verify_zip(archive_path)
    if bad_member is not None:
        raise RuntimeError(f"Outer archive CRC failed: {bad_member}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="_incoming_article1_v1_1_resume_", dir=str(repo)))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(stage)
        extracted = stage / PACKAGE_DIR_NAME
        if not extracted.is_dir():
            raise RuntimeError(f"Expected extracted directory is absent: {extracted}")
        pre_move = verify_destination(extracted)
        if not pre_move["pass"]:
            raise RuntimeError("Extracted destination failed manifest validation")
        subprocess.run(["mv", str(extracted), str(destination.parent)], check=True)
    finally:
        if stage.exists():
            stage_resolved = stage.resolve()
            repo_resolved = repo.resolve()
            if stage_resolved.parent == repo_resolved and stage_resolved.name.startswith(
                "_incoming_article1_v1_1_resume_"
            ):
                shutil.rmtree(stage_resolved)

    return "installed_from_verified_archive", {
        "archive_checked": True,
        "archive": str(archive_path),
        "archive_sha256": actual_sha,
        "archive_crc_pass": True,
    }


def collect_git_audit(repo: Path, destination: Path) -> dict[str, object]:
    inside_rc, inside, inside_err = git_value(repo, "rev-parse", "--is-inside-work-tree")
    if inside_rc != 0 or inside != "true":
        return {"pass": False, "error": inside_err or "not a Git worktree"}

    branch_rc, branch, branch_err = git_value(repo, "branch", "--show-current")
    head_rc, head, head_err = git_value(repo, "rev-parse", "HEAD")
    url_rc, remote_url, url_err = git_value(repo, "remote", "get-url", "origin")
    status_rc, status, status_err = git_value(repo, "status", "--short")
    rel_destination = str(destination.relative_to(repo))
    package_rc, package_status, package_err = git_value(repo, "status", "--short", "--", rel_destination)

    fetch = run(["git", "fetch", "--prune", "origin"], repo)
    remote_ref = f"origin/{branch}" if branch else ""
    remote_verify_rc = 1
    remote_head = ""
    ahead_behind = ""
    tracked_diff = ""
    local_only = ""
    remote_only = ""

    if branch and int(fetch["returncode"]) == 0:
        remote_verify_rc, remote_head, _ = git_value(repo, "rev-parse", "--verify", remote_ref)
        if remote_verify_rc == 0:
            _, ahead_behind, _ = git_value(repo, "rev-list", "--left-right", "--count", f"{remote_ref}...HEAD")
            _, tracked_diff, _ = git_value(repo, "diff", "--name-status", remote_ref, "--")
            _, local_files, _ = git_value(repo, "ls-files")
            _, remote_files, _ = git_value(repo, "ls-tree", "-r", "--name-only", remote_ref)
            local_set = set(local_files.splitlines()) if local_files else set()
            remote_set = set(remote_files.splitlines()) if remote_files else set()
            local_only = "\n".join(sorted(local_set - remote_set))
            remote_only = "\n".join(sorted(remote_set - local_set))

    errors = [
        message
        for rc, message in (
            (branch_rc, branch_err),
            (head_rc, head_err),
            (url_rc, url_err),
            (status_rc, status_err),
            (package_rc, package_err),
        )
        if rc != 0 and message
    ]

    return {
        "pass": not errors and branch_rc == 0 and bool(branch) and head_rc == 0 and url_rc == 0,
        "branch": branch,
        "local_head": head,
        "repository_url": remote_url,
        "worktree_status": status,
        "article_package_status": package_status,
        "fetch_returncode": int(fetch["returncode"]),
        "fetch_stdout": str(fetch["stdout"]).strip(),
        "fetch_stderr": str(fetch["stderr"]).strip(),
        "remote_ref": remote_ref,
        "remote_ref_available": remote_verify_rc == 0,
        "remote_head": remote_head,
        "ahead_behind_remote_then_local": ahead_behind,
        "tracked_content_differences": tracked_diff,
        "local_tracked_not_on_remote": local_only,
        "remote_tracked_not_local": remote_only,
        "errors": errors,
        "git_mutation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/Users/vahid/Desktop/xauusd-trader")
    parser.add_argument("--downloads", default=str(Path.home() / "Downloads"))
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    downloads = Path(args.downloads).expanduser().resolve()
    destination = repo / DESTINATION_RELATIVE
    downloads.mkdir(parents=True, exist_ok=True)
    report_dir = Path(tempfile.mkdtemp(prefix="article1_resume_report_", dir=str(downloads)))

    summary: dict[str, object] = {
        "program": "XAUUSD_ARTICLE1_RESUME_AUDIT_V1_1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "downloads": str(downloads),
        "destination": str(destination),
        "pass": False,
        "decision": "BLOCK_ARTICLE1_RESUME_AUDIT",
        "errors": [],
        "git_mutation_performed": False,
    }

    exit_code = 2
    try:
        if not repo.is_dir():
            raise FileNotFoundError(f"Repository directory not found: {repo}")
        action, archive_check = install_if_absent(repo, downloads, destination)
        destination_check = verify_destination(destination)
        git_audit = collect_git_audit(repo, destination)
        summary.update(
            {
                "destination_action": action,
                "archive_check": archive_check,
                "destination_check": destination_check,
                "git_audit": git_audit,
            }
        )
        if not destination_check["pass"]:
            raise RuntimeError("Existing Article 1 destination failed package validation; it was not overwritten")

        summary["pass"] = True
        summary["decision"] = (
            "PASS_LOCAL_ARTICLE1_PACKAGE_VALID_GIT_REVIEW_REQUIRED"
            if not git_audit.get("pass")
            or git_audit.get("worktree_status")
            or git_audit.get("ahead_behind_remote_then_local") not in ("0\t0", "0 0", "")
            else "PASS_LOCAL_ARTICLE1_PACKAGE_AND_GIT_STATE_CLEAN"
        )
        exit_code = 0
    except Exception as exc:  # always emit a diagnostic package
        summary["errors"] = [f"{type(exc).__name__}: {exc}"]

    git_audit = summary.get("git_audit", {})
    write_text(report_dir / "ARTICLE1_REPOSITORY_URL.txt", str(git_audit.get("repository_url", "UNAVAILABLE")))
    write_text(report_dir / "ARTICLE1_GITHUB_COMMIT.txt", str(git_audit.get("local_head", "UNAVAILABLE")))
    write_text(report_dir / "ARTICLE1_GIT_STATUS.txt", str(git_audit.get("worktree_status", "UNAVAILABLE")))
    write_text(
        report_dir / "ARTICLE1_REMOTE_COMPARISON.txt",
        json.dumps(
            {
                key: git_audit.get(key)
                for key in (
                    "branch",
                    "local_head",
                    "remote_ref",
                    "remote_head",
                    "ahead_behind_remote_then_local",
                    "article_package_status",
                    "local_tracked_not_on_remote",
                    "remote_tracked_not_local",
                    "tracked_content_differences",
                    "fetch_returncode",
                    "fetch_stdout",
                    "fetch_stderr",
                )
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    write_text(report_dir / "article1_resume_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))

    # Also leave the three frequently requested files directly in Downloads.
    for name in (
        "ARTICLE1_REPOSITORY_URL.txt",
        "ARTICLE1_GITHUB_COMMIT.txt",
        "ARTICLE1_GIT_STATUS.txt",
    ):
        shutil.copy2(report_dir / name, downloads / name)

    result_zip = downloads / f"XAUUSD_ARTICLE1_RESUME_AUDIT_{utc_stamp()}.zip"
    with zipfile.ZipFile(result_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(report_dir.iterdir()):
            archive.write(path, arcname=path.name)

    if report_dir.exists() and report_dir.parent == downloads and report_dir.name.startswith("article1_resume_report_"):
        shutil.rmtree(report_dir)

    terminal = {
        "decision": summary["decision"],
        "pass": summary["pass"],
        "destination_action": summary.get("destination_action"),
        "destination": str(destination),
        "git_mutation_performed": False,
        "results_zip": str(result_zip),
        "errors": summary["errors"],
    }
    print(json.dumps(terminal, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
