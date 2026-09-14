#!/usr/bin/env python3
"""Safely replace the local Article 1 submission folder with the final package.

The script verifies the release archive, extracts it into a temporary directory
inside the repository, validates the inner SHA-256 manifest, moves any existing
article folder to a timestamped Downloads backup, and then moves the verified
folder into place. It performs no Git operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile


ARCHIVE_NAME = "XAUUSD_ARTICLE1_JIFMIM_COMPLETE_SUBMISSION_PACKAGE_FINAL_20260905.zip"
PACKAGE_DIR_NAME = "XAUUSD_ARTICLE1_JIFMIM_SUBMISSION_V1_1_20260905"
EXPECTED_ARCHIVE_SHA256 = "7fad125b3d44973e40a46cc92288a9551b77b66e2d4cbd6aea18c35f01147d8a"
DESTINATION_RELATIVE = Path("docs/publications") / PACKAGE_DIR_NAME


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def safe_archive_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = zf.infolist()
    prefix = PACKAGE_DIR_NAME + "/"
    require(members, "release archive is empty")
    for member in members:
        name = member.filename
        pure = PurePosixPath(name)
        require(name.startswith(prefix), f"unexpected archive root: {name}")
        require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe archive path: {name}")
        mode = member.external_attr >> 16
        require((mode & 0o170000) != 0o120000, f"symbolic link not allowed in archive: {name}")
    return members


def validate_manifest(package_dir: Path) -> int:
    manifest = package_dir / "PACKAGE_MANIFEST_SHA256.txt"
    require(manifest.is_file(), "inner manifest is missing")
    lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(lines) == 59, f"unexpected manifest entry count: {len(lines)}")
    for line in lines:
        parts = line.split("  ", 1)
        require(len(parts) == 2, f"malformed manifest line: {line}")
        expected, relative = parts
        require(len(expected) == 64 and all(c in "0123456789abcdef" for c in expected), f"invalid digest: {relative}")
        pure = PurePosixPath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe manifest path: {relative}")
        target = package_dir / Path(*pure.parts)
        require(target.is_file(), f"manifest file is missing: {relative}")
        require(digest(target) == expected, f"manifest mismatch: {relative}")
    return len(lines)


def package_matches(destination: Path, staged_package: Path) -> bool:
    if not destination.is_dir():
        return False
    try:
        validate_manifest(destination)
    except Exception:
        return False
    return digest(destination / "PACKAGE_MANIFEST_SHA256.txt") == digest(
        staged_package / "PACKAGE_MANIFEST_SHA256.txt"
    )


def unique_backup_path(backup_dir: Path, stamp: str) -> Path:
    base = backup_dir / f"{PACKAGE_DIR_NAME}_PRE_FINAL_{stamp}"
    candidate = base
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = backup_dir / f"{base.name}_{counter}"
    return candidate


def parse_args() -> argparse.Namespace:
    home = Path.home()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=home / "Desktop/xauusd-trader")
    parser.add_argument("--archive", type=Path, default=home / "Downloads" / ARCHIVE_NAME)
    parser.add_argument("--backup-dir", type=Path, default=home / "Downloads")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    archive = args.archive.expanduser().resolve()
    backup_dir = args.backup_dir.expanduser().resolve()
    destination = repo / DESTINATION_RELATIVE
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging = repo / f"_article1_install_{stamp}"
    backup: Path | None = None
    old_moved = False
    installed = False

    require((repo / ".git").exists(), f"not a Git repository: {repo}")
    require(archive.is_file(), f"release archive not found: {archive}")
    require(digest(archive) == EXPECTED_ARCHIVE_SHA256, "release archive SHA-256 mismatch")
    require(not staging.exists(), f"temporary directory already exists: {staging}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        staging.mkdir()
        with zipfile.ZipFile(archive) as zf:
            safe_archive_members(zf)
            require(zf.testzip() is None, "release archive CRC failure")
            zf.extractall(staging)

        staged_package = staging / PACKAGE_DIR_NAME
        manifest_entries = validate_manifest(staged_package)

        if package_matches(destination, staged_package):
            shutil.rmtree(staging)
            print(json.dumps({
                "decision": "ALREADY_CURRENT",
                "installed": False,
                "destination": str(destination),
                "manifest_entries": manifest_entries,
                "git_mutation": False,
            }, indent=2))
            return 0

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup = unique_backup_path(backup_dir, stamp)
            shutil.move(str(destination), str(backup))
            old_moved = True

        shutil.move(str(staged_package), str(destination))
        installed = True
        staging.rmdir()

        print(json.dumps({
            "decision": "FINAL_PACKAGE_INSTALLED",
            "installed": True,
            "destination": str(destination),
            "backup": str(backup) if backup else None,
            "archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "manifest_entries": manifest_entries,
            "temporary_directory_removed": True,
            "git_mutation": False,
        }, indent=2))
        return 0
    except Exception:
        if installed and destination.exists():
            failed_install = backup_dir / f"{PACKAGE_DIR_NAME}_FAILED_INSTALL_{stamp}"
            if not failed_install.exists():
                shutil.move(str(destination), str(failed_install))
        if old_moved and backup is not None and backup.exists() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup), str(destination))
        if staging.exists():
            shutil.rmtree(staging)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            "decision": "INSTALL_BLOCKED_NO_REPOSITORY_MUTATION",
            "error": f"{type(exc).__name__}: {exc}",
        }, indent=2), file=sys.stderr)
        raise SystemExit(2)
