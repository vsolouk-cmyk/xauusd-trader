#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import re
import sys
import traceback
import zipfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

PROGRAM = "XAUUSD_CROSS_ASSET_EVENT_RESPONSE_SCAN_V1_1_RAW_EVENT_TIMESTAMP_REPAIR"
PANEL_PROGRAM = "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1_2_SESSION_ELIGIBILITY_CONTRACT_REPAIR"
REPORT_REL = Path("reports/xauusd_cross_asset_event_response_scan")
PANEL_REPORT_REL = Path("reports/xauusd_cross_asset_intraday_panel")
CONFIG_REL = Path("configs/xauusd_cross_asset_event_response_scan.json")
EVENT_SOURCE_DEFAULT_REL = Path("data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv")
PREFLIGHT_FAILURE_REL = Path("reports/xauusd_cross_asset_event_response_preflight_failure.json")
FORBIDDEN_EXECUTION_TOKENS = (
    "ordersend", "positionopen", "positionclose", "ctrade", "trade.buy",
    "trade.sell", "ordercalc", "broker_order_allowed=true",
    "paper_order_allowed=true", "demo_order_allowed=true", "live_order_allowed=true",
)


class ScanError(RuntimeError):
    pass

RUN_CONTEXT: dict[str, Any] = {
    "stage": "NOT_STARTED",
    "candidate_id": None,
    "candidate_index": None,
}

BASE_TRADE_COLUMNS = [
    "candidate_id", "family", "period", "side", "horizon_hours",
    "decision_time_utc", "exit_time_utc", "gross_bps",
    "normal_net_bps", "severe_net_bps", "year", "hour_utc",
]


def set_run_context(stage: str, candidate_id: str | None = None, candidate_index: int | None = None) -> None:
    RUN_CONTEXT["stage"] = stage
    RUN_CONTEXT["candidate_id"] = candidate_id
    RUN_CONTEXT["candidate_index"] = candidate_index


def trade_output_columns(config: dict[str, Any]) -> list[str]:
    signal_columns = sorted({
        f"signal_{str(condition['column'])}"
        for candidate in config.get("candidates", [])
        for condition in candidate.get("conditions", [])
    })
    return BASE_TRADE_COLUMNS + signal_columns


def empty_trade_frame(config: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(columns=trade_output_columns(config))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload.get("program") != PROGRAM:
        raise ScanError(f"config program mismatch: {payload.get('program')}")
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ScanError("candidate registry empty")
    ids = [str(x.get("candidate_id")) for x in candidates]
    if len(ids) != len(set(ids)):
        raise ScanError("candidate ids are not unique")
    return payload


def panel_paths(root: Path) -> dict[str, Path]:
    report = root / PANEL_REPORT_REL
    return {
        "report": report,
        "features": report / "cross_asset_intraday_features.csv",
        "targets": report / "cross_asset_intraday_targets.csv",
        "summary": report / "cross_asset_panel_summary.json",
        "quality": report / "cross_asset_panel_quality.json",
        "contract": report / "cross_asset_panel_contract.json",
        "policy": report / "cross_asset_feature_policy.csv",
        "large_manifest": report / "cross_asset_large_file_manifest.json",
    }


def verify_panel(root: Path) -> dict[str, Any]:
    paths = panel_paths(root)
    missing = [str(p) for key, p in paths.items() if key != "report" and not p.is_file()]
    if missing:
        raise ScanError(f"panel inputs missing: {missing}")
    summary = read_json(paths["summary"])
    quality = read_json(paths["quality"])
    contract = read_json(paths["contract"])
    large = read_json(paths["large_manifest"])
    if summary.get("program") != PANEL_PROGRAM:
        raise ScanError(f"unsupported panel program: {summary.get('program')}")
    if not bool(summary.get("pass")):
        raise ScanError(f"panel is not passed: {summary.get('decision')}")
    if summary.get("decision") != "PASS_CROSS_ASSET_INTRADAY_CAUSAL_PANEL_READY_FOR_FIXED_SCAN":
        raise ScanError(f"panel decision not event-response ready: {summary.get('decision')}")
    if quality.get("failed_gates"):
        raise ScanError(f"panel quality has failed gates: {quality.get('failed_gates')}")
    if not bool(quality.get("feature_target_time_match")):
        raise ScanError("panel feature/target time mismatch")
    if sum(int(v) for v in quality.get("availability_leakage_counts", {}).values()) != 0:
        raise ScanError("panel availability leakage is nonzero")
    entries = {x["path"]: x for x in large.get("files", [])}
    for name, key in [
        ("cross_asset_intraday_features.csv", "features"),
        ("cross_asset_intraday_targets.csv", "targets"),
    ]:
        item = entries.get(name)
        if not item:
            raise ScanError(f"large file manifest missing {name}")
        path = paths[key]
        if path.stat().st_size != int(item["size"]):
            raise ScanError(f"large file size mismatch: {name}")
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise ScanError(f"large file hash mismatch: {name}")
    return {
        "paths": {k: str(v) for k, v in paths.items()},
        "panel_summary": summary,
        "panel_quality": quality,
        "panel_contract": contract,
        "large_file_manifest": large,
    }


def required_columns(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    base_features = {
        "decision_time_utc", "sample_role", "core_h1_4h_history_ready",
        "xauusd_m15_ret_4", "xagusd_m15_ret_4",
        "eurusd_m15_ret_4", "usdjpy_m15_ret_4",
    }
    for source in config.get("rolling_z_features", {}).values():
        if source != "usd_m15_impulse":
            base_features.add(str(source))
    for candidate in config["candidates"]:
        for cond in candidate.get("conditions", []):
            col = str(cond["column"])
            if not col.startswith("z_") and col != "usd_m15_impulse":
                base_features.add(col)
    target_cols = {"decision_time_utc", "sample_role"}
    for h in sorted({int(x["horizon_hours"]) for x in config["candidates"]}):
        target_cols.update({f"exit_time_{h}h_utc", f"forward_return_{h}h_bps"})
    return sorted(base_features), sorted(target_cols)


CSV_PROJECT_CHUNK_ROWS = 10000

def read_csv_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
    except StopIteration as exc:
        raise ScanError(f"CSV has no header: {path}") from exc
    except Exception as exc:
        raise ScanError(f"CSV header read failed for {path}: {type(exc).__name__}: {exc}") from exc
    normalized = [str(x).strip() for x in header]
    if not normalized or not any(normalized):
        raise ScanError(f"CSV header empty: {path}")
    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise ScanError(f"CSV header has duplicate columns in {path}: {duplicates}")
    return normalized


def read_projected_csv(path: Path, columns: list[str], chunk_rows: int = CSV_PROJECT_CHUNK_ROWS) -> pd.DataFrame:
    header = read_csv_header(path)
    missing = sorted(set(columns) - set(header))
    if missing:
        raise ScanError(f"CSV columns missing from {path}: {missing}")
    if len(columns) != len(set(columns)):
        raise ScanError(f"projected column list has duplicates for {path}")
    if chunk_rows <= 0:
        raise ScanError("CSV chunk_rows must be positive")

    def consume(reader: Iterable[pd.DataFrame]) -> pd.DataFrame:
        chunks: list[pd.DataFrame] = []
        for chunk in reader:
            if list(chunk.columns) != columns:
                chunk = chunk.reindex(columns=columns)
            chunks.append(chunk)
        if not chunks:
            return pd.DataFrame(columns=columns)
        return pd.concat(chunks, ignore_index=True).reindex(columns=columns)

    try:
        # pandas 3.0.x can raise an internal IndexError in _concatenate_chunks
        # when low_memory=True, usecols is active, and selected columns have mixed
        # inferred types. Explicit StringDtype + an external chunk loop bypasses
        # that internal concatenation path while keeping memory bounded.
        reader = pd.read_csv(
            path,
            usecols=columns,
            dtype="string",
            chunksize=chunk_rows,
            low_memory=False,
            encoding="utf-8-sig",
        )
        return consume(reader)
    except IndexError:
        # Defensive portability fallback for parser-internal regressions.
        try:
            reader = pd.read_csv(
                path,
                usecols=columns,
                dtype="string",
                chunksize=chunk_rows,
                engine="python",
                encoding="utf-8-sig",
            )
            return consume(reader)
        except Exception as fallback_exc:
            raise ScanError(
                f"projected CSV read failed for {path} after C-parser IndexError: "
                f"{type(fallback_exc).__name__}: {fallback_exc}"
            ) from fallback_exc
    except Exception as exc:
        raise ScanError(
            f"projected CSV read failed for {path}: {type(exc).__name__}: {exc}"
        ) from exc


def resolve_event_source_path(root: Path, config: dict[str, Any]) -> Path:
    raw = str(config.get("official_event_source_relative_path", EVENT_SOURCE_DEFAULT_REL.as_posix()))
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise ScanError(f"official event source path must be repo-relative: {raw}")
    return (root / rel).resolve()


def load_official_events(root: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_event_source_path(root, config)
    if not path.is_file():
        raise ScanError(f"official event timestamp source missing: {path}")
    actual_sha = sha256_file(path)
    expected_sha = str(config.get("official_event_source_expected_sha256", "")).strip().lower()
    if expected_sha and actual_sha.lower() != expected_sha:
        raise ScanError(
            f"official event source hash mismatch: expected={expected_sha} actual={actual_sha} path={path}"
        )
    columns = ["event_time_utc", "source", "category", "title"]
    raw = read_projected_csv(path, columns)
    events = pd.DataFrame({
        "event_time_utc": pd.to_datetime(raw["event_time_utc"], utc=True, errors="coerce"),
        "event_source": raw["source"].astype("string"),
        "event_category": raw["category"].astype("string"),
        "event_title": raw["title"].astype("string"),
    }).dropna(subset=["event_time_utc"])
    events = events.sort_values("event_time_utc").drop_duplicates(
        ["event_time_utc", "event_source", "event_category", "event_title"], keep="last"
    ).reset_index(drop=True)
    minimum_rows = int(config.get("minimum_official_event_source_rows", 1))
    if len(events) < minimum_rows:
        raise ScanError(f"insufficient official event source rows: {len(events)} < {minimum_rows}")
    return events, {
        "path": str(path),
        "sha256": actual_sha,
        "size": path.stat().st_size,
        "rows": int(len(events)),
        "first_event_time_utc": str(events["event_time_utc"].min()),
        "last_event_time_utc": str(events["event_time_utc"].max()),
    }


def attach_event_response_flags(
    frame: pd.DataFrame, events: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    min_lag = int(config.get("event_response_min_lag_minutes", 15))
    max_lag = int(config.get("event_response_max_lag_minutes", 120))
    if min_lag < 0 or max_lag <= min_lag:
        raise ScanError(
            f"invalid event response lag window: min={min_lag} max={max_lag}"
        )
    decisions = pd.to_datetime(frame["decision_time_utc"], utc=True, errors="coerce")
    if decisions.isna().any():
        raise ScanError("invalid decision timestamps while attaching event response flags")
    event_times = pd.to_datetime(events["event_time_utc"], utc=True, errors="coerce").dropna().sort_values()
    event_values = event_times.dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
    decision_values = decisions.dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
    lower = decision_values - np.timedelta64(max_lag, "m")
    upper = decision_values - np.timedelta64(min_lag, "m")
    lo = np.searchsorted(event_values, lower, side="left")
    hi = np.searchsorted(event_values, upper, side="right")
    counts = np.maximum(0, hi - lo).astype(int)
    out = frame.copy()
    out["official_event_response_active"] = (counts > 0).astype(int)
    out["official_event_response_count"] = counts
    out["event_count_capped"] = np.clip(counts, 0, 3)
    return out


def load_panel_data(
    root: Path, config: dict[str, Any], events: pd.DataFrame | None = None
) -> pd.DataFrame:
    paths = panel_paths(root)
    feature_cols, target_cols = required_columns(config)
    features = read_projected_csv(paths["features"], feature_cols)
    targets = read_projected_csv(paths["targets"], target_cols)
    for frame in (features, targets):
        frame["decision_time_utc"] = pd.to_datetime(frame["decision_time_utc"], utc=True, errors="coerce")
        if frame["decision_time_utc"].isna().any():
            raise ScanError("invalid decision timestamps")
    for col in [c for c in targets.columns if c.startswith("exit_time_")]:
        targets[col] = pd.to_datetime(targets[col], utc=True, errors="coerce")
    if features["decision_time_utc"].duplicated().any() or targets["decision_time_utc"].duplicated().any():
        raise ScanError("duplicate decision timestamps")
    merged = features.merge(
        targets.drop(columns=["sample_role"]), on="decision_time_utc", how="inner", validate="one_to_one"
    ).sort_values("decision_time_utc").reset_index(drop=True)
    if len(merged) != len(features) or len(merged) != len(targets):
        raise ScanError("feature/target row count mismatch after merge")
    eur = pd.to_numeric(merged["eurusd_m15_ret_4"], errors="coerce")
    jpy = pd.to_numeric(merged["usdjpy_m15_ret_4"], errors="coerce")
    merged["usd_m15_impulse"] = (-eur + jpy) / 2.0
    if events is None:
        events, _ = load_official_events(root, config)
    return attach_event_response_flags(merged, events, config)


def add_past_only_zscores(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    out = frame.copy()
    window = int(config["rolling_z_window_rows"])
    min_periods = int(config["rolling_z_min_periods"])
    for z_col, source_col in config.get("rolling_z_features", {}).items():
        x = pd.to_numeric(out[source_col], errors="coerce")
        mean = x.rolling(window=window, min_periods=min_periods).mean().shift(1)
        std = x.rolling(window=window, min_periods=min_periods).std(ddof=0).shift(1)
        z = (x - mean) / std.where(std.abs() > 1e-12)
        out[z_col] = z.replace([np.inf, -np.inf], np.nan)
    return out


def apply_condition(frame: pd.DataFrame, condition: dict[str, Any]) -> pd.Series:
    col = str(condition["column"])
    if col not in frame.columns:
        raise ScanError(f"condition column missing: {col}")
    op = str(condition["op"])
    value = condition.get("value")
    series = pd.to_numeric(frame[col], errors="coerce")
    if op == ">=":
        return series >= float(value)
    if op == "<=":
        return series <= float(value)
    if op == ">":
        return series > float(value)
    if op == "<":
        return series < float(value)
    if op == "==":
        return series == float(value)
    if op == "!=":
        return series != float(value)
    if op == "isfinite":
        return series.notna() & np.isfinite(series)
    raise ScanError(f"unsupported condition operator: {op}")


def common_eligibility(frame: pd.DataFrame, horizon: int, config: dict[str, Any]) -> pd.Series:
    decisions = frame["decision_time_utc"]
    allowed_hours = set(int(x) for x in config["allowed_hours_utc"])
    allowed_weekdays = set(int(x) for x in config["allowed_weekdays"])
    target_col = f"forward_return_{horizon}h_bps"
    exit_col = f"exit_time_{horizon}h_utc"
    event_active = pd.to_numeric(frame["official_event_response_active"], errors="coerce").fillna(0)
    mask = (
        (pd.to_numeric(frame["core_h1_4h_history_ready"], errors="coerce") == 1)
        & (event_active == 1)
        & decisions.dt.hour.isin(allowed_hours)
        & decisions.dt.weekday.isin(allowed_weekdays)
        & pd.to_numeric(frame[target_col], errors="coerce").notna()
        & frame[exit_col].notna()
    )
    return mask


def candidate_masks(frame: pd.DataFrame, candidate: dict[str, Any], config: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    horizon = int(candidate["horizon_hours"])
    universe = common_eligibility(frame, horizon, config)
    required = [str(c["column"]) for c in candidate.get("conditions", [])]
    for col in required:
        universe &= pd.to_numeric(frame[col], errors="coerce").notna()
    signal = universe.copy()
    for condition in candidate.get("conditions", []):
        signal &= apply_condition(frame, condition).fillna(False)
    return universe, signal


def non_overlapping_trades(
    frame: pd.DataFrame, signal: pd.Series, candidate: dict[str, Any], config: dict[str, Any], period: str
) -> pd.DataFrame:
    horizon = int(candidate["horizon_hours"])
    side = str(candidate["side"]).upper()
    side_mult = 1.0 if side == "LONG" else -1.0
    target_col = f"forward_return_{horizon}h_bps"
    exit_col = f"exit_time_{horizon}h_utc"
    cost_normal = float(config["normal_cost_bps"])
    cost_severe = float(config["severe_cost_bps"])
    cols = ["decision_time_utc", exit_col, target_col]
    selected = frame.loc[signal, cols].copy().sort_values("decision_time_utc")
    keep: list[int] = []
    last_exit: pd.Timestamp | None = None
    for idx, row in selected.iterrows():
        decision = row["decision_time_utc"]
        exit_time = row[exit_col]
        if pd.isna(exit_time):
            continue
        if last_exit is not None and decision < last_exit:
            continue
        keep.append(idx)
        last_exit = exit_time
    trades = frame.loc[keep].copy()
    if trades.empty:
        columns = BASE_TRADE_COLUMNS + [
            f"signal_{str(condition['column'])}"
            for condition in candidate.get("conditions", [])
        ]
        return pd.DataFrame(columns=columns)
    gross = side_mult * pd.to_numeric(trades[target_col], errors="coerce")
    out = pd.DataFrame({
        "candidate_id": candidate["candidate_id"],
        "family": candidate["family"],
        "period": period,
        "side": side,
        "horizon_hours": horizon,
        "decision_time_utc": trades["decision_time_utc"].to_numpy(),
        "exit_time_utc": trades[exit_col].to_numpy(),
        "gross_bps": gross.to_numpy(dtype="float64"),
        "normal_net_bps": (gross - cost_normal).to_numpy(dtype="float64"),
        "severe_net_bps": (gross - cost_severe).to_numpy(dtype="float64"),
    })
    out["year"] = pd.to_datetime(out["decision_time_utc"], utc=True).dt.year.astype("int64")
    out["hour_utc"] = pd.to_datetime(out["decision_time_utc"], utc=True).dt.hour.astype("int64")
    for condition in candidate.get("conditions", []):
        col = str(condition["column"])
        out[f"signal_{col}"] = pd.to_numeric(trades[col], errors="coerce").to_numpy()
    return out.reset_index(drop=True)


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype="float64")
    pos = arr[arr > 0].sum()
    neg = -arr[arr < 0].sum()
    if neg <= 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def block_bootstrap_mean(values: np.ndarray, reps: int, block: int, seed: int) -> tuple[float, float]:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n == 0:
        return float("nan"), float("nan")
    if n == 1:
        return float(arr[0]), float(arr[0] <= 0)
    rng = np.random.default_rng(seed)
    block = max(1, min(int(block), n))
    means = np.empty(int(reps), dtype="float64")
    for r in range(int(reps)):
        pieces: list[np.ndarray] = []
        while sum(len(x) for x in pieces) < n:
            start = int(rng.integers(0, n))
            idx = (np.arange(block) + start) % n
            pieces.append(arr[idx])
        sample = np.concatenate(pieces)[:n]
        means[r] = sample.mean()
    return float(np.quantile(means, 0.10)), float((means <= 0).mean())


def fixed_period_years(config: dict[str, Any]) -> float:
    start = pd.Timestamp(config["reference_start_utc"])
    end = pd.Timestamp(config["reference_end_utc"])
    return max((end - start).total_seconds() / (365.2425 * 86400.0), 1e-9)


def matched_bucket_excess(
    frame: pd.DataFrame,
    universe: pd.Series,
    trades: pd.DataFrame,
    candidate: dict[str, Any],
    config: dict[str, Any],
) -> np.ndarray:
    if trades.empty:
        return np.asarray([], dtype="float64")
    horizon = int(candidate["horizon_hours"])
    side_mult = 1.0 if str(candidate["side"]).upper() == "LONG" else -1.0
    target_col = f"forward_return_{horizon}h_bps"
    cols = ["decision_time_utc", target_col, "z_xau_m15_impulse", "event_count_capped"]
    base = frame.loc[universe, cols].copy()
    base["year"] = base["decision_time_utc"].dt.year
    base["hour_utc"] = base["decision_time_utc"].dt.hour
    z = pd.to_numeric(base["z_xau_m15_impulse"], errors="coerce")
    base["xau_momentum_bin"] = pd.cut(
        z,
        bins=[-np.inf, -1.0, -0.25, 0.25, 1.0, np.inf],
        labels=False,
        include_lowest=True,
    ).fillna(-1).astype(int)
    base["event_count_bucket"] = pd.to_numeric(base["event_count_capped"], errors="coerce").fillna(0).astype(int)
    base["baseline_net"] = side_mult * pd.to_numeric(base[target_col], errors="coerce") - float(config["severe_cost_bps"])
    keys_cols = ["year", "hour_utc", "xau_momentum_bin", "event_count_bucket"]
    bucket = base.groupby(keys_cols, dropna=False)["baseline_net"].mean()

    trade_times = pd.to_datetime(trades["decision_time_utc"], utc=True)
    lookup = frame.set_index("decision_time_utc")[["z_xau_m15_impulse", "event_count_capped"]]
    tctx = lookup.reindex(trade_times)
    tz = pd.to_numeric(tctx["z_xau_m15_impulse"], errors="coerce")
    tbin = pd.cut(tz, bins=[-np.inf, -1.0, -0.25, 0.25, 1.0, np.inf], labels=False, include_lowest=True).fillna(-1).astype(int)
    tevent = pd.to_numeric(tctx["event_count_capped"], errors="coerce").fillna(0).astype(int)
    keys = list(zip(trades["year"].astype(int), trades["hour_utc"].astype(int), tbin, tevent))
    baseline = np.asarray([bucket.get(k, np.nan) for k in keys], dtype="float64")
    severe = trades["severe_net_bps"].to_numpy(dtype="float64")
    return severe - baseline


def annual_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["candidate_id", "period", "year", "trades", "mean_severe_bps", "sum_severe_bps", "profit_factor"])
    rows = []
    for (candidate_id, period, year), group in trades.groupby(["candidate_id", "period", "year"]):
        vals = group["severe_net_bps"].to_numpy(dtype="float64")
        rows.append({
            "candidate_id": candidate_id,
            "period": period,
            "year": int(year),
            "trades": int(len(vals)),
            "mean_severe_bps": float(np.mean(vals)),
            "sum_severe_bps": float(np.sum(vals)),
            "profit_factor": profit_factor(vals),
        })
    return pd.DataFrame(rows)


def fold_metrics(trades: pd.DataFrame, config: dict[str, Any], candidate_id: str) -> pd.DataFrame:
    rows = []
    for fold in config["reference_folds"]:
        start = pd.Timestamp(fold["start_utc"])
        end = pd.Timestamp(fold["end_utc"])
        mask = (trades["decision_time_utc"] >= start) & (trades["decision_time_utc"] < end)
        vals = trades.loc[mask, "severe_net_bps"].to_numpy(dtype="float64")
        rows.append({
            "candidate_id": candidate_id,
            "fold": fold["name"],
            "start_utc": fold["start_utc"],
            "end_utc": fold["end_utc"],
            "trades": int(len(vals)),
            "mean_severe_bps": float(np.mean(vals)) if len(vals) else float("nan"),
            "profit_factor": profit_factor(vals) if len(vals) else float("nan"),
        })
    return pd.DataFrame(rows)


def metrics_for_candidate(
    frame: pd.DataFrame,
    universe: pd.Series,
    trades: pd.DataFrame,
    candidate: dict[str, Any],
    config: dict[str, Any],
    period: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    values = trades["severe_net_bps"].to_numpy(dtype="float64") if not trades.empty else np.asarray([], dtype="float64")
    p10, prob_le_zero = block_bootstrap_mean(
        values,
        int(config["bootstrap_reps"]),
        int(config["bootstrap_block_trades"]),
        int(config["bootstrap_seed"]) + sum(ord(c) for c in str(candidate["candidate_id"])),
    )
    remove_largest = float("nan")
    if len(values) >= 2:
        remove_largest = float((values.sum() - values.max()) / (len(values) - 1))
    elif len(values) == 1:
        remove_largest = float(values[0])
    excess = matched_bucket_excess(frame, universe, trades, candidate, config)
    excess_p10, excess_prob_le_zero = block_bootstrap_mean(
        excess,
        int(config["bootstrap_reps"]),
        int(config["bootstrap_block_trades"]),
        int(config["bootstrap_seed"]) + 10000 + sum(ord(c) for c in str(candidate["candidate_id"])),
    )
    folds = fold_metrics(trades, config, str(candidate["candidate_id"])) if period == "REFERENCE" else pd.DataFrame()
    annual = annual_metrics(trades)
    positive_year_sums = annual.loc[annual["sum_severe_bps"] > 0, "sum_severe_bps"] if not annual.empty else pd.Series(dtype=float)
    year_concentration = (
        float(positive_year_sums.max() / positive_year_sums.sum())
        if len(positive_year_sums) and positive_year_sums.sum() > 0 else float("nan")
    )
    risk_ratio = float(config["locked_notional_to_equity"])
    equity = 1.0
    for v in values:
        equity *= max(1e-12, 1.0 + risk_ratio * float(v) / 10000.0)
    years = fixed_period_years(config) if period == "REFERENCE" else max(
        (pd.Timestamp(config["diagnostic_end_utc"]) - pd.Timestamp(config["diagnostic_start_utc"])).total_seconds() / (365.2425 * 86400),
        1e-9,
    )
    cagr = float(equity ** (1.0 / years) - 1.0) if equity > 0 else -1.0
    positive_folds = int((folds["mean_severe_bps"] > 0).sum()) if not folds.empty else 0
    worst_fold = float(folds["mean_severe_bps"].min()) if not folds.empty else float("nan")
    metric = {
        "candidate_id": candidate["candidate_id"],
        "family": candidate["family"],
        "side": candidate["side"],
        "horizon_hours": int(candidate["horizon_hours"]),
        "period": period,
        "trades": int(len(values)),
        "mean_gross_bps": float(trades["gross_bps"].mean()) if len(values) else float("nan"),
        "mean_normal_net_bps": float(trades["normal_net_bps"].mean()) if len(values) else float("nan"),
        "mean_severe_net_bps": float(np.mean(values)) if len(values) else float("nan"),
        "median_severe_net_bps": float(np.median(values)) if len(values) else float("nan"),
        "win_rate": float((values > 0).mean()) if len(values) else float("nan"),
        "profit_factor": profit_factor(values),
        "bootstrap_p10_mean_bps": p10,
        "bootstrap_probability_mean_le_zero": prob_le_zero,
        "remove_largest_winner_mean_bps": remove_largest,
        "matched_excess_mean_bps": float(np.nanmean(excess)) if len(excess) else float("nan"),
        "matched_excess_bootstrap_p10_bps": excess_p10,
        "matched_excess_probability_le_zero": excess_prob_le_zero,
        "positive_reference_folds": positive_folds,
        "worst_reference_fold_mean_bps": worst_fold,
        "max_positive_year_profit_share": year_concentration,
        "final_equity_locked_risk": float(equity),
        "locked_risk_cagr": cagr,
    }
    return metric, folds, annual


def reference_gate(metric: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    gates = config["reference_gates"]
    failed: list[str] = []
    checks = {
        "minimum_trades": metric["trades"] >= int(gates["minimum_trades"]),
        "mean_severe_positive": metric["mean_severe_net_bps"] > float(gates["minimum_mean_severe_bps"]),
        "profit_factor": metric["profit_factor"] >= float(gates["minimum_profit_factor"]),
        "bootstrap_p10_positive": metric["bootstrap_p10_mean_bps"] > float(gates["minimum_bootstrap_p10_bps"]),
        "remove_largest_positive": metric["remove_largest_winner_mean_bps"] > 0,
        "matched_excess_positive": metric["matched_excess_mean_bps"] > 0,
        "matched_excess_p10_positive": metric["matched_excess_bootstrap_p10_bps"] > 0,
        "positive_folds": metric["positive_reference_folds"] >= int(gates["minimum_positive_folds"]),
        "worst_fold": metric["worst_reference_fold_mean_bps"] >= float(gates["minimum_worst_fold_mean_bps"]),
        "year_concentration": metric["max_positive_year_profit_share"] <= float(gates["maximum_positive_year_profit_share"]),
        "cagr": metric["locked_risk_cagr"] >= float(gates["minimum_locked_risk_cagr"]),
    }
    for name, passed in checks.items():
        if not bool(passed):
            failed.append(name)
    return not failed, failed


def diagnostic_kill_pass(metric: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    gates = config["diagnostic_kill_gates"]
    failed: list[str] = []
    checks = {
        "minimum_trades": metric["trades"] >= int(gates["minimum_trades"]),
        "mean_positive": metric["mean_severe_net_bps"] > 0,
        "profit_factor": metric["profit_factor"] >= float(gates["minimum_profit_factor"]),
        "remove_largest_positive": metric["remove_largest_winner_mean_bps"] > 0,
    }
    for name, passed in checks.items():
        if not bool(passed):
            failed.append(name)
    return not failed, failed


def period_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    ts = frame["decision_time_utc"]
    return (ts >= pd.Timestamp(start)) & (ts < pd.Timestamp(end))


def candidate_registry_payload(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "candidate_count": len(config["candidates"]),
        "candidates": config["candidates"],
        "rolling_z_features": config.get("rolling_z_features", {}),
        "selection_used_2025_plus": False,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }


def write_csv_gz(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(frame.columns) == 0:
        raise ScanError(f"refusing to write schema-less CSV: {path}")
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})


def static_execution_violations(root: Path) -> list[str]:
    paths = [root / "app/xauusd_cross_asset_event_response_scan.py", root / CONFIG_REL]
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in paths if p.is_file())
    # Remove the literal deny-list declarations themselves before scanning behavior.
    for token in FORBIDDEN_EXECUTION_TOKENS:
        text = text.replace(f'"{token}"', "").replace(f"'{token}'", "")
    return [token for token in FORBIDDEN_EXECUTION_TOKENS if token in text]


def preflight(root: Path, config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    panel = verify_panel(root)
    violations = static_execution_violations(root)
    if violations:
        raise ScanError(f"static execution violations: {violations}")
    policy = pd.read_csv(panel_paths(root)["policy"])
    policy_map = dict(zip(policy["column"].astype(str), policy["fixed_scan_policy"].astype(str)))
    required_f, _ = required_columns(config)
    excluded = sorted([c for c in required_f if policy_map.get(c) == "EXCLUDE_NEAR_EMPTY"])
    if excluded:
        raise ScanError(f"candidate registry requires excluded features: {excluded}")
    events, event_meta = load_official_events(root, config)
    event_probe = read_projected_csv(panel_paths(root)["features"], ["decision_time_utc"])
    event_probe["decision_time_utc"] = pd.to_datetime(
        event_probe["decision_time_utc"], utc=True, errors="coerce"
    )
    if event_probe["decision_time_utc"].isna().any():
        raise ScanError("invalid decision timestamps in event-response preflight")
    event_probe = attach_event_response_flags(event_probe, events, config)
    reference = period_mask(event_probe, config["reference_start_utc"], config["reference_end_utc"])
    event_rows = int(
        (reference & (pd.to_numeric(
            event_probe["official_event_response_active"], errors="coerce"
        ).fillna(0) == 1)).sum()
    )
    if event_rows < int(config["minimum_reference_event_rows"]):
        raise ScanError(f"insufficient official-event response rows: {event_rows}")
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "PASS_CROSS_ASSET_EVENT_RESPONSE_PREFLIGHT_REFERENCE_ONLY",
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "panel_program": panel["panel_summary"]["program"],
        "panel_rows": panel["panel_summary"]["feature_rows"],
        "candidate_count": len(config["candidates"]),
        "official_event_source_rows": event_meta["rows"],
        "official_event_source_sha256": event_meta["sha256"],
        "official_event_response_rows": event_rows,
        "event_response_min_lag_minutes": int(config["event_response_min_lag_minutes"]),
        "event_response_max_lag_minutes": int(config["event_response_max_lag_minutes"]),
        "reference_start_utc": config["reference_start_utc"],
        "reference_end_utc": config["reference_end_utc"],
        "diagnostic_policy": "NOT_EVALUATED_UNLESS_REFERENCE_SURVIVOR",
        "static_execution_violations": [],
        "required_next_action": "RUN_EVENT_RESPONSE_REFERENCE_SCAN_ONCE",
    }


def run(root: Path, config_path: Path, out: Path | None = None) -> dict[str, Any]:
    set_run_context("LOAD_CONFIG")
    config = load_config(config_path)
    set_run_context("VERIFY_PANEL")
    verify_panel(root)
    report = out or (root / REPORT_REL)
    if report.exists() and any(report.iterdir()):
        raise ScanError(f"output directory already exists and is non-empty: {report}")
    report.mkdir(parents=True, exist_ok=True)
    write_json(report / "cross_asset_event_response_run_lock.json", {
        "program": PROGRAM,
        "created_utc": utc_now(),
        "status": "RUN_STARTED_FAIL_CLOSED",
    })
    set_run_context("LOAD_OFFICIAL_EVENT_SOURCE")
    events, event_meta = load_official_events(root, config)
    set_run_context("LOAD_PANEL_DATA")
    frame = load_panel_data(root, config, events=events)
    set_run_context("ADD_PAST_ONLY_ZSCORES")
    frame = add_past_only_zscores(frame, config)
    ref = period_mask(frame, config["reference_start_utc"], config["reference_end_utc"])
    if int(ref.sum()) < int(config["reference_gates"]["minimum_panel_rows"]):
        raise ScanError(f"insufficient reference panel rows: {int(ref.sum())}")
    registry = candidate_registry_payload(config)
    write_json(report / "event_response_candidate_registry.json", registry)
    input_contract = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "features_path": str(panel_paths(root)["features"]),
        "targets_path": str(panel_paths(root)["targets"]),
        "features_sha256": sha256_file(panel_paths(root)["features"]),
        "targets_sha256": sha256_file(panel_paths(root)["targets"]),
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "official_event_source_path": event_meta["path"],
        "official_event_source_sha256": event_meta["sha256"],
        "official_event_source_rows": event_meta["rows"],
        "event_response_min_lag_minutes": int(config["event_response_min_lag_minutes"]),
        "event_response_max_lag_minutes": int(config["event_response_max_lag_minutes"]),
        "reference_start_utc": config["reference_start_utc"],
        "reference_end_utc": config["reference_end_utc"],
        "selection_used_2025_plus": False,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
    }
    write_json(report / "cross_asset_event_response_input_contract.json", input_contract)

    metrics_rows: list[dict[str, Any]] = []
    fold_frames: list[pd.DataFrame] = []
    annual_frames: list[pd.DataFrame] = []
    trade_frames: list[pd.DataFrame] = []
    survivor_candidates: list[dict[str, Any]] = []
    for candidate_index, candidate in enumerate(config["candidates"]):
        set_run_context("REFERENCE_CANDIDATE_MASK", str(candidate["candidate_id"]), candidate_index)
        universe, signal = candidate_masks(frame, candidate, config)
        universe &= ref
        signal &= ref
        set_run_context("REFERENCE_NON_OVERLAPPING_TRADES", str(candidate["candidate_id"]), candidate_index)
        trades = non_overlapping_trades(frame, signal, candidate, config, "REFERENCE")
        set_run_context("REFERENCE_METRICS", str(candidate["candidate_id"]), candidate_index)
        metric, folds, annual = metrics_for_candidate(frame, universe, trades, candidate, config, "REFERENCE")
        passed, failed = reference_gate(metric, config)
        metric["reference_pass"] = bool(passed)
        metric["failed_gates"] = ";".join(failed)
        metrics_rows.append(metric)
        if not folds.empty:
            folds["reference_pass"] = bool(passed)
            fold_frames.append(folds)
        if not annual.empty:
            annual["reference_pass"] = bool(passed)
            annual_frames.append(annual)
        if not trades.empty:
            trade_frames.append(trades)
        if passed:
            survivor_candidates.append(candidate)

    set_run_context("ASSEMBLE_REFERENCE_OUTPUTS")
    metrics_df = pd.DataFrame(metrics_rows).sort_values(
        ["reference_pass", "bootstrap_p10_mean_bps", "profit_factor", "locked_risk_cagr"],
        ascending=[False, False, False, False],
    )
    folds_df = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    annual_df = pd.concat(annual_frames, ignore_index=True) if annual_frames else pd.DataFrame()
    trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else empty_trade_frame(config)
    trades_df = trades_df.reindex(columns=trade_output_columns(config))
    metrics_df.to_csv(report / "event_response_reference_metrics.csv", index=False)
    folds_df.to_csv(report / "event_response_reference_fold_metrics.csv", index=False)
    annual_df.to_csv(report / "event_response_reference_annual_metrics.csv", index=False)
    set_run_context("WRITE_REFERENCE_OUTPUTS")
    write_csv_gz(report / "event_response_reference_trades.csv.gz", trades_df)

    diagnostic_evaluated = False
    diagnostic_metrics = pd.DataFrame()
    diagnostic_trades = pd.DataFrame()
    shortlist: list[dict[str, Any]] = []
    if survivor_candidates:
        ranked_ids = metrics_df.loc[metrics_df["reference_pass"], "candidate_id"].tolist()
        families: set[str] = set()
        for candidate_id in ranked_ids:
            candidate = next(x for x in survivor_candidates if x["candidate_id"] == candidate_id)
            if candidate["family"] in families:
                continue
            shortlist.append(candidate)
            families.add(candidate["family"])
            if len(shortlist) >= int(config["maximum_reference_survivors_for_diagnostic"]):
                break
        write_json(report / "event_response_reference_survivor_contract.json", {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "selection_used_2025_plus": False,
            "survivors": shortlist,
            "reference_metrics_sha256": sha256_file(report / "event_response_reference_metrics.csv"),
            "status": "FROZEN_BEFORE_DIAGNOSTIC",
        })
        write_json(report / "event_response_diagnostic_access_lock.json", {
            "program": PROGRAM,
            "generated_utc": utc_now(),
            "diagnostic_start_utc": config["diagnostic_start_utc"],
            "diagnostic_end_utc": config["diagnostic_end_utc"],
            "purpose": "KILL_ONLY_SEEN_DIAGNOSTIC_NOT_SELECTION",
            "survivor_contract_sha256": sha256_file(report / "event_response_reference_survivor_contract.json"),
        })
        diagnostic_evaluated = True
        diag_mask = period_mask(frame, config["diagnostic_start_utc"], config["diagnostic_end_utc"])
        diag_metric_rows: list[dict[str, Any]] = []
        diag_trade_frames: list[pd.DataFrame] = []
        for diagnostic_index, candidate in enumerate(shortlist):
            set_run_context("DIAGNOSTIC_CANDIDATE_MASK", str(candidate["candidate_id"]), diagnostic_index)
            universe, signal = candidate_masks(frame, candidate, config)
            universe &= diag_mask
            signal &= diag_mask
            set_run_context("DIAGNOSTIC_NON_OVERLAPPING_TRADES", str(candidate["candidate_id"]), diagnostic_index)
            trades = non_overlapping_trades(frame, signal, candidate, config, "DIAGNOSTIC_2025_PLUS")
            set_run_context("DIAGNOSTIC_METRICS", str(candidate["candidate_id"]), diagnostic_index)
            metric, _, _ = metrics_for_candidate(frame, universe, trades, candidate, config, "DIAGNOSTIC_2025_PLUS")
            passed, failed = diagnostic_kill_pass(metric, config)
            metric["diagnostic_kill_pass"] = bool(passed)
            metric["failed_kill_gates"] = ";".join(failed)
            diag_metric_rows.append(metric)
            if not trades.empty:
                diag_trade_frames.append(trades)
        diagnostic_metrics = pd.DataFrame(diag_metric_rows)
        diagnostic_trades = pd.concat(diag_trade_frames, ignore_index=True) if diag_trade_frames else empty_trade_frame(config)
        diagnostic_trades = diagnostic_trades.reindex(columns=trade_output_columns(config))
        diagnostic_metrics.to_csv(report / "event_response_diagnostic_metrics.csv", index=False)
        write_csv_gz(report / "event_response_diagnostic_trades.csv.gz", diagnostic_trades)

    if not survivor_candidates:
        decision = "NO_REFERENCE_SURVIVOR_CLOSE_CROSS_ASSET_INTRADAY_PATH"
        required_next = "CLOSE_CROSS_ASSET_INTRADAY_PATH_AND_PIVOT_SYSTEM_DESIGN"
    elif (
        diagnostic_metrics.empty
        or "diagnostic_kill_pass" not in diagnostic_metrics.columns
        or not bool(diagnostic_metrics["diagnostic_kill_pass"].any())
    ):
        decision = "EVENT_RESPONSE_SURVIVOR_DIAGNOSTIC_BREAKDOWN_REJECT_PATH"
        required_next = "DO_NOT_RETUNE_ON_2025_PLUS"
    else:
        decision = "EVENT_RESPONSE_SURVIVOR_READY_FOR_INDEPENDENT_REPLICATION"
        required_next = "REPLICATE_FROZEN_EVENT_RESPONSE_ON_INDEPENDENT_FEED_AND_STRICT_COST_REPLAY"

    summary = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": decision,
        "pass": decision == "EVENT_RESPONSE_SURVIVOR_READY_FOR_INDEPENDENT_REPLICATION",
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "panel_rows_loaded": int(len(frame)),
        "reference_rows": int(ref.sum()),
        "official_event_source_rows": event_meta["rows"],
        "official_event_response_reference_rows": int((ref & (pd.to_numeric(frame["official_event_response_active"], errors="coerce").fillna(0) == 1)).sum()),
        "event_response_min_lag_minutes": int(config["event_response_min_lag_minutes"]),
        "event_response_max_lag_minutes": int(config["event_response_max_lag_minutes"]),
        "candidate_count": len(config["candidates"]),
        "reference_pass_count": int(metrics_df["reference_pass"].sum()),
        "reference_survivor_ids": metrics_df.loc[metrics_df["reference_pass"], "candidate_id"].tolist(),
        "diagnostic_evaluated": diagnostic_evaluated,
        "diagnostic_policy": "SEEN_DIAGNOSTIC_KILL_ONLY_NOT_SELECTION",
        "diagnostic_kill_pass_ids": (
            diagnostic_metrics.loc[diagnostic_metrics["diagnostic_kill_pass"], "candidate_id"].tolist()
            if not diagnostic_metrics.empty else []
        ),
        "required_next_action": required_next,
    }
    set_run_context("WRITE_SUMMARY")
    write_json(report / "cross_asset_event_response_summary.json", summary)
    decision_lines = [
        "# XAUUSD Cross-Asset Event-Response Scan",
        "",
        f"Decision: `{decision}`",
        "",
        f"Event-response candidates: {len(config['candidates'])}",
        f"Official event source rows: {event_meta['rows']}",
        f"Reference response-window rows: {int((ref & (pd.to_numeric(frame['official_event_response_active'], errors='coerce').fillna(0) == 1)).sum())}",
        f"Event-response reference survivors: {int(metrics_df['reference_pass'].sum())}",
        f"Diagnostic evaluated: {str(diagnostic_evaluated).lower()}",
        "",
        "2025+ is seen diagnostic evidence only and was never used for reference selection.",
        "No paper, demo, or live orders are authorized.",
    ]
    (report / "cross_asset_event_response_decision.md").write_text("\n".join(decision_lines) + "\n", encoding="utf-8")
    lock = read_json(report / "cross_asset_event_response_run_lock.json")
    lock["status"] = "RUN_COMPLETED"
    lock["completed_utc"] = utc_now()
    lock["decision"] = decision
    write_json(report / "cross_asset_event_response_run_lock.json", lock)
    set_run_context("RUN_COMPLETED")
    return summary


def collect(root: Path, out: Path | None = None) -> Path:
    report = root / REPORT_REL
    summary_path = report / "cross_asset_event_response_summary.json"
    if not summary_path.is_file():
        raise ScanError(f"event-response summary missing: {summary_path}")
    output = out or (Path.home() / "Downloads" / "XAUUSD_CROSS_ASSET_EVENT_RESPONSE_RESULTS.zip")
    names = [
        "cross_asset_event_response_summary.json",
        "cross_asset_event_response_decision.md",
        "cross_asset_event_response_input_contract.json",
        "cross_asset_event_response_run_lock.json",
        "event_response_candidate_registry.json",
        "event_response_reference_metrics.csv",
        "event_response_reference_fold_metrics.csv",
        "event_response_reference_annual_metrics.csv",
        "event_response_reference_trades.csv.gz",
        "event_response_reference_survivor_contract.json",
        "event_response_diagnostic_access_lock.json",
        "event_response_diagnostic_metrics.csv",
        "event_response_diagnostic_trades.csv.gz",
    ]
    files = [report / name for name in names if (report / name).is_file()]
    manifest = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "artifact_scope": "EVENT_RESPONSE_EVIDENCE_NO_LARGE_PANEL_INPUTS",
        "files": [
            {"path": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)} for p in files
        ],
        "excluded_large_inputs": [
            "cross_asset_intraday_features.csv", "cross_asset_intraday_targets.csv"
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
        archive.writestr("RESULTS_MANIFEST.json", json.dumps(manifest, indent=2))
    return output


def failure_payload(exc: Exception) -> dict[str, Any]:
    return {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "CROSS_ASSET_EVENT_RESPONSE_SCAN_FAIL_CLOSED",
        "pass": False,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "stage": RUN_CONTEXT.get("stage"),
        "candidate_id": RUN_CONTEXT.get("candidate_id"),
        "candidate_index": RUN_CONTEXT.get("candidate_index"),
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": traceback.format_exc(),
    }


def failure_output_path(root: Path, command: str) -> Path:
    if command == "preflight":
        return root / PREFLIGHT_FAILURE_REL
    return root / REPORT_REL / "cross_asset_event_response_failure.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["preflight", "run", "collect"]:
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=Path.cwd())
        p.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    config_path = (args.config.expanduser().resolve() if args.config else root / CONFIG_REL)
    try:
        if args.command == "preflight":
            payload = preflight(root, config_path)
            print(json.dumps(payload, indent=2))
        elif args.command == "run":
            payload = run(root, config_path)
            print(json.dumps(payload, indent=2))
        else:
            output = collect(root)
            print(json.dumps({
                "program": PROGRAM,
                "generated_utc": utc_now(),
                "decision": "PASS_CROSS_ASSET_EVENT_RESPONSE_RESULTS_PACK_CREATED",
                "pass": True,
                "paper_order_allowed": False,
                "demo_order_allowed": False,
                "live_order_allowed": False,
                "output": str(output),
            }, indent=2))
        return 0
    except Exception as exc:
        payload = failure_payload(exc)
        write_json(failure_output_path(root, args.command), payload)
        print(json.dumps(payload, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
