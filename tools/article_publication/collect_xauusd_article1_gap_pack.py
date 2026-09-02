#!/usr/bin/env python3
"""Collect the small P0/P1 provenance gap pack for XAUUSD Article 1.

The script is standard-library only. It copies small, targeted result/config/code
artifacts and profiles large canonical inputs without copying their bytes. It
does not modify the project tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import string
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


VERSION = "1.0.0"
MAX_COPY_BYTES = 25 * 1024 * 1024
SPLIT_BYTES = 15 * 1024 * 1024
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "node_modules",
    "dist",
    "build",
}
EXCLUDED_DIR_PREFIXES = (".venv", "venv", "env")
SENSITIVE_NAME_TERMS = (
    ".env",
    "credential",
    "private_key",
    "secret",
    "token",
    ".pem",
    ".p12",
    ".pfx",
)
TEXT_COPY_SUFFIXES = {
    ".json",
    ".md",
    ".csv",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".log",
    ".sha256",
}
ARCHIVE_COPY_SUFFIXES = {".zip"}
DISCOVERY_TERMS = (
    "stage177c",
    "stage180",
    "final_alpha_trend",
    "amarkets_dst_contract",
    "time_contract_repair",
    "output_review_and_transition_gate_repair",
)
DATA_NAME_TERMS = (
    "xauusd_extended_history.sqlite",
    "xauusd_amarkets_alignment.sqlite",
    "xauusd_controlled_paper.sqlite",
    "amarkets_xauusd_5m.csv",
    "amarkets_xauusd_1h.csv",
    "amarkets_xauusd_h1.csv",
    "dukascopy",
)
DECISION_TOKENS = (
    "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT",
    "BLOCK_AMARKETS_TIME_CONTRACT_UNRESOLVED",
    "NO_REFERENCE_EDGE_CLOSE_LONG_HORIZON_TREND_ON_XAUUSD_CFD",
    "KILL_CURRENT_COMMERCIAL_FORMULATION",
)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+]{16,}"),
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_label(path: Path, roots: list[tuple[str, Path]]) -> str:
    resolved = path.resolve()
    for label, root in roots:
        try:
            return f"{label}/{resolved.relative_to(root.resolve()).as_posix()}"
        except ValueError:
            continue
    return f"external/{path.name}"


def is_excluded_dir(name: str) -> bool:
    lower = name.lower()
    return lower in EXCLUDED_DIRS or lower.startswith(EXCLUDED_DIR_PREFIXES)


def is_sensitive_name(path: Path) -> bool:
    lower = path.name.lower()
    return any(term in lower for term in SENSITIVE_NAME_TERMS)


def contains_secret(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_COPY_SUFFIXES:
        return False
    try:
        with path.open("rb") as handle:
            sample = handle.read(min(path.stat().st_size, 5 * 1024 * 1024))
    except OSError:
        return True
    return any(pattern.search(sample) for pattern in SECRET_PATTERNS)


def walk_targeted(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
        current_path = Path(current)
        current_lower = current_path.as_posix().lower()
        for name in files:
            path = current_path / name
            key = f"{current_lower}/{name.lower()}"
            if any(term in key for term in DISCOVERY_TERMS) or any(
                term in name.lower() for term in DATA_NAME_TERMS
            ):
                yield path


def text_decision_tokens(path: Path) -> list[str]:
    if path.suffix.lower() not in TEXT_COPY_SUFFIXES or path.stat().st_size > 10 * 1024 * 1024:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [token for token in DECISION_TOKENS if token in text]


def profile_delimited(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "line_count": 0,
        "header": None,
        "first_data_line": None,
        "last_data_line": None,
    }
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                clean = line.rstrip("\r\n")
                if line_number == 1:
                    result["header"] = clean[:4000]
                elif clean:
                    if result["first_data_line"] is None:
                        result["first_data_line"] = clean[:4000]
                    result["last_data_line"] = clean[:4000]
                result["line_count"] = line_number
    except OSError as exc:
        result["profile_error"] = f"{type(exc).__name__}: {exc}"
    return result


def profile_sqlite(path: Path) -> dict[str, Any]:
    profile: dict[str, Any] = {"tables": []}
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            rows = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for name, sql in rows:
                table: dict[str, Any] = {"name": name, "schema_sql": sql}
                quoted = '"' + str(name).replace('"', '""') + '"'
                try:
                    table["row_count"] = connection.execute(
                        f"SELECT COUNT(*) FROM {quoted}"
                    ).fetchone()[0]
                except sqlite3.Error as exc:
                    table["row_count_error"] = f"{type(exc).__name__}: {exc}"
                profile["tables"].append(table)
        finally:
            connection.close()
    except sqlite3.Error as exc:
        profile["profile_error"] = f"{type(exc).__name__}: {exc}"
    return profile


def inspect_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        return {"json_parse": "pass", "top_level_type": type(parsed).__name__}
    except Exception as exc:  # The error is evidence and must be recorded.
        return {"json_parse": "fail", "json_error": f"{type(exc).__name__}: {exc}"}


def safe_copy(path: Path, destination_root: Path, label: str) -> Path:
    destination = destination_root / "files" / label
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def write_csv_manifest(rows: list[dict[str, Any]], path: Path) -> None:
    columns = [
        "source_label",
        "source_path",
        "size_bytes",
        "mtime_utc",
        "sha256",
        "selection_reason",
        "copy_status",
        "copied_path",
        "decision_tokens",
        "json_parse",
        "issue",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_readme(pack_dir: Path, manifest: dict[str, Any]) -> None:
    missing = "\n".join(f"- `{item}`" for item in manifest["missing_expected_paths"])
    text = f"""# XAUUSD Article 1 Gap Pack

Generated UTC: {manifest['generated_utc']}  
Collector version: {VERSION}

This package targets the provenance conflicts that block the final Article 1
protocol freeze. Small result, configuration, code, and decision artifacts are
copied without redaction. Large canonical datasets are not copied; their full
SHA-256 digests and structural profiles are recorded in `manifest.json`.

## Missing expected canonical paths

{missing if missing else '- None among the explicit canonical paths.'}

## Files

- `manifest.json`: full machine-readable audit.
- `file_manifest.csv`: compact file-level index.
- `files/`: selected small artifacts, preserving project/downloads paths.

No file in the project tree was modified.
"""
    (pack_dir / "README.md").write_text(text, encoding="utf-8")


def excel_letters(index: int) -> str:
    result = ""
    value = index
    while True:
        value, remainder = divmod(value, 26)
        result = string.ascii_lowercase[remainder] + result
        if value == 0:
            return result
        value -= 1


def split_for_upload(zip_path: Path) -> list[Path]:
    if zip_path.stat().st_size <= 45 * 1024 * 1024:
        return [zip_path]
    wrappers: list[Path] = []
    original_hash = sha256_file(zip_path)
    raw_parts: list[tuple[Path, str]] = []
    with zip_path.open("rb") as source:
        index = 0
        while True:
            block = source.read(SPLIT_BYTES)
            if not block:
                break
            raw = zip_path.with_name(f"{zip_path.name}.part-{excel_letters(index)}")
            raw.write_bytes(block)
            raw_parts.append((raw, hashlib.sha256(block).hexdigest()))
            index += 1

    raw_manifest = zip_path.with_name("RAW_PARTS_SHA256.txt")
    original_manifest = zip_path.with_name("ORIGINAL_SHA256.txt")
    raw_manifest.write_text(
        "".join(f"{digest}  {raw.name}\n" for raw, digest in raw_parts), encoding="utf-8"
    )
    original_manifest.write_text(f"{original_hash}  {zip_path.name}\n", encoding="utf-8")

    for raw, _ in raw_parts:
        wrapper = raw.with_name(raw.name + ".zip")
        with zipfile.ZipFile(wrapper, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.write(raw, arcname=raw.name)
        wrappers.append(wrapper)
        raw.unlink()

    upload_hashes = zip_path.with_name("UPLOAD_FILES_SHA256.txt")
    upload_list = zip_path.with_name("UPLOAD_FILES_LIST.txt")
    listed = wrappers + [original_manifest, raw_manifest]
    upload_hashes.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in listed), encoding="utf-8"
    )
    listed.append(upload_hashes)
    upload_list.write_text("".join(f"{path.name}\n" for path in listed), encoding="utf-8")
    zip_path.unlink()
    return wrappers + [original_manifest, raw_manifest, upload_hashes, upload_list]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("/Users/vahid/Desktop/xauusd-trader"),
    )
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()

    project_root = args.project_root.expanduser().resolve()
    downloads = args.downloads.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not project_root.is_dir():
        parser.error(f"project root does not exist: {project_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = utc_stamp()
    pack_name = f"XAUUSD_ARTICLE1_GAP_PACK_{stamp}"
    roots = [("project", project_root), ("downloads", downloads)]

    explicit_paths = [
        project_root / "reports/stage177c_amarkets_dst_contract",
        project_root / "docs/STAGE177C_OUTPUT_REVIEW_AND_TRANSITION_GATE_REPAIR.md",
        project_root / "reports/stage180_frozen_model_shadow/stage180_summary.json",
        project_root / "reports/xauusd_final_alpha_trend/final_alpha_trend_summary.json",
        project_root / "data/local/stage177b_extended_history/xauusd_extended_history.sqlite",
        project_root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite",
        project_root / "data/controlled_paper/xauusd_controlled_paper.sqlite",
        downloads / "xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv",
        downloads / "xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv",
        downloads / "amarkets_xauusd_5m.csv",
        downloads / "amarkets_xauusd_1h.csv",
    ]

    discovered: dict[Path, str] = {}
    for root in (project_root, downloads):
        for path in walk_targeted(root):
            if path.is_file():
                discovered[path.resolve()] = "targeted_name_or_path_discovery"

    missing_expected: list[str] = []
    for path in explicit_paths:
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not any(is_excluded_dir(part) for part in child.parts):
                    discovered[child.resolve()] = "explicit_canonical_directory"
        elif path.is_file():
            discovered[path.resolve()] = "explicit_canonical_path"
        else:
            missing_expected.append(str(path))

    with tempfile.TemporaryDirectory(prefix="xauusd_article1_gap_") as temporary:
        pack_dir = Path(temporary) / pack_name
        pack_dir.mkdir(parents=True)
        rows: list[dict[str, Any]] = []
        profiles: dict[str, Any] = {}

        for path in sorted(discovered, key=lambda item: str(item).lower()):
            label = relative_label(path, roots)
            stat = path.stat()
            row: dict[str, Any] = {
                "source_label": label,
                "source_path": str(path),
                "size_bytes": stat.st_size,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256_file(path),
                "selection_reason": discovered[path],
                "copy_status": "metadata_only",
                "copied_path": "",
                "decision_tokens": ";".join(text_decision_tokens(path)),
                "json_parse": "",
                "issue": "",
            }

            suffix = path.suffix.lower()
            profile: dict[str, Any] = {}
            if suffix in {".csv", ".tsv"} and stat.st_size > MAX_COPY_BYTES:
                profile = profile_delimited(path)
            elif suffix == ".sqlite":
                profile = profile_sqlite(path)
            elif suffix == ".json" and stat.st_size <= MAX_COPY_BYTES:
                json_result = inspect_json(path)
                profile.update(json_result)
                row["json_parse"] = json_result["json_parse"]

            can_copy = suffix in TEXT_COPY_SUFFIXES | ARCHIVE_COPY_SUFFIXES
            if is_sensitive_name(path):
                row["copy_status"] = "blocked_sensitive_filename"
                row["issue"] = "filename matched the sensitive-file exclusion policy"
            elif stat.st_size > MAX_COPY_BYTES:
                row["copy_status"] = "metadata_only_large_file"
            elif can_copy and contains_secret(path):
                row["copy_status"] = "blocked_secret_pattern"
                row["issue"] = "content matched a conservative secret pattern"
            elif can_copy:
                destination = safe_copy(path, pack_dir, label)
                row["copy_status"] = "copied"
                row["copied_path"] = destination.relative_to(pack_dir).as_posix()
            else:
                row["copy_status"] = "metadata_only_unsupported_type"

            if profile:
                profiles[label] = profile
            rows.append(row)

        pass_sources = [row["source_label"] for row in rows if "PASS_AMARKETS" in row["decision_tokens"]]
        block_sources = [row["source_label"] for row in rows if "BLOCK_AMARKETS" in row["decision_tokens"]]
        pass_result_sources = [source for source in pass_sources if "/reports/" in source]
        block_result_sources = [source for source in block_sources if "/reports/" in source]
        manifest = {
            "collector_version": VERSION,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python_version": sys.version,
            "project_root": str(project_root),
            "downloads_root": str(downloads),
            "max_copy_bytes": MAX_COPY_BYTES,
            "files_considered": len(rows),
            "files_copied": sum(row["copy_status"] == "copied" for row in rows),
            "missing_expected_paths": missing_expected,
            "stage177c_pass_token_sources": pass_sources,
            "stage177c_block_token_sources": block_sources,
            "stage177c_pass_result_sources": pass_result_sources,
            "stage177c_block_result_sources": block_result_sources,
            "stage177c_result_conflict_observed": bool(pass_result_sources and block_result_sources),
            "large_input_profiles": profiles,
            "files": rows,
        }
        (pack_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        write_csv_manifest(rows, pack_dir / "file_manifest.csv")
        write_readme(pack_dir, manifest)

        zip_path = output_dir / f"{pack_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(pack_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=f"{pack_name}/{path.relative_to(pack_dir).as_posix()}")

    outputs = split_for_upload(zip_path)
    print("Collection completed.")
    print(f"Files considered: {len(rows)}")
    print(f"Files copied: {sum(row['copy_status'] == 'copied' for row in rows)}")
    print(f"Stage177C PASS result sources: {len(pass_result_sources)}")
    print(f"Stage177C BLOCK result sources: {len(block_result_sources)}")
    print(f"Stage177C PASS mentions in code/docs/tests: {len(pass_sources) - len(pass_result_sources)}")
    print("Upload these files:")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
