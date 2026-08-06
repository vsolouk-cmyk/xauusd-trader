#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROGRAM = "XAUUSD_CROSS_ASSET_PANEL_COMPACT_DIAGNOSTIC_V1"
REPORT_REL = Path("reports/xauusd_cross_asset_intraday_panel")
FEATURE_NAME = "cross_asset_intraday_features.csv"
TARGET_NAME = "cross_asset_intraday_targets.csv"
SMALL_COPY_LIMIT = 5_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_time(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_nonempty(value: str | None) -> bool:
    if value is None:
        return False
    value = value.strip()
    return value != "" and value.lower() not in {"nan", "none", "null", "nat"}


def choose_key_columns(fieldnames: list[str], kind: str) -> list[str]:
    base = [
        "decision_time_utc",
        "decision_date_utc",
        "sample_role",
        "entry_open",
    ]
    patterns = (
        "_h1_ret4",
        "_h1_ret12",
        "_h1_ret24",
        "_m15_ret4",
        "available_time_utc",
        "real_yield",
        "nominal_yield",
        "breakeven",
        "vix",
        "gvz",
        "target",
        "return",
        "exit_",
        "horizon",
    )
    selected: list[str] = []
    for col in fieldnames:
        low = col.lower()
        if col in base or any(pattern in low for pattern in patterns):
            selected.append(col)
    if kind == "targets" and len(fieldnames) <= 80:
        selected = list(fieldnames)
    if not selected:
        selected = fieldnames[: min(30, len(fieldnames))]
    # Stable de-duplication and hard cap.
    return list(dict.fromkeys(selected))[:100]


def write_dict_rows(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def profile_csv(path: Path, out_dir: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            raise RuntimeError(f"CSV has no header: {path}")

        key_cols = choose_key_columns(fieldnames, kind)
        coverage_cols = [c for c in fieldnames if c.lower().endswith("_h1_ret4")]
        availability_cols = [c for c in fieldnames if c.lower().endswith("available_time_utc")]

        nonempty = Counter()
        first_valid: dict[str, str] = {}
        last_valid: dict[str, str] = {}
        row_count = 0
        min_time: str | None = None
        max_time: str | None = None
        duplicate_decision_times = 0
        prior_time: str | None = None
        time_sequence_hash = hashlib.sha256()
        sample_role_counts = Counter()
        head_rows: list[dict[str, str]] = []
        tail_rows: deque[dict[str, str]] = deque(maxlen=5)
        first_by_year: dict[str, dict[str, str]] = {}
        coverage_breakdown = Counter()
        core_completeness = Counter()
        availability_violations = Counter()

        compact_path = out_dir / f"{kind}_key_columns.csv.gz"
        compact_fh = gzip.open(compact_path, "wt", encoding="utf-8", newline="")
        compact_writer = csv.DictWriter(compact_fh, fieldnames=key_cols, extrasaction="ignore")
        compact_writer.writeheader()

        try:
            for row in reader:
                row_count += 1
                decision = (row.get("decision_time_utc") or "").strip()
                decision_dt = parse_time(decision)
                if decision:
                    time_sequence_hash.update(decision.encode("utf-8"))
                    time_sequence_hash.update(b"\n")
                    if min_time is None or decision < min_time:
                        min_time = decision
                    if max_time is None or decision > max_time:
                        max_time = decision
                    if decision == prior_time:
                        duplicate_decision_times += 1
                    prior_time = decision
                    year = decision[:4]
                    if year and year not in first_by_year:
                        first_by_year[year] = {c: row.get(c, "") for c in key_cols}
                else:
                    year = "MISSING"

                role = (row.get("sample_role") or "").strip()
                if role:
                    sample_role_counts[role] += 1

                for col in fieldnames:
                    value = row.get(col, "")
                    if is_nonempty(value):
                        nonempty[col] += 1
                        if col not in first_valid:
                            first_valid[col] = decision
                        last_valid[col] = decision

                if coverage_cols:
                    dt = decision_dt
                    hour = f"{dt.hour:02d}" if dt else "NA"
                    weekday = str(dt.weekday()) if dt else "NA"
                    present_count = 0
                    for col in coverage_cols:
                        present = is_nonempty(row.get(col))
                        present_count += int(present)
                        symbol = col[: -len("_h1_ret4")].upper()
                        coverage_breakdown[(symbol, "year", year, "present" if present else "missing")] += 1
                        coverage_breakdown[(symbol, "hour", hour, "present" if present else "missing")] += 1
                        coverage_breakdown[(symbol, "weekday", weekday, "present" if present else "missing")] += 1
                    core_completeness[(year, present_count, len(coverage_cols))] += 1

                if decision_dt:
                    for col in availability_cols:
                        value = row.get(col, "")
                        available_dt = parse_time(value)
                        if available_dt and available_dt > decision_dt:
                            availability_violations[col] += 1

                compact_writer.writerow({c: row.get(c, "") for c in key_cols})
                selected = {c: row.get(c, "") for c in key_cols}
                if len(head_rows) < 5:
                    head_rows.append(selected)
                tail_rows.append(selected)
        finally:
            compact_fh.close()

    column_rows = []
    for col in fieldnames:
        count = int(nonempty[col])
        column_rows.append(
            {
                "column": col,
                "nonempty_rows": count,
                "missing_rows": row_count - count,
                "coverage": (count / row_count) if row_count else 0.0,
                "first_valid_decision_time_utc": first_valid.get(col, ""),
                "last_valid_decision_time_utc": last_valid.get(col, ""),
            }
        )
    write_dict_rows(
        out_dir / f"{kind}_column_coverage.csv",
        [
            "column",
            "nonempty_rows",
            "missing_rows",
            "coverage",
            "first_valid_decision_time_utc",
            "last_valid_decision_time_utc",
        ],
        column_rows,
    )

    sample_rows = []
    for label, rows in (("HEAD", head_rows), ("TAIL", list(tail_rows))):
        for idx, row in enumerate(rows, 1):
            sample_rows.append({"sample_group": label, "sample_index": idx, **row})
    for year, row in sorted(first_by_year.items()):
        sample_rows.append({"sample_group": f"FIRST_{year}", "sample_index": 1, **row})
    write_dict_rows(
        out_dir / f"{kind}_samples.csv",
        ["sample_group", "sample_index", *key_cols],
        sample_rows,
    )

    if coverage_breakdown:
        rows = []
        grouped: dict[tuple[str, str, str], dict[str, int]] = {}
        for (symbol, dimension, bucket, state), value in coverage_breakdown.items():
            grouped.setdefault((symbol, dimension, bucket), {"present": 0, "missing": 0})[state] += value
        for (symbol, dimension, bucket), values in sorted(grouped.items()):
            total = values["present"] + values["missing"]
            rows.append(
                {
                    "symbol": symbol,
                    "dimension": dimension,
                    "bucket": bucket,
                    "present": values["present"],
                    "missing": values["missing"],
                    "coverage": values["present"] / total if total else 0.0,
                }
            )
        write_dict_rows(
            out_dir / f"{kind}_h1_ret4_coverage_breakdown.csv",
            ["symbol", "dimension", "bucket", "present", "missing", "coverage"],
            rows,
        )

    if core_completeness:
        rows = [
            {
                "year": year,
                "present_h1_ret4_columns": present,
                "total_h1_ret4_columns": total,
                "rows": count,
            }
            for (year, present, total), count in sorted(core_completeness.items())
        ]
        write_dict_rows(
            out_dir / f"{kind}_h1_ret4_joint_completeness.csv",
            ["year", "present_h1_ret4_columns", "total_h1_ret4_columns", "rows"],
            rows,
        )

    profile = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "rows": row_count,
        "columns": len(fieldnames),
        "fieldnames": fieldnames,
        "key_columns_exported": key_cols,
        "h1_ret4_columns": coverage_cols,
        "availability_columns": availability_cols,
        "availability_violations_recomputed": dict(availability_violations),
        "decision_time_min": min_time,
        "decision_time_max": max_time,
        "duplicate_adjacent_decision_times": duplicate_decision_times,
        "decision_time_sequence_sha256": time_sequence_hash.hexdigest(),
        "sample_role_counts": dict(sample_role_counts),
    }
    (out_dir / f"{kind}_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def detect_time_column(fieldnames: list[str]) -> str | None:
    candidates = ["time_utc", "timestamp_utc", "datetime_utc", "time", "timestamp", "datetime"]
    lower_map = {name.lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    for name in fieldnames:
        low = name.lower()
        if "time" in low or "date" in low:
            return name
    return None


def profile_source_exports(manifest_path: Path, out_dir: Path) -> None:
    if not manifest_path.is_file():
        return
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        manifest_rows = list(csv.DictReader(fh))

    summary_rows: list[dict[str, Any]] = []
    by_year = Counter()
    by_hour = Counter()
    by_weekday = Counter()
    sample_rows: list[dict[str, Any]] = []

    for item in manifest_rows:
        symbol = item.get("symbol", "")
        timeframe = item.get("timeframe", "")
        source_path = Path(item.get("path", ""))
        result: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "path": str(source_path),
            "exists": source_path.is_file(),
            "size_bytes": source_path.stat().st_size if source_path.is_file() else 0,
            "manifest_rows": item.get("rows", ""),
            "manifest_first_utc": item.get("first_utc", ""),
            "manifest_last_utc": item.get("last_utc", ""),
            "manifest_sha256": item.get("sha256", ""),
            "actual_sha256": "",
            "sha256_match": False,
            "parsed_rows": 0,
            "time_column": "",
            "first_time": "",
            "last_time": "",
            "adjacent_duplicate_times": 0,
            "non_monotonic_times": 0,
        }
        if not source_path.is_file():
            summary_rows.append(result)
            continue
        result["actual_sha256"] = sha256_file(source_path)
        result["sha256_match"] = result["actual_sha256"] == result["manifest_sha256"]
        with source_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            time_col = detect_time_column(fields)
            result["time_column"] = time_col or ""
            head: list[dict[str, str]] = []
            tail: deque[dict[str, str]] = deque(maxlen=3)
            prior_dt: datetime | None = None
            for row in reader:
                result["parsed_rows"] += 1
                if len(head) < 3:
                    head.append(row)
                tail.append(row)
                if time_col:
                    raw = (row.get(time_col) or "").strip()
                    dt = parse_time(raw)
                    if not result["first_time"]:
                        result["first_time"] = raw
                    result["last_time"] = raw
                    if dt:
                        by_year[(symbol, timeframe, str(dt.year))] += 1
                        by_hour[(symbol, timeframe, f"{dt.hour:02d}")] += 1
                        by_weekday[(symbol, timeframe, str(dt.weekday()))] += 1
                        if prior_dt == dt:
                            result["adjacent_duplicate_times"] += 1
                        if prior_dt and dt < prior_dt:
                            result["non_monotonic_times"] += 1
                        prior_dt = dt
            for group, rows in (("HEAD", head), ("TAIL", list(tail))):
                for idx, row in enumerate(rows, 1):
                    sample_rows.append(
                        {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "sample_group": group,
                            "sample_index": idx,
                            "row_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
                        }
                    )
        summary_rows.append(result)

    write_dict_rows(
        out_dir / "source_export_profile.csv",
        list(summary_rows[0].keys()) if summary_rows else ["symbol"],
        summary_rows,
    )
    write_dict_rows(
        out_dir / "source_export_samples.csv",
        ["symbol", "timeframe", "sample_group", "sample_index", "row_json"],
        sample_rows,
    )
    for filename, counter, bucket_name in (
        ("source_rows_by_year.csv", by_year, "year"),
        ("source_rows_by_hour.csv", by_hour, "hour_utc"),
        ("source_rows_by_weekday.csv", by_weekday, "weekday_utc_0_monday"),
    ):
        rows = [
            {"symbol": key[0], "timeframe": key[1], bucket_name: key[2], "rows": value}
            for key, value in sorted(counter.items())
        ]
        write_dict_rows(out_dir / filename, ["symbol", "timeframe", bucket_name, "rows"], rows)


def copy_small_inputs(root: Path, report_dir: Path, out_dir: Path) -> list[str]:
    candidates = [
        report_dir / "cross_asset_panel_contract.json",
        report_dir / "cross_asset_panel_decision.md",
        report_dir / "cross_asset_panel_quality.json",
        report_dir / "cross_asset_panel_summary.json",
        report_dir / "cross_asset_source_manifest.csv",
        root / "xauusd_cross_asset_panel_console.txt",
        root / "xauusd_cross_asset_panel_console(1).txt",
        root / "xauusd_cross_asset_panel_console(2).txt",
        root / "xauusd_cross_asset_panel_test_console.txt",
        root / "xauusd_cross_asset_panel_v11_test_console.txt",
        root / "app/xauusd_cross_asset_intraday_panel.py",
        root / "tests/test_xauusd_cross_asset_intraday_panel.py",
        root / "requirements/xauusd_cross_asset_intraday_panel.txt",
        root / "config/xauusd_cross_asset_intraday_panel.json",
        root / "SHA256SUMS.txt",
    ]
    copied: list[str] = []
    for path in candidates:
        if not path.is_file() or path.stat().st_size > SMALL_COPY_LIMIT:
            continue
        rel = path.relative_to(root) if root in path.parents else Path(path.name)
        dest = out_dir / "inputs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        copied.append(str(rel))
    return copied


def make_zip(folder: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder).as_posix())


def run(root: Path, output: Path | None = None) -> Path:
    root = root.resolve()
    report_dir = root / REPORT_REL
    features_path = report_dir / FEATURE_NAME
    targets_path = report_dir / TARGET_NAME
    if not features_path.is_file() or not targets_path.is_file():
        missing = [str(p) for p in (features_path, targets_path) if not p.is_file()]
        raise SystemExit(f"Missing required panel CSV(s): {missing}")

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    output = output or downloads / "XAUUSD_CROSS_ASSET_PANEL_COMPACT_DIAGNOSTIC.zip"

    with tempfile.TemporaryDirectory(prefix="xauusd_panel_diag_") as tmp:
        out_dir = Path(tmp) / "XAUUSD_CROSS_ASSET_PANEL_COMPACT_DIAGNOSTIC"
        out_dir.mkdir(parents=True)
        copied = copy_small_inputs(root, report_dir, out_dir)
        feature_profile = profile_csv(features_path, out_dir, "features")
        target_profile = profile_csv(targets_path, out_dir, "targets")
        profile_source_exports(report_dir / "cross_asset_source_manifest.csv", out_dir)

        alignment = {
            "feature_rows": feature_profile["rows"],
            "target_rows": target_profile["rows"],
            "row_count_match": feature_profile["rows"] == target_profile["rows"],
            "feature_decision_time_sequence_sha256": feature_profile["decision_time_sequence_sha256"],
            "target_decision_time_sequence_sha256": target_profile["decision_time_sequence_sha256"],
            "decision_time_sequence_match": feature_profile["decision_time_sequence_sha256"]
            == target_profile["decision_time_sequence_sha256"],
        }
        (out_dir / "feature_target_alignment.json").write_text(
            json.dumps(alignment, indent=2), encoding="utf-8"
        )

        manifest_entries = []
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                manifest_entries.append(
                    {
                        "path": path.relative_to(out_dir).as_posix(),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
        manifest = {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "root": str(root),
            "copied_small_inputs": copied,
            "excluded_large_files": [str(features_path), str(targets_path)],
            "files": manifest_entries,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        }
        (out_dir / "COMPACT_DIAGNOSTIC_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        make_zip(out_dir, output)

    print(json.dumps({
        "program": PROGRAM,
        "decision": "PASS_COMPACT_DIAGNOSTIC_PACK_CREATED",
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    run(Path(args.root), Path(args.output).expanduser() if args.output else None)


if __name__ == "__main__":
    main()
