#!/usr/bin/env python3
"""Build and verify the frozen Article 1 strategy-specification registry.

This utility is outcome-blind: it reads source code, configurations, and input
file bytes, but it never reads strategy-performance reports.  The ``build``
command is deterministic and is included for reproducibility.  The ``preflight``
command validates the installed registry, source bindings, and required input
hashes, then writes a compact evidence archive to ``~/Downloads``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROGRAM = "XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1"
FREEZE_UTC = "2026-09-02T05:19:30Z"
EVIDENCE_PACKAGE_SHA256 = "3378f61717a3a16f29ee33609ce0aa826157cd48fc065aaf6ae61b129eb74b06"
REPOSITORY_SNAPSHOT = "9fe0e02ce70256412080178b05972dd833212acf"
DATA_CONTRACT_PATH = "docs/article_publication/XAUUSD_ARTICLE1_DATA_CONTRACT_DECISION_V1_1.json"
DATA_CONTRACT_SHA256 = "afdcf838d59c0e5c18ae1f744b3c63d73148de9cb230a785d5ddca2ee7402609"
REGISTRY_JSON_PATH = "docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.json"
REGISTRY_CSV_PATH = "docs/article_publication/XAUUSD_ARTICLE1_LOCKED_SPECIFICATION_REGISTRY_V1_1.csv"


SOURCE_BINDINGS: dict[str, dict[str, str]] = {
    "successor_scan": {
        "script_path": "app/xauusd_successor_parallel_scan.py",
        "script_sha256": "1957d9964e3d031075b76f20a6a4c4c15afee2954ea9bcc63ca1e6def5a48024",
        "config_path": "configs/xauusd_successor_parallel_scan_v1.json",
        "config_sha256": "2fbdbc2b93abff46124916d9861877a4b7aee99c4f7f98ca21dab8d71f5678fa",
    },
    "cross_asset_fixed": {
        "script_path": "app/xauusd_cross_asset_fixed_scan.py",
        "script_sha256": "0ac88e74834b4510bd493930fc67ab6d1ec83295c5d80e608cd7a3691494f9e9",
        "config_path": "configs/xauusd_cross_asset_fixed_scan.json",
        "config_sha256": "7924616b0dea4de6678a655e0395988d5c116d97359ac390a05f5f3007730c1e",
    },
    "cross_asset_event_response": {
        "script_path": "app/xauusd_cross_asset_event_response_scan.py",
        "script_sha256": "e2b28566e33aec8e9d73582d7d4376b0541a15343ada7bd53731801c37da028d",
        "config_path": "configs/xauusd_cross_asset_event_response_scan.json",
        "config_sha256": "f231faef32a40e4dc767f3352cbcf12b3ebfff0978ec5662ec7d624ac535b640",
    },
    "stage178_ml": {
        "script_path": "app/stage178_commercial_edge_decision_sprint.py",
        "script_sha256": "3acac21c41c7285222ca8017cf3436372fd8d3c4466705932d0e69631379e2c7",
        "config_path": "configs/stage178_commercial_edge_decision_sprint.json",
        "config_sha256": "73c30a18eff9e2ce5b2b85ab9b63c5e374baa5d86c52fe5aa38fd2aa1f1edc1b",
    },
    "canonical_tsmom": {
        "script_path": "app/xauusd_final_alpha_trend.py",
        "script_sha256": "b69caaaf0022e2d5956e0ebac964a06ab35e1279961c1ef04231a250962c7970",
        "config_path": "configs/xauusd_final_alpha_trend.json",
        "config_sha256": "d524066350a743d0ce239bc226dec77a98f0f399d6c9b0248a5d8dc9eae37964",
    },
    "precious_metals_rv": {
        "script_path": "app/precious_metals_final_rv.py",
        "script_sha256": "2e9e96becd409b6a44aab140e0c00d1e2f65d356b9e3b7f2808517a4b9ab5fa6",
        "config_path": "configs/precious_metals_final_rv.json",
        "config_sha256": "2b5f2a571f745a3ca39223c1a8e24415abe3b17ac9fb2062695bd44c49c49109",
    },
}


REQUIRED_INPUTS: list[dict[str, Any]] = [
    {
        "input_id": "amarkets_alignment_sqlite",
        "candidates": ["data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"],
        "sha256": "c38491993ec5b76325d61f941cbdff7cda7147c83c97f43b80e97221385669f5",
        "kind": "sqlite",
        "required_for": ["successor_scan", "cross_feed_replication"],
    },
    {
        "input_id": "dukascopy_extended_history_sqlite",
        "candidates": ["data/local/stage177b_extended_history/xauusd_extended_history.sqlite"],
        "sha256": "8d9a3f9d7e8a05cc9fa97badd93aa809e1c09b105eacb3b96720671aa74c66de",
        "kind": "sqlite",
        "required_for": ["cross_feed_replication"],
    },
    {
        "input_id": "historical_event_context_sqlite",
        "candidates": ["data/local/historical_event_context/xauusd_historical_event_context.sqlite"],
        "sha256": "bbd9adacec575e0df89ce7f8dcce35c4980036b7e73c15cbc33bd332250bec72",
        "kind": "sqlite",
        "required_for": ["successor_scan"],
    },
    {
        "input_id": "cross_asset_intraday_features",
        "candidates": ["reports/xauusd_cross_asset_intraday_panel/cross_asset_intraday_features.csv"],
        "sha256": "66d2f5319cb419be5f1fd595b8f8a072342b4599747b31cf87cadc95bbc2a2d2",
        "kind": "csv",
        "required_for": ["cross_asset_fixed", "cross_asset_event_response"],
    },
    {
        "input_id": "cross_asset_intraday_targets",
        "candidates": ["reports/xauusd_cross_asset_intraday_panel/cross_asset_intraday_targets.csv"],
        "sha256": "cd81d4c32d66e9d1bd0c20621d099ef74d68ad9f0970e359d09760aee6af08f4",
        "kind": "csv",
        "required_for": ["cross_asset_fixed", "cross_asset_event_response"],
    },
    {
        "input_id": "official_event_timestamps",
        "candidates": ["data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"],
        "sha256": "601f587e0128d4322bc3ea5071545e53adf035b5e08fdbafa72cf16a550ec560",
        "kind": "csv",
        "required_for": ["cross_asset_event_response"],
    },
    {
        "input_id": "amarkets_xauusd_h1_long_history",
        "candidates": [
            "~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv",
            "~/Downloads/amarkets_xauusd_1h.csv",
        ],
        "sha256": "b32088f08f8217ea7b5bf81ab66c971fc7dc4eda2cc98d2364a742aa0f33e7d2",
        "kind": "csv",
        "required_for": ["canonical_tsmom"],
    },
    {
        "input_id": "cross_asset_xauusd_h1",
        "candidates": [
            "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/XAUUSD_CROSS_ASSET_HISTORY/xauusd__h1.csv",
            "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/XAUUSD_CROSS_ASSET_HISTORY/XAUUSD_H1.csv",
            "data/mt5_cross_asset/xauusd__h1.csv",
        ],
        "sha256": "9123ba8153f1b5541b5674323d80faf05f0008b6df6368074e6ccf9b5162f569",
        "kind": "csv",
        "required_for": ["precious_metals_rv"],
    },
    {
        "input_id": "cross_asset_xagusd_h1",
        "candidates": [
            "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/XAUUSD_CROSS_ASSET_HISTORY/xagusd__h1.csv",
            "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/XAUUSD_CROSS_ASSET_HISTORY/XAGUSD_H1.csv",
            "data/mt5_cross_asset/xagusd__h1.csv",
        ],
        "sha256": "392dd771cb6654d2eadfd1ae288bb4096022b9bacca39290580b9e28f89a9b86",
        "kind": "csv",
        "required_for": ["precious_metals_rv"],
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def checked_config(root: Path, block: str) -> dict[str, Any]:
    binding = SOURCE_BINDINGS[block]
    path = root / binding["config_path"]
    actual = sha256_file(path)
    if actual != binding["config_sha256"]:
        raise ValueError(f"config hash mismatch for {block}: {actual}")
    return load_json(path)


def source_binding(block: str) -> dict[str, str]:
    return dict(SOURCE_BINDINGS[block])


def reference_contract(block: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if block == "successor_scan":
        return {
            "start_utc": cfg["reference_start"],
            "end_utc_exclusive": cfg["holdout_start"],
            "folds": cfg["reference_folds"],
            "post_2024_role": "SEEN_TEMPORAL_DIAGNOSTIC_NOT_CONFIRMATORY",
        }
    if block in {"cross_asset_fixed", "cross_asset_event_response"}:
        return {
            "start_utc": cfg["reference_start_utc"],
            "end_utc_exclusive": cfg["reference_end_utc"],
            "folds": cfg["reference_folds"],
            "post_2024_role": "SEEN_TEMPORAL_DIAGNOSTIC_NOT_CONFIRMATORY",
        }
    if block == "stage178_ml":
        return {
            "historical_test_folds": cfg["reference_walk_forward_folds"],
            "end_utc_exclusive": cfg["final_holdout_start"],
            "role": "HISTORICAL_FORENSIC_ONLY_NO_ARTICLE1_PRIMARY_RERUN",
        }
    if block == "canonical_tsmom":
        return {
            "start_rule": "FIRST_ELIGIBLE_MONTH_AFTER_LOCKED_12_MONTH_LOOKBACK_AND_120_DAILY_RETURN_WARMUP",
            "end_utc_exclusive": cfg["reference_end_utc"],
            "post_2024_role": "SEEN_TEMPORAL_DIAGNOSTIC_NOT_CONFIRMATORY",
        }
    if block == "precious_metals_rv":
        return {
            "start_utc": cfg["selection"]["reference_start_utc"],
            "start_rule": "MAX_OF_CONFIG_START_AND_FIRST_ELIGIBLE_SIGNAL_AFTER_252_COMPLETED_DAILY_CLOSES",
            "end_utc_exclusive": cfg["selection"]["reference_end_utc"],
            "post_2024_role": "SEEN_TEMPORAL_DIAGNOSTIC_NOT_CONFIRMATORY",
        }
    raise KeyError(block)


def historical_cost_contract(block: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if block == "successor_scan":
        return {"unit": "round_trip_bps", "normal": cfg["normal_cost_bps"], "severe": cfg["severe_cost_bps"]}
    if block in {"cross_asset_fixed", "cross_asset_event_response"}:
        return {"unit": "round_trip_bps", "normal": cfg["normal_cost_bps"], "severe": cfg["severe_cost_bps"]}
    if block == "stage178_ml":
        return {"unit": "round_trip_bps", "normal": cfg["round_trip_cost_bps"], "severe": cfg["severe_round_trip_cost_bps"]}
    if block == "canonical_tsmom":
        return {"unit": "bps_per_1x_turnover", **cfg["cost_bps_per_1x_turnover"]}
    if block == "precious_metals_rv":
        strategy = cfg["strategy"]
        return {
            "unit": "two_leg_gross_notional_round_trip_bps",
            "normal": strategy["normal_roundtrip_cost_bps"],
            "severe": strategy["severe_roundtrip_cost_bps"],
        }
    raise KeyError(block)


def new_spec(
    order: int,
    block: str,
    candidate_id: str,
    parent: str,
    family: str,
    role: str,
    direction: str,
    horizon_value: int | None,
    horizon_unit: str | None,
    signal_contract: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    primary = role == "PRIMARY_LOCKED_RERUN"
    low_frequency = block in {"canonical_tsmom", "precious_metals_rv"}
    # Exact independent-feed signal replication is defined only where every
    # XAU-derived signal input can be rebuilt on the second feed.  The locked
    # cross-asset panel contains AMarkets-derived XAU features; replacing only
    # its target would not constitute same-code, same-signal replication.
    cross_feed = block in {"successor_scan", "canonical_tsmom"}
    return {
        "registry_order": order,
        "specification_id": f"A1R-{order:03d}",
        "source_block": block,
        "source_candidate_id": candidate_id,
        "parent_taxonomy": parent,
        "economic_family": family,
        "analysis_role": role,
        "primary_eligible": primary,
        "exclusion_reason": None if primary else "HISTORICALLY_SELECTED_MODEL_AND_SEEN_2025_PLUS_DIAGNOSTIC; FORENSIC_CASE_STUDY_ONLY",
        "direction": direction,
        "horizon": None if horizon_value is None else {"value": horizon_value, "unit": horizon_unit},
        "signal_contract": signal_contract,
        "reference_contract": reference_contract(block, cfg),
        "historical_cost_contract": historical_cost_contract(block, cfg),
        "article1_cost_contract_status": "TO_BE_FROZEN_IN_MAIN_RUN_MANIFEST_WITH_RUNNER_HASH",
        "alignment_warning_sensitivity": (
            "NOT_PRIMARY_RERUN"
            if not primary
            else "LOW_FREQUENCY_SEPARATE_DATA_CONTRACT"
            if low_frequency
            else "REQUIRED_EXCLUDE_2019_10_07_THROUGH_2019_10_14"
        ),
        "cross_feed_replication": "REQUIRED_ON_COMMON_WINDOW" if primary and cross_feed else "NOT_APPLICABLE",
        "source_binding": source_binding(block),
    }


def build_registry(root: Path) -> dict[str, Any]:
    configs = {block: checked_config(root, block) for block in SOURCE_BINDINGS}
    specs: list[dict[str, Any]] = []
    order = 0

    successor = configs["successor_scan"]
    for candidate in successor["candidates"]:
        order += 1
        event_family = str(candidate["family"]).startswith("post_event_")
        specs.append(
            new_spec(
                order,
                "successor_scan",
                candidate["key"],
                "event_and_news_response" if event_family else "canonical_technical_rules",
                candidate["family"],
                "PRIMARY_LOCKED_RERUN",
                "DYNAMIC_LONG_SHORT",
                int(candidate["horizon_hours"]),
                "hours",
                candidate,
                successor,
            )
        )

    fixed = configs["cross_asset_fixed"]
    for candidate in fixed["candidates"]:
        order += 1
        specs.append(
            new_spec(
                order,
                "cross_asset_fixed",
                candidate["candidate_id"],
                "fixed_thesis_cross_asset_rules",
                candidate["family"],
                "PRIMARY_LOCKED_RERUN",
                candidate["side"],
                int(candidate["horizon_hours"]),
                "hours",
                candidate,
                fixed,
            )
        )

    event_cfg = configs["cross_asset_event_response"]
    for candidate in event_cfg["candidates"]:
        order += 1
        specs.append(
            new_spec(
                order,
                "cross_asset_event_response",
                candidate["candidate_id"],
                "event_and_news_response",
                candidate["family"],
                "PRIMARY_LOCKED_RERUN",
                candidate["side"],
                int(candidate["horizon_hours"]),
                "hours",
                {
                    **candidate,
                    "event_response_min_lag_minutes": event_cfg["event_response_min_lag_minutes"],
                    "event_response_max_lag_minutes": event_cfg["event_response_max_lag_minutes"],
                },
                event_cfg,
            )
        )

    ml_cfg = configs["stage178_ml"]
    for model in ml_cfg["models"]:
        for target in ml_cfg["targets"]:
            order += 1
            candidate_id = f"{model}__{target['key']}"
            specs.append(
                new_spec(
                    order,
                    "stage178_ml",
                    candidate_id,
                    "supervised_machine_learning_meta_models",
                    "SUPERVISED_DIRECTIONAL_META_MODEL",
                    "HISTORICAL_FORENSIC_CASE_STUDY_ONLY",
                    "MODEL_PROBABILITY_LONG_SHORT",
                    int(target["horizon_hours"]),
                    "hours",
                    {
                        "model": model,
                        "target": target,
                        "probability_threshold": ml_cfg["probability_threshold"],
                        "training_stride_hours": ml_cfg["training_stride_hours"],
                        "minimum_training_rows": ml_cfg["minimum_training_rows"],
                        "random_state": ml_cfg["random_state"],
                    },
                    ml_cfg,
                )
            )

    trend = configs["canonical_tsmom"]
    order += 1
    specs.append(
        new_spec(
            order,
            "canonical_tsmom",
            trend["strategy_id"],
            "canonical_long_horizon_time_series_momentum",
            "TIME_SERIES_MOMENTUM",
            "PRIMARY_LOCKED_RERUN",
            "DYNAMIC_LONG_SHORT",
            int(trend["holding_months"]),
            "months",
            {
                "strategy_id": trend["strategy_id"],
                "lookback_months": trend["lookback_months"],
                "holding_months": trend["holding_months"],
                "volatility": trend["volatility"],
                "position": trend["position"],
            },
            trend,
        )
    )

    rv = configs["precious_metals_rv"]
    order += 1
    specs.append(
        new_spec(
            order,
            "precious_metals_rv",
            rv["strategy"]["strategy_id"],
            "precious_metals_relative_value_rules",
            "GOLD_SILVER_DYNAMIC_LOG_SPREAD_MEAN_REVERSION",
            "PRIMARY_LOCKED_RERUN",
            "MARKET_NEUTRAL_PAIR",
            int(rv["strategy"]["maximum_holding_days"]),
            "trading_days_maximum",
            dict(rv["strategy"]),
            rv,
        )
    )

    if order != 47:
        raise AssertionError(f"unexpected registry size: {order}")
    primary = [row for row in specs if row["primary_eligible"]]
    forensic = [row for row in specs if not row["primary_eligible"]]
    primary_families = sorted({row["economic_family"] for row in primary})
    parent_counts: dict[str, int] = {}
    for row in primary:
        parent_counts[row["parent_taxonomy"]] = parent_counts.get(row["parent_taxonomy"], 0) + 1

    registry = {
        "program": PROGRAM,
        "schema_version": "1.0",
        "freeze_utc": FREEZE_UTC,
        "freeze_status": "SPECIFICATION_REGISTRY_FROZEN; RUNNER_AND_MAIN_RUN_MANIFEST_PENDING",
        "study_interpretation": "RETROSPECTIVE_SYSTEMATIC_AUDIT_WITH_PROSPECTIVELY_LOCKED_CONSOLIDATED_RERUN",
        "historical_outcomes_already_seen": True,
        "confirmatory_claim_prohibited": True,
        "selection_rule": "INCLUDE_EVERY_EXACT_SPECIFICATION_IN_EACH_RECOVERABLE_FINAL_FIXED_REGISTRY; DO_NOT_SELECT_ON_HISTORICAL_PERFORMANCE",
        "evidence_binding": {
            "historical_evidence_package_sha256": EVIDENCE_PACKAGE_SHA256,
            "repository_snapshot": REPOSITORY_SNAPSHOT,
            "data_contract_path": DATA_CONTRACT_PATH,
            "data_contract_sha256": DATA_CONTRACT_SHA256,
            "data_contract_decision": "PASS_ARTICLE1_2015_2024_REFERENCE_DATA_CONTRACT_WITH_ALIGNMENT_WARNING",
        },
        "counts": {
            "registry_specifications": len(specs),
            "primary_locked_rerun_specifications": len(primary),
            "historical_forensic_only_specifications": len(forensic),
            "primary_economic_families": len(primary_families),
            "primary_parent_taxonomy_counts": parent_counts,
            "source_blocks": len(SOURCE_BINDINGS),
        },
        "primary_economic_families": primary_families,
        "source_blocks": [
            {
                "source_block": block,
                "source_binding": source_binding(block),
                "registry_rows": sum(row["source_block"] == block for row in specs),
                "primary_rows": sum(row["source_block"] == block and row["primary_eligible"] for row in specs),
            }
            for block in SOURCE_BINDINGS
        ],
        "global_temporal_policy": {
            "primary_intraday_start_utc": "2015-01-02T07:00:00Z",
            "primary_end_utc_exclusive": "2025-01-01T00:00:00Z",
            "pre_2015_intraday_policy": "EXCLUDED_FROM_PRIMARY_INTRADAY_INFERENCE",
            "post_2024_policy": "SEEN_TEMPORAL_DIAGNOSTIC_NOT_CONFIRMATORY",
            "warned_interval_start_utc": "2019-10-07T00:00:00Z",
            "warned_interval_end_utc_exclusive": "2019-10-14T00:00:00Z",
        },
        "execution_policy": {
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        },
        "specifications": specs,
    }
    registry["canonical_specification_set_sha256"] = hashlib.sha256(canonical_bytes(specs)).hexdigest()
    return registry


CSV_FIELDS = [
    "registry_order",
    "specification_id",
    "source_block",
    "source_candidate_id",
    "parent_taxonomy",
    "economic_family",
    "analysis_role",
    "primary_eligible",
    "direction",
    "horizon_value",
    "horizon_unit",
    "reference_start_utc",
    "reference_end_utc_exclusive",
    "alignment_warning_sensitivity",
    "cross_feed_replication",
    "source_script_path",
    "source_script_sha256",
    "source_config_path",
    "source_config_sha256",
    "signal_contract_json",
    "exclusion_reason",
]


def registry_csv_bytes(registry: dict[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in registry["specifications"]:
        reference = row["reference_contract"]
        horizon = row["horizon"] or {}
        binding = row["source_binding"]
        writer.writerow(
            {
                "registry_order": row["registry_order"],
                "specification_id": row["specification_id"],
                "source_block": row["source_block"],
                "source_candidate_id": row["source_candidate_id"],
                "parent_taxonomy": row["parent_taxonomy"],
                "economic_family": row["economic_family"],
                "analysis_role": row["analysis_role"],
                "primary_eligible": str(row["primary_eligible"]).lower(),
                "direction": row["direction"],
                "horizon_value": horizon.get("value", ""),
                "horizon_unit": horizon.get("unit", ""),
                "reference_start_utc": reference.get("start_utc", reference.get("start_rule", "")),
                "reference_end_utc_exclusive": reference.get("end_utc_exclusive", ""),
                "alignment_warning_sensitivity": row["alignment_warning_sensitivity"],
                "cross_feed_replication": row["cross_feed_replication"],
                "source_script_path": binding["script_path"],
                "source_script_sha256": binding["script_sha256"],
                "source_config_path": binding["config_path"],
                "source_config_sha256": binding["config_sha256"],
                "signal_contract_json": json.dumps(row["signal_contract"], sort_keys=True, separators=(",", ":")),
                "exclusion_reason": row["exclusion_reason"] or "",
            }
        )
    return stream.getvalue().encode("utf-8")


def write_registry(root: Path, output_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    registry = build_registry(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / Path(REGISTRY_JSON_PATH).name
    csv_path = output_dir / Path(REGISTRY_CSV_PATH).name
    json_path.write_bytes(pretty_bytes(registry))
    csv_path.write_bytes(registry_csv_bytes(registry))
    return json_path, csv_path, registry


def resolve_candidate(root: Path, raw: str) -> Path:
    expanded = Path(os.path.expanduser(raw))
    return expanded if expanded.is_absolute() else root / expanded


def check_input(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    paths = [resolve_candidate(root, raw) for raw in contract["candidates"]]
    matched: Path | None = None
    actual_hash: str | None = None
    candidates_seen: list[dict[str, Any]] = []
    for path in paths:
        item: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
        if path.is_file():
            item["size_bytes"] = path.stat().st_size
            digest = sha256_file(path)
            item["sha256"] = digest
            item["hash_match"] = digest == contract["sha256"]
            if matched is None and item["hash_match"]:
                matched = path
                actual_hash = digest
        candidates_seen.append(item)
    sqlite_ok: bool | None = None
    if matched is not None and contract["kind"] == "sqlite":
        try:
            with sqlite3.connect(f"file:{matched}?mode=ro", uri=True) as connection:
                sqlite_ok = connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            sqlite_ok = False
    passed = matched is not None and sqlite_ok is not False
    return {
        "input_id": contract["input_id"],
        "required_for": contract["required_for"],
        "expected_sha256": contract["sha256"],
        "matched_path": str(matched) if matched else None,
        "actual_sha256": actual_hash,
        "sqlite_quick_check": sqlite_ok,
        "pass": passed,
        "candidates": candidates_seen,
    }


def run_preflight(root: Path, output: Path | None) -> tuple[dict[str, Any], Path]:
    errors: list[str] = []
    file_checks: list[dict[str, Any]] = []
    try:
        expected = build_registry(root)
    except Exception as exc:  # fail closed with a machine-readable report
        expected = {}
        errors.append(f"registry_rebuild_failed:{type(exc).__name__}:{exc}")

    expected_json = pretty_bytes(expected) if expected else b""
    expected_csv = registry_csv_bytes(expected) if expected else b""
    for relative, expected_bytes in ((REGISTRY_JSON_PATH, expected_json), (REGISTRY_CSV_PATH, expected_csv)):
        path = root / relative
        exists = path.is_file()
        exact = exists and path.read_bytes() == expected_bytes
        file_checks.append(
            {
                "path": relative,
                "exists": exists,
                "byte_exact_rebuild_match": exact,
                "sha256": sha256_file(path) if exists else None,
                "pass": exact,
            }
        )

    for block, binding in SOURCE_BINDINGS.items():
        for kind in ("script", "config"):
            relative = binding[f"{kind}_path"]
            path = root / relative
            actual = sha256_file(path) if path.is_file() else None
            passed = actual == binding[f"{kind}_sha256"]
            file_checks.append(
                {
                    "block": block,
                    "kind": kind,
                    "path": relative,
                    "exists": path.is_file(),
                    "expected_sha256": binding[f"{kind}_sha256"],
                    "sha256": actual,
                    "pass": passed,
                }
            )

    data_contract = root / DATA_CONTRACT_PATH
    data_contract_actual = sha256_file(data_contract) if data_contract.is_file() else None
    file_checks.append(
        {
            "kind": "data_contract",
            "path": DATA_CONTRACT_PATH,
            "exists": data_contract.is_file(),
            "expected_sha256": DATA_CONTRACT_SHA256,
            "sha256": data_contract_actual,
            "pass": data_contract_actual == DATA_CONTRACT_SHA256,
        }
    )

    input_checks = [check_input(root, contract) for contract in REQUIRED_INPUTS]
    if any(not item["pass"] for item in file_checks):
        errors.append("one_or_more_registry_or_source_binding_checks_failed")
    if any(not item["pass"] for item in input_checks):
        errors.append("one_or_more_required_input_binding_checks_failed")

    passed = not errors
    report = {
        "program": f"{PROGRAM}_PREFLIGHT",
        "generated_utc": utc_now(),
        "root": str(root),
        "outcome_information_read": False,
        "strategy_result_files_read": False,
        "registry_counts": expected.get("counts") if expected else None,
        "registry_specification_set_sha256": expected.get("canonical_specification_set_sha256") if expected else None,
        "file_checks": file_checks,
        "input_checks": input_checks,
        "errors": errors,
        "decision": "PASS_ARTICLE1_REGISTRY_SOURCE_AND_INPUT_BINDINGS" if passed else "BLOCK_ARTICLE1_REGISTRY_SOURCE_AND_INPUT_BINDINGS",
        "pass": passed,
        "authorization": {"paper_order_allowed": False, "demo_order_allowed": False, "live_order_allowed": False},
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output or (Path.home() / "Downloads" / f"XAUUSD_ARTICLE1_REGISTRY_PREFLIGHT_{stamp}.zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    report_name = "article1_registry_preflight_report.json"
    with tempfile.TemporaryDirectory(prefix="article1_registry_preflight_") as temp_name:
        temp = Path(temp_name)
        report_path = temp / report_name
        report_path.write_bytes(pretty_bytes(report))
        checksum_path = temp / "SHA256SUMS.txt"
        checksum_path.write_text(f"{sha256_file(report_path)}  {report_name}\n", encoding="utf-8")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.write(report_path, report_path.name)
            archive.write(checksum_path, checksum_path.name)
    return report, destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="deterministically rebuild the frozen registry")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    preflight = sub.add_parser("preflight", help="verify registry, sources, and required inputs")
    preflight.add_argument("--root", type=Path, default=Path.cwd())
    preflight.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.command == "build":
        json_path, csv_path, registry = write_registry(root, args.output_dir.expanduser().resolve())
        print(
            json.dumps(
                {
                    "decision": "REGISTRY_BUILD_COMPLETE",
                    "registry_json": str(json_path),
                    "registry_csv": str(csv_path),
                    "counts": registry["counts"],
                    "canonical_specification_set_sha256": registry["canonical_specification_set_sha256"],
                },
                indent=2,
            )
        )
        return 0
    report, destination = run_preflight(root, args.output.expanduser().resolve() if args.output else None)
    print(json.dumps({"decision": report["decision"], "pass": report["pass"], "errors": report["errors"], "results_zip": str(destination)}, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
