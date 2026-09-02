#!/usr/bin/env python3
"""Execute the frozen, reference-only Article 1 strategy audit.

The runner imports the six hash-bound project implementations but invokes only
their pre-2025 reference paths.  It never reads historical strategy-result
files.  ``execute`` performs an outcome-blind preflight, freezes the complete
execution manifest, computes the 39 primary specifications once, applies the
locked multiplicity and replication rules, and creates one review archive.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True


PROGRAM = "XAUUSD_ARTICLE1_UNIFIED_REFERENCE_RUNNER_V1_0"
REGISTRY_PATH = Path("docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.json")
REGISTRY_CSV_PATH = Path("docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.csv")
REGISTRY_PREFLIGHT_PATH = Path("tools/article_publication/article1_registry_preflight.py")
DATA_CONTRACT_PATH = Path("docs/article_publication/XAUUSD_ARTICLE1_DATA_CONTRACT_DECISION_V1_1.json")
PROTOCOL_PATH = Path("configs/article_publication/XAUUSD_ARTICLE1_EVALUATION_PROTOCOL_V1_0.json")
DEVIATION_LOG_PATH = Path("docs/article_publication/XAUUSD_ARTICLE1_PROTOCOL_DEVIATION_LOG_V1_0.json")
RUNNER_PATH = Path("tools/article_publication/article1_unified_reference_runner.py")
FAILURE_DIR = Path("reports/article1_locked_reference_rerun_failures")


@dataclass
class SpecResult:
    specification_id: str
    source_block: str
    source_candidate_id: str
    economic_family: str
    parent_taxonomy: str
    trades: pd.DataFrame
    sensitivity_trades: pd.DataFrame
    source_metrics: dict[str, Any]
    sensitivity_source_metrics: dict[str, Any]
    source_native_pass: bool
    sensitivity_source_native_pass: bool
    source_failed_gates: list[str]
    sensitivity_failed_gates: list[str]
    cross_feed: dict[str, Any]
    auxiliary: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_value(value), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def import_path(path: Path, name: str) -> Any:
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"cannot import source module: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


def registry_index(registry: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = [row for row in registry["specifications"] if row["primary_eligible"]]
    index = {(row["source_block"], row["source_candidate_id"]): row for row in rows}
    if len(rows) != 39 or len(index) != 39:
        raise RuntimeError(f"primary registry cardinality failure: rows={len(rows)} unique={len(index)}")
    return index


def find_spec(index: dict[tuple[str, str], dict[str, Any]], block: str, candidate: str) -> dict[str, Any]:
    try:
        return index[(block, candidate)]
    except KeyError as exc:
        raise RuntimeError(f"unregistered primary specification: {block}/{candidate}") from exc


def normalized_trade_frame(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    decision_col: str,
    exit_col: str,
    gross_bps: Iterable[float],
    normal_bps: Iterable[float],
    severe_bps: Iterable[float],
    stress_bps: Iterable[float],
) -> pd.DataFrame:
    columns = [
        "specification_id",
        "source_block",
        "source_candidate_id",
        "economic_family",
        "parent_taxonomy",
        "decision_time_utc",
        "exit_time_utc",
        "gross_bps",
        "normal_net_bps",
        "severe_net_bps",
        "fixed_stress_net_bps",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame(
        {
            "specification_id": spec["specification_id"],
            "source_block": spec["source_block"],
            "source_candidate_id": spec["source_candidate_id"],
            "economic_family": spec["economic_family"],
            "parent_taxonomy": spec["parent_taxonomy"],
            "decision_time_utc": pd.to_datetime(frame[decision_col], utc=True),
            "exit_time_utc": pd.to_datetime(frame[exit_col], utc=True),
            "gross_bps": np.asarray(list(gross_bps), dtype=float),
            "normal_net_bps": np.asarray(list(normal_bps), dtype=float),
            "severe_net_bps": np.asarray(list(severe_bps), dtype=float),
            "fixed_stress_net_bps": np.asarray(list(stress_bps), dtype=float),
        }
    )
    return out.sort_values(["decision_time_utc", "exit_time_utc"]).reset_index(drop=True)


def exclude_warning_overlap(frame: pd.DataFrame, protocol: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    warning = protocol["alignment_warning_sensitivity"]
    start = pd.Timestamp(warning["start_utc"])
    end = pd.Timestamp(warning["end_utc_exclusive"])
    entry = pd.to_datetime(frame["decision_time_utc"], utc=True)
    exit_time = pd.to_datetime(frame["exit_time_utc"], utc=True)
    overlap = (entry < end) & (exit_time > start)
    return frame.loc[~overlap].copy().reset_index(drop=True)


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def mean_or_nan(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def direction_sign(value: float) -> int:
    if not math.isfinite(value) or value == 0:
        return 0
    return 1 if value > 0 else -1


def cross_feed_comparison(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    signal_key_primary: Iterable[str],
    signal_key_secondary: Iterable[str],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    cfg = protocol["cross_feed_replication"]
    a = set(str(x) for x in signal_key_primary)
    b = set(str(x) for x in signal_key_secondary)
    union = a | b
    jaccard = len(a & b) / len(union) if union else float("nan")
    left = primary[["decision_time_utc", "gross_bps"]].copy()
    right = secondary[["decision_time_utc", "gross_bps"]].copy()
    matched = left.merge(right, on="decision_time_utc", suffixes=("_amarkets", "_dukascopy"))
    corr = float("nan")
    if len(matched) >= 2:
        x = matched["gross_bps_amarkets"].to_numpy(dtype=float)
        y = matched["gross_bps_dukascopy"].to_numpy(dtype=float)
        if np.std(x) > 0 and np.std(y) > 0:
            corr = float(np.corrcoef(x, y)[0, 1])
    mean_a = mean_or_nan(primary["severe_net_bps"]) if not primary.empty else float("nan")
    mean_b = mean_or_nan(secondary["severe_net_bps"]) if not secondary.empty else float("nan")
    direction_consistent = direction_sign(mean_a) != 0 and direction_sign(mean_a) == direction_sign(mean_b)
    checks = {
        "signal_jaccard": math.isfinite(jaccard) and jaccard >= float(cfg["minimum_signal_jaccard"]),
        "minimum_matched_outcomes": len(matched) >= int(cfg["minimum_matched_outcomes"]),
        "matched_gross_return_correlation": math.isfinite(corr) and corr >= float(cfg["minimum_matched_gross_return_correlation"]),
        "effect_direction_consistency": direction_consistent,
    }
    return {
        "applicable": True,
        "primary_trade_count": int(len(primary)),
        "secondary_trade_count": int(len(secondary)),
        "matched_outcomes": int(len(matched)),
        "signal_jaccard": jaccard,
        "matched_gross_return_correlation": corr,
        "primary_mean_severe_bps": mean_a,
        "secondary_mean_severe_bps": mean_b,
        "effect_direction_consistent": direction_consistent,
        "checks": checks,
        "pass": bool(all(checks.values())),
    }


def native_metric_summary(trades: pd.DataFrame, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": int(len(trades)),
        "mean_gross_bps": mean_or_nan(trades["gross_bps"]) if not trades.empty else float("nan"),
        "mean_normal_net_bps": mean_or_nan(trades["normal_net_bps"]) if not trades.empty else float("nan"),
        "mean_severe_net_bps": mean_or_nan(trades["severe_net_bps"]) if not trades.empty else float("nan"),
        "mean_fixed_stress_net_bps": mean_or_nan(trades["fixed_stress_net_bps"]) if not trades.empty else float("nan"),
        "profit_factor_severe": profit_factor(trades["severe_net_bps"]) if not trades.empty else 0.0,
        "source_metrics": source,
    }


def load_modules(root: Path) -> dict[str, Any]:
    paths = {
        "successor_scan": root / "app/xauusd_successor_parallel_scan.py",
        "cross_asset_fixed": root / "app/xauusd_cross_asset_fixed_scan.py",
        "cross_asset_event_response": root / "app/xauusd_cross_asset_event_response_scan.py",
        "canonical_tsmom": root / "app/xauusd_final_alpha_trend.py",
        "precious_metals_rv": root / "app/precious_metals_final_rv.py",
    }
    return {key: import_path(path, f"article1_bound_{key}") for key, path in paths.items()}


def successor_results(
    root: Path,
    module: Any,
    registry: dict[tuple[str, str], dict[str, Any]],
    protocol: dict[str, Any],
) -> list[SpecResult]:
    cfg = load_json(root / "configs/xauusd_successor_parallel_scan_v1.json")
    start = pd.Timestamp(cfg["reference_start"])
    end = pd.Timestamp(cfg["holdout_start"])
    db = root / cfg["alignment_db"]
    events = module.load_events(root / cfg["event_db"])
    candidates = module.parse_candidates(cfg)

    def feed_features(table: str) -> pd.DataFrame:
        h1 = module.load_h1(db, table, int(cfg["minimum_m5_bar_count"]))
        h1 = h1.loc[(h1["dt"] >= start) & (h1["dt"] < end)].copy().reset_index(drop=True)
        built = module.build_features(h1, events, candidates)
        module.validate_candidate_feature_contract(built, candidates)
        return built

    am_features = feed_features(protocol["cross_feed_replication"]["amarkets_h1_table"])
    dk_features = feed_features(protocol["cross_feed_replication"]["dukascopy_h1_table"])
    results: list[SpecResult] = []
    stress_cost = float(protocol["secondary_costs"]["fixed_stress"]["successor_scan_round_trip_bps"])
    for candidate in candidates:
        spec = find_spec(registry, "successor_scan", candidate.key)
        raw = module.candidate_trades(am_features, candidate, float(cfg["normal_cost_bps"]), float(cfg["severe_cost_bps"]))
        raw = raw.loc[(raw["entry_utc"] >= start) & (raw["exit_utc"] < end)].copy() if not raw.empty else raw
        trades = normalized_trade_frame(
            raw,
            spec,
            "entry_utc",
            "exit_utc",
            raw["gross_bps"] if not raw.empty else [],
            raw["normal_net_bps"] if not raw.empty else [],
            raw["severe_net_bps"] if not raw.empty else [],
            raw["gross_bps"] - stress_cost if not raw.empty else [],
        )
        source = module.metrics(raw, start, end, float(cfg["maximum_notional_to_equity"]), cfg["bootstrap"])
        folds, fold_summary = module.fold_metrics(raw, cfg["reference_folds"])
        source.update(fold_summary)
        gates = module.gate_results(source, cfg["reference_gates"], reference=True)

        sensitivity = exclude_warning_overlap(trades, protocol)
        raw_sensitivity = raw.loc[raw.index[:0]].copy() if raw.empty else raw.loc[
            ~((pd.to_datetime(raw["entry_utc"], utc=True) < pd.Timestamp(protocol["alignment_warning_sensitivity"]["end_utc_exclusive"]))
              & (pd.to_datetime(raw["exit_utc"], utc=True) > pd.Timestamp(protocol["alignment_warning_sensitivity"]["start_utc"])))
        ].copy()
        sensitivity_source = module.metrics(raw_sensitivity, start, end, float(cfg["maximum_notional_to_equity"]), cfg["bootstrap"])
        _, sensitivity_fold_summary = module.fold_metrics(raw_sensitivity, cfg["reference_folds"])
        sensitivity_source.update(sensitivity_fold_summary)
        sensitivity_gates = module.gate_results(sensitivity_source, cfg["reference_gates"], reference=True)

        raw_dk = module.candidate_trades(dk_features, candidate, float(cfg["normal_cost_bps"]), float(cfg["severe_cost_bps"]))
        raw_dk = raw_dk.loc[(raw_dk["entry_utc"] >= start) & (raw_dk["exit_utc"] < end)].copy() if not raw_dk.empty else raw_dk
        dk_trades = normalized_trade_frame(
            raw_dk,
            spec,
            "entry_utc",
            "exit_utc",
            raw_dk["gross_bps"] if not raw_dk.empty else [],
            raw_dk["normal_net_bps"] if not raw_dk.empty else [],
            raw_dk["severe_net_bps"] if not raw_dk.empty else [],
            raw_dk["gross_bps"] - stress_cost if not raw_dk.empty else [],
        )
        cross = cross_feed_comparison(
            trades,
            dk_trades,
            pd.to_datetime(raw["entry_utc"], utc=True).astype(str) if not raw.empty else [],
            pd.to_datetime(raw_dk["entry_utc"], utc=True).astype(str) if not raw_dk.empty else [],
            protocol,
        )
        results.append(
            SpecResult(
                specification_id=spec["specification_id"],
                source_block="successor_scan",
                source_candidate_id=candidate.key,
                economic_family=spec["economic_family"],
                parent_taxonomy=spec["parent_taxonomy"],
                trades=trades,
                sensitivity_trades=sensitivity,
                source_metrics=source,
                sensitivity_source_metrics=sensitivity_source,
                source_native_pass=bool(all(gates.values())),
                sensitivity_source_native_pass=bool(all(sensitivity_gates.values())),
                source_failed_gates=[key for key, passed in gates.items() if not passed],
                sensitivity_failed_gates=[key for key, passed in sensitivity_gates.items() if not passed],
                cross_feed=cross,
                auxiliary={"reference_folds": folds, "dukascopy_trades": dk_trades},
            )
        )
    return results


def cross_asset_results(
    root: Path,
    module: Any,
    block: str,
    config_name: str,
    registry: dict[tuple[str, str], dict[str, Any]],
    protocol: dict[str, Any],
) -> list[SpecResult]:
    cfg = load_json(root / f"configs/{config_name}")
    if block == "cross_asset_event_response":
        events, _ = module.load_official_events(root, cfg)
        frame = module.load_panel_data(root, cfg, events=events)
    else:
        frame = module.load_panel_data(root, cfg)
    end = pd.Timestamp(cfg["reference_end_utc"])
    frame = frame.loc[pd.to_datetime(frame["decision_time_utc"], utc=True) < end].copy().reset_index(drop=True)
    frame = module.add_past_only_zscores(frame, cfg)
    ref = module.period_mask(frame, cfg["reference_start_utc"], cfg["reference_end_utc"])
    stress_cost = float(protocol["secondary_costs"]["fixed_stress"][f"{block}_round_trip_bps"])
    results: list[SpecResult] = []
    for candidate in cfg["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        spec = find_spec(registry, block, candidate_id)
        universe, signal = module.candidate_masks(frame, candidate, cfg)
        universe &= ref
        signal &= ref
        raw = module.non_overlapping_trades(frame, signal, candidate, cfg, "REFERENCE")
        if not raw.empty:
            raw = raw.loc[pd.to_datetime(raw["exit_time_utc"], utc=True) < end].copy().reset_index(drop=True)
        metric, folds, annual = module.metrics_for_candidate(frame, universe, raw, candidate, cfg, "REFERENCE")
        passed, failed = module.reference_gate(metric, cfg)
        trades = normalized_trade_frame(
            raw,
            spec,
            "decision_time_utc",
            "exit_time_utc",
            raw["gross_bps"] if not raw.empty else [],
            raw["normal_net_bps"] if not raw.empty else [],
            raw["severe_net_bps"] if not raw.empty else [],
            raw["gross_bps"] - stress_cost if not raw.empty else [],
        )
        sensitivity = exclude_warning_overlap(trades, protocol)
        if raw.empty:
            raw_sensitivity = raw.copy()
        else:
            w = protocol["alignment_warning_sensitivity"]
            overlap = (
                (pd.to_datetime(raw["decision_time_utc"], utc=True) < pd.Timestamp(w["end_utc_exclusive"]))
                & (pd.to_datetime(raw["exit_time_utc"], utc=True) > pd.Timestamp(w["start_utc"]))
            )
            raw_sensitivity = raw.loc[~overlap].copy().reset_index(drop=True)
        sensitivity_metric, _, _ = module.metrics_for_candidate(frame, universe, raw_sensitivity, candidate, cfg, "REFERENCE")
        sensitivity_passed, sensitivity_failed = module.reference_gate(sensitivity_metric, cfg)
        results.append(
            SpecResult(
                specification_id=spec["specification_id"],
                source_block=block,
                source_candidate_id=candidate_id,
                economic_family=spec["economic_family"],
                parent_taxonomy=spec["parent_taxonomy"],
                trades=trades,
                sensitivity_trades=sensitivity,
                source_metrics=metric,
                sensitivity_source_metrics=sensitivity_metric,
                source_native_pass=bool(passed),
                sensitivity_source_native_pass=bool(sensitivity_passed),
                source_failed_gates=list(failed),
                sensitivity_failed_gates=list(sensitivity_failed),
                cross_feed={"applicable": False, "pass": None, "reason": "LOCKED_PANEL_CONTAINS_AMARKETS_DERIVED_XAU_SIGNAL_INPUTS"},
                auxiliary={"reference_folds": folds, "reference_annual": annual},
            )
        )
    return results


def tsmom_results(
    root: Path,
    module: Any,
    successor_module: Any,
    registry: dict[tuple[str, str], dict[str, Any]],
    protocol: dict[str, Any],
    input_paths: dict[str, Path],
) -> list[SpecResult]:
    cfg = load_json(root / "configs/xauusd_final_alpha_trend.json")
    successor_cfg = load_json(root / "configs/xauusd_successor_parallel_scan_v1.json")
    spec = find_spec(registry, "canonical_tsmom", cfg["strategy_id"])
    end = pd.Timestamp(cfg["reference_end_utc"])
    h1 = module.load_mt5_h1(input_paths["amarkets_xauusd_h1_long_history"], cfg)
    h1 = h1.loc[h1["timestamp_utc"] < end].copy().reset_index(drop=True)
    raw = module.build_monthly_strategy(h1, cfg)
    raw = raw.loc[pd.to_datetime(raw["exit_utc"], utc=True) < end].copy().reset_index(drop=True)
    source = module.metrics(raw, "net_return_severe", cfg)
    normal = module.metrics(raw, "net_return_normal", cfg, "normal_")
    folds = module.fold_metrics(raw, "net_return_severe")
    years = module.year_metrics(raw, "net_return_severe")
    paired = module.paired_excess_metrics(raw, cfg, "net_return_severe", "passive_net_return_severe")
    gates = module.reference_gate_checks(raw, cfg, source, folds, years, paired)
    source = {"strategy_severe": source, "strategy_normal": normal, "paired_excess_vs_passive_severe": paired, "gates": gates}
    fixed = float(protocol["secondary_costs"]["fixed_stress"]["canonical_tsmom_bps_per_1x_turnover"])
    trades = normalized_trade_frame(
        raw,
        spec,
        "entry_utc",
        "exit_utc",
        raw["gross_return"] * 10000.0,
        raw["net_return_normal"] * 10000.0,
        raw["net_return_severe"] * 10000.0,
        (raw["gross_return"] - raw["turnover"] * fixed / 10000.0) * 10000.0,
    )

    alignment_db = input_paths["amarkets_alignment_sqlite"]
    common_start = pd.Timestamp("2015-01-02T07:00:00Z")

    def common_feed(table: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        feed = successor_module.load_h1(
            alignment_db,
            table,
            int(successor_cfg["minimum_m5_bar_count"]),
        )
        feed = feed.loc[(feed["dt"] >= common_start) & (feed["dt"] < end)].copy().reset_index(drop=True)
        adapted = feed.rename(columns={"dt": "timestamp_utc"})[["timestamp_utc", "open", "high", "low", "close"]].copy()
        ledger = module.build_monthly_strategy(adapted, cfg)
        ledger = ledger.loc[pd.to_datetime(ledger["exit_utc"], utc=True) < end].copy().reset_index(drop=True)
        normalized = normalized_trade_frame(
            ledger,
            spec,
            "entry_utc",
            "exit_utc",
            ledger["gross_return"] * 10000.0,
            ledger["net_return_normal"] * 10000.0,
            ledger["net_return_severe"] * 10000.0,
            (ledger["gross_return"] - ledger["turnover"] * fixed / 10000.0) * 10000.0,
        )
        return ledger, normalized

    am_common_raw, am_common = common_feed(protocol["cross_feed_replication"]["amarkets_h1_table"])
    dk_common_raw, dk_common = common_feed(protocol["cross_feed_replication"]["dukascopy_h1_table"])
    cross = cross_feed_comparison(
        am_common.assign(decision_time_utc=pd.to_datetime(am_common_raw["month"].astype(str) + "-01", utc=True).to_numpy()),
        dk_common.assign(decision_time_utc=pd.to_datetime(dk_common_raw["month"].astype(str) + "-01", utc=True).to_numpy()),
        am_common_raw["month"].astype(str) if not am_common_raw.empty else [],
        dk_common_raw["month"].astype(str) if not dk_common_raw.empty else [],
        protocol,
    )
    return [
        SpecResult(
            specification_id=spec["specification_id"],
            source_block="canonical_tsmom",
            source_candidate_id=cfg["strategy_id"],
            economic_family=spec["economic_family"],
            parent_taxonomy=spec["parent_taxonomy"],
            trades=trades,
            sensitivity_trades=trades.copy(),
            source_metrics=source,
            sensitivity_source_metrics=source,
            source_native_pass=bool(gates["all"]),
            sensitivity_source_native_pass=bool(gates["all"]),
            source_failed_gates=[key for key, passed in gates.items() if key not in {"all", "derived"} and not passed],
            sensitivity_failed_gates=[key for key, passed in gates.items() if key not in {"all", "derived"} and not passed],
            cross_feed=cross,
            auxiliary={"reference_folds": folds, "reference_years": years, "dukascopy_trades": dk_common},
        )
    ]


def rv_results(
    root: Path,
    module: Any,
    registry: dict[tuple[str, str], dict[str, Any]],
    protocol: dict[str, Any],
    input_paths: dict[str, Path],
) -> list[SpecResult]:
    cfg = load_json(root / "configs/precious_metals_final_rv.json")
    candidate_id = cfg["strategy"]["strategy_id"]
    spec = find_spec(registry, "precious_metals_rv", candidate_id)
    xau = module.load_mt5_h1(input_paths["cross_asset_xauusd_h1"], cfg, "XAUUSD")
    xag = module.load_mt5_h1(input_paths["cross_asset_xagusd_h1"], cfg, "XAGUSD")
    sync = module.synchronize_h1(xau, xag, cfg)
    daily = module.build_common_daily(sync)
    start = pd.Timestamp(cfg["selection"]["reference_start_utc"])
    end = pd.Timestamp(cfg["selection"]["reference_end_utc"])
    daily = daily.loc[daily["date"] < end].copy().reset_index(drop=True)
    calibration_daily = daily.loc[(daily["date"] >= start) & (daily["date"] < end)].copy().reset_index(drop=True)
    _, calibration = module.run_clustered_regime_calibration(calibration_daily, cfg)
    raw = pd.DataFrame()
    source: dict[str, Any] = {"clustered_regime_calibration": calibration}
    passed = False
    failed = ["clustered_regime_calibration"]
    if bool(calibration.get("pass")):
        raw = module.simulate_pair_trades(daily, cfg, start, end)
        if not raw.empty:
            raw = raw.loc[pd.to_datetime(raw["exit_date"], utc=True) < end].copy().reset_index(drop=True)
        evaluation = module.evaluate_reference(raw, cfg)
        source["reference_metrics"] = evaluation.metrics
        source["reference_gates"] = evaluation.gates
        passed = bool(evaluation.passed)
        failed = [key for key, value in evaluation.gates.items() if not value]
    fixed = float(protocol["secondary_costs"]["fixed_stress"]["precious_metals_rv_two_leg_round_trip_bps"])
    if raw.empty:
        trades = normalized_trade_frame(raw, spec, "entry_date", "exit_date", [], [], [], [])
    else:
        trades = normalized_trade_frame(
            raw,
            spec,
            "entry_date",
            "exit_date",
            raw["gross_return"] * 10000.0,
            raw["normal_net_return"] * 10000.0,
            raw["severe_net_return"] * 10000.0,
            (raw["gross_return"] - fixed / 10000.0) * 10000.0,
        )
    return [
        SpecResult(
            specification_id=spec["specification_id"],
            source_block="precious_metals_rv",
            source_candidate_id=candidate_id,
            economic_family=spec["economic_family"],
            parent_taxonomy=spec["parent_taxonomy"],
            trades=trades,
            sensitivity_trades=trades.copy(),
            source_metrics=source,
            sensitivity_source_metrics=source,
            source_native_pass=passed,
            sensitivity_source_native_pass=passed,
            source_failed_gates=failed,
            sensitivity_failed_gates=failed,
            cross_feed={"applicable": False, "pass": None, "reason": "NO_INDEPENDENT_XAGUSD_FEED_IN_FROZEN_DATA_CONTRACT"},
            auxiliary={"calibration": calibration},
        )
    ]


def calendar_daily_series(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    index = pd.date_range(start.floor("D"), end.floor("D"), inclusive="left", freq="D", tz="UTC")
    result = pd.Series(0.0, index=index, dtype=float)
    if frame.empty:
        return result
    dates = pd.to_datetime(frame["exit_time_utc"], utc=True).dt.floor("D")
    sums = frame.assign(_date=dates).groupby("_date")["severe_net_bps"].sum()
    common = result.index.intersection(sums.index)
    result.loc[common] = sums.loc[common].astype(float)
    return result


def max_t_family(
    series_by_spec: dict[str, pd.Series],
    repetitions: int,
    block_days: int,
    seed: int,
) -> dict[str, Any]:
    ids = sorted(series_by_spec)
    matrix = np.column_stack([series_by_spec[key].to_numpy(dtype=float) for key in ids])
    n = matrix.shape[0]
    means = matrix.mean(axis=0)
    sd = matrix.std(axis=0, ddof=1)
    se = sd / math.sqrt(n)
    observed = np.divide(means, se, out=np.zeros_like(means), where=se > 0)
    centered = matrix - means
    rng = np.random.default_rng(seed)
    maxima = np.empty(repetitions, dtype=float)
    block = max(1, min(int(block_days), n))
    blocks_per_sample = int(math.ceil(n / block))
    offsets = np.arange(block, dtype=np.int64)
    batch_size = 100
    for first in range(0, repetitions, batch_size):
        count = min(batch_size, repetitions - first)
        starts = rng.integers(0, n, size=(count, blocks_per_sample), dtype=np.int64)
        indices = (starts[:, :, None] + offsets[None, None, :]) % n
        indices = indices.reshape(count, -1)[:, :n]
        sample_means = centered[indices, :].mean(axis=1)
        t_values = np.divide(sample_means, se[None, :], out=np.zeros_like(sample_means), where=se[None, :] > 0)
        maxima[first:first + count] = np.max(t_values, axis=1)
    adjusted = {key: float((1.0 + np.sum(maxima >= observed[i])) / (repetitions + 1.0)) for i, key in enumerate(ids)}
    best = int(np.argmax(observed))
    return {
        "observations": n,
        "specification_ids": ids,
        "observed_t": {key: float(observed[i]) for i, key in enumerate(ids)},
        "adjusted_p": adjusted,
        "family_max_t": float(observed[best]),
        "family_adjusted_p": adjusted[ids[best]],
        "best_specification_id": ids[best],
    }


def daily_bounds(result: SpecResult) -> tuple[pd.Timestamp, pd.Timestamp]:
    if result.source_block in {"successor_scan"}:
        return pd.Timestamp("2015-01-02T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z")
    if result.source_block in {"cross_asset_fixed", "cross_asset_event_response"}:
        return pd.Timestamp("2016-01-01T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z")
    if result.source_block == "canonical_tsmom":
        return pd.Timestamp("2012-01-01T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z")
    return pd.Timestamp("2012-01-01T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z")


def family_inference(results: list[SpecResult], protocol: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float]]:
    cfg = protocol["family_multiplicity"]
    alpha = float(cfg["alpha"])
    primary_p: dict[str, float] = {}
    sensitivity_p: dict[str, float] = {}
    output: list[dict[str, Any]] = []
    families = sorted({result.economic_family for result in results})
    for family_no, family in enumerate(families):
        group = [result for result in results if result.economic_family == family]
        starts, ends = zip(*(daily_bounds(result) for result in group))
        # Family-wise inference uses the intersection of eligible calendars.
        # At present every locked family belongs to one source block, but the
        # intersection rule prevents silent dilution if a later registry
        # version groups specifications with different reference starts.
        start, end = max(starts), min(ends)
        if start >= end:
            raise RuntimeError(f"no common inference calendar for family: {family}")
        primary_series = {result.specification_id: calendar_daily_series(result.trades, start, end) for result in group}
        sensitivity_series = {result.specification_id: calendar_daily_series(result.sensitivity_trades, start, end) for result in group}
        primary = max_t_family(primary_series, int(cfg["replications"]), int(cfg["block_calendar_days"]), int(cfg["seed"]) + family_no * 1009)
        sensitivity = max_t_family(sensitivity_series, int(cfg["replications"]), int(cfg["block_calendar_days"]), int(cfg["seed"]) + 500000 + family_no * 1009)
        primary_p.update(primary["adjusted_p"])
        sensitivity_p.update(sensitivity["adjusted_p"])
        primary_candidates = [
            result for result in group
            if result.source_native_pass
            and primary["adjusted_p"][result.specification_id] <= alpha
            and (not result.cross_feed.get("applicable") or bool(result.cross_feed.get("pass")))
        ]
        sensitivity_candidates = [
            result for result in group
            if result.sensitivity_source_native_pass
            and sensitivity["adjusted_p"][result.specification_id] <= alpha
            and (not result.cross_feed.get("applicable") or bool(result.cross_feed.get("pass")))
        ]
        alignment_applicable = any(result.source_block in protocol["alignment_warning_sensitivity"]["eligible_source_blocks"] for result in group)
        sign_change_ids = []
        if alignment_applicable:
            for result in group:
                before = mean_or_nan(result.trades["severe_net_bps"]) if not result.trades.empty else float("nan")
                after = mean_or_nan(result.sensitivity_trades["severe_net_bps"]) if not result.sensitivity_trades.empty else float("nan")
                if direction_sign(before) != direction_sign(after):
                    sign_change_ids.append(result.specification_id)
        rejection_changed = (primary["family_adjusted_p"] <= alpha) != (sensitivity["family_adjusted_p"] <= alpha)
        support_changed = bool(primary_candidates) != bool(sensitivity_candidates)
        alignment_fragile = alignment_applicable and bool(sign_change_ids or rejection_changed or support_changed)
        supported = bool(primary_candidates) and not alignment_fragile
        output.append(
            {
                "economic_family": family,
                "parent_taxonomy": group[0].parent_taxonomy,
                "specification_count": len(group),
                "native_pass_count": sum(result.source_native_pass for result in group),
                "family_max_t": primary["family_max_t"],
                "family_adjusted_p": primary["family_adjusted_p"],
                "best_specification_id": primary["best_specification_id"],
                "alignment_applicable": alignment_applicable,
                "alignment_sign_change_ids": sign_change_ids,
                "alignment_rejection_changed": rejection_changed,
                "alignment_support_changed": support_changed,
                "alignment_fragile": alignment_fragile,
                "sensitivity_family_adjusted_p": sensitivity["family_adjusted_p"],
                "supporting_specification_ids": [result.specification_id for result in primary_candidates] if supported else [],
                "decision": protocol["family_support_rule"]["supported_label"] if supported else protocol["family_support_rule"]["unsupported_label"],
            }
        )
    return output, primary_p, sensitivity_p


def sample_moments(values: np.ndarray) -> tuple[float, float]:
    x = values[np.isfinite(values)]
    if len(x) < 4 or np.std(x, ddof=1) == 0:
        return 0.0, 3.0
    centered = x - x.mean()
    sd = x.std(ddof=1)
    skew = float(np.mean((centered / sd) ** 3))
    kurt = float(np.mean((centered / sd) ** 4))
    return skew, kurt


def deflated_sharpe(results: list[SpecResult], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = protocol["deflated_sharpe_ratio"]
    start = pd.Timestamp(cfg["common_calendar_start_utc"])
    end = pd.Timestamp(cfg["common_calendar_end_utc_exclusive"])
    series = {result.specification_id: calendar_daily_series(result.trades, start, end) / 10000.0 for result in results}
    daily_sr: dict[str, float] = {}
    for key, values in series.items():
        arr = values.to_numpy(dtype=float)
        daily_sr[key] = float(arr.mean() / arr.std(ddof=1)) if arr.std(ddof=1) > 0 else 0.0
    n_trials = int(cfg["eligible_specifications"])
    sigma_sr = float(np.std(list(daily_sr.values()), ddof=1)) if len(daily_sr) > 1 else 0.0
    nd = NormalDist()
    gamma = 0.5772156649015329
    benchmark = 0.0
    # The Bailey--Lopez de Prado expected-maximum-Sharpe benchmark is written
    # explicitly to avoid an otherwise unnecessary scipy dependency.
    if n_trials > 1 and sigma_sr > 0:
        benchmark = sigma_sr * (
            (1.0 - gamma) * nd.inv_cdf(1.0 - 1.0 / n_trials)
            + gamma * nd.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
        )
    rows: list[dict[str, Any]] = []
    for result in results:
        arr = series[result.specification_id].to_numpy(dtype=float)
        sr = daily_sr[result.specification_id]
        skew, kurt = sample_moments(arr)
        denominator = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
        z = (sr - benchmark) * math.sqrt(max(len(arr) - 1, 1)) / math.sqrt(max(denominator, 1e-12))
        probability = nd.cdf(z)
        rows.append(
            {
                "specification_id": result.specification_id,
                "daily_sharpe_unannualized": sr,
                "annualized_sharpe_365": sr * math.sqrt(float(cfg["annualization_days"])),
                "expected_maximum_daily_sharpe_under_trials": benchmark,
                "skewness": skew,
                "kurtosis": kurt,
                "observations": len(arr),
                "eligible_trials": n_trials,
                "deflated_sharpe_probability": probability,
                "passes_0_95": probability >= float(cfg["report_probability_threshold"]),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("empty\n", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(safe_value(value), sort_keys=True) if isinstance(value, (dict, list)) else safe_value(value) for key, value in row.items()})


def write_gzip_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False)


def dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    for package in ("scipy", "sklearn", "statsmodels"):
        try:
            imported = __import__(package)
            versions[package] = getattr(imported, "__version__", "unknown")
        except Exception:
            versions[package] = None
    return versions


def outcome_blind_preflight(root: Path) -> tuple[dict[str, Any], dict[str, Path], Any]:
    registry_tool = import_path(root / REGISTRY_PREFLIGHT_PATH, "article1_registry_binding_tool")
    expected = registry_tool.build_registry(root)
    registry_path = root / REGISTRY_PATH
    registry_csv_path = root / REGISTRY_CSV_PATH
    protocol_path = root / PROTOCOL_PATH
    data_contract_path = root / DATA_CONTRACT_PATH
    deviation_path = root / DEVIATION_LOG_PATH
    runner_path = root / RUNNER_PATH
    checks: list[dict[str, Any]] = []
    checks.append({"name": "registry_json_byte_exact", "pass": registry_path.is_file() and registry_path.read_bytes() == registry_tool.pretty_bytes(expected)})
    checks.append({"name": "registry_csv_byte_exact", "pass": registry_csv_path.is_file() and registry_csv_path.read_bytes() == registry_tool.registry_csv_bytes(expected)})
    registry = load_json(registry_path)
    checks.append({"name": "registry_primary_count_39", "pass": registry["counts"]["primary_locked_rerun_specifications"] == 39})
    checks.append({"name": "registry_forensic_count_8", "pass": registry["counts"]["historical_forensic_only_specifications"] == 8})
    protocol = load_json(protocol_path)
    checks.append({"name": "protocol_registry_hash", "pass": protocol["registry_specification_set_sha256"] == registry["canonical_specification_set_sha256"]})
    checks.append({"name": "reference_only", "pass": protocol.get("reference_only") is True and protocol.get("post_2024_outcome_computation_allowed") is False})
    data_contract_actual = sha256_file(data_contract_path) if data_contract_path.is_file() else None
    checks.append(
        {
            "name": "data_contract_binding",
            "pass": data_contract_actual == registry_tool.DATA_CONTRACT_SHA256,
            "path": str(data_contract_path),
            "sha256": data_contract_actual,
        }
    )
    checks.append({"name": "deviation_log_exists", "pass": deviation_path.is_file()})
    checks.append({"name": "runner_exists", "pass": runner_path.is_file()})
    input_checks = [registry_tool.check_input(root, contract) for contract in registry_tool.REQUIRED_INPUTS]
    input_paths = {item["input_id"]: Path(item["matched_path"]) for item in input_checks if item["pass"] and item["matched_path"]}
    for item in input_checks:
        checks.append({"name": f"input:{item['input_id']}", "pass": bool(item["pass"]), "sha256": item.get("actual_sha256"), "path": item.get("matched_path")})
    for block, binding in registry_tool.SOURCE_BINDINGS.items():
        for kind in ("script", "config"):
            path = root / binding[f"{kind}_path"]
            actual = sha256_file(path) if path.is_file() else None
            checks.append({"name": f"source:{block}:{kind}", "pass": actual == binding[f"{kind}_sha256"], "sha256": actual})
            if path.is_file() and kind == "script":
                try:
                    compile(path.read_text(encoding="utf-8"), str(path), "exec")
                    compile_error = None
                except Exception as exc:
                    compile_error = f"{type(exc).__name__}: {exc}"
                checks.append({"name": f"compile:{block}", "pass": compile_error is None, "error": compile_error})
    run_dir = root / protocol["run_directory"]
    checks.append({"name": "run_directory_absent", "pass": not run_dir.exists()})
    passed = all(bool(item["pass"]) for item in checks)
    report = {
        "program": f"{PROGRAM}_PREFLIGHT",
        "generated_utc": utc_now(),
        "outcome_information_read": False,
        "historical_strategy_result_files_read": False,
        "checks": checks,
        "dependencies": dependency_versions(),
        "decision": "PASS_ARTICLE1_UNIFIED_RUNNER_PREFLIGHT" if passed else "BLOCK_ARTICLE1_UNIFIED_RUNNER_PREFLIGHT",
        "pass": passed,
    }
    return report, input_paths, registry_tool


def freeze_manifest(
    root: Path,
    run_dir: Path,
    registry: dict[str, Any],
    protocol: dict[str, Any],
    preflight: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    source_bindings = {item["source_block"]: item["source_binding"] for item in registry["source_blocks"]}
    input_bindings = [
        {"name": item["name"], "path": item.get("path"), "sha256": item.get("sha256")}
        for item in preflight["checks"] if str(item["name"]).startswith("input:")
    ]
    manifest = {
        "program": "XAUUSD_ARTICLE1_MAIN_RUN_MANIFEST_V1_0",
        "frozen_utc": utc_now(),
        "status": "FROZEN_BEFORE_OUTCOME_COMPUTATION",
        "study_interpretation": registry["study_interpretation"],
        "historical_outcomes_already_seen": True,
        "reference_only": True,
        "post_2024_outcome_computation_allowed": False,
        "registry": {
            "path": str(REGISTRY_PATH),
            "file_sha256": sha256_file(root / REGISTRY_PATH),
            "specification_set_sha256": registry["canonical_specification_set_sha256"],
            "primary_specifications": 39,
            "forensic_only_specifications": 8,
        },
        "execution_bindings": {
            "runner_path": str(RUNNER_PATH),
            "runner_sha256": sha256_file(root / RUNNER_PATH),
            "evaluation_protocol_path": str(PROTOCOL_PATH),
            "evaluation_protocol_sha256": sha256_file(root / PROTOCOL_PATH),
            "registry_preflight_path": str(REGISTRY_PREFLIGHT_PATH),
            "registry_preflight_sha256": sha256_file(root / REGISTRY_PREFLIGHT_PATH),
            "registry_csv_path": str(REGISTRY_CSV_PATH),
            "registry_csv_sha256": sha256_file(root / REGISTRY_CSV_PATH),
            "data_contract_path": str(DATA_CONTRACT_PATH),
            "data_contract_sha256": sha256_file(root / DATA_CONTRACT_PATH),
            "deviation_log_path": str(DEVIATION_LOG_PATH),
            "deviation_log_sha256": sha256_file(root / DEVIATION_LOG_PATH),
        },
        "source_bindings": source_bindings,
        "input_bindings": input_bindings,
        "environment": dependency_versions(),
        "evaluation_protocol": protocol,
        "authorization": {"paper_order_allowed": False, "demo_order_allowed": False, "live_order_allowed": False},
    }
    manifest_path = run_dir / "main_run_manifest.json"
    write_json(manifest_path, manifest)
    digest = sha256_file(manifest_path)
    lock = {
        "program": PROGRAM,
        "created_utc": utc_now(),
        "status": "FROZEN_BEFORE_OUTCOME_COMPUTATION",
        "main_run_manifest": manifest_path.name,
        "main_run_manifest_sha256": digest,
        "rerun_without_a_versioned_deviation_allowed": False,
    }
    write_json(run_dir / "REFERENCE_RUN_LOCK.json", lock)
    return manifest, digest


def verify_frozen_bindings(root: Path, run_dir: Path, manifest: dict[str, Any], expected_digest: str) -> None:
    manifest_path = run_dir / "main_run_manifest.json"
    if sha256_file(manifest_path) != expected_digest:
        raise RuntimeError("main run manifest changed after freeze")
    bindings = manifest["execution_bindings"]
    pairs = [
        (RUNNER_PATH, bindings["runner_sha256"]),
        (PROTOCOL_PATH, bindings["evaluation_protocol_sha256"]),
        (REGISTRY_PREFLIGHT_PATH, bindings["registry_preflight_sha256"]),
        (REGISTRY_CSV_PATH, bindings["registry_csv_sha256"]),
        (DATA_CONTRACT_PATH, bindings["data_contract_sha256"]),
        (DEVIATION_LOG_PATH, bindings["deviation_log_sha256"]),
        (REGISTRY_PATH, manifest["registry"]["file_sha256"]),
    ]
    for relative, expected in pairs:
        if sha256_file(root / relative) != expected:
            raise RuntimeError(f"frozen execution binding changed: {relative}")
    for binding in manifest["source_bindings"].values():
        for kind in ("script", "config"):
            relative = Path(binding[f"{kind}_path"])
            if sha256_file(root / relative) != binding[f"{kind}_sha256"]:
                raise RuntimeError(f"frozen source binding changed: {relative}")
    for item in manifest["input_bindings"]:
        path = Path(str(item["path"]))
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"frozen input binding changed: {path}")


def execute_reference(root: Path) -> tuple[dict[str, Any], Path]:
    preflight, input_paths, _ = outcome_blind_preflight(root)
    if not preflight["pass"]:
        raise RuntimeError("unified runner preflight failed: " + ",".join(item["name"] for item in preflight["checks"] if not item["pass"]))
    registry = load_json(root / REGISTRY_PATH)
    protocol = load_json(root / PROTOCOL_PATH)
    index = registry_index(registry)
    run_dir = root / protocol["run_directory"]
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "outcome_blind_preflight.json", preflight)
    for relative in (REGISTRY_PATH, REGISTRY_CSV_PATH, DATA_CONTRACT_PATH, PROTOCOL_PATH, DEVIATION_LOG_PATH):
        shutil.copy2(root / relative, run_dir / relative.name)
    manifest, manifest_digest = freeze_manifest(root, run_dir, registry, protocol, preflight)
    verify_frozen_bindings(root, run_dir, manifest, manifest_digest)

    modules = load_modules(root)
    results: list[SpecResult] = []
    results.extend(successor_results(root, modules["successor_scan"], index, protocol))
    results.extend(cross_asset_results(root, modules["cross_asset_fixed"], "cross_asset_fixed", "xauusd_cross_asset_fixed_scan.json", index, protocol))
    results.extend(cross_asset_results(root, modules["cross_asset_event_response"], "cross_asset_event_response", "xauusd_cross_asset_event_response_scan.json", index, protocol))
    results.extend(tsmom_results(root, modules["canonical_tsmom"], modules["successor_scan"], index, protocol, input_paths))
    results.extend(rv_results(root, modules["precious_metals_rv"], index, protocol, input_paths))
    if len(results) != 39 or len({result.specification_id for result in results}) != 39:
        raise RuntimeError(f"result cardinality failure: {len(results)}")

    families, adjusted_p, sensitivity_adjusted_p = family_inference(results, protocol)
    dsr = deflated_sharpe(results, protocol)
    metrics_rows: list[dict[str, Any]] = []
    cross_rows: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    source_metrics: dict[str, Any] = {}
    all_trades: list[pd.DataFrame] = []
    for result in results:
        summary = native_metric_summary(result.trades, result.source_metrics)
        sensitivity_summary = native_metric_summary(result.sensitivity_trades, result.sensitivity_source_metrics)
        before_sign = direction_sign(summary["mean_severe_net_bps"])
        after_sign = direction_sign(sensitivity_summary["mean_severe_net_bps"])
        metrics_rows.append(
            {
                "specification_id": result.specification_id,
                "source_block": result.source_block,
                "source_candidate_id": result.source_candidate_id,
                "economic_family": result.economic_family,
                "parent_taxonomy": result.parent_taxonomy,
                "trades": summary["trades"],
                "mean_gross_bps": summary["mean_gross_bps"],
                "mean_normal_net_bps": summary["mean_normal_net_bps"],
                "mean_severe_net_bps": summary["mean_severe_net_bps"],
                "mean_fixed_stress_net_bps": summary["mean_fixed_stress_net_bps"],
                "profit_factor_severe": summary["profit_factor_severe"],
                "source_native_pass": result.source_native_pass,
                "source_failed_gates": result.source_failed_gates,
                "family_max_t_adjusted_p": adjusted_p[result.specification_id],
                "sensitivity_family_max_t_adjusted_p": sensitivity_adjusted_p[result.specification_id],
                "cross_feed_applicable": result.cross_feed.get("applicable"),
                "cross_feed_pass": result.cross_feed.get("pass"),
                "alignment_sign_changed": before_sign != after_sign,
            }
        )
        source_metrics[result.specification_id] = {
            "source_metrics": result.source_metrics,
            "sensitivity_source_metrics": result.sensitivity_source_metrics,
            "source_native_pass": result.source_native_pass,
            "sensitivity_source_native_pass": result.sensitivity_source_native_pass,
            "source_failed_gates": result.source_failed_gates,
            "sensitivity_failed_gates": result.sensitivity_failed_gates,
        }
        cross_rows.append({"specification_id": result.specification_id, "source_block": result.source_block, **result.cross_feed})
        alignment_rows.append(
            {
                "specification_id": result.specification_id,
                "source_block": result.source_block,
                "applicable": result.source_block in protocol["alignment_warning_sensitivity"]["eligible_source_blocks"],
                "primary_trades": len(result.trades),
                "sensitivity_trades": len(result.sensitivity_trades),
                "primary_mean_severe_bps": summary["mean_severe_net_bps"],
                "sensitivity_mean_severe_bps": sensitivity_summary["mean_severe_net_bps"],
                "effect_sign_changed": before_sign != after_sign,
                "source_native_pass_changed": result.source_native_pass != result.sensitivity_source_native_pass,
            }
        )
        if not result.trades.empty:
            all_trades.append(result.trades)
    combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    write_gzip_csv(run_dir / "all_primary_reference_trades.csv.gz", combined)
    write_csv(run_dir / "specification_reference_metrics.csv", metrics_rows)
    write_csv(run_dir / "family_reference_decisions.csv", families)
    write_csv(run_dir / "cross_feed_replication.csv", cross_rows)
    write_csv(run_dir / "alignment_warning_sensitivity.csv", alignment_rows)
    write_csv(run_dir / "deflated_sharpe_ratio.csv", dsr)
    write_json(run_dir / "source_native_metrics.json", source_metrics)

    supported = [row["economic_family"] for row in families if row["decision"] == protocol["family_support_rule"]["supported_label"]]
    summary = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "reference_only": True,
        "post_2024_outcomes_computed": False,
        "historical_strategy_result_files_read": False,
        "registry_specifications": 47,
        "primary_specifications_evaluated": len(results),
        "forensic_only_specifications_not_rerun": 8,
        "economic_families_evaluated": len(families),
        "supported_family_count": len(supported),
        "supported_families": supported,
        "family_decision_counts": {
            label: sum(row["decision"] == label for row in families)
            for label in sorted({row["decision"] for row in families})
        },
        "pbo_status": protocol["probability_of_backtest_overfitting"],
        "decision": "ARTICLE1_REFERENCE_RERUN_COMPLETE_READY_FOR_INDEPENDENT_AUDIT",
        "pass": True,
        "authorization": {"paper_order_allowed": False, "demo_order_allowed": False, "live_order_allowed": False},
    }
    write_json(run_dir / "article1_reference_rerun_summary.json", summary)
    lock_path = run_dir / "REFERENCE_RUN_LOCK.json"
    lock = load_json(lock_path)
    lock.update({"status": "REFERENCE_OUTCOME_COMPUTATION_COMPLETE", "completed_utc": utc_now(), "summary_sha256": sha256_file(run_dir / "article1_reference_rerun_summary.json")})
    write_json(lock_path, lock)

    files = []
    for path in sorted(run_dir.iterdir()):
        if path.is_file() and path.name != "RESULTS_MANIFEST.json":
            files.append({"name": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_json(run_dir / "RESULTS_MANIFEST.json", {"program": PROGRAM, "generated_utc": utc_now(), "files": files})
    output = Path.home() / "Downloads" / f"XAUUSD_ARTICLE1_REFERENCE_RERUN_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(run_dir.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    return summary, output


def failure_archive(root: Path, exc: Exception) -> Path:
    root_failure = root / FAILURE_DIR
    root_failure.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    failure = {
        "program": PROGRAM,
        "generated_utc": utc_now(),
        "decision": "ARTICLE1_UNIFIED_REFERENCE_RUNNER_FAIL_CLOSED",
        "pass": False,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "authorization": {"paper_order_allowed": False, "demo_order_allowed": False, "live_order_allowed": False},
    }
    json_path = root_failure / f"article1_unified_runner_failure_{stamp}.json"
    write_json(json_path, failure)
    output = Path.home() / "Downloads" / f"XAUUSD_ARTICLE1_REFERENCE_RERUN_FAILURE_{stamp}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.name)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preflight", "execute"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        if args.command == "preflight":
            report, _, _ = outcome_blind_preflight(root)
            print(json.dumps(safe_value(report), indent=2))
            return 0 if report["pass"] else 2
        summary, output = execute_reference(root)
        print(json.dumps({"decision": summary["decision"], "pass": True, "results_zip": str(output)}, indent=2))
        return 0
    except Exception as exc:
        output = failure_archive(root, exc)
        print(json.dumps({"decision": "ARTICLE1_UNIFIED_REFERENCE_RUNNER_FAIL_CLOSED", "pass": False, "error": f"{type(exc).__name__}: {exc}", "results_zip": str(output)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
