#!/usr/bin/env python3
"""Stage178 — Commercial Edge Decision Sprint.

Purpose
-------
Run one bounded, pre-registered commercial edge screen on the canonical
Dukascopy H1 research history and an untouched AMarkets 2025+ broker holdout.
The stage compares two fixed model classes across four fixed targets and emits
one decision. It does not place, simulate, or authorize orders.

The implementation is intentionally narrow:
- fixed features;
- fixed model hyperparameters;
- fixed probability threshold;
- expanding/purged walk-forward reference evaluation;
- one selected candidate evaluated once on AMarkets 2025+;
- fixed normal and severe cost assumptions;
- no hyperparameter search.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pickle
import importlib
import sqlite3
import sys
import warnings
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import numpy as np
    import pandas as pd
except Exception as exc:  # pragma: no cover - required data-stack error
    raise SystemExit(
        "Stage178 core dependency import failed. Run:\n"
        "python3 -m pip install --user -r requirements/stage178.txt\n"
        f"Original error: {exc}"
    ) from exc

_ML_DEPENDENCIES: dict[str, Any] | None = None
_ML_DEPENDENCY_ERROR: str | None = None


def load_ml_dependencies() -> dict[str, Any]:
    """Load the ML stack lazily so module import and unit tests remain usable.

    scikit-learn depends on joblib internally.  A broken or incomplete Python
    environment must therefore fail at explicit preflight/model construction,
    not while importing this module.
    """
    global _ML_DEPENDENCIES, _ML_DEPENDENCY_ERROR
    if _ML_DEPENDENCIES is not None:
        return _ML_DEPENDENCIES
    if _ML_DEPENDENCY_ERROR is not None:
        raise RuntimeError(_ML_DEPENDENCY_ERROR)
    try:
        sklearn = importlib.import_module("sklearn")
        ensemble = importlib.import_module("sklearn.ensemble")
        impute = importlib.import_module("sklearn.impute")
        linear_model = importlib.import_module("sklearn.linear_model")
        pipeline = importlib.import_module("sklearn.pipeline")
        preprocessing = importlib.import_module("sklearn.preprocessing")
    except Exception as exc:
        _ML_DEPENDENCY_ERROR = (
            "Stage178 ML dependencies are unavailable or incomplete. Run:\n"
            "python3 -m pip install --user -r requirements/stage178.txt\n"
            f"Original error: {type(exc).__name__}: {exc}"
        )
        raise RuntimeError(_ML_DEPENDENCY_ERROR) from exc

    _ML_DEPENDENCIES = {
        "sklearn": sklearn,
        "HistGradientBoostingClassifier": ensemble.HistGradientBoostingClassifier,
        "SimpleImputer": impute.SimpleImputer,
        "LogisticRegression": linear_model.LogisticRegression,
        "Pipeline": pipeline.Pipeline,
        "StandardScaler": preprocessing.StandardScaler,
    }
    return _ML_DEPENDENCIES


def ml_dependencies_available() -> tuple[bool, str | None]:
    try:
        load_ml_dependencies()
        return True, None
    except RuntimeError as exc:
        return False, str(exc)

MS_HOUR = 3_600_000
UTC = timezone.utc


@dataclass(frozen=True)
class TargetSpec:
    key: str
    kind: str
    horizon_hours: int
    barrier_atr_mult: float | None = None


@dataclass(frozen=True)
class FoldSpec:
    name: str
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )


def sqlite_tables(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path)) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            name: [row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')]
            for name in names
        }


def load_ohlcv_table(path: Path, preferred_tables: list[str]) -> tuple[pd.DataFrame, str]:
    tables = sqlite_tables(path)
    selected: str | None = None
    for name in preferred_tables:
        columns = set(tables.get(name, []))
        if {"timestamp", "open", "high", "low", "close"}.issubset(columns):
            selected = name
            break
    if selected is None:
        candidates = [
            name
            for name, columns in tables.items()
            if {"timestamp", "open", "high", "low", "close"}.issubset(set(columns))
        ]
        if not candidates:
            raise RuntimeError(
                f"No OHLC table found in {path}. Available tables: {sorted(tables)}"
            )
        selected = candidates[0]

    query_columns = ["timestamp", "open", "high", "low", "close"]
    if "volume" in tables[selected]:
        query_columns.append("volume")
    else:
        query_columns.append("NULL AS volume")

    with closing(sqlite3.connect(path)) as connection:
        frame = pd.read_sql_query(
            f'SELECT {", ".join(query_columns)} FROM "{selected}" ORDER BY timestamp',
            connection,
        )

    frame = frame.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    for column in ["timestamp", "open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame["dt"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("dt", drop=False)
    return frame, selected


def resolve_existing(root: Path, configured: str, fallbacks: list[str]) -> Path:
    candidates: list[Path] = []
    configured_path = Path(os.path.expanduser(configured))
    candidates.append(configured_path if configured_path.is_absolute() else root / configured_path)
    for item in fallbacks:
        path = Path(os.path.expanduser(item))
        candidates.append(path if path.is_absolute() else root / path)
    for path in candidates:
        if path.exists():
            return path.resolve()
    raise FileNotFoundError("No input found. Checked:\n" + "\n".join(str(p) for p in candidates))


def quality_summary(frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = frame["timestamp"].to_numpy(dtype=np.int64)
    gaps = np.diff(timestamps) / MS_HOUR if len(timestamps) > 1 else np.array([])
    o = frame["open"].to_numpy(float)
    h = frame["high"].to_numpy(float)
    l = frame["low"].to_numpy(float)
    c = frame["close"].to_numpy(float)
    violations = int(
        np.sum((h < np.maximum.reduce([o, l, c])) | (l > np.minimum.reduce([o, h, c])))
    )
    return {
        "rows": int(len(frame)),
        "first_utc": frame["dt"].iloc[0].isoformat() if len(frame) else None,
        "last_utc": frame["dt"].iloc[-1].isoformat() if len(frame) else None,
        "duplicate_timestamps": int(frame["timestamp"].duplicated().sum()),
        "ohlc_violations": violations,
        "max_gap_hours": float(np.max(gaps)) if gaps.size else None,
    }


def build_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    x = pd.DataFrame(index=frame.index)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)

    log_close = np.log(close)
    ret1 = log_close.diff()
    x["body_pct"] = (close / open_ - 1.0).replace([np.inf, -np.inf], np.nan)
    x["range_pct"] = ((high - low) / close).replace([np.inf, -np.inf], np.nan)

    for lag in [1, 3, 6, 12, 24, 48, 72, 120, 240]:
        x[f"ret_{lag}h"] = log_close.diff(lag)

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    for window in [14, 48, 120]:
        x[f"atr_{window}_pct"] = true_range.rolling(window, min_periods=window).mean() / close

    for window in [24, 72, 240]:
        rolling_mean = close.rolling(window, min_periods=window).mean()
        rolling_std_ret = ret1.rolling(window, min_periods=window).std()
        rolling_high = high.rolling(window, min_periods=window).max()
        rolling_low = low.rolling(window, min_periods=window).min()
        denom = (rolling_high - rolling_low).replace(0.0, np.nan)
        x[f"sma_gap_{window}"] = close / rolling_mean - 1.0
        x[f"rv_{window}"] = rolling_std_ret * math.sqrt(24.0)
        x[f"range_pos_{window}"] = (close - rolling_low) / denom

    log_volume = np.log1p(volume.clip(lower=0))
    volume_mean = log_volume.rolling(120, min_periods=60).mean()
    volume_std = log_volume.rolling(120, min_periods=60).std().replace(0.0, np.nan)
    x["volume_z_120"] = (log_volume - volume_mean) / volume_std

    hour = frame["dt"].dt.hour.astype(float)
    dow = frame["dt"].dt.dayofweek.astype(float)
    x["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    x["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    x["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    x["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)

    x["timestamp"] = frame["timestamp"].astype("int64")
    x["dt"] = frame["dt"]
    feature_columns = [column for column in x.columns if column not in {"timestamp", "dt"}]
    x[feature_columns] = x[feature_columns].replace([np.inf, -np.inf], np.nan)
    return x, feature_columns


def directional_target(
    frame: pd.DataFrame,
    horizon_hours: int,
    cost_bps: float,
) -> pd.DataFrame:
    entry = frame["open"].shift(-1)
    exit_ = frame["close"].shift(-horizon_hours)
    underlying = (exit_ / entry - 1.0) * 10_000.0
    label = pd.Series(np.nan, index=frame.index, dtype=float)
    label.loc[underlying > cost_bps] = 1.0
    label.loc[underlying < -cost_bps] = 0.0
    return pd.DataFrame(
        {
            "timestamp": frame["timestamp"],
            "dt": frame["dt"],
            "underlying_bps": underlying,
            "label": label,
            "resolution_hours": float(horizon_hours),
        },
        index=frame.index,
    )


def triple_barrier_target(
    frame: pd.DataFrame,
    horizon_hours: int,
    barrier_atr_mult: float,
    cost_bps: float,
) -> pd.DataFrame:
    close = frame["close"].to_numpy(float)
    open_ = frame["open"].to_numpy(float)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    prev = np.r_[np.nan, close[:-1]]
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev), np.abs(low - prev)]), axis=0)
    atr = pd.Series(tr, index=frame.index).rolling(24, min_periods=24).mean().to_numpy(float)

    n = len(frame)
    underlying = np.full(n, np.nan, dtype=float)
    labels = np.full(n, np.nan, dtype=float)
    resolution = np.full(n, np.nan, dtype=float)

    last_signal_index = n - horizon_hours - 1
    for i in range(24, max(24, last_signal_index + 1)):
        entry = open_[i + 1]
        distance = barrier_atr_mult * atr[i]
        if not np.isfinite(entry) or entry <= 0 or not np.isfinite(distance) or distance <= 0:
            continue
        upper = entry + distance
        lower = entry - distance
        resolved: float | None = None
        resolved_h = horizon_hours
        ambiguous = False
        for step in range(1, horizon_hours + 1):
            j = i + step
            hit_up = high[j] >= upper
            hit_down = low[j] <= lower
            if hit_up and hit_down:
                ambiguous = True
                break
            if hit_up:
                resolved = (upper / entry - 1.0) * 10_000.0
                resolved_h = step
                break
            if hit_down:
                resolved = (lower / entry - 1.0) * 10_000.0
                resolved_h = step
                break
        if ambiguous:
            continue
        if resolved is None:
            exit_close = close[i + horizon_hours]
            resolved = (exit_close / entry - 1.0) * 10_000.0
        underlying[i] = resolved
        resolution[i] = float(resolved_h)
        if resolved > cost_bps:
            labels[i] = 1.0
        elif resolved < -cost_bps:
            labels[i] = 0.0

    return pd.DataFrame(
        {
            "timestamp": frame["timestamp"],
            "dt": frame["dt"],
            "underlying_bps": underlying,
            "label": labels,
            "resolution_hours": resolution,
        },
        index=frame.index,
    )


def make_target(frame: pd.DataFrame, spec: TargetSpec, cost_bps: float) -> pd.DataFrame:
    if spec.kind == "directional":
        return directional_target(frame, spec.horizon_hours, cost_bps)
    if spec.kind == "triple_barrier":
        if spec.barrier_atr_mult is None:
            raise ValueError("triple-barrier target requires barrier_atr_mult")
        return triple_barrier_target(
            frame, spec.horizon_hours, spec.barrier_atr_mult, cost_bps
        )
    raise ValueError(f"Unknown target kind: {spec.kind}")


def make_model(model_key: str, random_state: int) -> Any:
    deps = load_ml_dependencies()
    Pipeline = deps["Pipeline"]
    SimpleImputer = deps["SimpleImputer"]
    StandardScaler = deps["StandardScaler"]
    LogisticRegression = deps["LogisticRegression"]
    HistGradientBoostingClassifier = deps["HistGradientBoostingClassifier"]
    if model_key == "logistic":
        classifier = LogisticRegression(
            C=0.25,
            class_weight="balanced",
            max_iter=500,
            solver="lbfgs",
            random_state=random_state,
        )
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("classifier", classifier),
            ]
        )
    if model_key == "hist_gb":
        classifier = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=90,
            max_leaf_nodes=15,
            max_depth=3,
            min_samples_leaf=150,
            l2_regularization=1.0,
            random_state=random_state,
        )
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("classifier", classifier),
            ]
        )
    raise ValueError(f"Unknown model key: {model_key}")


def model_dataset(
    features: pd.DataFrame,
    target: pd.DataFrame,
    feature_columns: list[str],
    *,
    require_label: bool,
) -> pd.DataFrame:
    """Build a causal model/evaluation dataset.

    Training rows require a non-neutral class label. Evaluation rows do not:
    they retain every resolved future outcome, including small moves inside the
    cost dead-zone. Dropping neutral outcomes from evaluation would condition
    trades on future information and is explicitly forbidden.
    """
    joined = features[["timestamp", "dt", *feature_columns]].join(
        target[["underlying_bps", "label", "resolution_hours"]]
    )
    required = ["underlying_bps", "resolution_hours", "ret_240h", "sma_gap_240"]
    if require_label:
        required.append("label")
    joined = joined.dropna(subset=required)
    if require_label:
        joined["label"] = joined["label"].astype(int)
    return joined


def probability_to_direction(probability: np.ndarray, threshold: float) -> np.ndarray:
    direction = np.zeros(len(probability), dtype=np.int8)
    direction[probability >= threshold] = 1
    direction[probability <= (1.0 - threshold)] = -1
    return direction


def non_overlapping_trades(
    rows: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
    cost_bps: float,
    severe_cost_bps: float,
    fold: str,
    model_key: str,
    target_key: str,
) -> pd.DataFrame:
    if len(rows) != len(probabilities):
        raise ValueError("row/probability length mismatch")
    directions = probability_to_direction(probabilities, threshold)
    records: list[dict[str, Any]] = []
    next_allowed = -2**63

    for position, (_, row) in enumerate(rows.sort_values("timestamp").iterrows()):
        direction = int(directions[position])
        timestamp = int(row["timestamp"])
        if direction == 0 or timestamp < next_allowed:
            continue
        gross = direction * float(row["underlying_bps"])
        resolution_hours = max(1, int(round(float(row["resolution_hours"]))))
        records.append(
            {
                "timestamp": timestamp,
                "dt": pd.to_datetime(timestamp, unit="ms", utc=True),
                "direction": direction,
                "probability_up": float(probabilities[position]),
                "gross_bps": gross,
                "net_bps": gross - cost_bps,
                "severe_net_bps": gross - severe_cost_bps,
                "resolution_hours": resolution_hours,
                "fold": fold,
                "model": model_key,
                "target": target_key,
            }
        )
        next_allowed = timestamp + resolution_hours * MS_HOUR

    return pd.DataFrame.from_records(records)


def max_drawdown(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return 0.0
    equity = np.cumsum(array)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])
    drawdowns = peaks[1:] - equity
    return float(np.max(drawdowns)) if drawdowns.size else 0.0


def profit_factor(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=float)
    gains = float(array[array > 0].sum())
    losses = float(-array[array < 0].sum())
    if losses == 0:
        return None if gains == 0 else 999.0
    return gains / losses


def trade_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "mean_net_bps": None,
            "median_net_bps": None,
            "mean_severe_net_bps": None,
            "win_rate": None,
            "profit_factor": None,
            "max_drawdown_bps": None,
            "max_year_share": None,
            "max_month_share": None,
            "first_trade_utc": None,
            "last_trade_utc": None,
        }
    net = trades["net_bps"].to_numpy(float)
    severe = trades["severe_net_bps"].to_numpy(float)
    years = trades["dt"].dt.year.value_counts(normalize=True)
    months = trades["dt"].dt.strftime("%Y-%m").value_counts(normalize=True)
    return {
        "trades": int(len(trades)),
        "mean_net_bps": float(np.mean(net)),
        "median_net_bps": float(np.median(net)),
        "mean_severe_net_bps": float(np.mean(severe)),
        "win_rate": float(np.mean(net > 0)),
        "profit_factor": profit_factor(net),
        "max_drawdown_bps": max_drawdown(net),
        "max_year_share": float(years.iloc[0]),
        "max_month_share": float(months.iloc[0]),
        "first_trade_utc": trades["dt"].min().isoformat(),
        "last_trade_utc": trades["dt"].max().isoformat(),
    }


def fold_specs(config: dict[str, Any]) -> list[FoldSpec]:
    return [
        FoldSpec(
            name=item["name"],
            test_start=pd.Timestamp(item["test_start"], tz="UTC"),
            test_end=pd.Timestamp(item["test_end"], tz="UTC"),
        )
        for item in config["reference_walk_forward_folds"]
    ]


def evaluate_candidate_reference(
    training_dataset: pd.DataFrame,
    evaluation_dataset: pd.DataFrame,
    feature_columns: list[str],
    target_spec: TargetSpec,
    model_key: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    trades_all: list[pd.DataFrame] = []
    fold_records: list[dict[str, Any]] = []
    stride = int(config["training_stride_hours"])
    threshold = float(config["probability_threshold"])
    normal_cost = float(config["round_trip_cost_bps"])
    severe_cost = float(config["severe_round_trip_cost_bps"])
    random_state = int(config["random_state"])

    for fold in fold_specs(config):
        embargo_boundary = fold.test_start - pd.Timedelta(hours=target_spec.horizon_hours)
        train = training_dataset[training_dataset["dt"] < embargo_boundary].iloc[::stride].copy()
        test = evaluation_dataset[
            (evaluation_dataset["dt"] >= fold.test_start)
            & (evaluation_dataset["dt"] < fold.test_end)
        ].copy()
        if len(train) < int(config["minimum_training_rows"]) or len(test) < 100:
            fold_records.append(
                {
                    "candidate": f"{model_key}__{target_spec.key}",
                    "fold": fold.name,
                    "status": "INSUFFICIENT_ROWS",
                    "train_rows": int(len(train)),
                    "test_rows": int(len(test)),
                }
            )
            continue
        if train["label"].nunique() < 2:
            fold_records.append(
                {
                    "candidate": f"{model_key}__{target_spec.key}",
                    "fold": fold.name,
                    "status": "ONE_CLASS_TRAIN",
                    "train_rows": int(len(train)),
                    "test_rows": int(len(test)),
                }
            )
            continue

        model = make_model(model_key, random_state)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(train[feature_columns], train["label"])
        probabilities = model.predict_proba(test[feature_columns])[:, 1]
        trades = non_overlapping_trades(
            test,
            probabilities,
            threshold,
            normal_cost,
            severe_cost,
            fold.name,
            model_key,
            target_spec.key,
        )
        metrics = trade_metrics(trades)
        fold_records.append(
            {
                "candidate": f"{model_key}__{target_spec.key}",
                "fold": fold.name,
                "status": "EVALUATED",
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                **metrics,
            }
        )
        if not trades.empty:
            trades_all.append(trades)

    all_trades = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    metrics = trade_metrics(all_trades)
    evaluated_folds = [row for row in fold_records if row["status"] == "EVALUATED"]
    fold_means = [row["mean_net_bps"] for row in evaluated_folds if row.get("mean_net_bps") is not None]
    positive_fold_share = (
        float(np.mean(np.asarray(fold_means) > 0)) if fold_means else None
    )
    min_fold_mean = float(np.min(fold_means)) if fold_means else None
    median_fold_mean = float(np.median(fold_means)) if fold_means else None
    pf = metrics.get("profit_factor")
    if (
        metrics["trades"] >= 1
        and median_fold_mean is not None
        and min_fold_mean is not None
        and pf is not None
    ):
        selection_score = (
            median_fold_mean
            + 0.25 * min_fold_mean
            + 2.0 * math.log(max(float(pf), 1e-6))
            + 0.002 * min(metrics["trades"], 500)
        )
    else:
        selection_score = -1e9

    summary = {
        "candidate": f"{model_key}__{target_spec.key}",
        "model": model_key,
        "target": target_spec.key,
        "horizon_hours": target_spec.horizon_hours,
        "evaluated_folds": len(evaluated_folds),
        "positive_fold_share": positive_fold_share,
        "minimum_fold_mean_net_bps": min_fold_mean,
        "median_fold_mean_net_bps": median_fold_mean,
        "selection_score": float(selection_score),
        **metrics,
    }
    return summary, pd.DataFrame(fold_records), all_trades


def baseline_trades(
    dataset: pd.DataFrame,
    target_spec: TargetSpec,
    config: dict[str, Any],
    direction_mode: str,
    label: str,
) -> pd.DataFrame:
    threshold_rows = dataset.copy().sort_values("timestamp")
    records: list[dict[str, Any]] = []
    next_allowed = -2**63
    normal_cost = float(config["round_trip_cost_bps"])
    severe_cost = float(config["severe_round_trip_cost_bps"])
    for _, row in threshold_rows.iterrows():
        timestamp = int(row["timestamp"])
        if timestamp < next_allowed:
            continue
        if direction_mode == "always_long":
            direction = 1
        elif direction_mode == "trend24":
            value = row.get("ret_24h")
            if not np.isfinite(value) or value == 0:
                continue
            direction = 1 if value > 0 else -1
        else:
            raise ValueError(direction_mode)
        gross = direction * float(row["underlying_bps"])
        resolution = max(1, int(round(float(row["resolution_hours"]))))
        records.append(
            {
                "timestamp": timestamp,
                "dt": pd.to_datetime(timestamp, unit="ms", utc=True),
                "direction": direction,
                "probability_up": None,
                "gross_bps": gross,
                "net_bps": gross - normal_cost,
                "severe_net_bps": gross - severe_cost,
                "resolution_hours": resolution,
                "fold": label,
                "model": direction_mode,
                "target": target_spec.key,
            }
        )
        next_allowed = timestamp + resolution * MS_HOUR
    return pd.DataFrame(records)


def reference_gates(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    gates = config["reference_gates"]
    return {
        "minimum_trades": metrics["trades"] >= int(gates["minimum_trades"]),
        "mean_net_bps": metrics["mean_net_bps"] is not None
        and metrics["mean_net_bps"] >= float(gates["minimum_mean_net_bps"]),
        "mean_severe_net_bps": metrics["mean_severe_net_bps"] is not None
        and metrics["mean_severe_net_bps"] >= float(gates["minimum_mean_severe_net_bps"]),
        "profit_factor": metrics["profit_factor"] is not None
        and metrics["profit_factor"] >= float(gates["minimum_profit_factor"]),
        "positive_fold_share": metrics["positive_fold_share"] is not None
        and metrics["positive_fold_share"] >= float(gates["minimum_positive_fold_share"]),
        "year_concentration": metrics["max_year_share"] is not None
        and metrics["max_year_share"] <= float(gates["maximum_year_share"]),
        "beats_trend24_mean_net": metrics.get("trend24_mean_net_bps") is not None
        and metrics["mean_net_bps"] is not None
        and metrics["mean_net_bps"]
        >= metrics["trend24_mean_net_bps"] + float(gates["minimum_margin_over_trend24_bps"]),
    }


def evaluate_selected_holdout(
    reference_training_dataset: pd.DataFrame,
    amarkets_evaluation_dataset: pd.DataFrame,
    feature_columns: list[str],
    target_spec: TargetSpec,
    model_key: str,
    config: dict[str, Any],
) -> tuple[Any, pd.DataFrame, dict[str, Any], dict[str, bool], dict[str, Any]]:
    boundary = pd.Timestamp(config["final_holdout_start"], tz="UTC")
    embargo = boundary - pd.Timedelta(hours=target_spec.horizon_hours)
    stride = int(config["training_stride_hours"])
    train = reference_training_dataset[
        reference_training_dataset["dt"] < embargo
    ].iloc[::stride].copy()
    holdout = amarkets_evaluation_dataset[
        amarkets_evaluation_dataset["dt"] >= boundary
    ].copy()
    if len(train) < int(config["minimum_training_rows"]):
        raise RuntimeError(f"Final training set too small: {len(train)}")
    if len(holdout) < 100:
        raise RuntimeError(f"AMarkets final holdout too small: {len(holdout)}")

    model = make_model(model_key, int(config["random_state"]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(train[feature_columns], train["label"])
    probabilities = model.predict_proba(holdout[feature_columns])[:, 1]
    trades = non_overlapping_trades(
        holdout,
        probabilities,
        float(config["probability_threshold"]),
        float(config["round_trip_cost_bps"]),
        float(config["severe_round_trip_cost_bps"]),
        "AMARKETS_2025_PLUS_UNTOUCHED",
        model_key,
        target_spec.key,
    )
    metrics = trade_metrics(trades)
    gates = config["holdout_gates"]
    gate_results = {
        "minimum_trades": metrics["trades"] >= int(gates["minimum_trades"]),
        "mean_net_bps": metrics["mean_net_bps"] is not None
        and metrics["mean_net_bps"] >= float(gates["minimum_mean_net_bps"]),
        "mean_severe_net_bps": metrics["mean_severe_net_bps"] is not None
        and metrics["mean_severe_net_bps"] >= float(gates["minimum_mean_severe_net_bps"]),
        "profit_factor": metrics["profit_factor"] is not None
        and metrics["profit_factor"] >= float(gates["minimum_profit_factor"]),
        "month_concentration": metrics["max_month_share"] is not None
        and metrics["max_month_share"] <= float(gates["maximum_month_share"]),
    }
    metadata = {
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "holdout_start": boundary.isoformat(),
        "selection_used_holdout": False,
    }
    return model, trades, metrics, gate_results, metadata


def legacy_inventory(root: Path, output_csv: Path) -> dict[str, Any]:
    tokens = ["stage58b", "h13", "h14", "stage35c"]
    records: list[dict[str, Any]] = []
    skip_parts = {".git", "__pycache__", "node_modules", "data"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip_parts for part in path.parts):
            continue
        lower = path.name.lower()
        matched = [token for token in tokens if token in lower]
        if not matched:
            continue
        records.append(
            {
                "relative_path": str(path.relative_to(root)),
                "matched_tokens": ",".join(matched),
                "size_bytes": path.stat().st_size,
            }
        )
        if len(records) >= 500:
            break
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["relative_path", "matched_tokens", "size_bytes"]
        )
        writer.writeheader()
        writer.writerows(records)
    counts = {token: 0 for token in tokens}
    for record in records:
        for token in record["matched_tokens"].split(","):
            counts[token] += 1
    return {"files_found": len(records), "counts": counts}


def decision_markdown(summary: dict[str, Any]) -> str:
    selected = summary.get("selected_candidate") or {}
    holdout = summary.get("selected_holdout_metrics") or {}
    reference = summary.get("selected_reference_metrics") or {}
    failed_ref = [key for key, value in summary.get("selected_reference_gates", {}).items() if not value]
    failed_holdout = [key for key, value in summary.get("selected_holdout_gates", {}).items() if not value]
    return "\n".join(
        [
            "# Stage178 Commercial Edge Decision Sprint",
            "",
            f"Decision: `{summary['decision']}`",
            "",
            "## Selected candidate",
            "",
            f"- Candidate: `{selected.get('candidate')}`",
            f"- Model: `{selected.get('model')}`",
            f"- Target: `{selected.get('target')}`",
            f"- Selection used AMarkets final holdout: `False`",
            "",
            "## Reference walk-forward",
            "",
            f"- Trades: `{reference.get('trades')}`",
            f"- Mean net: `{reference.get('mean_net_bps')}` bps",
            f"- Severe mean net: `{reference.get('mean_severe_net_bps')}` bps",
            f"- Profit factor: `{reference.get('profit_factor')}`",
            f"- Positive fold share: `{reference.get('positive_fold_share')}`",
            f"- Failed gates: `{failed_ref}`",
            "",
            "## Untouched AMarkets 2025+ holdout",
            "",
            f"- Trades: `{holdout.get('trades')}`",
            f"- Mean net: `{holdout.get('mean_net_bps')}` bps",
            f"- Severe mean net: `{holdout.get('mean_severe_net_bps')}` bps",
            f"- Profit factor: `{holdout.get('profit_factor')}`",
            f"- Failed gates: `{failed_holdout}`",
            "",
            "## Operational boundary",
            "",
            "This stage authorizes no paper, demo, or live order. A PROMOTE decision",
            "authorizes preparation of a controlled paper-design package only.",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/stage178_commercial_edge_decision_sprint.json",
    )
    parser.add_argument("--reference-db")
    parser.add_argument("--amarkets-db")
    parser.add_argument("--out")
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="Validate the Stage178 ML dependency stack and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_dependencies:
        available, error = ml_dependencies_available()
        if not available:
            print(error, file=sys.stderr)
            return 3
        deps = load_ml_dependencies()
        print(json.dumps({
            "status": "PASS_STAGE178_ML_DEPENDENCIES",
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": deps["sklearn"].__version__,
        }, indent=2))
        return 0

    # Fail early with a concise dependency message before reading large datasets.
    try:
        ml_deps = load_ml_dependencies()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    root = repo_root_from_script()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = read_json(config_path)

    reference_db = Path(args.reference_db).expanduser().resolve() if args.reference_db else resolve_existing(
        root,
        config["reference_db"],
        ["data/local/stage177b_extended_history/xauusd_extended_history.sqlite"],
    )
    amarkets_db = Path(args.amarkets_db).expanduser().resolve() if args.amarkets_db else resolve_existing(
        root,
        config["amarkets_db"],
        ["data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"],
    )
    out = Path(args.out) if args.out else root / config["output_dir"]
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    reference, reference_table = load_ohlcv_table(
        reference_db, ["dukascopy_h1_canonical", "dukascopy_h1_from_m5"]
    )
    amarkets, amarkets_table = load_ohlcv_table(
        amarkets_db, ["amarkets_h1_from_m5_utc", "amarkets_h1_direct_utc"]
    )
    reference_quality = quality_summary(reference)
    amarkets_quality = quality_summary(amarkets)
    if reference_quality["ohlc_violations"] or amarkets_quality["ohlc_violations"]:
        raise RuntimeError("OHLC invariant failure in Stage178 input")

    reference_features, feature_columns = build_features(reference)
    amarkets_features, amarkets_feature_columns = build_features(amarkets)
    if feature_columns != amarkets_feature_columns:
        raise RuntimeError("Reference and AMarkets feature schemas differ")

    target_specs = [TargetSpec(**item) for item in config["targets"]]
    candidate_rows: list[dict[str, Any]] = []
    fold_frames: list[pd.DataFrame] = []
    candidate_trades: dict[str, pd.DataFrame] = {}
    reference_training_datasets: dict[str, pd.DataFrame] = {}
    reference_evaluation_datasets: dict[str, pd.DataFrame] = {}
    amarkets_evaluation_datasets: dict[str, pd.DataFrame] = {}
    reference_target_baselines: dict[str, list[dict[str, Any]]] = {}

    for target_spec in target_specs:
        reference_target = make_target(
            reference, target_spec, float(config["round_trip_cost_bps"])
        )
        amarkets_target = make_target(
            amarkets, target_spec, float(config["round_trip_cost_bps"])
        )
        reference_training_dataset = model_dataset(
            reference_features,
            reference_target,
            feature_columns,
            require_label=True,
        )
        reference_evaluation_dataset = model_dataset(
            reference_features,
            reference_target,
            feature_columns,
            require_label=False,
        )
        amarkets_evaluation_dataset = model_dataset(
            amarkets_features,
            amarkets_target,
            feature_columns,
            require_label=False,
        )
        reference_training_datasets[target_spec.key] = reference_training_dataset
        reference_evaluation_datasets[target_spec.key] = reference_evaluation_dataset
        amarkets_evaluation_datasets[target_spec.key] = amarkets_evaluation_dataset

        fold_windows = fold_specs(config)
        evaluation_start = min(fold.test_start for fold in fold_windows)
        evaluation_end = max(fold.test_end for fold in fold_windows)
        reference_comparator_window = reference_evaluation_dataset[
            (reference_evaluation_dataset["dt"] >= evaluation_start)
            & (reference_evaluation_dataset["dt"] < evaluation_end)
        ]
        target_baselines: list[dict[str, Any]] = []
        for baseline_mode in ["always_long", "trend24"]:
            comparator_trades = baseline_trades(
                reference_comparator_window,
                target_spec,
                config,
                baseline_mode,
                "REFERENCE_WALK_FORWARD_COMPARATOR",
            )
            target_baselines.append(
                {"baseline": baseline_mode, **trade_metrics(comparator_trades)}
            )
        reference_target_baselines[target_spec.key] = target_baselines
        trend_baseline = next(
            row for row in target_baselines if row["baseline"] == "trend24"
        )

        for model_key in config["models"]:
            summary, fold_frame, trades = evaluate_candidate_reference(
                reference_training_dataset,
                reference_evaluation_dataset,
                feature_columns,
                target_spec,
                model_key,
                config,
            )
            summary["trend24_mean_net_bps"] = trend_baseline["mean_net_bps"]
            summary["trend24_profit_factor"] = trend_baseline["profit_factor"]
            summary["reference_gate_results"] = reference_gates(summary, config)
            summary["reference_pass"] = all(summary["reference_gate_results"].values())
            candidate_rows.append(summary)
            fold_frames.append(fold_frame)
            candidate_trades[summary["candidate"]] = trades

    candidate_frame = pd.DataFrame(candidate_rows).sort_values(
        ["reference_pass", "selection_score"], ascending=[False, False]
    )
    if candidate_frame.empty:
        raise RuntimeError("No candidate was evaluated")
    selected_row = candidate_frame.iloc[0].to_dict()
    selected_candidate = str(selected_row["candidate"])
    selected_model = str(selected_row["model"])
    selected_target_key = str(selected_row["target"])
    selected_target = next(spec for spec in target_specs if spec.key == selected_target_key)

    final_model, holdout_trades, holdout_metrics, holdout_gates, holdout_metadata = evaluate_selected_holdout(
        reference_training_datasets[selected_target_key],
        amarkets_evaluation_datasets[selected_target_key],
        feature_columns,
        selected_target,
        selected_model,
        config,
    )

    selected_reference_metrics = dict(selected_row)
    selected_reference_gates = selected_reference_metrics.pop("reference_gate_results")
    selected_reference_pass = bool(selected_reference_metrics.pop("reference_pass"))

    reference_mean = selected_reference_metrics.get("mean_net_bps")
    holdout_mean = holdout_metrics.get("mean_net_bps")
    degradation_ratio = None
    if reference_mean is not None and holdout_mean is not None and reference_mean > 0:
        degradation_ratio = holdout_mean / reference_mean
    holdout_gates["minimum_degradation_ratio"] = (
        degradation_ratio is not None
        and degradation_ratio >= float(config["holdout_gates"]["minimum_degradation_ratio"])
    )

    holdout_dataset = amarkets_evaluation_datasets[selected_target_key]
    holdout_start = pd.Timestamp(config["final_holdout_start"], tz="UTC")
    holdout_dataset = holdout_dataset[holdout_dataset["dt"] >= holdout_start]
    baseline_records: list[dict[str, Any]] = []
    for mode in ["always_long", "trend24"]:
        trades = baseline_trades(
            holdout_dataset,
            selected_target,
            config,
            mode,
            "AMARKETS_2025_PLUS_UNTOUCHED",
        )
        baseline_records.append({"baseline": mode, **trade_metrics(trades)})

    holdout_trend = next(row for row in baseline_records if row["baseline"] == "trend24")
    holdout_gates["beats_trend24_mean_net"] = (
        holdout_metrics["mean_net_bps"] is not None
        and holdout_trend["mean_net_bps"] is not None
        and holdout_metrics["mean_net_bps"]
        >= holdout_trend["mean_net_bps"]
        + float(config["holdout_gates"]["minimum_margin_over_trend24_bps"])
    )

    if selected_reference_pass and all(holdout_gates.values()):
        decision = "PROMOTE_TO_CONTROLLED_PAPER_DESIGN"
    elif selected_reference_pass and holdout_mean is not None and holdout_mean > 0:
        decision = "RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_TEST"
    else:
        decision = "KILL_CURRENT_CANDIDATE_SET_AND_CHANGE_METHOD_FAMILY"

    legacy_summary = legacy_inventory(root, out / "stage178_legacy_survivor_inventory.csv")

    candidate_csv = out / "stage178_candidate_metrics.csv"
    flat_candidates = candidate_frame.copy()
    flat_candidates["reference_gate_results"] = flat_candidates["reference_gate_results"].map(json.dumps)
    flat_candidates.to_csv(candidate_csv, index=False)
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    folds.to_csv(out / "stage178_fold_metrics.csv", index=False)
    holdout_trades.to_csv(out / "stage178_selected_holdout_trades.csv", index=False)
    pd.DataFrame(baseline_records).to_csv(out / "stage178_holdout_baselines.csv", index=False)

    model_dir = root / config["model_output_dir"]
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    model_path = model_dir / "stage178_selected_model.pkl"
    contract_path = model_dir / "stage178_selected_model_contract.json"
    with model_path.open("wb") as handle:
        pickle.dump(final_model, handle, protocol=pickle.HIGHEST_PROTOCOL)
    model_contract = {
        "stage": "178",
        "generated_utc": now_utc_iso(),
        "candidate": selected_candidate,
        "model": selected_model,
        "target": selected_target_key,
        "horizon_hours": selected_target.horizon_hours,
        "feature_columns": feature_columns,
        "probability_threshold": config["probability_threshold"],
        "round_trip_cost_bps": config["round_trip_cost_bps"],
        "severe_round_trip_cost_bps": config["severe_round_trip_cost_bps"],
        "training_end_before_holdout": config["final_holdout_start"],
        "selection_used_amarkets_holdout": False,
        "execution_allowed": False,
    }
    write_json(contract_path, model_contract)

    summary = {
        "stage": "178",
        "generated_utc": now_utc_iso(),
        "decision": decision,
        "execution_allowed": False,
        "paper_design_authorized": decision == "PROMOTE_TO_CONTROLLED_PAPER_DESIGN",
        "reference_db": str(reference_db),
        "reference_table": reference_table,
        "amarkets_db": str(amarkets_db),
        "amarkets_table": amarkets_table,
        "reference_quality": reference_quality,
        "amarkets_quality": amarkets_quality,
        "feature_count": len(feature_columns),
        "candidate_count": len(candidate_rows),
        "target_dataset_rows": {
            key: {
                "reference_training_labeled": int(len(reference_training_datasets[key])),
                "reference_evaluation_all_resolved": int(len(reference_evaluation_datasets[key])),
                "amarkets_evaluation_all_resolved": int(len(amarkets_evaluation_datasets[key])),
            }
            for key in reference_training_datasets
        },
        "selected_candidate": {
            "candidate": selected_candidate,
            "model": selected_model,
            "target": selected_target_key,
            "horizon_hours": selected_target.horizon_hours,
            "selection_score": selected_reference_metrics["selection_score"],
        },
        "selected_reference_metrics": selected_reference_metrics,
        "selected_reference_gates": selected_reference_gates,
        "selected_holdout_metrics": holdout_metrics,
        "selected_holdout_gates": holdout_gates,
        "holdout_degradation_ratio": degradation_ratio,
        "holdout_metadata": holdout_metadata,
        "reference_target_baselines": reference_target_baselines,
        "holdout_baselines": baseline_records,
        "legacy_survivor_inventory": legacy_summary,
        "model_path": str(model_path),
        "model_contract_path": str(contract_path),
        "library_versions": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": ml_deps["sklearn"].__version__,
        },
    }
    write_json(out / "stage178_summary.json", summary)
    (out / "stage178_decision.md").write_text(decision_markdown(summary), encoding="utf-8")

    print(json.dumps({
        "decision": decision,
        "selected_candidate": selected_candidate,
        "reference_pass": selected_reference_pass,
        "holdout_pass": all(holdout_gates.values()),
        "reports": str(out),
    }, indent=2))
    return 0 if decision != "KILL_CURRENT_CANDIDATE_SET_AND_CHANGE_METHOD_FAMILY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
