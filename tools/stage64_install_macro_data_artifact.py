#!/usr/bin/env python3
"""Install a Stage64 macro data artifact downloaded from GitHub Actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile


def copy_tree_contents(src: Path, dst: Path, *, dry_run: bool) -> list[str]:
    copied: list[str] = []
    if not src.exists():
        return copied
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        copied.append(str(target))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    return copied


def find_dir(root: Path, suffix_parts: tuple[str, ...]) -> Path | None:
    for p in root.rglob(suffix_parts[-1]):
        if not p.is_dir():
            continue
        parts = p.parts
        if len(parts) >= len(suffix_parts) and tuple(parts[-len(suffix_parts):]) == suffix_parts:
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Install Stage64 macro data artifact")
    ap.add_argument("artifact_zip")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args()

    root = Path(ns.root).resolve()
    artifact = Path(ns.artifact_zip).expanduser().resolve()
    if not artifact.exists():
        raise FileNotFoundError(artifact)

    installed: dict[str, list[str] | str | bool] = {"artifact": str(artifact), "dry_run": ns.dry_run, "raw": [], "reports": []}
    with tempfile.TemporaryDirectory(prefix="stage64_macro_artifact_") as tmp:
        tmp_root = Path(tmp)
        with zipfile.ZipFile(artifact) as zf:
            zf.extractall(tmp_root)

        raw_src = find_dir(tmp_root, ("data", "macro_regime", "raw"))
        reports_src = find_dir(tmp_root, ("reports", "stage64_macro_data_acquisition"))

        if raw_src is None:
            raise RuntimeError("Artifact does not contain data/macro_regime/raw")

        installed["raw"] = copy_tree_contents(raw_src, root / "data" / "macro_regime" / "raw", dry_run=ns.dry_run)
        if reports_src is not None:
            installed["reports"] = copy_tree_contents(reports_src, root / "reports" / "stage64_macro_data_acquisition", dry_run=ns.dry_run)

    out_dir = root / "reports" / "stage64_macro_data_acquisition"
    if not ns.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "stage64_macro_artifact_install_summary.json").write_text(json.dumps(installed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(installed, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
