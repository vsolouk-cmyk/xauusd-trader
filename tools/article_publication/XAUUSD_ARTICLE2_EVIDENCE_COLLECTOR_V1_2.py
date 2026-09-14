#!/usr/bin/env python3
"""Create a safe software/method evidence bundle for XAUUSD Article 2.

The collector inventories the full project tree, including backup directories,
Git history, source code, tests, workflows, contracts, decisions, and archive
member lists. It extracts structural software evidence and copies small relevant
text files after redaction. It does not copy manuscript drafts, raw market
databases, large tables, virtual environments, Git objects, credentials, or
archive payloads.

Python standard library only.
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import traceback
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


COLLECTOR_VERSION = "2.0.2"
CHUNK = 1024 * 1024

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
    "build",
    "dist",
}

EXCLUDED_REL_PREFIXES = {
    "docs/publications",
    "docs/pulications",
}

SENSITIVE_NAME_PATTERNS = (
    re.compile(r"^\.env(?:\..*)?$", re.I),
    re.compile(r"(?:^|[_\-.])(credential|credentials|secret|secrets)(?:[_\-.]|$)", re.I),
    re.compile(r"(?:^|[_\-.])(api[_-]?key|access[_-]?token|refresh[_-]?token)(?:[_\-.]|$)", re.I),
    re.compile(r"^(id_rsa|id_ed25519|known_hosts)$", re.I),
    re.compile(r"\.(pem|p12|pfx|key)$", re.I),
)

TEXT_EXTS = {
    ".md",
    ".markdown",
    ".txt",
    ".json",
    ".jsonl",
    ".ndjson",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".py",
    ".r",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".mql5",
    ".mqh",
    ".mq4",
    ".ipynb",
    ".html",
    ".xml",
    ".tex",
    ".bib",
}

CODE_CONFIG_EXTS = {
    ".py",
    ".r",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".mql5",
    ".mqh",
    ".mq4",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
}

TABULAR_EXTS = {".csv", ".tsv"}
SQLITE_EXTS = {".sqlite", ".sqlite3", ".db"}
ZIP_EXTS = {".zip"}
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")

EVIDENCE_KEYWORDS = {
    "stage",
    "summary",
    "review",
    "decision",
    "manifest",
    "audit",
    "transfer",
    "report",
    "contract",
    "schema",
    "ledger",
    "result",
    "scan",
    "replay",
    "cost",
    "readme",
    "feature",
    "candidate",
    "promotion",
    "validation",
    "holdout",
    "forward",
    "baseline",
    "strategy",
    "thesis",
    "archive",
    "observer",
    "shadow",
    "cross_asset",
    "macro",
    "cot",
    "xauusd",
    "test",
    "fixture",
    "workflow",
    "provenance",
    "lineage",
    "fail_closed",
    "fail-closed",
    "point_in_time",
    "point-in-time",
    "asof",
    "as_of",
    "dedup",
    "truncate",
    "timestamp",
    "timezone",
    "dst",
    "fault",
    "deterministic",
    "reproduc",
    "kill_switch",
}

ARCHITECTURE_PATTERNS = {
    "point_in_time": re.compile(r"(?i)\b(as[_-]?of|available[_-]?from|release[_-]?time|point[_-]?in[_-]?time|lookahead|look[_-]?ahead)\b"),
    "provenance": re.compile(r"(?i)\b(provenance|lineage|sha256|manifest|source[_-]?hash|content[_-]?hash)\b"),
    "fail_closed": re.compile(r"(?i)\b(fail[_-]?closed|no[_-]?go|research[_-]?only|kill[_-]?switch|order[_-]?allowed)\b"),
    "replay": re.compile(r"(?i)\b(replay|historical[_-]?as[_-]?of|deterministic|seed)\b"),
    "data_integrity": re.compile(r"(?i)\b(dedup|duplicate|truncat|stale|schema|timezone|\bdst\b|bar[_-]?boundary|alignment)\b"),
    "economic_integrity": re.compile(r"(?i)\b(transaction[_-]?cost|slippage|spread|cost[_-]?stress|commission)\b"),
    "decision_evidence": re.compile(r"(?i)\b(decision[_-]?contract|evidence[_-]?contract|acceptance[_-]?gate|promotion|decision[_-]?ledger)\b"),
}

SOURCE_EXTS = {".py", ".r", ".sql", ".sh", ".ps1", ".bat", ".mql5", ".mqh", ".mq4"}

STAGE_RE = re.compile(r"(?i)(?:^|[^a-z0-9])(?:stage|s)[_\- ]?(\d{1,3}[a-z]?(?:\d+)?)")

SECRET_VALUE_PATTERNS = (
    re.compile(
        r"(?im)((?:[\"']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|authorization)\b[\"']?)\s*[=:]\s*)([\"'][^\"'\r\n]*[\"']|[^\s,;\]\}\)]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)

JSON_DECISION_KEYS = (
    "program",
    "generated_utc",
    "decision",
    "status",
    "commercial_status",
    "pass",
    "broker_order_allowed",
    "demo_order_allowed",
    "live_order_allowed",
    "error",
    "rows",
    "row_count",
    "observations_total",
    "new_signals",
)


def utc_iso(timestamp: float | None = None) -> str:
    value = dt.datetime.now(dt.timezone.utc) if timestamp is None else dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def safe_rel(path: Path, root: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


def is_sensitive_name(path: Path) -> bool:
    return any(pattern.search(path.name) for pattern in SENSITIVE_NAME_PATTERNS)


def classify(path: Path) -> str:
    lower = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in SQLITE_EXTS:
        return "sqlite"
    if suffix in TABULAR_EXTS:
        return "tabular"
    if suffix in ZIP_EXTS:
        return "zip_archive"
    if lower.endswith(TAR_SUFFIXES):
        return "tar_archive"
    if suffix in TEXT_EXTS:
        return "text_or_code"
    return "other"


def sha256_full(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(4 * CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_sampled(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(f"sampled-v1:{size}:".encode("ascii"))
    with path.open("rb") as handle:
        digest.update(handle.read(CHUNK))
        if size > 2 * CHUNK:
            handle.seek(max(0, size // 2 - CHUNK // 2))
            digest.update(handle.read(CHUNK))
        if size > CHUNK:
            handle.seek(max(0, size - CHUNK))
            digest.update(handle.read(CHUNK))
    return digest.hexdigest()


def hash_file(path: Path, full_hash_limit: int) -> tuple[str, str]:
    if path.stat().st_size <= full_hash_limit:
        return sha256_full(path), "sha256_full"
    return sha256_sampled(path), "sha256_sample_3x1MiB"


def has_evidence_keyword(rel: str) -> bool:
    normalized = rel.lower().replace("-", "_").replace(" ", "_")
    return any(word in normalized for word in EVIDENCE_KEYWORDS)


def should_copy(path: Path, rel: str, max_copy_bytes: int) -> bool:
    size = path.stat().st_size
    suffix = path.suffix.lower()
    if size > max_copy_bytes or is_sensitive_name(path):
        return False
    if suffix in CODE_CONFIG_EXTS:
        return True
    if suffix in TEXT_EXTS and has_evidence_keyword(rel) and size <= min(max_copy_bytes, 5 * 1024 * 1024):
        return True
    if path.name.lower() in {"readme", "readme.md", "license", "license.md", "license.txt", "pyproject.toml", "requirements.txt"}:
        return True
    if suffix in TABULAR_EXTS and has_evidence_keyword(rel):
        return True
    return False


def redact_text(text: str) -> tuple[str, int]:
    count = 0
    redacted = text
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.groups:
            redacted, replacements = pattern.subn(lambda m: f'{m.group(1)}"<REDACTED>"', redacted)
        else:
            redacted, replacements = pattern.subn("<REDACTED>", redacted)
        count += replacements
    return redacted, count


def copy_redacted_text(source: Path, destination: Path) -> tuple[int, str | None]:
    data = source.read_bytes()
    if b"\x00" in data[:65536]:
        return 0, "binary_content_detected"
    text = data.decode("utf-8", errors="replace")
    redacted, count = redact_text(text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(redacted, encoding="utf-8")
    return count, None


def run_git(root: Path, args: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        return result.returncode, result.stdout
    except Exception as exc:  # pragma: no cover - diagnostic path
        return 99, f"{type(exc).__name__}: {exc}\n"


def write_git_metadata(root: Path, output: Path) -> dict[str, Any]:
    git_dir = root / ".git"
    summary: dict[str, Any] = {"git_repository": git_dir.exists()}
    if not git_dir.exists():
        return summary
    commands = {
        "git_head.txt": ["rev-parse", "HEAD"],
        "git_status_short.txt": ["status", "--short"],
        "git_branches.txt": ["branch", "--all", "--no-color"],
        "git_tags.txt": ["tag", "--list"],
        "git_tracked_files.txt": ["ls-files", "-s"],
        "git_log.tsv": [
            "log",
            "--all",
            "--date=iso-strict",
            "--pretty=format:%H%x09%ad%x09%an%x09%ae%x09%D%x09%s",
        ],
        "git_change_history.tsv": [
            "log",
            "--all",
            "--date=iso-strict",
            "--pretty=format:COMMIT%x09%H%x09%ad%x09%s",
            "--numstat",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, args in commands.items():
        code, content = run_git(root, args)
        (output / filename).write_text(content, encoding="utf-8")
        summary[filename] = {"exit_code": code, "bytes": len(content.encode("utf-8"))}
    return summary


def source_profile(path: Path, rel: str) -> dict[str, Any]:
    """Return structural source metrics without executing project code."""
    record: dict[str, Any] = {
        "path": rel,
        "language": path.suffix.lower().lstrip("."),
        "physical_lines": None,
        "nonblank_lines": None,
        "functions": None,
        "async_functions": None,
        "classes": None,
        "imports": None,
        "parse_error": None,
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        record["physical_lines"] = len(lines)
        record["nonblank_lines"] = sum(1 for line in lines if line.strip())
        if path.suffix.lower() == ".py":
            tree = ast.parse(text, filename=rel)
            record["functions"] = sum(isinstance(node, ast.FunctionDef) for node in ast.walk(tree))
            record["async_functions"] = sum(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))
            record["classes"] = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
            record["imports"] = sum(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
    except Exception as exc:
        record["parse_error"] = f"{type(exc).__name__}: {exc}"
    return record


def architecture_hits(path: Path, rel: str, max_scan_bytes: int = 5 * 1024 * 1024) -> list[dict[str, Any]]:
    if path.suffix.lower() not in TEXT_EXTS or path.stat().st_size > max_scan_bytes or is_sensitive_name(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        categories = sorted(name for name, pattern in ARCHITECTURE_PATTERNS.items() if pattern.search(line))
        if categories:
            safe_line, _ = redact_text(line.strip())
            hits.append(
                {
                    "path": rel,
                    "line": line_number,
                    "categories": ";".join(categories),
                    "excerpt": safe_line[:500],
                }
            )
    return hits


def csv_profile(path: Path, rel: str) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "path": rel,
        "size_bytes": path.stat().st_size,
        "delimiter": "\t" if path.suffix.lower() == ".tsv" else ",",
        "header": None,
        "sample_rows": [],
        "estimated_data_rows": None,
        "estimate_method": None,
        "error": None,
    }
    delimiter = profile["delimiter"]
    try:
        sample_lines: list[str] = []
        sampled_bytes = 0
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for _ in range(101):
                line = handle.readline()
                if line == "":
                    break
                sampled_bytes += len(line.encode("utf-8", errors="replace"))
                if line.strip():
                    sample_lines.append(line)
        if sample_lines:
            rows = list(csv.reader(sample_lines, delimiter=delimiter))
            profile["header"] = rows[0]
            profile["sample_rows"] = rows[1:6]
            if len(sample_lines) > 1:
                average = sampled_bytes / len(sample_lines)
                profile["estimated_data_rows"] = max(0, round(path.stat().st_size / max(average, 1) - 1))
                profile["estimate_method"] = "byte_size_over_first_101_line_mean"
    except Exception as exc:
        profile["error"] = f"{type(exc).__name__}: {exc}"
    return profile


def json_decision_record(path: Path, rel: str, max_parse_bytes: int = 10 * 1024 * 1024) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json" or path.stat().st_size > max_parse_bytes:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    record: dict[str, Any] = {"path": rel}
    found = False
    for key in JSON_DECISION_KEYS:
        if key in value:
            cell = value[key]
            record[key] = json.dumps(cell, ensure_ascii=False) if isinstance(cell, (dict, list)) else cell
            found = True
    for container_key in ("summary", "metrics", "result"):
        container = value.get(container_key)
        if isinstance(container, dict):
            for key in JSON_DECISION_KEYS:
                if key in container and key not in record:
                    cell = container[key]
                    record[key] = json.dumps(cell, ensure_ascii=False) if isinstance(cell, (dict, list)) else cell
                    found = True
    return record if found else None


def sqlite_profile(path: Path, rel: str) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "path": rel,
        "size_bytes": path.stat().st_size,
        "page_count": None,
        "page_size": None,
        "user_version": None,
        "objects": [],
        "error": None,
    }
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            profile["page_count"] = connection.execute("PRAGMA page_count").fetchone()[0]
            profile["page_size"] = connection.execute("PRAGMA page_size").fetchone()[0]
            profile["user_version"] = connection.execute("PRAGMA user_version").fetchone()[0]
            rows = connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table','view','index','trigger') ORDER BY type, name"
            ).fetchall()
            profile["objects"] = [
                {"type": row[0], "name": row[1], "table": row[2], "sql": row[3]}
                for row in rows
            ]
        finally:
            connection.close()
    except Exception as exc:
        profile["error"] = f"{type(exc).__name__}: {exc}"
    return profile


def archive_members(path: Path, rel: str, max_members: int) -> tuple[list[dict[str, Any]], str | None, bool]:
    members: list[dict[str, Any]] = []
    truncated = False
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as archive:
                for index, item in enumerate(archive.infolist()):
                    if index >= max_members:
                        truncated = True
                        break
                    members.append(
                        {
                            "archive_path": rel,
                            "member_path": item.filename,
                            "member_size": item.file_size,
                            "compressed_size": item.compress_size,
                            "crc": f"{item.CRC:08x}",
                            "member_type": "directory" if item.is_dir() else "file",
                        }
                    )
        elif path.name.lower().endswith(TAR_SUFFIXES):
            with tarfile.open(path, "r:*") as archive:
                for index, item in enumerate(archive):
                    if index >= max_members:
                        truncated = True
                        break
                    members.append(
                        {
                            "archive_path": rel,
                            "member_path": item.name,
                            "member_size": item.size,
                            "compressed_size": None,
                            "crc": None,
                            "member_type": "directory" if item.isdir() else "file",
                        }
                    )
        return members, None, truncated
    except Exception as exc:
        return members, f"{type(exc).__name__}: {exc}", truncated


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def part_suffix(index: int) -> str:
    if index < 0 or index >= 26 * 26:
        raise ValueError("too_many_upload_parts")
    return chr(ord("a") + index // 26) + chr(ord("a") + index % 26)


def make_upload_parts(zip_path: Path, output_dir: Path, part_mb: int) -> tuple[Path | None, list[Path]]:
    chunk_size = max(1, part_mb) * 1024 * 1024
    if zip_path.stat().st_size <= chunk_size:
        return None, []
    upload_dir = output_dir / f"{zip_path.stem}_UPLOAD_PARTS"
    upload_dir.mkdir(parents=True, exist_ok=False)
    wrappers: list[Path] = []
    raw_hash_rows: list[str] = []
    with zip_path.open("rb") as source:
        index = 0
        while True:
            block = source.read(chunk_size)
            if not block:
                break
            suffix = part_suffix(index)
            raw_name = f"{zip_path.name}.part-{suffix}"
            wrapper = upload_dir / f"{raw_name}.zip"
            with zipfile.ZipFile(wrapper, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(raw_name, block)
            wrappers.append(wrapper)
            raw_hash_rows.append(f"{hashlib.sha256(block).hexdigest()}  {raw_name}")
            index += 1

    (upload_dir / "UPLOAD_FILES_LIST.txt").write_text(
        "\n".join(path.name for path in wrappers) + "\n", encoding="utf-8")
    (upload_dir / "UPLOAD_FILES_SHA256.txt").write_text(
        "\n".join(f"{sha256_full(path)}  {path.name}" for path in wrappers) + "\n",
        encoding="utf-8",
    )
    (upload_dir / "RAW_PARTS_SHA256.txt").write_text(
        "\n".join(raw_hash_rows) + "\n", encoding="utf-8")
    (upload_dir / "ORIGINAL_SHA256.txt").write_text(
        f"{sha256_full(zip_path)}  {zip_path.name}\n", encoding="utf-8")
    return upload_dir, wrappers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, help="Absolute or relative XAUUSD project root")
    parser.add_argument("--output-dir", required=True, help="Directory in which the final ZIP is created")
    parser.add_argument("--max-copy-mb", type=int, default=8, help="Maximum size of any copied evidence file")
    parser.add_argument("--full-hash-mb", type=int, default=128, help="Maximum size for a full SHA-256 hash")
    parser.add_argument("--max-archive-members", type=int, default=20000, help="Per-archive member listing cap")
    parser.add_argument("--upload-part-mb", type=int, default=18, help="Split ZIP into upload wrappers above this size")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"PROJECT_ROOT_NOT_FOUND: {root}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if root == Path("/") or len(root.parts) < 3:
        raise SystemExit(f"REFUSING_BROAD_ROOT: {root}")

    max_copy_bytes = max(1, args.max_copy_mb) * 1024 * 1024
    full_hash_limit = max(1, args.full_hash_mb) * 1024 * 1024
    run_stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_name = f"XAUUSD_ARTICLE2_SOFTWARE_EVIDENCE_INTAKE_{run_stamp}"
    temp_root = Path(tempfile.mkdtemp(prefix=f"_{bundle_name}_", dir=output_dir))
    payload = temp_root / bundle_name
    payload.mkdir(parents=True, exist_ok=False)

    inventory_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    copied_rows: list[dict[str, Any]] = []
    duplicate_rows: list[dict[str, Any]] = []
    archive_rows: list[dict[str, Any]] = []
    archive_error_rows: list[dict[str, Any]] = []
    csv_profiles: list[dict[str, Any]] = []
    sqlite_profiles: list[dict[str, Any]] = []
    json_decisions: list[dict[str, Any]] = []
    source_profiles: list[dict[str, Any]] = []
    architecture_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    extension_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    full_hash_to_first: dict[str, str] = {}
    total_bytes = 0

    try:
        git_summary = write_git_metadata(root, payload / "git_metadata")

        for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in EXCLUDED_DIR_NAMES
                and safe_rel(current_path / name, root) not in EXCLUDED_REL_PREFIXES
                and not (current_path / name).is_symlink()
            )
            for filename in sorted(filenames):
                path = current_path / filename
                rel = safe_rel(path, root)
                if path.is_symlink():
                    target = os.readlink(path)
                    inventory_rows.append(
                        {
                            "path": rel,
                            "size_bytes": None,
                            "mtime_utc": None,
                            "extension": path.suffix.lower(),
                            "category": "symlink",
                            "sha256_or_sample": None,
                            "hash_method": None,
                            "sensitive_filename": False,
                            "evidence_keyword": has_evidence_keyword(rel),
                            "stage_tokens": "",
                            "note": f"target={target}",
                        }
                    )
                    continue
                if not path.is_file():
                    continue

                try:
                    stat = path.stat()
                    size = stat.st_size
                    total_bytes += size
                    category = classify(path)
                    extension = path.suffix.lower() or "<none>"
                    extension_counts[extension] += 1
                    category_counts[category] += 1
                    sensitive = is_sensitive_name(path)
                    digest, hash_method = hash_file(path, full_hash_limit)
                    stage_tokens = sorted(set(match.group(1) for match in STAGE_RE.finditer(rel)))
                    keyword = has_evidence_keyword(rel)
                    row = {
                        "path": rel,
                        "size_bytes": size,
                        "mtime_utc": utc_iso(stat.st_mtime),
                        "extension": extension,
                        "category": category,
                        "sha256_or_sample": digest,
                        "hash_method": hash_method,
                        "sensitive_filename": sensitive,
                        "evidence_keyword": keyword,
                        "stage_tokens": ";".join(stage_tokens),
                        "note": "",
                    }
                    inventory_rows.append(row)
                    if stage_tokens or keyword:
                        stage_rows.append(dict(row))

                    if category == "tabular":
                        csv_profiles.append(csv_profile(path, rel))
                    elif category == "sqlite":
                        sqlite_profiles.append(sqlite_profile(path, rel))
                    elif category in {"zip_archive", "tar_archive"}:
                        members, archive_error, truncated = archive_members(path, rel, args.max_archive_members)
                        archive_rows.extend(members)
                        if archive_error or truncated:
                            archive_error_rows.append(
                                {
                                    "archive_path": rel,
                                    "error": archive_error or "",
                                    "member_listing_truncated": truncated,
                                    "members_recorded": len(members),
                                }
                            )

                    decision_record = json_decision_record(path, rel)
                    if decision_record is not None:
                        json_decisions.append(decision_record)

                    if path.suffix.lower() in SOURCE_EXTS:
                        source_profiles.append(source_profile(path, rel))
                    architecture_rows.extend(architecture_hits(path, rel))

                    if should_copy(path, rel, max_copy_bytes):
                        full_digest = digest if hash_method == "sha256_full" else sha256_full(path)
                        if full_digest in full_hash_to_first:
                            duplicate_rows.append(
                                {
                                    "duplicate_path": rel,
                                    "canonical_path": full_hash_to_first[full_digest],
                                    "sha256": full_digest,
                                    "size_bytes": size,
                                }
                            )
                        else:
                            destination = payload / "evidence" / PurePosixPath(rel)
                            redactions, copy_error = copy_redacted_text(path, destination)
                            if copy_error:
                                warnings.append(f"COPY_SKIPPED {rel}: {copy_error}")
                            else:
                                full_hash_to_first[full_digest] = rel
                                copied_rows.append(
                                    {
                                        "source_path": rel,
                                        "bundle_path": PurePosixPath("evidence", rel).as_posix(),
                                        "sha256_source": full_digest,
                                        "size_bytes_source": size,
                                        "redactions": redactions,
                                    }
                                )
                except (PermissionError, OSError) as exc:
                    warnings.append(f"FILE_READ_ERROR {rel}: {type(exc).__name__}: {exc}")

        inventory_fields = [
            "path",
            "size_bytes",
            "mtime_utc",
            "extension",
            "category",
            "sha256_or_sample",
            "hash_method",
            "sensitive_filename",
            "evidence_keyword",
            "stage_tokens",
            "note",
        ]
        write_csv(payload / "file_inventory.csv", inventory_rows, inventory_fields)
        write_csv(payload / "stage_evidence_catalog.csv", stage_rows, inventory_fields)
        write_csv(
            payload / "copied_evidence_index.csv",
            copied_rows,
            ["source_path", "bundle_path", "sha256_source", "size_bytes_source", "redactions"],
        )
        write_csv(
            payload / "duplicate_evidence_map.csv",
            duplicate_rows,
            ["duplicate_path", "canonical_path", "sha256", "size_bytes"],
        )
        write_csv(
            payload / "archive_members.csv",
            archive_rows,
            ["archive_path", "member_path", "member_size", "compressed_size", "crc", "member_type"],
        )
        write_csv(
            payload / "archive_listing_issues.csv",
            archive_error_rows,
            ["archive_path", "error", "member_listing_truncated", "members_recorded"],
        )
        write_jsonl(payload / "csv_profiles.jsonl", csv_profiles)
        write_jsonl(payload / "sqlite_profiles.jsonl", sqlite_profiles)
        write_csv(
            payload / "software_source_inventory.csv",
            source_profiles,
            [
                "path",
                "language",
                "physical_lines",
                "nonblank_lines",
                "functions",
                "async_functions",
                "classes",
                "imports",
                "parse_error",
            ],
        )
        write_csv(
            payload / "architecture_evidence_hits.csv",
            architecture_rows,
            ["path", "line", "categories", "excerpt"],
        )

        decision_fields = ["path", *JSON_DECISION_KEYS]
        write_csv(payload / "json_decision_index.csv", json_decisions, decision_fields)

        system_info = {
            "collector_version": COLLECTOR_VERSION,
            "generated_utc": utc_iso(),
            "project_root": str(root),
            "output_dir": str(output_dir),
            "platform": platform.platform(),
            "python_version": sys.version,
            "git": git_summary,
            "limits": {
                "max_copy_bytes": max_copy_bytes,
                "full_hash_limit_bytes": full_hash_limit,
                "max_archive_members_per_archive": args.max_archive_members,
            },
        }
        write_json(payload / "system_and_run_context.json", system_info)

        run_report = {
            "collector_version": COLLECTOR_VERSION,
            "generated_utc": utc_iso(),
            "project_root": str(root),
            "files_scanned": len(inventory_rows),
            "total_source_bytes": total_bytes,
            "unique_evidence_files_copied": len(copied_rows),
            "duplicate_evidence_files_mapped": len(duplicate_rows),
            "archives_found": category_counts.get("zip_archive", 0) + category_counts.get("tar_archive", 0),
            "archive_members_recorded": len(archive_rows),
            "csv_tsv_profiles": len(csv_profiles),
            "sqlite_profiles": len(sqlite_profiles),
            "json_decision_records": len(json_decisions),
            "source_files_profiled": len(source_profiles),
            "source_nonblank_lines": sum(int(row.get("nonblank_lines") or 0) for row in source_profiles),
            "architecture_evidence_hits": len(architecture_rows),
            "sensitive_filenames_not_copied": sum(1 for row in inventory_rows if row.get("sensitive_filename")),
            "extension_counts": dict(sorted(extension_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
            "warnings_count": len(warnings),
            "warnings": warnings,
            "completeness_notes": [
                "The full project tree was inventoried except standard build/cache/VCS/virtual-environment directories.",
                "Backup folders were traversed; ZIP/TAR payloads were not copied, but their member lists were recorded.",
                "Large/raw market data and SQLite bytes were not copied; metadata, profiles, schemas, and hashes/sampled hashes were recorded.",
                "Potential credential files were inventoried by metadata only and never copied.",
                "Copied text/code was redacted for common secret patterns.",
                "Manuscript and journal-submission drafts under docs/publications or docs/pulications were excluded.",
            ],
        }
        write_json(payload / "run_report.json", run_report)

        readme = f"""# XAUUSD Article 2 Software/Method Evidence Intake Bundle

Generated: {run_report['generated_utc']}
Collector version: {COLLECTOR_VERSION}

## Purpose

This bundle supports the software/method paper on a fail-closed, point-in-time
architecture for reproducible trading-strategy audits. It inventories the
complete project tree, including backup folders and Git history.
It intentionally excludes raw market-data bytes, SQLite database bytes, archive
payloads, Git objects, virtual environments, build caches, credentials, and
manuscript/submission drafts.

## Core files

- `file_inventory.csv`: every scanned file, size, timestamp, hash method, and stage tokens.
- `stage_evidence_catalog.csv`: files whose paths suggest research/stage relevance.
- `copied_evidence_index.csv`: unique copied research/code evidence.
- `duplicate_evidence_map.csv`: duplicate backup evidence mapped to one canonical copy.
- `archive_members.csv`: ZIP/TAR member listings without extracting archives.
- `json_decision_index.csv`: selected decision/status fields from JSON artifacts.
- `csv_profiles.jsonl`: headers and small samples; raw tabular data are not copied by default.
- `sqlite_profiles.jsonl`: read-only SQLite schema/object metadata; databases are not copied.
- `git_metadata/`: HEAD, status, branches, tags, tracked files, and history.
- `software_source_inventory.csv`: language, line, function, class, import, and parse metrics.
- `architecture_evidence_hits.csv`: line-level evidence for point-in-time, provenance,
  fail-closed, replay, integrity, cost, and decision mechanisms.
- `run_report.json`: completeness counts and warnings.

## Important

This is an intake package. The Article 2 benchmark and fault-injection suite
will be frozen only after the evidence audit identifies the reusable core and
the missing contracts.
"""
        (payload / "README.md").write_text(readme, encoding="utf-8")

        collector_copy = payload / "collector_source.py"
        shutil.copyfile(Path(__file__).resolve(), collector_copy)

        zip_path = output_dir / f"{bundle_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in sorted(payload.rglob("*")):
                if item.is_file():
                    archive.write(item, arcname=PurePosixPath(bundle_name, safe_rel(item, payload)).as_posix())

        zip_sha = sha256_full(zip_path)
        zip_size = zip_path.stat().st_size
        upload_dir, upload_wrappers = make_upload_parts(zip_path, output_dir, args.upload_part_mb)
        shutil.rmtree(temp_root)

        print(f"OUTPUT={zip_path}")
        print(f"SHA256={zip_sha}")
        print(f"SIZE_BYTES={zip_size}")
        print(f"FILES_SCANNED={len(inventory_rows)}")
        print(f"EVIDENCE_UNIQUE={len(copied_rows)}")
        print(f"DUPLICATES_MAPPED={len(duplicate_rows)}")
        print(f"WARNINGS={len(warnings)}")
        if upload_wrappers:
            print(f"UPLOAD_PARTS_DIR={upload_dir}")
            print(f"UPLOAD_PARTS={len(upload_wrappers)}")
            print("SEND_ALL_FILES_IN_UPLOAD_PARTS_DIR=YES")
        else:
            print(f"SEND_THIS_FILE={zip_path}")
        return 0
    except Exception:
        failure_path = temp_root / "COLLECTOR_FAILURE.txt"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"COLLECTOR_FAILED_TEMP_RETAINED={temp_root}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
