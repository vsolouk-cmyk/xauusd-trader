#!/usr/bin/env python3
"""Commercial Closure Sprint for the frozen XAUUSD candidate.

This is a single bounded commercial-readiness audit, not a new research scan.

It:
- reconstructs the exact Stage178 walk-forward trades;
- verifies parity with the saved Stage178 result;
- joins 2015+ signals to broker M5 execution data;
- applies frozen EU-DST timestamp alignment;
- models observed spread plus fixed slippage stress;
- includes the untouched 2025+ holdout trades;
- computes period stability, bootstrap uncertainty, drawdown and a risk contract;
- emits one commercial decision.

It never places, previews, routes, or authorizes a live broker order.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


MS_HOUR = 3_600_000
UTC = timezone.utc

READY = "READY_FOR_CONTROLLED_PAPER_ORDERS"
SHADOW = "KEEP_SHADOW_AND_START_PARALLEL_NEXT_METHOD_FAMILY"
KILL = "KILL_CURRENT_COMMERCIAL_FORMULATION"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=json_default)
        + "\n",
        encoding="utf-8",
    )


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(os.path.expanduser(str(value)))
    return path if path.is_absolute() else root / path


def safe_import(path: Path, name: str) -> Any:
    """Import source compatibly with Python 3.14 dataclasses."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    old_path = list(sys.path)
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
        sys.path[:] = old_path
    return module


def profit_factor(values: Iterable[float]) -> float | None:
    arr = np.asarray(list(values), dtype=float)
    gains = float(arr[arr > 0].sum())
    losses = float(-arr[arr < 0].sum())
    if losses == 0.0:
        return None if gains == 0.0 else 999.0
    return gains / losses


def max_drawdown(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return 0.0
    equity = np.cumsum(arr)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])
    return float(np.max(peaks[1:] - equity))


def metrics(values: Iterable[float]) -> dict[str, Any]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {
            "trades": 0,
            "mean_bps": None,
            "median_bps": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown_bps": None,
            "total_bps": None,
        }
    return {
        "trades": int(arr.size),
        "mean_bps": float(np.mean(arr)),
        "median_bps": float(np.median(arr)),
        "win_rate": float(np.mean(arr > 0.0)),
        "profit_factor": profit_factor(arr),
        "max_drawdown_bps": max_drawdown(arr),
        "total_bps": float(np.sum(arr)),
    }


def datetime_to_epoch_ms(values: Any) -> np.ndarray:
    parsed = pd.to_datetime(values, utc=True)
    if isinstance(parsed, pd.Series):
        array = parsed.to_numpy(dtype="datetime64[ms]")
    elif isinstance(parsed, pd.DatetimeIndex):
        array = parsed.to_numpy(dtype="datetime64[ms]")
    else:
        array = np.asarray(parsed, dtype="datetime64[ms]")
    return np.asarray(array, dtype="datetime64[ms]").astype("int64")


def infer_point_size(raw_close: pd.Series) -> tuple[float, dict[str, Any]]:
    samples = raw_close.dropna().astype(str).str.strip().head(20_000)
    decimals: list[int] = []
    for value in samples:
        if "e" in value.lower():
            continue
        if "." in value:
            decimals.append(len(value.rsplit(".", 1)[1].rstrip()))
        else:
            decimals.append(0)
    if not decimals:
        return 0.01, {"mode_decimals": None, "fallback": True}
    counts = pd.Series(decimals).value_counts()
    mode_decimals = int(counts.index[0])
    mode_decimals = max(0, min(mode_decimals, 5))
    return 10.0 ** (-mode_decimals), {
        "mode_decimals": mode_decimals,
        "sample_count": int(len(decimals)),
        "fallback": False,
    }


def load_and_align_raw_m5(
    path: Path,
    stage177b: Any,
    stage177c: Any,
    contract_payload: dict[str, Any],
    operational_floor_ms: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, diagnostics = stage177b.read_flexible_csv(path)
    columns = list(frame.columns)
    mapping: dict[str, str] = {}
    for target, candidates in {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c", "last"),
        "volume": ("tick_volume", "tickvolume", "tickvol", "volume", "vol"),
        "spread": ("spread",),
    }.items():
        selected = stage177b.pick_column(columns, candidates)
        if target in {"open", "high", "low", "close"} and selected is None:
            raise RuntimeError(f"Raw M5 missing {target}: {columns}")
        if selected is not None:
            mapping[target] = selected

    parsed, timestamp_diag = stage177b.parse_timestamp(frame)
    point_size, point_diag = infer_point_size(frame[mapping["close"]])

    output = pd.DataFrame({"datetime_naive": parsed})
    for column in ["open", "high", "low", "close"]:
        output[column] = pd.to_numeric(frame[mapping[column]], errors="coerce")
    output["volume"] = (
        pd.to_numeric(frame[mapping["volume"]], errors="coerce")
        if "volume" in mapping
        else np.nan
    )
    output["spread_points"] = (
        pd.to_numeric(frame[mapping["spread"]], errors="coerce")
        if "spread" in mapping
        else np.nan
    )
    output = output.dropna(subset=["datetime_naive", "open", "high", "low", "close"])
    invariant = (
        (output["high"] >= output[["open", "close", "low"]].max(axis=1))
        & (output["low"] <= output[["open", "close", "high"]].min(axis=1))
        & (output[["open", "high", "low", "close"]] > 0).all(axis=1)
    )
    output = output[invariant].copy()
    output["timestamp_naive_ms"] = datetime_to_epoch_ms(output["datetime_naive"])

    contract = stage177c.Contract(
        name=str(contract_payload["contract"]),
        standard_shift_minutes=int(contract_payload["standard_shift_minutes"]),
        dst_shift_minutes=(
            int(contract_payload["dst_shift_minutes"])
            if contract_payload.get("dst_shift_minutes") is not None
            else None
        ),
        dst_calendar=contract_payload.get("dst_calendar"),
    )
    aligned = stage177c.apply_contract(output, contract)
    raw_aligned_rows = int(len(aligned))
    aligned = aligned[aligned["timestamp"] >= int(operational_floor_ms)].copy()
    aligned["bucket_h1"] = (aligned["timestamp"] // MS_HOUR) * MS_HOUR
    aligned = aligned.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    aligned["spread_price"] = aligned["spread_points"] * float(point_size)

    diag = {
        **diagnostics,
        **timestamp_diag,
        "path": str(path),
        "raw_rows": int(len(frame)),
        "valid_rows_before_alignment": int(len(output)),
        "aligned_rows_before_floor": raw_aligned_rows,
        "aligned_rows_after_floor": int(len(aligned)),
        "pre_floor_rows_excluded": raw_aligned_rows - int(len(aligned)),
        "first_aligned_utc": (
            pd.to_datetime(int(aligned["timestamp"].min()), unit="ms", utc=True).isoformat()
            if len(aligned)
            else None
        ),
        "last_aligned_utc": (
            pd.to_datetime(int(aligned["timestamp"].max()), unit="ms", utc=True).isoformat()
            if len(aligned)
            else None
        ),
        "point_size": float(point_size),
        "point_size_diagnostics": point_diag,
        "spread_column_present": "spread" in mapping,
    }
    return aligned.reset_index(drop=True), diag


def operational_floor_from_db(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT MIN(timestamp) FROM amarkets_m5_utc"
        ).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError("Cannot determine operational AMarkets history floor")
    return int(row[0])


def load_operational_h1_timestamps(path: Path) -> np.ndarray:
    """Load the exact ordered AMarkets H1 sequence used by Stage178.

    Stage178's directional target is based on pandas ``shift(-horizon)``.
    Therefore the commercial execution audit must advance by H1 row position,
    not by elapsed wall-clock hours. This matters across weekends, holidays,
    and broker maintenance gaps.
    """
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        selected = next(
            (
                name
                for name in (
                    "amarkets_h1_from_m5_utc",
                    "amarkets_h1_direct_utc",
                )
                if name in tables
            ),
            None,
        )
        if selected is None:
            raise RuntimeError(
                "Aligned AMarkets database has no operational H1 table"
            )
        frame = pd.read_sql_query(
            f'SELECT timestamp FROM "{selected}" ORDER BY timestamp',
            connection,
        )

    values = pd.to_numeric(frame["timestamp"], errors="coerce").dropna()
    values = values.astype("int64").drop_duplicates().sort_values()
    timestamps = values.to_numpy(dtype=np.int64)
    if timestamps.size < 2:
        raise RuntimeError("Operational AMarkets H1 sequence is too short")
    if np.any(np.diff(timestamps) <= 0):
        raise RuntimeError("Operational AMarkets H1 timestamps are not monotonic")
    return timestamps


def read_pass_contract_from_db(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT value FROM provenance WHERE key = ?",
            ("stage177c_time_contract",),
        ).fetchone()
    if row is None:
        raise RuntimeError("PASS Stage177C contract missing from provenance")
    payload = json.loads(row[0])
    if not str(payload.get("decision", "")).startswith("PASS"):
        raise RuntimeError("Stage177C provenance is not PASS")
    if payload.get("selection_used_holdout") is not False:
        raise RuntimeError("Stage177C contract selection used holdout")
    return payload


def reconstruct_reference_trades(
    stage178: Any,
    stage178_config: dict[str, Any],
    stage178_summary: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    reference_db = Path(stage178_summary["reference_db"]).expanduser()
    reference, _ = stage178.load_ohlcv_table(
        reference_db,
        ["dukascopy_h1_canonical", "dukascopy_h1_from_m5"],
    )
    features, feature_columns = stage178.build_features(reference)

    selected = stage178_summary["selected_candidate"]
    target_item = next(
        item for item in stage178_config["targets"]
        if item["key"] == selected["target"]
    )
    target_spec = stage178.TargetSpec(**target_item)
    target = stage178.make_target(
        reference,
        target_spec,
        float(stage178_config["round_trip_cost_bps"]),
    )
    training = stage178.model_dataset(
        features, target, feature_columns, require_label=True
    )
    evaluation = stage178.model_dataset(
        features, target, feature_columns, require_label=False
    )
    summary, folds, trades = stage178.evaluate_candidate_reference(
        training,
        evaluation,
        feature_columns,
        target_spec,
        selected["model"],
        stage178_config,
    )

    saved = stage178_summary["selected_reference_metrics"]
    checks = {
        "candidate": summary["candidate"] == selected["candidate"],
        "trades": int(summary["trades"]) == int(saved["trades"]),
        "mean_net_bps": abs(
            float(summary["mean_net_bps"]) - float(saved["mean_net_bps"])
        ) <= 1e-8,
        "profit_factor": abs(
            float(summary["profit_factor"]) - float(saved["profit_factor"])
        ) <= 1e-8,
        "minimum_fold_mean": abs(
            float(summary["minimum_fold_mean_net_bps"])
            - float(saved["minimum_fold_mean_net_bps"])
        ) <= 1e-8,
    }
    if not all(checks.values()):
        raise RuntimeError(
            "Stage178 reference parity failed: "
            + json.dumps(checks, sort_keys=True)
        )
    trades = trades.copy()
    trades["source_period"] = "REFERENCE_WALK_FORWARD"
    return trades, {"checks": checks, "pass": True, "reconstructed": summary}


def load_holdout_trades(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "timestamp", "dt", "direction", "gross_bps", "net_bps",
        "severe_net_bps", "resolution_hours"
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"Stage178 holdout ledger missing columns: {missing}")
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame["direction"] = pd.to_numeric(frame["direction"], errors="coerce")
    frame["resolution_hours"] = pd.to_numeric(
        frame["resolution_hours"], errors="coerce"
    )
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp", "direction", "resolution_hours", "dt"])
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame["direction"] = frame["direction"].astype("int64")
    frame["source_period"] = "AMARKETS_2025_PLUS_HOLDOUT"
    return frame.sort_values("timestamp").reset_index(drop=True)


def execution_ledger(
    signals: pd.DataFrame,
    m5: pd.DataFrame,
    h1_timestamps: np.ndarray,
    *,
    minimum_normal_cost_bps: float,
    minimum_severe_cost_bps: float,
    normal_slippage_bps: float,
    severe_slippage_bps: float,
    severe_spread_multiplier: float,
) -> pd.DataFrame:
    """Evaluate frozen signals with exact Stage178 horizon semantics.

    Stage178 defines the directional target as:

    - entry: open of H1 row ``i + 1``;
    - exit: close of H1 row ``i + horizon``.

    The former implementation incorrectly used
    ``signal_timestamp + horizon * one_hour``. That is not equivalent across
    weekends, holidays, or missing broker bars and caused artificial coverage
    loss plus incorrect exits.
    """
    grouped = {
        int(bucket): group.sort_values("timestamp")
        for bucket, group in m5.groupby("bucket_h1", sort=False)
    }
    h1_values = np.asarray(h1_timestamps, dtype=np.int64)
    h1_position = {int(timestamp): index for index, timestamp in enumerate(h1_values)}
    rows: list[dict[str, Any]] = []

    for record in signals.sort_values("timestamp").itertuples(index=False):
        signal_ts = int(record.timestamp)
        horizon = int(round(float(record.resolution_hours)))
        position = h1_position.get(signal_ts)

        common = {
            "timestamp": signal_ts,
            "dt": pd.to_datetime(signal_ts, unit="ms", utc=True),
            "source_period": record.source_period,
            "fold": getattr(record, "fold", None),
            "direction": int(record.direction),
            "probability_up": getattr(record, "probability_up", None),
            "resolution_hours": horizon,
            "research_gross_bps": float(record.gross_bps),
            "horizon_semantics": "H1_ROW_POSITION",
        }

        if position is None:
            rows.append({
                **common,
                "status": "SIGNAL_H1_TIMESTAMP_MISSING",
            })
            continue

        if position + horizon >= len(h1_values):
            rows.append({
                **common,
                "status": "HORIZON_NOT_YET_AVAILABLE",
            })
            continue

        entry_bucket = int(h1_values[position + 1])
        exit_bucket = int(h1_values[position + horizon])
        entry = grouped.get(entry_bucket)
        exit_ = grouped.get(exit_bucket)

        if entry is None or exit_ is None or len(entry) < 12 or len(exit_) < 12:
            rows.append({
                **common,
                "entry_bucket_timestamp": entry_bucket,
                "exit_bucket_timestamp": exit_bucket,
                "entry_bucket_utc": pd.to_datetime(
                    entry_bucket, unit="ms", utc=True
                ).isoformat(),
                "exit_bucket_utc": pd.to_datetime(
                    exit_bucket, unit="ms", utc=True
                ).isoformat(),
                "status": "MISSING_COMPLETE_M5_BUCKET",
            })
            continue

        entry_open = float(entry.iloc[0]["open"])
        exit_close = float(exit_.iloc[-1]["close"])
        entry_spread_price = (
            float(entry.iloc[0]["spread_price"])
            if np.isfinite(entry.iloc[0]["spread_price"])
            else 0.0
        )
        exit_spread_price = (
            float(exit_.iloc[-1]["spread_price"])
            if np.isfinite(exit_.iloc[-1]["spread_price"])
            else 0.0
        )
        direction = int(record.direction)
        gross = direction * (exit_close / entry_open - 1.0) * 10_000.0

        if direction > 0:
            observed_spread_bps = entry_spread_price / entry_open * 10_000.0
        else:
            observed_spread_bps = exit_spread_price / exit_close * 10_000.0

        normal_cost = max(
            float(minimum_normal_cost_bps),
            observed_spread_bps + float(normal_slippage_bps),
        )
        severe_cost = max(
            float(minimum_severe_cost_bps),
            observed_spread_bps * float(severe_spread_multiplier)
            + float(severe_slippage_bps),
        )
        rows.append({
            **common,
            "entry_bucket_timestamp": entry_bucket,
            "exit_bucket_timestamp": exit_bucket,
            "entry_bucket_utc": pd.to_datetime(
                entry_bucket, unit="ms", utc=True
            ).isoformat(),
            "exit_bucket_utc": pd.to_datetime(
                exit_bucket, unit="ms", utc=True
            ).isoformat(),
            "status": "EVALUATED",
            "m5_gross_bps": gross,
            "gross_transfer_difference_bps": gross - float(record.gross_bps),
            "entry_open": entry_open,
            "exit_close": exit_close,
            "observed_spread_bps": observed_spread_bps,
            "normal_execution_cost_bps": normal_cost,
            "severe_execution_cost_bps": severe_cost,
            "normal_net_bps": gross - normal_cost,
            "severe_net_bps": gross - severe_cost,
            "stress_8bps_net_bps": gross - max(
                8.0, observed_spread_bps + 4.0
            ),
            "stress_10bps_net_bps": gross - max(
                10.0, observed_spread_bps + 6.0
            ),
        })
    return pd.DataFrame(rows)


def moving_block_means(
    values: np.ndarray,
    *,
    reps: int,
    block_length: int,
    seed: int,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)
    block_length = max(1, min(int(block_length), n))
    blocks_needed = math.ceil(n / block_length)
    starts_max = n - block_length
    rng = np.random.default_rng(seed)
    output = np.empty(int(reps), dtype=float)
    for i in range(int(reps)):
        starts = rng.integers(0, starts_max + 1, size=blocks_needed)
        sample = np.concatenate(
            [values[start:start + block_length] for start in starts]
        )[:n]
        output[i] = float(np.mean(sample))
    return output


def bootstrap_summary(
    values: np.ndarray,
    *,
    reps: int,
    block_length: int,
    seed: int,
) -> dict[str, Any]:
    boot = moving_block_means(
        values, reps=reps, block_length=block_length, seed=seed
    )
    return {
        "reps": int(reps),
        "block_length": int(block_length),
        "mean_bps": float(np.mean(values)) if len(values) else None,
        "p10_mean_bps": float(np.quantile(boot, 0.10)) if len(boot) else None,
        "p50_mean_bps": float(np.quantile(boot, 0.50)) if len(boot) else None,
        "p90_mean_bps": float(np.quantile(boot, 0.90)) if len(boot) else None,
        "probability_mean_le_zero": float(np.mean(boot <= 0.0)) if len(boot) else None,
    }


def bootstrap_drawdowns(
    values: np.ndarray,
    *,
    reps: int,
    block_length: int,
    seed: int,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)
    block_length = max(1, min(int(block_length), n))
    blocks_needed = math.ceil(n / block_length)
    starts_max = n - block_length
    rng = np.random.default_rng(seed)
    out = np.empty(int(reps), dtype=float)
    for i in range(int(reps)):
        starts = rng.integers(0, starts_max + 1, size=blocks_needed)
        sample = np.concatenate(
            [values[start:start + block_length] for start in starts]
        )[:n]
        out[i] = max_drawdown(sample)
    return out


def period_label(dt: pd.Timestamp) -> str:
    year = int(dt.year)
    if year <= 2017:
        return "2015_2017"
    if year <= 2021:
        return "2018_2021"
    if year <= 2024:
        return "2022_2024"
    return "2025_PLUS"


def period_table(ledger: pd.DataFrame) -> pd.DataFrame:
    evaluated = ledger[ledger["status"] == "EVALUATED"].copy()
    evaluated["period"] = evaluated["dt"].map(period_label)
    rows: list[dict[str, Any]] = []
    for period in ["2015_2017", "2018_2021", "2022_2024", "2025_PLUS"]:
        part = evaluated[evaluated["period"] == period]
        rows.append({
            "period": period,
            **metrics(part["normal_net_bps"].to_numpy(float)),
            "severe_mean_bps": (
                float(part["severe_net_bps"].mean()) if len(part) else None
            ),
            "mean_observed_spread_bps": (
                float(part["observed_spread_bps"].mean()) if len(part) else None
            ),
        })
    return pd.DataFrame(rows)


def risk_contract(
    net_bps: np.ndarray,
    *,
    target_q95_trade_loss_equity_pct: float,
    maximum_bootstrap_drawdown_pct: float,
    bootstrap_reps: int,
    block_length: int,
    seed: int,
) -> dict[str, Any]:
    losses = -np.asarray(net_bps, dtype=float)
    losses = losses[losses > 0]
    q95_loss_bps = float(np.quantile(losses, 0.95)) if len(losses) else 1.0
    target_loss_bps_equity = float(target_q95_trade_loss_equity_pct) * 100.0
    exposure_from_trade = min(1.0, target_loss_bps_equity / max(q95_loss_bps, 1e-9))

    drawdown_boot = bootstrap_drawdowns(
        np.asarray(net_bps, dtype=float),
        reps=int(bootstrap_reps),
        block_length=int(block_length),
        seed=int(seed),
    )
    p95_drawdown_bps = (
        float(np.quantile(drawdown_boot, 0.95)) if len(drawdown_boot) else 0.0
    )
    maximum_dd_bps_equity = float(maximum_bootstrap_drawdown_pct) * 100.0
    exposure_from_dd = (
        min(1.0, maximum_dd_bps_equity / p95_drawdown_bps)
        if p95_drawdown_bps > 0
        else 1.0
    )
    exposure = min(exposure_from_trade, exposure_from_dd, 0.50)
    return {
        "maximum_notional_to_equity": float(exposure),
        "q95_single_trade_loss_bps_at_1x": q95_loss_bps,
        "bootstrap_p95_drawdown_bps_at_1x": p95_drawdown_bps,
        "estimated_q95_single_trade_loss_equity_pct": (
            exposure * q95_loss_bps / 100.0
        ),
        "estimated_bootstrap_p95_drawdown_equity_pct": (
            exposure * p95_drawdown_bps / 100.0
        ),
        "maximum_concurrent_positions": 1,
        "daily_new_positions_cap": 1,
        "weekly_loss_pause_equity_pct": 2.0,
        "hard_drawdown_kill_switch_equity_pct": 8.0,
        "paper_only": True,
        "demo_allowed": False,
        "live_allowed": False,
    }


def decision_markdown(summary: dict[str, Any]) -> str:
    failed = [name for name, passed in summary["gates"].items() if not passed]
    m = summary["execution_metrics"]
    return "\n".join([
        "# XAUUSD Commercial Closure Sprint",
        "",
        f"Decision: `{summary['decision']}`",
        "",
        "## Frozen candidate",
        "",
        f"- Candidate: `{summary['candidate']}`",
        f"- Execution-aware trades: `{m['trades']}`",
        f"- Mean normal net: `{m['mean_bps']}` bps",
        f"- Profit factor: `{m['profit_factor']}`",
        f"- Maximum drawdown: `{m['max_drawdown_bps']}` bps at 1x notional",
        f"- Bootstrap p10 mean: `{summary['bootstrap']['p10_mean_bps']}` bps",
        "",
        "## Decision gates",
        "",
        f"- Failed gates: `{failed}`",
        "",
        "## Operational boundary",
        "",
        "- No live or demo order is authorized by this sprint.",
        "- READY authorizes controlled paper orders only.",
        "- The frozen Stage180 shadow remains active in parallel.",
        "",
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/commercial_closure_sprint.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    config_path = resolve(root, args.config)
    config = read_json(config_path)

    out = resolve(root, config["output_dir"])
    out.mkdir(parents=True, exist_ok=True)

    stage178_path = resolve(root, config["stage178_app"])
    stage177b_path = resolve(root, config["stage177b_app"])
    stage177c_path = resolve(root, config["stage177c_app"])
    stage178_config_path = resolve(root, config["stage178_config"])
    stage178_summary_path = resolve(root, config["stage178_summary"])
    stage179_summary_path = resolve(root, config["stage179_summary"])
    holdout_trades_path = resolve(root, config["stage178_holdout_trades"])
    aligned_db = resolve(root, config["aligned_amarkets_db"])
    raw_m5_path = resolve(root, config["raw_amarkets_m5"])

    for path in [
        stage178_path, stage177b_path, stage177c_path, stage178_config_path,
        stage178_summary_path, stage179_summary_path, holdout_trades_path,
        aligned_db, raw_m5_path,
    ]:
        if not path.exists():
            raise FileNotFoundError(path)

    stage178 = safe_import(stage178_path, "commercial_closure_stage178")
    stage177b = safe_import(stage177b_path, "commercial_closure_stage177b")
    stage177c = safe_import(stage177c_path, "commercial_closure_stage177c")

    stage178_config = read_json(stage178_config_path)
    stage178_summary = read_json(stage178_summary_path)
    stage179_summary = read_json(stage179_summary_path)

    selected = stage178_summary["selected_candidate"]
    if selected["candidate"] != stage179_summary["stage178_selected"]["candidate"]:
        raise RuntimeError("Stage178/179 candidate mismatch")
    if stage178_summary["decision"] != "PROMOTE_TO_CONTROLLED_PAPER_DESIGN":
        raise RuntimeError("Stage178 selected candidate was not promoted to paper design")
    if stage179_summary["decision"] != "RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_DIAGNOSTIC":
        raise RuntimeError("Unexpected Stage179 state")
    failed179 = sorted(
        name for name, passed in stage179_summary["gates"].items() if not bool(passed)
    )
    if failed179 != ["candidate_bootstrap_p10_positive"]:
        raise RuntimeError(
            "Commercial closure is allowed only when Stage179 failed solely on "
            "bootstrap lower-bound uncertainty"
        )

    reference_trades, reference_parity = reconstruct_reference_trades(
        stage178,
        stage178_config,
        stage178_summary,
    )
    holdout = load_holdout_trades(holdout_trades_path)

    floor_ms = operational_floor_from_db(aligned_db)
    operational_h1_timestamps = load_operational_h1_timestamps(aligned_db)
    reference_trades = reference_trades[
        (reference_trades["timestamp"] >= floor_ms)
        & (reference_trades["timestamp"] < int(pd.Timestamp("2025-01-01", tz="UTC").timestamp() * 1000))
    ].copy()
    signals = pd.concat([reference_trades, holdout], ignore_index=True)
    signals = signals.sort_values("timestamp").drop_duplicates(
        ["timestamp", "source_period"], keep="last"
    )

    frozen_contract = read_pass_contract_from_db(aligned_db)
    m5, m5_diag = load_and_align_raw_m5(
        raw_m5_path,
        stage177b,
        stage177c,
        frozen_contract,
        floor_ms,
    )

    execution = execution_ledger(
        signals,
        m5,
        operational_h1_timestamps,
        minimum_normal_cost_bps=float(config["execution"]["minimum_normal_cost_bps"]),
        minimum_severe_cost_bps=float(config["execution"]["minimum_severe_cost_bps"]),
        normal_slippage_bps=float(config["execution"]["normal_slippage_bps"]),
        severe_slippage_bps=float(config["execution"]["severe_slippage_bps"]),
        severe_spread_multiplier=float(config["execution"]["severe_spread_multiplier"]),
    )
    execution.to_csv(out / "commercial_closure_execution_ledger.csv", index=False)

    evaluated = execution[execution["status"] == "EVALUATED"].copy()
    normal_metrics = metrics(evaluated["normal_net_bps"].to_numpy(float))
    severe_metrics = metrics(evaluated["severe_net_bps"].to_numpy(float))
    stress8_metrics = metrics(evaluated["stress_8bps_net_bps"].to_numpy(float))
    stress10_metrics = metrics(evaluated["stress_10bps_net_bps"].to_numpy(float))

    periods = period_table(execution)
    periods.to_csv(out / "commercial_closure_period_metrics.csv", index=False)
    positive_period_share = float(
        np.mean(
            periods.loc[periods["trades"] > 0, "mean_bps"].to_numpy(float) > 0
        )
    ) if int((periods["trades"] > 0).sum()) else 0.0
    holdout_row = periods[periods["period"] == "2025_PLUS"].iloc[0]

    bootstrap = bootstrap_summary(
        evaluated["normal_net_bps"].to_numpy(float),
        reps=int(config["bootstrap"]["reps"]),
        block_length=int(config["bootstrap"]["block_length"]),
        seed=int(config["bootstrap"]["seed"]),
    )
    risk = risk_contract(
        evaluated["normal_net_bps"].to_numpy(float),
        target_q95_trade_loss_equity_pct=float(
            config["risk"]["target_q95_trade_loss_equity_pct"]
        ),
        maximum_bootstrap_drawdown_pct=float(
            config["risk"]["maximum_bootstrap_drawdown_pct"]
        ),
        bootstrap_reps=int(config["risk"]["bootstrap_reps"]),
        block_length=int(config["risk"]["block_length"]),
        seed=int(config["risk"]["seed"]),
    )

    research_mean = float(signals["gross_bps"].mean()) if len(signals) else None
    execution_gross_mean = (
        float(evaluated["m5_gross_bps"].mean()) if len(evaluated) else None
    )
    transfer_ratio = (
        execution_gross_mean / research_mean
        if research_mean is not None and research_mean > 0 and execution_gross_mean is not None
        else None
    )
    evaluated_coverage = len(evaluated) / len(signals) if len(signals) else 0.0
    spread_p95 = (
        float(evaluated["observed_spread_bps"].quantile(0.95))
        if len(evaluated)
        else None
    )
    max_year_share = (
        float(evaluated["dt"].dt.year.value_counts(normalize=True).iloc[0])
        if len(evaluated)
        else 1.0
    )

    gate_cfg = config["gates"]
    gates = {
        "stage178_reference_parity": bool(reference_parity["pass"]),
        "minimum_execution_coverage": evaluated_coverage
        >= float(gate_cfg["minimum_execution_coverage"]),
        "minimum_trades": normal_metrics["trades"] >= int(gate_cfg["minimum_trades"]),
        "minimum_normal_mean": normal_metrics["mean_bps"] is not None
        and normal_metrics["mean_bps"] >= float(gate_cfg["minimum_normal_mean_bps"]),
        "minimum_severe_mean": severe_metrics["mean_bps"] is not None
        and severe_metrics["mean_bps"] >= float(gate_cfg["minimum_severe_mean_bps"]),
        "minimum_profit_factor": normal_metrics["profit_factor"] is not None
        and normal_metrics["profit_factor"] >= float(gate_cfg["minimum_profit_factor"]),
        "positive_period_share": positive_period_share
        >= float(gate_cfg["minimum_positive_period_share"]),
        "holdout_positive": int(holdout_row["trades"]) >= int(
            gate_cfg["minimum_holdout_trades"]
        ) and float(holdout_row["mean_bps"]) > 0.0,
        "bootstrap_p10_positive": bootstrap["p10_mean_bps"] is not None
        and bootstrap["p10_mean_bps"] > 0.0,
        "transfer_ratio": transfer_ratio is not None
        and transfer_ratio >= float(gate_cfg["minimum_transfer_ratio"]),
        "year_concentration": max_year_share
        <= float(gate_cfg["maximum_year_share"]),
        "stress_8bps_positive": stress8_metrics["mean_bps"] is not None
        and stress8_metrics["mean_bps"] > 0.0,
        "risk_contract_drawdown": risk[
            "estimated_bootstrap_p95_drawdown_equity_pct"
        ] <= float(config["risk"]["maximum_bootstrap_drawdown_pct"]),
    }

    structural_keys = [
        name for name in gates
        if name not in {"bootstrap_p10_positive"}
    ]
    if all(gates.values()):
        decision = READY
    elif all(gates[name] for name in structural_keys):
        decision = SHADOW
    else:
        decision = KILL

    risk["decision"] = decision
    risk["candidate"] = selected["candidate"]
    risk["normal_execution_cost_floor_bps"] = float(
        config["execution"]["minimum_normal_cost_bps"]
    )
    risk["severe_execution_cost_floor_bps"] = float(
        config["execution"]["minimum_severe_cost_bps"]
    )
    write_json(out / "commercial_closure_risk_contract.json", risk)

    cost_rows = []
    for label, result in [
        ("normal_observed_spread_plus_slippage", normal_metrics),
        ("severe_observed_spread_plus_slippage", severe_metrics),
        ("stress_8bps_floor", stress8_metrics),
        ("stress_10bps_floor", stress10_metrics),
    ]:
        cost_rows.append({"scenario": label, **result})
    pd.DataFrame(cost_rows).to_csv(
        out / "commercial_closure_cost_stress.csv", index=False
    )

    summary = {
        "program": "XAUUSD_COMMERCIAL_CLOSURE_SPRINT",
        "generated_utc": now_utc(),
        "decision": decision,
        "candidate": selected["candidate"],
        "model": selected["model"],
        "target": selected["target"],
        "execution_allowed": False,
        "controlled_paper_orders_authorized": decision == READY,
        "demo_allowed": False,
        "live_allowed": False,
        "stage180_shadow_remains_active": True,
        "reference_parity": reference_parity,
        "signals_total": int(len(signals)),
        "execution_evaluated_trades": int(len(evaluated)),
        "execution_coverage": float(evaluated_coverage),
        "execution_horizon_semantics": (
            "entry=open of AMarkets H1 row i+1; "
            "exit=close of AMarkets H1 row i+horizon"
        ),
        "operational_h1_rows": int(len(operational_h1_timestamps)),
        "execution_metrics": normal_metrics,
        "severe_execution_metrics": severe_metrics,
        "stress_8bps_metrics": stress8_metrics,
        "stress_10bps_metrics": stress10_metrics,
        "bootstrap": bootstrap,
        "positive_period_share": positive_period_share,
        "holdout_period": holdout_row.to_dict(),
        "research_gross_mean_bps": research_mean,
        "execution_gross_mean_bps": execution_gross_mean,
        "gross_transfer_ratio": transfer_ratio,
        "observed_spread_p95_bps": spread_p95,
        "max_year_share": max_year_share,
        "risk_contract": risk,
        "gates": gates,
        "m5_loader": m5_diag,
        "history_policy": {
            "raw_amarkets_start": m5_diag["first_aligned_utc"],
            "commercial_gate_start": pd.to_datetime(
                floor_ms, unit="ms", utc=True
            ).isoformat(),
            "pre_floor_history_excluded_from_commercial_gate": True,
            "reason": (
                "The broker timestamp contract was validated operationally from "
                "the existing PASS database floor. Earlier raw history is retained "
                "for separate research but cannot change this commercial decision."
            ),
        },
        "dukascopy_update_required_now": False,
    }
    write_json(out / "commercial_closure_summary.json", summary)
    write_json(out / "commercial_closure_bootstrap.json", bootstrap)
    (out / "commercial_closure_decision.md").write_text(
        decision_markdown(summary), encoding="utf-8"
    )

    print(json.dumps({
        "decision": decision,
        "candidate": selected["candidate"],
        "signals_total": len(signals),
        "execution_evaluated_trades": len(evaluated),
        "mean_normal_net_bps": normal_metrics["mean_bps"],
        "profit_factor": normal_metrics["profit_factor"],
        "bootstrap_p10_mean_bps": bootstrap["p10_mean_bps"],
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output_dir": str(out),
    }, indent=2))
    return 0 if decision != KILL else 2


if __name__ == "__main__":
    raise SystemExit(main())
