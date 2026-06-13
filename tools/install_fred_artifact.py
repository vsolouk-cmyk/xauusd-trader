#!/usr/bin/env python3
"""Install GitHub FRED exogenous artifact files into data/exogenous safely.

Usage:
    python3 tools/install_fred_artifact.py ~/Downloads/xauusd-fred-exogenous-us10y-27479778865.zip

This avoids zsh wildcard pitfalls and handles GitHub artifact zip layouts such as:
    exogenous/_artifact_success/us10y.csv
    data/exogenous/_artifact_success/us10y.csv
    us10y.csv

Research/shadow infrastructure only. No trading/order behavior.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import tempfile
import zipfile
from pathlib import Path

SERIES_FILES = {
    "dxy.csv",
    "us10y.csv",
    "real_yield.csv",
    "vix.csv",
    "spx.csv",
    "oil.csv",
}
META_FILES = {"fred_download_manifest.csv", "fred_selected_series.txt"}
ALLOWED_FILES = SERIES_FILES | META_FILES


def _is_safe_member(name: str) -> bool:
    path = Path(name)
    return not path.is_absolute() and ".." not in path.parts


def _should_install(member_name: str) -> bool:
    parts = Path(member_name).parts
    basename = Path(member_name).name
    if basename not in ALLOWED_FILES:
        return False
    if basename in SERIES_FILES:
        return (
            "_artifact_success" in parts
            or "exogenous" in parts
            or len(parts) == 1
        )
    if basename in META_FILES:
        return "exogenous" in parts or "_artifact_success" in parts or len(parts) == 1
    return False


def _real_rows(csv_path: Path) -> int:
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "timestamp" not in reader.fieldnames or "close" not in reader.fieldnames:
                return 0
            count = 0
            for row in reader:
                val = str(row.get("close", "")).strip()
                if not val or val == ".":
                    continue
                try:
                    float(val)
                except ValueError:
                    continue
                count += 1
            return count
    except Exception:
        return 0


def install_artifact(zip_path: Path, out_dir: Path, min_real_rows: int = 50) -> int:
    zip_path = zip_path.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    if not zip_path.exists():
        raise FileNotFoundError(f"artifact zip not found: {zip_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    installed = 0
    seen: set[str] = set()
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        with zipfile.ZipFile(zip_path) as zf:
            members = [m for m in zf.namelist() if not m.endswith("/")]
            unsafe = [m for m in members if not _is_safe_member(m)]
            if unsafe:
                raise RuntimeError(f"Unsafe zip member(s): {unsafe[:5]}")
            selected = [m for m in members if _should_install(m)]
            if not selected:
                print("No installable FRED files found in artifact. Members:")
                for m in members[:80]:
                    print(f"  {m}")
                return 0
            for member in selected:
                basename = Path(member).name
                # Prefer _artifact_success copies when duplicate basenames exist.
                if basename in seen and "_artifact_success" not in Path(member).parts:
                    continue
                extracted = tmp_dir / member
                zf.extract(member, tmp_dir)
                if basename in SERIES_FILES:
                    rows = _real_rows(extracted)
                    if rows < min_real_rows:
                        print(f"skip {basename}: rows={rows} < min_real_rows={min_real_rows}")
                        continue
                else:
                    rows = None
                dest = out_dir / basename
                shutil.copy2(extracted, dest)
                seen.add(basename)
                installed += 1
                row_note = f" rows={rows}" if rows is not None else ""
                print(f"installed {basename}:{row_note} {dest}")
    return installed


def main() -> None:
    parser = argparse.ArgumentParser(description="Install XAUUSD FRED exogenous artifact safely.")
    parser.add_argument("artifact_zip", help="Path to downloaded GitHub artifact zip")
    parser.add_argument(
        "--out-dir",
        default="data/exogenous",
        help="Output directory inside repo, default data/exogenous",
    )
    parser.add_argument(
        "--min-real-rows",
        type=int,
        default=50,
        help="Minimum numeric rows required before installing a series CSV, default 50",
    )
    args = parser.parse_args()

    count = install_artifact(Path(args.artifact_zip), Path(args.out_dir), min_real_rows=args.min_real_rows)
    if count <= 0:
        raise SystemExit(2)
    print(f"done installed_files={count}")


if __name__ == "__main__":
    main()
