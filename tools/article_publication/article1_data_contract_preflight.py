#!/usr/bin/env python3
"""Outcome-blind data-contract preflight for XAUUSD Article 1.

This script validates the fixed 2015-2024 AMarkets/Dukascopy reference window.
It does not calculate strategy returns, rank candidates, inspect 2025+ strategy
outcomes, modify source data, or authorize any order.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROGRAM = "XAUUSD_ARTICLE1_2015_2024_DATA_CONTRACT_PREFLIGHT_V1_1"
REFERENCE_START_UTC = "2015-01-02T07:00:00Z"
REFERENCE_END_UTC_EXCLUSIVE = "2025-01-01T00:00:00Z"
M5_MS = 5 * 60 * 1000
H1_MS = 60 * 60 * 1000

EXPECTED_HASHES = {
    "reference_db": "8d9a3f9d7e8a05cc9fa97badd93aa809e1c09b105eacb3b96720671aa74c66de",
    "alignment_db": "c38491993ec5b76325d61f941cbdff7cda7147c83c97f43b80e97221385669f5",
    "time_contract": "635ed1f9cd9ec62fecdff61e3e9660657194d972e4f4f889731e97d1432ea362",
}

GATES = {
    "m5_min_amarkets_rows": 600_000,
    "m5_min_overlap_pct": 99.0,
    "m5_min_return_corr_60m": 0.99,
    "m5_max_median_abs_close_bps": 1.0,
    "m5_max_p95_abs_close_bps": 10.0,
    "m5_min_range_corr": 0.90,
    "h1_min_amarkets_rows": 50_000,
    "h1_min_overlap_pct": 99.0,
    "h1_min_return_corr_1bar": 0.99,
    "h1_max_median_abs_close_bps": 1.0,
    "h1_max_p95_abs_close_bps": 10.0,
    "h1_min_range_corr": 0.90,
    "year_min_overlap_pct": 98.0,
    "year_min_return_corr_60m": 0.90,
    "year_max_median_abs_close_bps": 2.0,
    "year_max_p95_abs_close_bps": 20.0,
}

WARNING_THRESHOLDS = {
    "year_return_corr_60m": 0.98,
}


@dataclass(frozen=True)
class InputBinding:
    name: str
    path: Path
    expected_sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def epoch_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)


def iso_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(value, unit="ms", tz="UTC").isoformat()


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def metric_or(mapping: dict[str, Any], key: str, fallback: float) -> float:
    """Return a finite metric without treating a valid numeric zero as missing."""
    value = finite(mapping.get(key))
    return fallback if value is None else value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pairwise_corr(left: Any, right: Any, min_pairs: int = 3) -> float | None:
    x = np.asarray(left, dtype="float64")
    y = np.asarray(right, dtype="float64")
    if x.shape != y.shape:
        raise ValueError("Correlation inputs must have identical shapes")
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < min_pairs:
        return None
    x = x[mask]
    y = y[mask]
    x = x - x.mean()
    y = y - y.mean()
    denominator = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    if not math.isfinite(denominator) or denominator <= 0.0:
        return None
    return finite(np.dot(x, y) / denominator)


def lagged_returns(
    close: pd.Series,
    timestamps: pd.Series,
    lag_rows: int,
    expected_interval_ms: int,
) -> np.ndarray:
    close_values = pd.to_numeric(close, errors="coerce").to_numpy(dtype="float64")
    ts_values = pd.to_numeric(timestamps, errors="coerce").to_numpy(dtype="float64")
    result = np.full(len(close_values), np.nan, dtype="float64")
    if len(close_values) <= lag_rows:
        return result
    current = close_values[lag_rows:]
    previous = close_values[:-lag_rows]
    current_ts = ts_values[lag_rows:]
    previous_ts = ts_values[:-lag_rows]
    valid = (
        np.isfinite(current)
        & np.isfinite(previous)
        & (current > 0.0)
        & (previous > 0.0)
        & np.isfinite(current_ts)
        & np.isfinite(previous_ts)
        & ((current_ts - previous_ts) == expected_interval_ms * lag_rows)
    )
    values = np.full(len(current), np.nan, dtype="float64")
    values[valid] = np.log(current[valid] / previous[valid])
    result[lag_rows:] = values
    return result


def metrics_from_joined(
    frame: pd.DataFrame,
    amarkets_rows: int,
    reference_rows: int,
    interval_ms: int,
) -> dict[str, Any]:
    overlap = int(len(frame))
    coverage = 100.0 * overlap / amarkets_rows if amarkets_rows else 0.0
    result: dict[str, Any] = {
        "amarkets_rows": int(amarkets_rows),
        "reference_rows": int(reference_rows),
        "overlap_rows": overlap,
        "overlap_pct_of_amarkets": coverage,
        "first_overlap_utc": iso_ms(int(frame["timestamp"].min())) if overlap else None,
        "last_overlap_utc": iso_ms(int(frame["timestamp"].max())) if overlap else None,
    }
    if overlap < 3:
        return result

    timestamps = frame["timestamp"]
    result["close_level_corr"] = pairwise_corr(frame["close_ref"], frame["close_am"])
    lag_15 = 3 if interval_ms == M5_MS else 1
    lag_60 = 12 if interval_ms == M5_MS else 1
    for label, lag in (("1bar", 1), ("15m", lag_15), ("60m", lag_60)):
        ref_returns = lagged_returns(frame["close_ref"], timestamps, lag, interval_ms)
        am_returns = lagged_returns(frame["close_am"], timestamps, lag, interval_ms)
        result[f"return_corr_{label}"] = pairwise_corr(ref_returns, am_returns)

    close_bps = (frame["close_am"] / frame["close_ref"] - 1.0).abs() * 10_000
    result["median_abs_close_bps"] = finite(close_bps.median())
    result["p95_abs_close_bps"] = finite(close_bps.quantile(0.95))
    result["range_corr"] = pairwise_corr(
        frame["high_ref"] - frame["low_ref"],
        frame["high_am"] - frame["low_am"],
    )
    return result


def sqlite_quick_check(path: Path) -> str:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return str(connection.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        connection.close()


def table_names(path: Path) -> list[str]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    finally:
        connection.close()


def load_joined(
    alignment_db: Path,
    reference_db: Path,
    am_table: str,
    ref_table: str,
    start_ms: int,
    end_ms: int,
) -> tuple[pd.DataFrame, int, int]:
    uri = f"file:{alignment_db.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        escaped = reference_db.resolve().as_posix().replace("'", "''")
        connection.execute(f"ATTACH DATABASE '{escaped}' AS reference_db")
        am_rows = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {am_table} WHERE timestamp >= ? AND timestamp < ?",
                (start_ms, end_ms),
            ).fetchone()[0]
        )
        ref_rows = int(
            connection.execute(
                f"SELECT COUNT(*) FROM reference_db.{ref_table} "
                "WHERE timestamp >= ? AND timestamp < ?",
                (start_ms, end_ms),
            ).fetchone()[0]
        )
        query = f"""
            SELECT
                a.timestamp AS timestamp,
                r.open AS open_ref, r.high AS high_ref,
                r.low AS low_ref, r.close AS close_ref,
                a.open AS open_am, a.high AS high_am,
                a.low AS low_am, a.close AS close_am
            FROM {am_table} AS a
            INNER JOIN reference_db.{ref_table} AS r
                ON r.timestamp = a.timestamp
            WHERE a.timestamp >= ? AND a.timestamp < ?
            ORDER BY a.timestamp
        """
        frame = pd.read_sql_query(query, connection, params=(start_ms, end_ms))
        return frame, am_rows, ref_rows
    finally:
        connection.close()


def sql_integrity_counts(path: Path, table: str, start_ms: int, end_ms: int) -> dict[str, int]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        invalid_ohlc = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM {table}
                WHERE timestamp >= ? AND timestamp < ? AND (
                    open <= 0 OR high <= 0 OR low <= 0 OR close <= 0 OR
                    high < open OR high < close OR high < low OR
                    low > open OR low > close OR low > high
                )
                """,
                (start_ms, end_ms),
            ).fetchone()[0]
        )
        total, distinct_ts = connection.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT timestamp) FROM {table} "
            "WHERE timestamp >= ? AND timestamp < ?",
            (start_ms, end_ms),
        ).fetchone()
        return {
            "rows": int(total),
            "duplicate_timestamps": int(total - distinct_ts),
            "invalid_ohlc_rows": invalid_ohlc,
        }
    finally:
        connection.close()


def provenance_rows(path: Path) -> dict[str, str]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        names = table_names(path)
        if "provenance" not in names:
            return {}
        return {str(k): str(v) for k, v in connection.execute("SELECT key, value FROM provenance")}
    finally:
        connection.close()


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_results_manifest(run_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(run_dir.iterdir()):
        if path.is_file() and path.name != "RESULTS_MANIFEST.json":
            files.append(
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {"program": PROGRAM, "generated_utc": utc_now(), "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("/Users/vahid/Desktop/xauusd-trader"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    project = args.project_root.expanduser().resolve()
    if not project.is_dir():
        parser.error(f"Project root does not exist: {project}")
    output_root = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else project / "reports/article1_data_contract_preflight"
    )
    stamp = stamp_now()
    run_dir = output_root / f"run_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)

    bindings = [
        InputBinding(
            "reference_db",
            project / "data/local/stage177b_extended_history/xauusd_extended_history.sqlite",
            EXPECTED_HASHES["reference_db"],
        ),
        InputBinding(
            "alignment_db",
            project / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite",
            EXPECTED_HASHES["alignment_db"],
        ),
        InputBinding(
            "time_contract",
            project / "reports/stage177c_amarkets_dst_contract/stage177c_time_contract.json",
            EXPECTED_HASHES["time_contract"],
        ),
    ]

    input_rows: list[dict[str, Any]] = []
    for binding in bindings:
        exists = binding.path.is_file()
        actual = sha256_file(binding.path) if exists else None
        input_rows.append(
            {
                "name": binding.name,
                "path": str(binding.path),
                "exists": exists,
                "size_bytes": binding.path.stat().st_size if exists else None,
                "expected_sha256": binding.expected_sha256,
                "actual_sha256": actual,
                "hash_match": actual == binding.expected_sha256,
            }
        )
    write_csv(
        run_dir / "article1_input_bindings.csv",
        input_rows,
        ["name", "path", "exists", "size_bytes", "expected_sha256", "actual_sha256", "hash_match"],
    )

    all_inputs_exist = all(row["exists"] for row in input_rows)
    all_hashes_match = all(row["hash_match"] for row in input_rows)
    errors: list[str] = []
    if not all_inputs_exist:
        errors.append("missing_locked_input")
    if not all_hashes_match:
        errors.append("locked_input_hash_mismatch")

    summary: dict[str, Any] = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "reference_window": {
            "start_utc": REFERENCE_START_UTC,
            "end_utc_exclusive": REFERENCE_END_UTC_EXCLUSIVE,
            "pre_2015_policy": "EXCLUDED_FROM_PRIMARY_INTRADAY_INFERENCE_DATA_CONTRACT_FAILURE_CASE",
            "post_2024_policy": "NOT_READ_BY_THIS_PREFLIGHT",
        },
        "outcome_blind": True,
        "strategy_results_read": False,
        "input_bindings": input_rows,
        "gates": GATES,
        "warning_thresholds": WARNING_THRESHOLDS,
        "errors": errors,
        "authorization": {
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        },
    }

    if all_inputs_exist:
        reference_db = bindings[0].path
        alignment_db = bindings[1].path
        time_contract_path = bindings[2].path
        sqlite_checks = {
            "reference_db": sqlite_quick_check(reference_db),
            "alignment_db": sqlite_quick_check(alignment_db),
        }
        summary["sqlite_quick_check"] = sqlite_checks
        if any(value != "ok" for value in sqlite_checks.values()):
            errors.append("sqlite_quick_check_failed")

        required_reference = {"dukascopy_m5", "dukascopy_h1_canonical", "provenance"}
        required_alignment = {"amarkets_m5_utc", "amarkets_h1_from_m5_utc", "provenance"}
        reference_tables = set(table_names(reference_db))
        alignment_tables = set(table_names(alignment_db))
        schemas_pass = required_reference <= reference_tables and required_alignment <= alignment_tables
        summary["schema_check"] = {
            "pass": schemas_pass,
            "reference_tables": sorted(reference_tables),
            "alignment_tables": sorted(alignment_tables),
            "missing_reference_tables": sorted(required_reference - reference_tables),
            "missing_alignment_tables": sorted(required_alignment - alignment_tables),
        }
        if not schemas_pass:
            errors.append("required_schema_missing")

        contract = json.loads(time_contract_path.read_text(encoding="utf-8"))
        contract_checks = {
            "contract": contract.get("contract") == "EU_DST_GMT_OFFSET_PAIR",
            "dst_calendar": contract.get("dst_calendar") == "EU",
            "standard_shift_minutes": contract.get("standard_shift_minutes") == -120,
            "dst_shift_minutes": contract.get("dst_shift_minutes") == -180,
            "selection_used_holdout": contract.get("selection_used_holdout") is False,
            "shift_semantics": contract.get("shift_semantics")
            == "timestamp_utc = timestamp_naive + shift_minutes",
        }
        summary["time_contract"] = {
            "legacy_decision": contract.get("decision"),
            "checks": contract_checks,
            "pass": all(contract_checks.values()),
        }
        if not all(contract_checks.values()):
            errors.append("time_contract_semantics_mismatch")

        summary["provenance"] = {
            "reference_db": provenance_rows(reference_db),
            "alignment_db": provenance_rows(alignment_db),
        }

        if schemas_pass:
            start_ms = epoch_ms(REFERENCE_START_UTC)
            end_ms = epoch_ms(REFERENCE_END_UTC_EXCLUSIVE)
            m5, m5_am_rows, m5_ref_rows = load_joined(
                alignment_db,
                reference_db,
                "amarkets_m5_utc",
                "dukascopy_m5",
                start_ms,
                end_ms,
            )
            h1, h1_am_rows, h1_ref_rows = load_joined(
                alignment_db,
                reference_db,
                "amarkets_h1_from_m5_utc",
                "dukascopy_h1_canonical",
                start_ms,
                end_ms,
            )
            m5_metrics = metrics_from_joined(m5, m5_am_rows, m5_ref_rows, M5_MS)
            h1_metrics = metrics_from_joined(h1, h1_am_rows, h1_ref_rows, H1_MS)
            summary["m5_metrics"] = m5_metrics
            summary["h1_metrics"] = h1_metrics

            summary["integrity"] = {
                "amarkets_m5": sql_integrity_counts(alignment_db, "amarkets_m5_utc", start_ms, end_ms),
                "amarkets_h1": sql_integrity_counts(alignment_db, "amarkets_h1_from_m5_utc", start_ms, end_ms),
                "dukascopy_m5": sql_integrity_counts(reference_db, "dukascopy_m5", start_ms, end_ms),
                "dukascopy_h1": sql_integrity_counts(reference_db, "dukascopy_h1_canonical", start_ms, end_ms),
            }

            m5["year"] = pd.to_datetime(m5["timestamp"], unit="ms", utc=True).dt.year
            yearly_rows: list[dict[str, Any]] = []
            for year in range(2015, 2025):
                year_start = max(start_ms, epoch_ms(f"{year}-01-01T00:00:00Z"))
                year_end = min(end_ms, epoch_ms(f"{year + 1}-01-01T00:00:00Z"))
                am_count = sql_integrity_counts(
                    alignment_db, "amarkets_m5_utc", year_start, year_end
                )["rows"]
                ref_count = sql_integrity_counts(
                    reference_db, "dukascopy_m5", year_start, year_end
                )["rows"]
                metrics = metrics_from_joined(
                    m5[m5["year"] == year].drop(columns=["year"]),
                    am_count,
                    ref_count,
                    M5_MS,
                )
                yearly_rows.append({"year": year, **metrics})

            yearly_columns = [
                "year", "amarkets_rows", "reference_rows", "overlap_rows",
                "overlap_pct_of_amarkets", "first_overlap_utc", "last_overlap_utc",
                "close_level_corr", "return_corr_1bar", "return_corr_15m",
                "return_corr_60m", "median_abs_close_bps", "p95_abs_close_bps", "range_corr",
            ]
            write_csv(run_dir / "article1_m5_yearly_alignment.csv", yearly_rows, yearly_columns)
            summary["m5_yearly_metrics"] = yearly_rows
            alignment_warning_years = [
                {
                    "year": int(row["year"]),
                    "return_corr_60m": metric_or(row, "return_corr_60m", -9.0),
                    "warning_threshold": WARNING_THRESHOLDS["year_return_corr_60m"],
                    "classification": "LOCALIZED_ALIGNMENT_WARNING_REQUIRES_SENSITIVITY_TEST",
                }
                for row in yearly_rows
                if metric_or(row, "return_corr_60m", -9.0)
                < WARNING_THRESHOLDS["year_return_corr_60m"]
            ]
            summary["alignment_warning_years"] = alignment_warning_years

            metric_checks = {
                "m5_min_rows": m5_metrics["amarkets_rows"] >= GATES["m5_min_amarkets_rows"],
                "m5_overlap": m5_metrics["overlap_pct_of_amarkets"] >= GATES["m5_min_overlap_pct"],
                "m5_return_corr_60m": metric_or(m5_metrics, "return_corr_60m", -9.0)
                >= GATES["m5_min_return_corr_60m"],
                "m5_median_close_bps": metric_or(m5_metrics, "median_abs_close_bps", 9999.0)
                <= GATES["m5_max_median_abs_close_bps"],
                "m5_p95_close_bps": metric_or(m5_metrics, "p95_abs_close_bps", 9999.0)
                <= GATES["m5_max_p95_abs_close_bps"],
                "m5_range_corr": metric_or(m5_metrics, "range_corr", -9.0) >= GATES["m5_min_range_corr"],
                "h1_min_rows": h1_metrics["amarkets_rows"] >= GATES["h1_min_amarkets_rows"],
                "h1_overlap": h1_metrics["overlap_pct_of_amarkets"] >= GATES["h1_min_overlap_pct"],
                "h1_return_corr": metric_or(h1_metrics, "return_corr_1bar", -9.0)
                >= GATES["h1_min_return_corr_1bar"],
                "h1_median_close_bps": metric_or(h1_metrics, "median_abs_close_bps", 9999.0)
                <= GATES["h1_max_median_abs_close_bps"],
                "h1_p95_close_bps": metric_or(h1_metrics, "p95_abs_close_bps", 9999.0)
                <= GATES["h1_max_p95_abs_close_bps"],
                "h1_range_corr": metric_or(h1_metrics, "range_corr", -9.0) >= GATES["h1_min_range_corr"],
                "year_count": len(yearly_rows) == 10 and all(row["overlap_rows"] > 0 for row in yearly_rows),
                "year_overlap": all(
                    row["overlap_pct_of_amarkets"] >= GATES["year_min_overlap_pct"] for row in yearly_rows
                ),
                "year_return_corr": all(
                    metric_or(row, "return_corr_60m", -9.0) >= GATES["year_min_return_corr_60m"]
                    for row in yearly_rows
                ),
                "year_median_close_bps": all(
                    metric_or(row, "median_abs_close_bps", 9999.0)
                    <= GATES["year_max_median_abs_close_bps"] for row in yearly_rows
                ),
                "year_p95_close_bps": all(
                    metric_or(row, "p95_abs_close_bps", 9999.0)
                    <= GATES["year_max_p95_abs_close_bps"] for row in yearly_rows
                ),
                "integrity": all(
                    values["duplicate_timestamps"] == 0 and values["invalid_ohlc_rows"] == 0
                    for values in summary["integrity"].values()
                ),
            }
            summary["metric_checks"] = metric_checks
            if not all(metric_checks.values()):
                errors.append("one_or_more_alignment_gates_failed")

    summary["errors"] = errors
    summary["pass"] = len(errors) == 0
    alignment_warnings = summary.get("alignment_warning_years", [])
    if summary["pass"] and alignment_warnings:
        summary["decision"] = (
            "PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT_WITH_ALIGNMENT_WARNING"
        )
    elif summary["pass"]:
        summary["decision"] = "PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT"
    else:
        summary["decision"] = "BLOCK_ARTICLE1_REFERENCE_DATA_CONTRACT"

    summary_path = run_dir / "article1_data_contract_preflight.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    failed_checks = [name for name, value in summary.get("metric_checks", {}).items() if not value]
    decision_text = "\n".join(
        [
            "# XAUUSD Article 1 Data-Contract Preflight",
            "",
            f"Decision: `{summary['decision']}`",
            "",
            f"Reference window: `{REFERENCE_START_UTC}` to `{REFERENCE_END_UTC_EXCLUSIVE}` (exclusive)",
            "",
            f"Input hash lock: `{'PASS' if all_hashes_match else 'FAIL'}`",
            f"Failed metric checks: `{failed_checks}`",
            f"Alignment warnings: `{alignment_warnings}`",
            f"Errors: `{errors}`",
            "",
            "This preflight did not read strategy outcomes and authorizes no paper, demo, or live order.",
        ]
    ) + "\n"
    (run_dir / "article1_data_contract_decision.md").write_text(decision_text, encoding="utf-8")
    shutil.copy2(Path(__file__).resolve(), run_dir / Path(__file__).name)
    result_manifest = build_results_manifest(run_dir)
    (run_dir / "RESULTS_MANIFEST.json").write_text(
        json.dumps(result_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    zip_path = downloads / f"XAUUSD_ARTICLE1_DATA_CONTRACT_PREFLIGHT_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(run_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=f"{run_dir.name}/{path.name}")

    print(json.dumps({
        "decision": summary["decision"],
        "pass": summary["pass"],
        "failed_metric_checks": failed_checks,
        "alignment_warnings": alignment_warnings,
        "errors": errors,
        "results_zip": str(zip_path),
    }, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
