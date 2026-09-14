#!/usr/bin/env python3
"""Read-only verification for the committed Article 2 evidence folder and ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

FOLDER = "article2_evidence_v1"
ZIP_NAME = "XAUUSD_ARTICLE2_BENCHMARK_FAULT_INJECTION_EVIDENCE_V1.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path) -> dict:
    parent = root / "artifacts/article2"
    folder = parent / FOLDER
    archive_path = parent / ZIP_NAME
    problems: list[str] = []
    if not folder.is_dir():
        problems.append("EXPANDED_FOLDER_MISSING")
    if not archive_path.is_file():
        problems.append("ZIP_MISSING")
    if problems:
        return {"pass": False, "decision": "BLOCK_ARTICLE2", "problems": problems}

    decision_path = folder / "article2_decision.json"
    if not decision_path.is_file():
        problems.append("DECISION_MISSING")
    else:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        if decision.get("decision") != "ARTICLE2_EVIDENCE_SUFFICIENT" or decision.get("pass") is not True:
            problems.append("DECISION_NOT_SUFFICIENT")

    sums_path = folder / "SHA256SUMS.txt"
    if not sums_path.is_file():
        problems.append("SHA256SUMS_MISSING")
    else:
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            expected, rel = line.split("  ", 1)
            path = folder / rel
            if not path.is_file() or sha256_file(path) != expected:
                problems.append(f"EXPANDED_HASH_MISMATCH:{rel}")

    sidecar = parent / f"{ZIP_NAME}.sha256"
    if not sidecar.is_file() or sidecar.read_text(encoding="utf-8").split()[0] != sha256_file(archive_path):
        problems.append("ZIP_SHA256_MISMATCH")

    with zipfile.ZipFile(archive_path) as archive:
        bad = archive.testzip()
        if bad:
            problems.append(f"ZIP_CRC_FAILURE:{bad}")
        names = sorted(name for name in archive.namelist() if not name.endswith("/"))
        expanded = sorted(str(Path(FOLDER) / path.relative_to(folder)).replace("\\", "/") for path in folder.rglob("*") if path.is_file())
        if names != expanded:
            problems.append("ZIP_EXPANDED_MEMBER_MISMATCH")

    return {
        "pass": not problems,
        "decision": "ARTICLE2_EVIDENCE_SUFFICIENT" if not problems else "BLOCK_ARTICLE2",
        "problems": problems,
        "zip_sha256": sha256_file(archive_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    result = verify(Path(parser.parse_args().root).expanduser().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

