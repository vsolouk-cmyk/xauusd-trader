#!/usr/bin/env python3
"""Freeze and preflight a bounded XAUUSD demo design without an order path."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_BOUNDED_DEMO_DESIGN_V1_1_RISK_SOURCE_PROVENANCE_REPAIR_NO_ORDER"
REPLAY_PROGRAM = "XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V7_OFFICIAL_EVENT_CONTEXT_CLOSURE"
EVENT_PROGRAM = "XAUUSD_HISTORICAL_EVENT_CONTEXT_V1_2_EXISTING_PIPELINE_BRIDGE"
CONTROLLED_PROGRAM = "XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY"
REPLAY_DECISION = "PASS_FULL_HISTORICAL_EVENT_AWARE_REPLAY_DEMO_DESIGN_ALLOWED_NO_FORWARD_WAIT"
EVENT_DECISION = "PASS_EXISTING_PIPELINE_HISTORICAL_EVENT_CONTEXT_CORE_BLACKOUT"
PREFLIGHT_DECISION = "PASS_CONTROLLED_PAPER_PREFLIGHT"
REQUIRED_EVENT_CATEGORIES = {
    "BLS_EMPLOYMENT_SITUATION", "BLS_CPI", "BLS_PPI", "BLS_JOLTS", "BLS_ECI",
    "BEA_GDP", "BEA_PERSONAL_INCOME_OUTLAYS", "FOMC_STATEMENT", "FOMC_PRESS_CONFERENCE",
}

class DemoDesignError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DemoDesignError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DemoDesignError(f"JSON root is not an object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DemoDesignError(message)


def bool_path(payload: Mapping[str, Any], *keys: str) -> bool:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            return False
        value = value[key]
    return value is True


def resolve(root: Path, relative: str) -> Path:
    path = Path(relative).expanduser()
    return path if path.is_absolute() else root / path


def newest_existing(root: Path, candidates: Sequence[str]) -> Path:
    paths = [resolve(root, item) for item in candidates]
    existing = [p for p in paths if p.is_file()]
    if not existing:
        raise DemoDesignError(f"none of the required files exist: {[str(p) for p in paths]}")
    return max(existing, key=lambda p: p.stat().st_mtime_ns)


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def identify_h1_timestamp_column(conn: sqlite3.Connection, table: str) -> tuple[str, str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    columns = [str(row[1]) for row in rows]
    for name in ("timestamp", "timestamp_ms", "utc_time", "time_utc", "dt"):
        if name in columns:
            sample = conn.execute(f'SELECT "{name}" FROM "{table}" WHERE "{name}" IS NOT NULL LIMIT 1').fetchone()
            if sample is None:
                return name, "text"
            val = sample[0]
            if isinstance(val, (int, float)):
                return name, "milliseconds" if abs(float(val)) >= 1e11 else "seconds"
            return name, "text"
    raise DemoDesignError(f"no timestamp column found in {table}; columns={columns}")


def latest_h1_utc(db_path: Path, table: str) -> datetime:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(table in tables, f"aligned H1 table missing: {table}")
        col, storage = identify_h1_timestamp_column(conn, table)
        row = conn.execute(f'SELECT MAX("{col}") FROM "{table}"').fetchone()
        require(row is not None and row[0] is not None, f"aligned H1 table is empty: {table}")
        value = row[0]
        if storage == "milliseconds":
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        if storage == "seconds":
            return datetime.fromtimestamp(float(value), tz=UTC)
        return parse_time(value)
    finally:
        conn.close()


def read_event_calendar(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(bool(rows), f"official event CSV is empty: {path}")
    required = {"event_time_utc", "source", "category", "blackout_before_minutes", "blackout_after_minutes"}
    missing_columns = sorted(required - set(rows[0]))
    require(not missing_columns, f"official event CSV missing columns: {missing_columns}")
    parsed: list[datetime] = []
    categories: set[str] = set()
    for index, row in enumerate(rows, start=2):
        try:
            parsed.append(parse_time(row.get("event_time_utc")))
        except Exception as exc:
            raise DemoDesignError(f"bad event timestamp at CSV row {index}: {exc}") from exc
        categories.add(str(row.get("category") or "").strip())
        for key in ("blackout_before_minutes", "blackout_after_minutes"):
            try:
                require(float(row.get(key) or 0) >= 0, f"negative {key} at row {index}")
            except ValueError as exc:
                raise DemoDesignError(f"non-numeric {key} at row {index}") from exc
    return {
        "rows": len(rows),
        "minimum_event_utc": iso_utc(min(parsed)),
        "maximum_event_utc": iso_utc(max(parsed)),
        "maximum_event_dt": max(parsed),
        "categories": sorted(categories),
        "missing_required_categories": sorted(REQUIRED_EVENT_CATEGORIES - categories),
    }


def core_design_checks(root: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    paths = {
        "replay": resolve(root, str(config["historical_replay_summary"])),
        "event": resolve(root, str(config["historical_event_context_summary"])),
        "controlled_summary": resolve(root, str(config["controlled_paper_summary"])),
        "controlled_preflight": resolve(root, str(config["controlled_paper_preflight"])),
        "controlled_config": resolve(root, str(config["controlled_paper_config"])),
        "intent_schema": resolve(root, str(config["intent_schema"])),
    }
    for name, path in paths.items():
        require(path.is_file(), f"required {name} file missing: {path}")

    replay = load_json(paths["replay"])
    event = load_json(paths["event"])
    controlled = load_json(paths["controlled_summary"])
    preflight = load_json(paths["controlled_preflight"])
    controlled_config = load_json(paths["controlled_config"])

    checks: dict[str, Any] = {}
    checks["replay_program"] = replay.get("program") == REPLAY_PROGRAM
    checks["replay_decision"] = replay.get("decision") == REPLAY_DECISION
    checks["replay_pass"] = replay.get("pass") is True
    checks["replay_demo_design_allowed"] = replay.get("demo_design_allowed") is True
    checks["replay_no_forward_wait"] = replay.get("forward_wait_required_for_replay") is False
    checks["replay_demo_order_forbidden"] = replay.get("demo_order_allowed") is False
    checks["replay_live_order_forbidden"] = replay.get("live_order_allowed") is False
    checks["replay_broker_order_forbidden"] = replay.get("broker_order_allowed") is False
    checks["replay_demo_gate"] = bool_path(replay, "demo_design_gate", "pass")
    checks["replay_forward_policy_parity"] = bool_path(replay, "current_forward_policy_parity", "pass")
    checks["replay_event_coverage"] = bool_path(replay, "event_evidence", "coverage_complete")

    checks["event_program"] = event.get("program") == EVENT_PROGRAM
    checks["event_decision"] = event.get("decision") == EVENT_DECISION
    checks["event_pass"] = event.get("pass") is True
    checks["event_core_coverage"] = event.get("core_coverage_complete") is True
    checks["event_146_entries"] = int(event.get("evaluated_entry_rows") or 0) == 146
    checks["event_scope_bounded"] = event.get("scope") == "SCHEDULED_USD_CORE_BLACKOUT_ONLY_NOT_EVENT_SURPRISE"
    checks["event_surprise_not_claimed"] = event.get("event_surprise_layer_complete") is False
    checks["event_no_direct_network"] = event.get("network_access_attempted") is False
    checks["event_summary_hash_link"] = (
        sha256_file(paths["event"]) == str(replay.get("historical_event_context", {}).get("summary_sha256") or "")
    )

    checks["controlled_program"] = controlled.get("program") == CONTROLLED_PROGRAM
    checks["controlled_direction_policy"] = controlled.get("direction_policy") == "BIDIRECTIONAL_PROBABILITY_TAILS"
    checks["controlled_side_source"] = controlled.get("side_source") == "PROBABILITY_TAILS_ONLY"
    checks["controlled_replay_parity"] = controlled.get("historical_replay_forward_direction_parity") is True
    checks["controlled_paper_only"] = controlled.get("paper_log_only") is True
    checks["controlled_orders_forbidden"] = all(controlled.get(key) is False for key in (
        "broker_order_allowed", "demo_order_allowed", "live_order_allowed"
    ))

    checks["controlled_preflight_program"] = preflight.get("program") == CONTROLLED_PROGRAM
    checks["controlled_preflight_decision"] = preflight.get("decision") == PREFLIGHT_DECISION
    checks["controlled_preflight_pass"] = preflight.get("pass") is True
    checks["controlled_preflight_orders_forbidden"] = all(preflight.get(key) is False for key in (
        "broker_order_allowed", "demo_order_allowed", "live_order_allowed"
    ))
    checks["controlled_preflight_replay_pass"] = preflight.get("checks", {}).get("historical_replay_pass") is True
    checks["controlled_preflight_event_source_configured"] = (
        "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"
        in controlled_config.get("event_guard", {}).get("csv_candidates", [])
    )

    failed = sorted(key for key, value in checks.items() if value is not True)
    require(not failed, f"bounded demo design evidence failed checks: {failed}")

    locked = replay.get("locked_contract") or {}
    required_locked = (
        "maximum_notional_to_equity", "maximum_concurrent_positions", "daily_new_positions_cap",
        "weekly_loss_pause_equity_pct", "hard_drawdown_kill_switch_equity_pct",
        "observed_entry_spread_guard_bps", "entry_offset_h1_rows", "exit_offset_h1_rows",
        "lower_probability_threshold", "upper_probability_threshold",
    )
    missing_locked = [key for key in required_locked if key not in locked]
    require(not missing_locked, f"replay locked contract missing: {missing_locked}")

    design_cfg = config.get("demo_design", {})
    fraction = float(design_cfg.get("initial_exposure_fraction_of_validated_ceiling", 0.25))
    require(0 < fraction <= 1, "initial exposure fraction must be in (0,1]")
    max_notional = float(locked["maximum_notional_to_equity"])
    initial_notional = max_notional * fraction

    design = {
        "schema_version": "XAUUSD_BOUNDED_DEMO_DESIGN_CONTRACT_V1",
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": "PASS_BOUNDED_DEMO_DESIGN_NO_ORDER_PATH",
        "pass": True,
        "mode": "DESIGN_ONLY_NO_BROKER_OR_ORDER_ADAPTER",
        "broker_api_present": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "explicit_arming_required_later": True,
        "signal_contract": {
            "candidate": str(controlled.get("candidate") or "logistic__direction_24h"),
            "side_source": "PROBABILITY_TAILS_ONLY",
            "long": f"probability_up >= {float(locked['upper_probability_threshold'])}",
            "short": f"probability_up <= {float(locked['lower_probability_threshold'])}",
            "neutral_band_no_order": True,
            "entry_offset_h1_rows": int(locked["entry_offset_h1_rows"]),
            "exit_offset_h1_rows": int(locked["exit_offset_h1_rows"]),
            "entry": f"open of aligned H1 row i+{int(locked['entry_offset_h1_rows'])}",
            "exit": f"close of aligned H1 row i+{int(locked['exit_offset_h1_rows'])}",
        },
        "risk_contract": {
            "validated_maximum_notional_to_equity": max_notional,
            "initial_demo_notional_to_equity": initial_notional,
            "initial_exposure_fraction_of_validated_ceiling": fraction,
            "maximum_concurrent_positions": int(locked["maximum_concurrent_positions"]),
            "daily_new_positions_cap": int(locked["daily_new_positions_cap"]),
            "weekly_loss_pause_equity_pct": float(locked["weekly_loss_pause_equity_pct"]),
            "hard_drawdown_kill_switch_equity_pct": float(locked["hard_drawdown_kill_switch_equity_pct"]),
            "observed_entry_spread_guard_bps": float(locked["observed_entry_spread_guard_bps"]),
        },
        "event_contract": {
            "source": "STAGE115_OFFICIAL_CORE_EVENT_TIMESTAMPS",
            "csv": str(resolve(root, str(config["official_event_csv"]))),
            "blackout_before_minutes": float(event.get("blackout_before_minutes")),
            "blackout_after_minutes": float(event.get("blackout_after_minutes")),
            "scheduled_core_coverage_complete": True,
            "event_surprise_layer_required": False,
            "event_surprise_layer_complete": False,
        },
        "qualification_contract": {
            "purpose": str(design_cfg.get("qualification_purpose")),
            "maximum_calendar_days": int(design_cfg.get("qualification_max_calendar_days", 30)),
            "maximum_resolved_positions": int(design_cfg.get("qualification_max_resolved_positions", 10)),
            "stop_when_either_bound_is_reached": True,
            "model_reselection_allowed": False,
            "threshold_tuning_allowed": False,
            "performance_is_not_a_demo_implementation_gate": True,
            "operational_failures_are_blocking": True,
        },
        "validated_historical_readout": {
            "strict_resolved_positions": int(replay["commercial_reference_strict_event_replay"]["resolved_positions"]),
            "strict_profit_factor": float(replay["commercial_reference_strict_event_replay"]["normal_profit_factor"]),
            "strict_normal_mean_bps": float(replay["commercial_reference_strict_event_replay"]["normal_mean_bps"]),
            "strict_max_drawdown_pct": float(replay["commercial_reference_strict_event_replay"]["max_drawdown_pct"]),
            "event_blackout_blocked_signals": int(replay["commercial_reference_strict_event_replay"]["blocked_reasons"].get("EVENT_BLACKOUT_ACTIVE", 0)),
        },
        "source_hashes": {
            "historical_replay_summary": sha256_file(paths["replay"]),
            "historical_event_context_summary": sha256_file(paths["event"]),
            "controlled_paper_summary": sha256_file(paths["controlled_summary"]),
            "controlled_paper_preflight": sha256_file(paths["controlled_preflight"]),
            "controlled_paper_config": sha256_file(paths["controlled_config"]),
            "intent_schema": sha256_file(paths["intent_schema"]),
        },
        "checks": checks,
        "required_next_action": "RUN_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_THEN_IMPLEMENT_MT5_DEMO_BRIDGE_DISABLED_BY_DEFAULT",
    }
    return checks, paths, design


def build_design(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    _, _, design = core_design_checks(root, config)
    report_dir = resolve(root, str(config.get("report_dir", "reports/xauusd_bounded_demo_design")))
    write_json(report_dir / "bounded_demo_design_contract.json", design)
    summary = dict(design)
    summary["outputs"] = {
        "design_contract": str(report_dir / "bounded_demo_design_contract.json"),
        "summary": str(report_dir / "bounded_demo_design_summary.json"),
    }
    write_json(report_dir / "bounded_demo_design_summary.json", summary)
    return summary


def build_preflight(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    _, paths, design = core_design_checks(root, config)
    event_summary = load_json(paths["event"])
    event_csv = resolve(root, str(config["official_event_csv"]))
    aligned_db = resolve(root, str(config["aligned_db"]))
    require(event_csv.is_file(), f"official event CSV missing: {event_csv}")
    require(aligned_db.is_file(), f"aligned database missing: {aligned_db}")
    require(sha256_file(event_csv) == str(event_summary.get("source_official_events_csv_sha256")),
            "official event CSV hash differs from the passed event-context summary")
    calendar = read_event_calendar(event_csv)
    require(not calendar["missing_required_categories"],
            f"official event CSV missing required categories: {calendar['missing_required_categories']}")
    latest_h1 = latest_h1_utc(aligned_db, str(config.get("aligned_h1_table", "amarkets_h1_direct_utc")))
    exit_rows = int(design["signal_contract"]["exit_offset_h1_rows"])
    required_through = latest_h1.timestamp() + exit_rows * 3600.0
    horizon_ok = calendar["maximum_event_dt"].timestamp() >= required_through
    require(horizon_ok, (
        f"official event calendar does not cover the full exit horizon: "
        f"latest_h1={iso_utc(latest_h1)} required_through={iso_utc(datetime.fromtimestamp(required_through, tz=UTC))} "
        f"calendar_max={calendar['maximum_event_utc']}"
    ))

    risk_path = newest_existing(root, list(config.get("commercial_risk_contract_candidates", [])))
    commercial_summary_path = newest_existing(root, list(config.get("commercial_summary_candidates", [])))
    risk = load_json(risk_path)
    commercial_summary = load_json(commercial_summary_path)
    controlled_summary = load_json(paths["controlled_summary"])
    replay_summary = load_json(paths["replay"])
    hard = design["risk_contract"]

    # The Commercial Closure risk contract owns sizing, concentration and loss limits.
    # It does not own the observed-spread guard in the real artifact. That guard is
    # sourced from commercial_closure_summary.observed_spread_p95_bps, then frozen in
    # Replay V7 and the controlled-paper runtime contract.
    aliases = {
        "maximum_notional_to_equity": hard["validated_maximum_notional_to_equity"],
        "maximum_concurrent_positions": hard["maximum_concurrent_positions"],
        "daily_new_positions_cap": hard["daily_new_positions_cap"],
        "weekly_loss_pause_equity_pct": hard["weekly_loss_pause_equity_pct"],
        "hard_drawdown_kill_switch_equity_pct": hard["hard_drawdown_kill_switch_equity_pct"],
    }
    risk_checks: dict[str, bool] = {}
    for key, expected in aliases.items():
        actual = risk.get(key)
        risk_checks[key] = actual is not None and math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-10)
    risk_checks["paper_only"] = risk.get("paper_only") is True
    risk_checks["demo_forbidden"] = risk.get("demo_allowed") is False
    risk_checks["live_forbidden"] = risk.get("live_allowed") is False

    embedded_risk = commercial_summary.get("risk_contract")
    require(isinstance(embedded_risk, Mapping), "commercial summary risk_contract is missing")
    embedded_risk_checks: dict[str, bool] = {}
    for key in (*aliases.keys(), "paper_only", "demo_allowed", "live_allowed"):
        file_value = risk.get(key)
        embedded_value = embedded_risk.get(key)
        if isinstance(file_value, bool) or isinstance(embedded_value, bool):
            embedded_risk_checks[key] = file_value is embedded_value
        elif file_value is None or embedded_value is None:
            embedded_risk_checks[key] = False
        else:
            embedded_risk_checks[key] = math.isclose(float(file_value), float(embedded_value), rel_tol=0, abs_tol=1e-10)

    expected_spread_guard = float(hard["observed_entry_spread_guard_bps"])
    commercial_spread = commercial_summary.get("observed_spread_p95_bps")
    controlled_spread = (controlled_summary.get("risk_contract") or {}).get("observed_entry_spread_guard_bps")
    replay_spread = (replay_summary.get("locked_contract") or {}).get("observed_entry_spread_guard_bps")
    optional_risk_spread = risk.get("observed_entry_spread_guard_bps")
    spread_guard_checks = {
        "commercial_summary_observed_spread_p95_bps": commercial_spread is not None and math.isclose(float(commercial_spread), expected_spread_guard, rel_tol=0, abs_tol=1e-10),
        "controlled_paper_observed_entry_spread_guard_bps": controlled_spread is not None and math.isclose(float(controlled_spread), expected_spread_guard, rel_tol=0, abs_tol=1e-10),
        "replay_locked_observed_entry_spread_guard_bps": replay_spread is not None and math.isclose(float(replay_spread), expected_spread_guard, rel_tol=0, abs_tol=1e-10),
        "commercial_risk_contract_optional_field": optional_risk_spread is None or math.isclose(float(optional_risk_spread), expected_spread_guard, rel_tol=0, abs_tol=1e-10),
    }

    failed_risk = sorted(key for key, passed in risk_checks.items() if not passed)
    failed_embedded = sorted(key for key, passed in embedded_risk_checks.items() if not passed)
    failed_spread = sorted(key for key, passed in spread_guard_checks.items() if not passed)
    require(not failed_risk, f"commercial risk contract mismatch: {failed_risk}")
    require(not failed_embedded, f"commercial risk file/summary mismatch: {failed_embedded}")
    require(not failed_spread, f"spread guard provenance mismatch: {failed_spread}")

    preflight = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": "PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH",
        "pass": True,
        "broker_api_present": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "design_contract": design,
        "operational_checks": {
            "official_event_csv_hash": True,
            "official_event_required_categories": True,
            "official_event_calendar_through_exit_horizon": True,
            "aligned_h1_latest_utc": iso_utc(latest_h1),
            "required_calendar_through_utc": iso_utc(datetime.fromtimestamp(required_through, tz=UTC)),
            "calendar": {key: value for key, value in calendar.items() if key != "maximum_event_dt"},
            "commercial_risk_contract": risk_checks,
            "commercial_risk_file_summary_parity": embedded_risk_checks,
            "spread_guard_provenance": {
                "checks": spread_guard_checks,
                "value_bps": expected_spread_guard,
                "authoritative_source": "commercial_closure_summary.observed_spread_p95_bps",
                "commercial_risk_contract_field_present": optional_risk_spread is not None,
                "commercial_risk_contract_decision": risk.get("decision"),
                "commercial_risk_contract_decision_used_for_authorization": False,
                "authorization_source": REPLAY_DECISION,
            },
        },
        "source_hashes": {
            **design["source_hashes"],
            "official_event_csv": sha256_file(event_csv),
            "aligned_db": sha256_file(aligned_db),
            "commercial_risk_contract": sha256_file(risk_path),
            "commercial_closure_summary": sha256_file(commercial_summary_path),
        },
        "required_next_action": "IMPLEMENT_MT5_DEMO_BRIDGE_WITH_DEFAULT_DISABLED_ARMING_AND_FILE_BASED_INTENTS",
    }
    report_dir = resolve(root, str(config.get("report_dir", "reports/xauusd_bounded_demo_design")))
    write_json(report_dir / "bounded_demo_preflight.json", preflight)
    if not (report_dir / "bounded_demo_design_contract.json").is_file():
        write_json(report_dir / "bounded_demo_design_contract.json", design)
    return preflight


def load_config(root: Path, value: str) -> dict[str, Any]:
    path = resolve(root, value)
    return load_json(path)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("design", "preflight"), nargs="?", default="design")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="config/xauusd_bounded_demo_design.json")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports/xauusd_bounded_demo_design"
    try:
        config = load_config(root, args.config)
        result = build_design(root, config) if args.command == "design" else build_preflight(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        failure = report_dir / "bounded_demo_failure.json"
        if failure.exists():
            failure.unlink()
        return 0
    except Exception as exc:
        payload = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(),
            "decision": "BOUNDED_DEMO_DESIGN_FAIL_CLOSED",
            "pass": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json(report_dir / "bounded_demo_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
