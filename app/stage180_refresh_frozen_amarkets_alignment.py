#!/usr/bin/env python3
"""Refresh AMarkets alignment using the already-PASSed frozen Stage177C contract.

This is an operational updater, not a new contract-discovery audit.

Key rules:
- The frozen contract is read from the provenance table of the existing PASS DB.
- Raw AMarkets files may begin earlier than the validated operational history.
- Rows before the existing validated database floor are quarantined/excluded.
- No Dukascopy download or Stage177C full audit is required for routine refresh.
- The existing database is replaced atomically only after overlap and schema
  checks pass.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def safe_import(path: Path, name: str) -> Any:
    """Import a source module compatibly with Python 3.14 dataclasses."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    old_sys_path = list(sys.path)
    sys.path.insert(0, str(path.parent))
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    finally:
        sys.path[:] = old_sys_path
    return module


def read_frozen_contract(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(
            f"Existing PASS alignment DB is required for frozen refresh: {db_path}"
        )
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT value FROM provenance WHERE key = ?",
            ("stage177c_time_contract",),
        ).fetchone()
    if row is None:
        raise RuntimeError("PASS database lacks stage177c_time_contract provenance")
    payload = json.loads(row[0])
    checks = {
        "pass_decision": str(payload.get("decision", "")).startswith("PASS"),
        "selection_no_holdout": payload.get("selection_used_holdout") is False,
        "contract_present": bool(payload.get("contract")),
        "standard_shift_present": payload.get("standard_shift_minutes") is not None,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "Frozen contract provenance is not eligible for operational refresh: "
            + json.dumps(checks, sort_keys=True)
        )
    return payload


def existing_db_stats(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"amarkets_m5_utc", "amarkets_h1_from_m5_utc", "provenance"}
        missing = sorted(required - tables)
        if missing:
            raise RuntimeError(f"Existing alignment DB missing tables: {missing}")
        m5 = connection.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM amarkets_m5_utc"
        ).fetchone()
        h1 = connection.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) "
            "FROM amarkets_h1_from_m5_utc"
        ).fetchone()
    return {
        "m5_rows": int(m5[0]),
        "m5_min_timestamp": int(m5[1]),
        "m5_max_timestamp": int(m5[2]),
        "h1_rows": int(h1[0]),
        "h1_min_timestamp": int(h1[1]),
        "h1_max_timestamp": int(h1[2]),
    }


def load_existing_overlap(db_path: Path, floor_timestamp: int) -> pd.DataFrame:
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query(
            """
            SELECT timestamp, open, high, low, close
            FROM amarkets_m5_utc
            WHERE timestamp >= ?
            ORDER BY timestamp
            """,
            connection,
            params=(int(floor_timestamp),),
        )
    return frame


def overlap_diagnostics(
    old_frame: pd.DataFrame,
    new_frame: pd.DataFrame,
    *,
    minimum_overlap_rows: int,
    max_median_close_diff_bps: float,
    max_p99_close_diff_bps: float,
) -> dict[str, Any]:
    merged = old_frame.merge(
        new_frame[["timestamp", "open", "high", "low", "close"]],
        on="timestamp",
        how="inner",
        suffixes=("_old", "_new"),
    )
    if len(merged) < minimum_overlap_rows:
        raise RuntimeError(
            f"Frozen refresh overlap too short: {len(merged)} < {minimum_overlap_rows}"
        )

    denominator = merged["close_old"].abs().replace(0.0, np.nan)
    close_diff_bps = (
        (merged["close_new"] - merged["close_old"]).abs() / denominator * 10_000.0
    ).dropna()
    median = float(close_diff_bps.median()) if len(close_diff_bps) else math.inf
    p99 = float(close_diff_bps.quantile(0.99)) if len(close_diff_bps) else math.inf
    checks = {
        "minimum_overlap_rows": len(merged) >= minimum_overlap_rows,
        "median_close_diff_bps": median <= max_median_close_diff_bps,
        "p99_close_diff_bps": p99 <= max_p99_close_diff_bps,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "Frozen refresh overlap parity failed: "
            + json.dumps(
                {
                    "checks": checks,
                    "overlap_rows": int(len(merged)),
                    "median_close_diff_bps": median,
                    "p99_close_diff_bps": p99,
                },
                sort_keys=True,
            )
        )
    return {
        "checks": checks,
        "overlap_rows": int(len(merged)),
        "median_close_diff_bps": median,
        "p99_close_diff_bps": p99,
        "first_overlap_utc": pd.to_datetime(
            int(merged["timestamp"].min()), unit="ms", utc=True
        ).isoformat(),
        "last_overlap_utc": pd.to_datetime(
            int(merged["timestamp"].max()), unit="ms", utc=True
        ).isoformat(),
    }




def load_mt5_history_csv(path: Path, expected_interval_ms: int) -> pd.DataFrame:
    """Load a complete MT5 tab-delimited history export without legacy row caps.

    Stage180 operational refresh must consume every valid row present in the
    canonical export.  This loader intentionally does not reuse the older
    Stage177B research loader because that path may apply bounded-history
    behaviour suitable for cross-feed audits but unsafe for routine append
    freshness.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if path.stat().st_size <= 0:
        raise RuntimeError(f"AMarkets export is empty: {path}")

    frame = pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )
    required = {"<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"AMarkets MT5 export missing columns {missing}: {path}")

    timestamps = pd.to_datetime(
        frame["<DATE>"].str.strip() + " " + frame["<TIME>"].str.strip(),
        format="%Y.%m.%d %H:%M",
        errors="coerce",
    )
    numeric_map = {
        "<OPEN>": "open",
        "<HIGH>": "high",
        "<LOW>": "low",
        "<CLOSE>": "close",
    }
    output = pd.DataFrame(index=frame.index)
    # Pandas datetime resolution is version-dependent (commonly ns, but us in
    # newer builds used with Python 3.14). Convert explicitly to datetime64[ms]
    # before extracting integers so the result is always epoch milliseconds.
    timestamp_is_valid = timestamps.notna().to_numpy(dtype=bool, copy=False)
    timestamp_ms_values = timestamps.to_numpy(dtype="datetime64[ms]").astype(
        "int64", copy=False
    )
    output["timestamp_naive_ms"] = timestamp_ms_values
    output.loc[~timestamp_is_valid, "timestamp_naive_ms"] = np.nan
    for source, target in numeric_map.items():
        output[target] = pd.to_numeric(frame[source], errors="coerce")
    volume_source = "<TICKVOL>" if "<TICKVOL>" in frame.columns else "<VOL>"
    output["volume"] = (
        pd.to_numeric(frame[volume_source], errors="coerce")
        if volume_source in frame.columns
        else 0.0
    )

    raw_rows = len(output)
    output = output.dropna(
        subset=["timestamp_naive_ms", "open", "high", "low", "close"]
    ).copy()
    output["timestamp_naive_ms"] = output["timestamp_naive_ms"].astype("int64")
    output["volume"] = pd.to_numeric(output["volume"], errors="coerce").fillna(0.0)
    output = output.sort_values("timestamp_naive_ms")
    duplicate_rows = int(output.duplicated("timestamp_naive_ms", keep="last").sum())
    output = output.drop_duplicates("timestamp_naive_ms", keep="last").reset_index(drop=True)

    if output.empty:
        raise RuntimeError(f"No valid AMarkets rows loaded from {path}")
    invariant = (
        (output["high"] >= output[["open", "close", "low"]].max(axis=1))
        & (output["low"] <= output[["open", "close", "high"]].min(axis=1))
        & (output["volume"] >= 0.0)
    )
    if not bool(invariant.all()):
        bad = int((~invariant).sum())
        raise RuntimeError(f"AMarkets MT5 export OHLC/volume invariant failed: {bad} rows")

    # Validate each bar directly against the expected epoch-aligned grid.
    # Avoid pandas Series.diff/modulo here: pandas/Python combinations can
    # promote the intermediate values and produce false remainders on large
    # millisecond timestamps. Integer numpy remainder is deterministic.
    interval_ms = int(expected_interval_ms)
    if interval_ms <= 0:
        raise RuntimeError(f"Invalid expected MT5 interval: {interval_ms}")
    timestamp_values = output["timestamp_naive_ms"].to_numpy(dtype="int64", copy=False)
    grid_remainders = np.remainder(timestamp_values, interval_ms)
    invalid_grid_count = int(np.count_nonzero(grid_remainders))
    if invalid_grid_count:
        raise RuntimeError(
            "AMarkets MT5 export timestamp grid mismatch: "
            f"{invalid_grid_count} rows"
        )

    first_ms = int(output["timestamp_naive_ms"].iloc[0])
    last_ms = int(output["timestamp_naive_ms"].iloc[-1])
    output.attrs["loader_diagnostics"] = {
        "loader": "STAGE180_COMPLETE_MT5_EXPORT_LOADER_V1",
        "source": str(path),
        "raw_rows": int(raw_rows),
        "valid_rows": int(len(output)),
        "dropped_invalid_rows": int(raw_rows - len(output) - duplicate_rows),
        "duplicate_timestamps_removed": duplicate_rows,
        "first_timestamp_naive": pd.to_datetime(first_ms, unit="ms").isoformat(),
        "last_timestamp_naive": pd.to_datetime(last_ms, unit="ms").isoformat(),
    }
    return output


def assert_source_tail_loaded(path: Path, loaded: pd.DataFrame) -> dict[str, Any]:
    """Fail closed if the loaded dataframe does not reach the export's final row."""
    tail = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, nrows=0)
    if "<DATE>" not in tail.columns or "<TIME>" not in tail.columns:
        raise RuntimeError(f"Cannot verify AMarkets export tail schema: {path}")
    # Read only the final non-empty data line to avoid a second full-file load.
    last_line = ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = bytearray()
        while position > 0 and len(buffer) < 65536:
            position -= 1
            handle.seek(position)
            char = handle.read(1)
            if char == b"\n" and buffer:
                candidate = bytes(reversed(buffer)).decode("utf-8", errors="replace").strip()
                if candidate:
                    last_line = candidate
                    break
                buffer.clear()
            else:
                buffer.extend(char)
        if not last_line and buffer:
            last_line = bytes(reversed(buffer)).decode("utf-8", errors="replace").strip()
    fields = last_line.split("\t")
    columns = list(tail.columns)
    if len(fields) != len(columns):
        raise RuntimeError(f"Cannot parse final AMarkets export row: {path}")
    row = dict(zip(columns, fields))
    source_last = pd.to_datetime(
        f"{row['<DATE>']} {row['<TIME>']}",
        format="%Y.%m.%d %H:%M",
        errors="raise",
    )
    source_last_ms = int(source_last.value // 1_000_000)
    loaded_last_ms = int(loaded["timestamp_naive_ms"].max())
    if loaded_last_ms != source_last_ms:
        raise RuntimeError(
            "AMarkets loader truncated source tail: "
            f"loaded={pd.to_datetime(loaded_last_ms, unit='ms')} "
            f"source={source_last}"
        )
    return {
        "source_last_naive": source_last.isoformat(),
        "loaded_last_naive": pd.to_datetime(loaded_last_ms, unit="ms").isoformat(),
        "pass": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aligned-db",
        default="data/local/stage177c_amarkets_alignment/"
        "xauusd_amarkets_alignment.sqlite",
    )
    parser.add_argument(
        "--stage177c-app",
        default="app/stage177c_amarkets_dst_contract.py",
    )
    parser.add_argument(
        "--report",
        default="reports/stage180_frozen_model_shadow/"
        "stage180_frozen_alignment_refresh.json",
    )
    parser.add_argument("--minimum-overlap-rows", type=int, default=10_000)
    parser.add_argument("--max-median-close-diff-bps", type=float, default=0.50)
    parser.add_argument("--max-p99-close-diff-bps", type=float, default=5.00)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    aligned_db = resolve(root, args.aligned_db)
    stage177c_path = resolve(root, args.stage177c_app)
    report_path = resolve(root, args.report)

    frozen = read_frozen_contract(aligned_db)
    before = existing_db_stats(aligned_db)
    operational_floor = int(before["m5_min_timestamp"])

    stage177c = safe_import(stage177c_path, "stage177c_frozen_refresh_runtime")
    contract = stage177c.Contract(
        name=str(frozen["contract"]),
        standard_shift_minutes=int(frozen["standard_shift_minutes"]),
        dst_shift_minutes=(
            int(frozen["dst_shift_minutes"])
            if frozen.get("dst_shift_minutes") is not None
            else None
        ),
        dst_calendar=frozen.get("dst_calendar"),
    )

    m5_path = Path(frozen["source_amarkets_m5"]).expanduser().resolve()
    h1_value = frozen.get("source_amarkets_h1")
    h1_path = Path(h1_value).expanduser().resolve() if h1_value else None
    if not m5_path.exists():
        raise FileNotFoundError(m5_path)
    if h1_path is not None and not h1_path.exists():
        raise FileNotFoundError(h1_path)

    raw_m5 = load_mt5_history_csv(m5_path, stage177c.M5_MS)
    raw_m5_tail = assert_source_tail_loaded(m5_path, raw_m5)
    raw_h1 = (
        load_mt5_history_csv(h1_path, stage177c.H1_MS)
        if h1_path is not None
        else None
    )
    raw_h1_tail = (
        assert_source_tail_loaded(h1_path, raw_h1)
        if h1_path is not None and raw_h1 is not None
        else None
    )

    aligned_m5_all = stage177c.apply_contract(raw_m5, contract)
    aligned_h1_all = (
        stage177c.apply_contract(raw_h1, contract)
        if raw_h1 is not None
        else None
    )

    # Quarantine any history older than the floor of the previously PASSed DB.
    aligned_m5 = aligned_m5_all[
        aligned_m5_all["timestamp"] >= operational_floor
    ].copy()
    aligned_h1_direct = (
        aligned_h1_all[aligned_h1_all["timestamp"] >= operational_floor].copy()
        if aligned_h1_all is not None
        else None
    )
    if aligned_m5.empty:
        raise RuntimeError("No M5 rows remain after applying operational history floor")

    old_overlap = load_existing_overlap(aligned_db, operational_floor)
    parity = overlap_diagnostics(
        old_overlap,
        aligned_m5,
        minimum_overlap_rows=min(
            int(args.minimum_overlap_rows),
            max(100, len(old_overlap)),
        ),
        max_median_close_diff_bps=float(args.max_median_close_diff_bps),
        max_p99_close_diff_bps=float(args.max_p99_close_diff_bps),
    )

    aligned_h1_from_m5 = stage177c.derive_h1_from_aligned_m5(aligned_m5)
    if aligned_h1_from_m5.empty:
        raise RuntimeError("Derived H1 is empty after frozen refresh")

    refreshed_payload = dict(frozen)
    refreshed_payload.update(
        {
            "operational_refresh": True,
            "operational_refresh_generated_utc": now_utc(),
            "operational_history_floor_utc": pd.to_datetime(
                operational_floor, unit="ms", utc=True
            ).isoformat(),
            "pre_floor_raw_history_quarantined": True,
            "full_contract_rediscovery_performed": False,
        }
    )

    stage177c.write_sqlite(
        aligned_db,
        aligned_m5,
        aligned_h1_direct,
        aligned_h1_from_m5,
        refreshed_payload,
    )

    with sqlite3.connect(aligned_db) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO provenance(key, value) VALUES (?, ?)",
            (
                "stage180_frozen_operational_refresh",
                json.dumps(
                    {
                        "generated_utc": now_utc(),
                        "operational_floor_timestamp": operational_floor,
                        "source_m5": str(m5_path),
                        "source_h1": str(h1_path) if h1_path else None,
                        "pre_floor_rows_excluded": int(
                            len(aligned_m5_all) - len(aligned_m5)
                        ),
                        "overlap_parity": parity,
                    },
                    sort_keys=True,
                ),
            ),
        )
        connection.commit()

    after = existing_db_stats(aligned_db)
    complete_h1 = aligned_h1_from_m5[
        aligned_h1_from_m5["m5_bar_count"] >= 12
    ]
    result = {
        "status": "PASS_STAGE180_FROZEN_ALIGNMENT_REFRESH",
        "generated_utc": now_utc(),
        "frozen_contract": {
            "contract": frozen["contract"],
            "standard_shift_minutes": frozen["standard_shift_minutes"],
            "dst_shift_minutes": frozen.get("dst_shift_minutes"),
            "dst_calendar": frozen.get("dst_calendar"),
            "selection_used_holdout": frozen.get("selection_used_holdout"),
        },
        "source_m5": str(m5_path),
        "source_h1": str(h1_path) if h1_path else None,
        "raw_m5_first_naive": raw_m5.attrs.get("loader_diagnostics", {}).get(
            "first_timestamp_naive"
        ),
        "raw_m5_last_naive": raw_m5.attrs.get("loader_diagnostics", {}).get(
            "last_timestamp_naive"
        ),
        "raw_h1_first_naive": (
            raw_h1.attrs.get("loader_diagnostics", {}).get("first_timestamp_naive")
            if raw_h1 is not None
            else None
        ),
        "raw_m5_loader": raw_m5.attrs.get("loader_diagnostics", {}),
        "raw_h1_loader": (
            raw_h1.attrs.get("loader_diagnostics", {}) if raw_h1 is not None else None
        ),
        "raw_m5_tail_verification": raw_m5_tail,
        "raw_h1_tail_verification": raw_h1_tail,
        "operational_history_floor_utc": pd.to_datetime(
            operational_floor, unit="ms", utc=True
        ).isoformat(),
        "pre_floor_m5_rows_quarantined": int(len(aligned_m5_all) - len(aligned_m5)),
        "before": before,
        "after": after,
        "overlap_parity": parity,
        "latest_complete_h1_utc": (
            pd.to_datetime(
                int(complete_h1["timestamp"].max()), unit="ms", utc=True
            ).isoformat()
            if len(complete_h1)
            else None
        ),
        "dukascopy_required_for_routine_refresh": False,
        "full_stage177c_audit_rerun": False,
    }
    write_json(report_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
