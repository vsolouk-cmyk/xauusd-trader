#!/usr/bin/env python3
"""Verify the extracted submission package without rebuilding its contents."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "PACKAGE_MANIFEST_SHA256.txt"
FLAT_ARCHIVES = [
    "JIFMIM_ARTICLE1_LATEX_SOURCE_FLAT.zip",
    "JIFMIM_ARTICLE1_LATEX_SOURCE_ANONYMIZED_FLAT.zip",
]
ARCHIVES = [*FLAT_ARCHIVES, "supplementary_data.zip"]
IDENTITY_PATTERNS = [
    rb"Vahid", rb"Solouk", rb"v\.solouk", rb"Urmia",
    rb"0000-0001-8304-6394", rb"vsolouk-cmyk", rb"author_metadata",
]


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    if not MANIFEST.is_file():
        raise FileNotFoundError(MANIFEST)

    checked = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise AssertionError(f"Malformed manifest line: {line!r}")
        expected, relative_name = match.groups()
        path = ROOT / relative_name
        if not path.is_file():
            raise FileNotFoundError(path)
        if digest(path) != expected:
            raise AssertionError(f"SHA-256 mismatch: {relative_name}")
        checked += 1

    for name in ARCHIVES:
        with zipfile.ZipFile(ROOT / name) as archive:
            corrupt = archive.testzip()
            if corrupt is not None:
                raise AssertionError(f"CRC failure in {name}: {corrupt}")

    for name in FLAT_ARCHIVES:
        with zipfile.ZipFile(ROOT / name) as archive:
            if any("/" in member.rstrip("/") for member in archive.namelist()):
                raise AssertionError(f"Nested path in flat archive: {name}")

    anonymous_path = ROOT / "JIFMIM_ARTICLE1_LATEX_SOURCE_ANONYMIZED_FLAT.zip"
    with zipfile.ZipFile(anonymous_path) as archive:
        anonymous_content = b"\n".join(
            archive.read(member)
            for member in archive.namelist()
            if member.endswith((".tex", ".bib", ".bbl"))
        )
    for pattern in IDENTITY_PATTERNS:
        if re.search(pattern, anonymous_content, flags=re.IGNORECASE):
            raise AssertionError(f"Author identity found in anonymized source: {pattern!r}")

    print("DECISION=PASS_ARTICLE1_PACKAGE_INTEGRITY")
    print(f"MANIFEST_FILES_VERIFIED={checked}")
    print(f"ZIP_ARCHIVES_VERIFIED={len(ARCHIVES)}")
    print("ANONYMIZED_SOURCE_IDENTITY_SCAN=PASS")


if __name__ == "__main__":
    main()
