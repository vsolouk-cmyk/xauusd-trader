#!/usr/bin/env python3
"""File-based XAUUSD bounded-demo bridge. Python never sends broker orders."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_MT5_BOUNDED_DEMO_BRIDGE_V1_1_VOLUME_DIAGNOSTIC_LOGGING"
BOUNDED_PROGRAM = "XAUUSD_BOUNDED_DEMO_DESIGN_V1_1_RISK_SOURCE_PROVENANCE_REPAIR_NO_ORDER"
BOUNDED_DECISION = "PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH"
CONTROLLED_PROGRAM = "XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY"
CONTROLLED_PREFLIGHT_DECISION = "PASS_CONTROLLED_PAPER_PREFLIGHT"
CANDIDATE_SCHEMA = "XAUUSD_DEMO_CANDIDATE_V1"
EA_PROGRAM_VERSION = "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR"


class BridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class H1Contract:
    signal_epoch: int
    entry_epoch: int
    projected_exit_epoch: int
    exit_after_h1_bars: int


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise BridgeError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BridgeError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeError(f"JSON root is not an object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BridgeError(message)


def resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def load_config(root: Path, config_path: str) -> dict[str, Any]:
    return load_json(resolve(root, config_path))


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def bounded_evidence(root: Path, config: Mapping[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    path = resolve(root, str(config["bounded_demo_preflight"]))
    require(path.is_file(), f"bounded-demo preflight missing: {path}")
    payload = load_json(path)
    checks = {
        "program": payload.get("program") == BOUNDED_PROGRAM,
        "decision": payload.get("decision") == BOUNDED_DECISION,
        "pass": payload.get("pass") is True,
        "broker_order_forbidden": payload.get("broker_order_allowed") is False,
        "demo_order_forbidden": payload.get("demo_order_allowed") is False,
        "live_order_forbidden": payload.get("live_order_allowed") is False,
        "next_action": payload.get("required_next_action") == (
            "IMPLEMENT_MT5_DEMO_BRIDGE_WITH_DEFAULT_DISABLED_ARMING_AND_FILE_BASED_INTENTS"
        ),
        "calendar_horizon": payload.get("operational_checks", {}).get(
            "official_event_calendar_through_exit_horizon"
        ) is True,
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    require(not failed, f"bounded-demo evidence failed checks: {failed}")
    return path, payload, checks


def source_scan(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    return {
        "default_armed_false": ("InpArmed" in text and "= false;" in text),
        "demo_mode_required": "ACCOUNT_TRADE_MODE_DEMO" in text,
        "allowed_login_required": "InpAllowedDemoLogin" in text,
        "arming_permit_required": "ARMING_PERMIT_MISSING" in text and "XAUUSD_DEMO_ARMING_PERMIT_V1" in text,
        "live_fallback_absent": "LIVE_ACCOUNT_FALLBACK" not in text,
        "spread_guard_present": "SpreadBps" in text and "spread_guard_bps" in text,
        "minimum_volume_fail_closed": "TARGET_BELOW_MINIMUM_VOLUME" in text,
        "experts_log_present": "Print(" in text and "volume_contract_decision" in text,
        "runtime_file_log_present": "bridge_runtime.log" in text,
        "chart_status_present": "Comment(" in text,
        "idempotent_receipt": "ReceiptExists" in text,
        "hard_kill_present": "HARD_DRAWDOWN_KILL" in text,
        "daily_cap_present": "DAILY_NEW_POSITION_CAP" in text,
        "qualification_bound_present": "QUALIFICATION_BOUND_REACHED" in text,
        "qualification_probe_label": "QUALIFICATION_PROBE_NOT_ALPHA" in text,
        "qualification_probe_permit": "XAUUSD_DEMO_QUALIFICATION_PROBE_PERMIT_V1" in text,
        "qualification_probe_journal": "qualification_probe_journal.tsv" in text,
        "qualification_probe_lockdown": "QUALIFICATION_PROBE_COMPLETE_MANUAL_DISARM_REQUIRED" in text,
        "no_webrequest": "WebRequest(" not in text,
    }


def build_design(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    bounded_path, bounded, bounded_checks = bounded_evidence(root, config)
    ea_source = resolve(root, str(config["ea_source"]))
    schema = resolve(root, str(config["candidate_schema"]))
    require(ea_source.is_file(), f"EA source missing: {ea_source}")
    require(schema.is_file(), f"candidate schema missing: {schema}")
    scan = source_scan(ea_source)
    failed_scan = sorted(key for key, passed in scan.items() if not passed)
    require(not failed_scan, f"EA safety source checks failed: {failed_scan}")

    arming = config.get("arming") or {}
    require(arming.get("enabled") is False, "bridge config must remain disabled by default")
    require(int(arming.get("allowed_demo_login") or 0) == 0, "allowed demo login must be zero before explicit arming")
    require(arming.get("require_demo_account") is True, "demo account requirement must be true")
    require(arming.get("live_account_fallback_allowed") is False, "live account fallback must be false")

    design_contract = bounded["design_contract"]
    risk = design_contract["risk_contract"]
    qualification = design_contract["qualification_contract"]
    result = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": "PASS_MT5_DEMO_BRIDGE_DESIGN_DISABLED_NO_ORDER",
        "pass": True,
        "mode": "FILE_BASED_DEMO_ONLY_DISABLED_BY_DEFAULT",
        "python_broker_api_present": False,
        "python_broker_order_allowed": False,
        "bridge_armed": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "account_contract": {
            "required_trade_mode": "ACCOUNT_TRADE_MODE_DEMO",
            "allowed_demo_login": 0,
            "explicit_nonzero_login_required_before_arming": True,
            "live_account_fallback_allowed": False,
            "expected_symbol": str(config["expected_symbol"]),
            "magic_number": int(config["magic_number"]),
        },
        "risk_contract": {
            "initial_demo_notional_to_equity": float(risk["initial_demo_notional_to_equity"]),
            "validated_maximum_notional_to_equity": float(risk["validated_maximum_notional_to_equity"]),
            "spread_guard_bps": float(risk["observed_entry_spread_guard_bps"]),
            "maximum_concurrent_positions": int(risk["maximum_concurrent_positions"]),
            "daily_new_positions_cap": int(risk["daily_new_positions_cap"]),
            "weekly_loss_pause_equity_pct": float(risk["weekly_loss_pause_equity_pct"]),
            "hard_drawdown_kill_switch_equity_pct": float(risk["hard_drawdown_kill_switch_equity_pct"]),
            "minimum_lot_may_not_increase_target_risk": True,
        },
        "qualification_contract": dict(qualification),
        "candidate_contract": {
            "schema_version": CANDIDATE_SCHEMA,
            "event_guard_must_pass_before_file_emission": True,
            "live_spread_guard_must_pass_inside_mt5_before_order": True,
            "target_entry": "OPEN_OF_ALIGNED_H1_ROW_I_PLUS_1",
            "target_exit": "CLOSE_OF_ALIGNED_H1_ROW_I_PLUS_24",
            "idempotent_intent_id": True,
            "python_order_authorized": False,
        },
        "paths": {
            "mt5_files_dir": str(Path(str(config["mt5_files_dir"])).expanduser()),
            "mt5_experts_dir": str(Path(str(config["mt5_experts_dir"])).expanduser()),
            "mt5_bridge_subdir": str(config["mt5_bridge_subdir"]),
            "ea_source": str(ea_source),
        },
        "checks": {
            "bounded_evidence": bounded_checks,
            "ea_source_safety": scan,
        },
        "source_hashes": {
            "bounded_demo_preflight": sha256_file(bounded_path),
            "candidate_schema": sha256_file(schema),
            "ea_source": sha256_file(ea_source),
        },
        "required_next_action": "COPY_AND_COMPILE_EA_ATTACH_DISABLED_THEN_RUN_RUNTIME_PREFLIGHT",
    }
    report_dir = resolve(root, str(config["report_dir"]))
    write_json(report_dir / "mt5_demo_bridge_design.json", result)
    return result


def build_install_preflight(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    design = build_design(root, config)
    mt5_files = Path(str(config["mt5_files_dir"])).expanduser()
    mt5_experts = Path(str(config["mt5_experts_dir"])).expanduser()
    checks = {
        "mt5_files_dir_exists": mt5_files.is_dir(),
        "mt5_experts_dir_exists": mt5_experts.is_dir(),
        "bridge_config_disabled": config.get("arming", {}).get("enabled") is False,
        "allowed_login_unset": int(config.get("arming", {}).get("allowed_demo_login") or 0) == 0,
        "python_broker_path_absent": design.get("python_broker_api_present") is False,
        "ea_default_disabled": design["checks"]["ea_source_safety"]["default_armed_false"] is True,
    }
    # Directory absence is not a contract failure in CI/build environments. It is explicit in the result.
    local_ready = checks["mt5_files_dir_exists"] and checks["mt5_experts_dir_exists"]
    result = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": (
            "PASS_MT5_DEMO_BRIDGE_INSTALL_PREFLIGHT_DISABLED_NO_ORDER"
            if local_ready else
            "PASS_MT5_DEMO_BRIDGE_DESIGN_PREFLIGHT_MT5_PATHS_NOT_PRESENT_NO_ORDER"
        ),
        "pass": True,
        "local_mt5_paths_ready": local_ready,
        "bridge_armed": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "checks": checks,
        "design": design,
        "required_next_action": "COPY_EA_TO_MT5_COMPILE_ATTACH_WITH_INP_ARMED_FALSE",
    }
    report_dir = resolve(root, str(config["report_dir"]))
    write_json(report_dir / "mt5_demo_bridge_install_preflight.json", result)
    return result


def timestamp_column(conn: sqlite3.Connection, table: str) -> tuple[str, str]:
    cols = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
    for name in ("timestamp", "timestamp_ms", "utc_time", "time_utc", "dt"):
        if name in cols:
            sample = conn.execute(f'SELECT "{name}" FROM "{table}" WHERE "{name}" IS NOT NULL LIMIT 1').fetchone()
            if sample is None:
                return name, "text"
            value = sample[0]
            if isinstance(value, (int, float)):
                return name, "milliseconds" if abs(float(value)) >= 1e11 else "seconds"
            return name, "text"
    raise BridgeError(f"no timestamp column found in {table}: {cols}")


def to_epoch(value: Any, storage: str) -> int:
    if storage == "milliseconds":
        return int(float(value) / 1000.0)
    if storage == "seconds":
        return int(float(value))
    return int(parse_time(value).timestamp())


def project_trading_h1_rows(start_epoch: int, row_count: int, observed_epochs: Sequence[int]) -> int:
    require(row_count >= 0, "row_count must be non-negative")
    if row_count == 0:
        return start_epoch
    # Learn normal tradable UTC weekday/hour slots from the latest observed months.
    tail = list(observed_epochs[-24 * 120:])
    slots = {(datetime.fromtimestamp(epoch, tz=UTC).weekday(), datetime.fromtimestamp(epoch, tz=UTC).hour) for epoch in tail}
    require(bool(slots), "cannot infer H1 trading slots")
    current = datetime.fromtimestamp(start_epoch, tz=UTC)
    advanced = 0
    for _ in range(24 * 14):
        current += timedelta(hours=1)
        if (current.weekday(), current.hour) in slots:
            advanced += 1
            if advanced == row_count:
                return int(current.timestamp())
    raise BridgeError(f"cannot project {row_count} future H1 rows from {iso_utc(datetime.fromtimestamp(start_epoch, tz=UTC))}")


def h1_contract(db_path: Path, table: str, signal_epoch: int, entry_offset: int, exit_offset: int) -> H1Contract:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require(table in names, f"aligned H1 table missing: {table}")
        col, storage = timestamp_column(conn, table)
        rows = conn.execute(f'SELECT "{col}" FROM "{table}" ORDER BY "{col}"').fetchall()
        epochs = [to_epoch(row[0], storage) for row in rows]
        try:
            index = epochs.index(signal_epoch)
        except ValueError as exc:
            raise BridgeError(f"signal H1 timestamp missing from aligned table: {signal_epoch}") from exc
        entry_epoch = (
            epochs[index + entry_offset]
            if index + entry_offset < len(epochs)
            else project_trading_h1_rows(signal_epoch, entry_offset, epochs)
        )
        projected_exit_epoch = (
            epochs[index + exit_offset]
            if index + exit_offset < len(epochs)
            else project_trading_h1_rows(signal_epoch, exit_offset, epochs)
        )
        return H1Contract(signal_epoch, entry_epoch, projected_exit_epoch, exit_offset)
    finally:
        conn.close()


def latest_waiting_signal(ledger_path: Path) -> dict[str, Any] | None:
    uri = f"file:{ledger_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require({"positions", "signals"}.issubset(tables), "controlled-paper ledger lacks positions/signals tables")
        row = conn.execute(
            """
            SELECT p.signal_key, p.signal_timestamp_ms, p.signal_utc, p.side, p.side_source,
                   p.status, s.probability_up
            FROM positions p
            JOIN signals s ON s.signal_key=p.signal_key
            WHERE p.status='WAIT_ENTRY'
              AND p.side IN ('LONG','SHORT')
              AND NOT EXISTS (
                  SELECT 1 FROM blocked_signals b WHERE b.signal_key=p.signal_key
              )
            ORDER BY p.signal_timestamp_ms DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def event_guard(csv_path: Path, target: datetime) -> tuple[bool, str, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            event_time = parse_time(row.get("event_time_utc"))
            before = float(row.get("blackout_before_minutes") or 0)
            after = float(row.get("blackout_after_minutes") or 0)
            if event_time - timedelta(minutes=before) <= target <= event_time + timedelta(minutes=after):
                matches.append({
                    "event_time_utc": iso_utc(event_time),
                    "source": row.get("source"),
                    "category": row.get("category"),
                    "title": row.get("title"),
                })
    return (not matches, "EVENT_CONTEXT_PRESENT_NO_BLOCK" if not matches else "EVENT_BLACKOUT_ACTIVE", matches)


def candidate_to_kv(payload: Mapping[str, Any]) -> str:
    order = [
        "schema_version", "intent_id", "created_utc", "created_epoch", "expires_utc", "expires_epoch",
        "symbol", "side", "probability_up", "signal_utc", "signal_epoch", "target_entry_utc",
        "target_entry_epoch", "target_exit_utc", "target_exit_epoch", "entry_semantics", "exit_semantics", "exit_after_h1_bars", "notional_to_equity",
        "event_guard_pass", "event_guard_reason", "spread_guard_bps", "bounded_preflight_sha256",
        "magic_number", "execution_mode", "requires_mt5_runtime_authorization", "python_order_authorized",
    ]
    return "\n".join(f"{key}={payload[key]}" for key in order) + "\n"


def clear_candidate_files(root: Path, config: Mapping[str, Any]) -> None:
    paths = [
        resolve(root, str(config["outbox_dir"])) / "demo_candidate.json",
        resolve(root, str(config["outbox_dir"])) / "demo_candidate.txt",
        Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"]) / "demo_candidate.txt",
    ]
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            raise BridgeError(f"cannot remove stale candidate {path}: {exc}") from exc

def emit_candidate(root: Path, config: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    bounded_path, bounded, _ = bounded_evidence(root, config)
    controlled_summary_path = resolve(root, str(config["controlled_paper_summary"]))
    controlled_preflight_path = resolve(root, str(config["controlled_paper_preflight"]))
    ledger_path = resolve(root, str(config["controlled_paper_ledger"]))
    aligned_db = resolve(root, str(config["aligned_db"]))
    event_csv = resolve(root, str(config["official_event_csv"]))
    for name, path in {
        "controlled summary": controlled_summary_path,
        "controlled preflight": controlled_preflight_path,
        "controlled ledger": ledger_path,
        "aligned database": aligned_db,
        "official event CSV": event_csv,
    }.items():
        require(path.is_file(), f"{name} missing: {path}")

    controlled = load_json(controlled_summary_path)
    preflight = load_json(controlled_preflight_path)
    require(controlled.get("program") == CONTROLLED_PROGRAM, "controlled-paper program mismatch")
    require(controlled.get("direction_policy") == "BIDIRECTIONAL_PROBABILITY_TAILS", "controlled-paper direction mismatch")
    require(controlled.get("paper_log_only") is True, "controlled-paper must remain paper-only")
    require(preflight.get("program") == CONTROLLED_PROGRAM, "controlled-paper preflight program mismatch")
    require(preflight.get("decision") == CONTROLLED_PREFLIGHT_DECISION and preflight.get("pass") is True,
            "controlled-paper preflight is not passed")
    require(all(controlled.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
            "controlled-paper order boundary is not closed")
    risk_state = controlled.get("risk_state") or {}
    require(risk_state.get("hard_kill_latched") is False, "controlled-paper hard kill is latched")
    require(risk_state.get("weekly_pause_active") is False, "controlled-paper weekly pause is active")

    waiting = latest_waiting_signal(ledger_path)
    report_dir = resolve(root, str(config["report_dir"]))
    if waiting is None:
        clear_candidate_files(root, config)
        result = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(now),
            "decision": "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL",
            "pass": True,
            "candidate_emitted": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "required_next_action": "CONTINUE_NORMAL_SCHEDULE_NO_FORWARD_WAIT_GATE",
        }
        write_json(report_dir / "mt5_demo_bridge_candidate_summary.json", result)
        return result

    signal_epoch = int(waiting["signal_timestamp_ms"]) // 1000
    design = bounded["design_contract"]
    signal_contract = design["signal_contract"]
    h1 = h1_contract(
        aligned_db,
        str(config["aligned_h1_table"]),
        signal_epoch,
        int(signal_contract["entry_offset_h1_rows"]),
        int(signal_contract["exit_offset_h1_rows"]),
    )
    current = (now or utc_now()).astimezone(UTC)
    current_epoch = int(current.timestamp())
    limits = config.get("candidate") or {}
    lead = h1.entry_epoch - current_epoch
    grace = int(limits.get("entry_grace_seconds", 60))
    max_lead = int(limits.get("maximum_lead_seconds", 7200))
    if lead > max_lead:
        clear_candidate_files(root, config)
        result = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(current),
            "decision": "WAIT_FOR_TARGET_ENTRY_WINDOW_NO_CANDIDATE",
            "pass": True,
            "candidate_emitted": False,
            "lead_seconds": lead,
            "maximum_lead_seconds": max_lead,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "required_next_action": "RERUN_BRIDGE_CYCLE_NEAR_TARGET_ENTRY",
        }
        write_json(report_dir / "mt5_demo_bridge_candidate_summary.json", result)
        return result
    if current_epoch > h1.entry_epoch + grace:
        clear_candidate_files(root, config)
        result = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(current),
            "decision": "BLOCK_DEMO_CANDIDATE_STALE_ENTRY_WINDOW",
            "pass": True,
            "candidate_emitted": False,
            "target_entry_epoch": h1.entry_epoch,
            "entry_grace_seconds": grace,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "required_next_action": "NO_ORDER_FOR_STALE_SIGNAL",
        }
        write_json(report_dir / "mt5_demo_bridge_candidate_summary.json", result)
        return result

    target_entry = datetime.fromtimestamp(h1.entry_epoch, tz=UTC)
    event_ok, event_reason, event_matches = event_guard(event_csv, target_entry)
    if not event_ok:
        clear_candidate_files(root, config)
        result = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(current),
            "decision": "BLOCK_MT5_DEMO_CANDIDATE_EVENT_BLACKOUT",
            "pass": True,
            "candidate_emitted": False,
            "event_matches": event_matches,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "required_next_action": "NO_ORDER_FOR_THIS_SIGNAL",
        }
        write_json(report_dir / "mt5_demo_bridge_candidate_summary.json", result)
        return result

    bounded_hash = sha256_file(bounded_path)
    intent_seed = f"{waiting['signal_key']}|{waiting['side']}|{bounded_hash}|{config['magic_number']}"
    digest = hashlib.sha256(intent_seed.encode("utf-8")).hexdigest()
    intent_id = f"XAUUSD_{waiting['signal_key']}_{digest[:12]}"
    expiry_epoch = h1.entry_epoch + grace
    risk = design["risk_contract"]
    payload: dict[str, Any] = {
        "schema_version": CANDIDATE_SCHEMA,
        "intent_id": intent_id,
        "created_utc": iso_utc(current),
        "created_epoch": current_epoch,
        "expires_utc": iso_utc(datetime.fromtimestamp(expiry_epoch, tz=UTC)),
        "expires_epoch": expiry_epoch,
        "symbol": str(config["expected_symbol"]),
        "side": str(waiting["side"]),
        "probability_up": float(waiting["probability_up"]),
        "signal_utc": str(waiting["signal_utc"]),
        "signal_epoch": signal_epoch,
        "target_entry_utc": iso_utc(target_entry),
        "target_entry_epoch": h1.entry_epoch,
        "target_exit_utc": iso_utc(datetime.fromtimestamp(h1.projected_exit_epoch, tz=UTC)),
        "target_exit_epoch": h1.projected_exit_epoch,
        "entry_semantics": "OPEN_OF_ALIGNED_H1_ROW_I_PLUS_1",
        "exit_semantics": "CLOSE_OF_ALIGNED_H1_ROW_I_PLUS_24",
        "exit_after_h1_bars": h1.exit_after_h1_bars,
        "notional_to_equity": float(risk["initial_demo_notional_to_equity"]),
        "event_guard_pass": True,
        "event_guard_reason": event_reason,
        "spread_guard_bps": float(risk["observed_entry_spread_guard_bps"]),
        "bounded_preflight_sha256": bounded_hash,
        "magic_number": int(config["magic_number"]),
        "execution_mode": "DEMO_ONLY",
        "requires_mt5_runtime_authorization": True,
        "python_order_authorized": False,
    }

    outbox = resolve(root, str(config["outbox_dir"]))
    repo_json = outbox / "demo_candidate.json"
    repo_txt = outbox / "demo_candidate.txt"
    write_json(repo_json, payload)
    write_text_atomic(repo_txt, candidate_to_kv(payload))

    mt5_dir = Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])
    mt5_dir.mkdir(parents=True, exist_ok=True)
    mt5_candidate = mt5_dir / "demo_candidate.txt"
    write_text_atomic(mt5_candidate, candidate_to_kv(payload))

    result = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(current),
        "decision": "PASS_DEMO_CANDIDATE_EMITTED_RUNTIME_AUTHORIZATION_REQUIRED",
        "pass": True,
        "candidate_emitted": True,
        "bridge_armed": False,
        "python_order_authorized": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "candidate": payload,
        "outputs": {
            "repo_json": str(repo_json),
            "repo_kv": str(repo_txt),
            "mt5_candidate": str(mt5_candidate),
        },
        "required_next_action": "MT5_EA_RUNTIME_GUARDS_AND_EXPLICIT_ARMING_REQUIRED",
    }
    write_json(report_dir / "mt5_demo_bridge_candidate_summary.json", result)
    return result


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def runtime_preflight(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate disabled runtime connectivity separately from future arming readiness.

    A minimum-lot mismatch is an arming blocker, not an EA installation failure.  It
    remains fail-closed for orders, but the command returns a successful disabled
    runtime diagnosis so the user receives actionable broker/account sizing data.
    """
    mt5_dir = Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])
    heartbeat_path = mt5_dir / "bridge_heartbeat.txt"
    require(heartbeat_path.is_file(), f"MT5 bridge heartbeat missing: {heartbeat_path}")
    heartbeat = read_kv(heartbeat_path)
    design_path = resolve(root, str(config["report_dir"])) / "mt5_demo_bridge_design.json"
    if not design_path.is_file():
        build_design(root, config)
    design = load_json(design_path)
    expected_risk = design["risk_contract"]

    checks = {
        "ea_program": heartbeat.get("program") == EA_PROGRAM_VERSION,
        "heartbeat_status": heartbeat.get("status") == "DISABLED_DEFAULT_NO_ORDER",
        "armed_false": not as_bool(heartbeat.get("armed")),
        "account_mode_demo": heartbeat.get("account_trade_mode") == "DEMO",
        "symbol": heartbeat.get("symbol") == str(config["expected_symbol"]),
        "magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "live_fallback_false": not as_bool(heartbeat.get("live_fallback_allowed")),
        "spread_guard": math.isclose(
            float(heartbeat.get("spread_guard_bps") or -1),
            float(expected_risk["spread_guard_bps"]), rel_tol=0, abs_tol=1e-10,
        ),
        "initial_notional": math.isclose(
            float(heartbeat.get("notional_to_equity") or -1),
            float(expected_risk["initial_demo_notional_to_equity"]), rel_tol=0, abs_tol=1e-10,
        ),
        "validated_maximum_notional": math.isclose(
            float(heartbeat.get("validated_maximum_notional_ratio") or -1),
            float(expected_risk["validated_maximum_notional_to_equity"]), rel_tol=0, abs_tol=1e-10,
        ),
        "minimum_volume_contract_reported": "minimum_volume_ratio" in heartbeat,
        "volume_diagnostics_reported": all(
            key in heartbeat
            for key in (
                "account_equity", "symbol_mid_price", "trade_contract_size",
                "volume_min", "volume_step", "minimum_volume_notional",
                "raw_target_volume", "required_equity_for_validated_ceiling",
                "required_equity_for_initial_target", "volume_contract_decision",
            )
        ),
        "minimum_volume_within_validated_ceiling": as_bool(
            heartbeat.get("minimum_volume_within_validated_ceiling")
        ),
        "target_volume_executable_without_risk_increase": as_bool(
            heartbeat.get("target_volume_executable")
        ),
    }

    runtime_check_names = (
        "ea_program", "heartbeat_status", "armed_false", "account_mode_demo",
        "symbol", "magic", "live_fallback_false", "spread_guard",
        "initial_notional", "validated_maximum_notional",
        "minimum_volume_contract_reported", "volume_diagnostics_reported",
    )
    arming_check_names = (
        "minimum_volume_within_validated_ceiling",
        "target_volume_executable_without_risk_increase",
    )
    runtime_failed = sorted(name for name in runtime_check_names if not checks[name])
    arming_failed = sorted(name for name in arming_check_names if not checks[name])
    runtime_pass = not runtime_failed
    arming_ready = runtime_pass and not arming_failed

    numeric_fields = (
        "account_equity", "symbol_bid", "symbol_ask", "symbol_mid_price",
        "trade_contract_size", "volume_min", "volume_max", "volume_step",
        "minimum_volume_notional", "minimum_volume_ratio", "raw_target_volume",
        "floored_target_volume", "actual_executable_ratio",
        "required_equity_for_validated_ceiling", "required_equity_for_initial_target",
        "equity_multiplier_to_validated_ceiling", "equity_multiplier_to_initial_target",
    )
    volume_diagnostic = {name: _float_or_none(heartbeat.get(name)) for name in numeric_fields}
    volume_diagnostic.update({
        "decision": heartbeat.get("volume_contract_decision", "UNKNOWN"),
        "minimum_volume_within_validated_ceiling": checks["minimum_volume_within_validated_ceiling"],
        "target_volume_executable_without_risk_increase": checks[
            "target_volume_executable_without_risk_increase"
        ],
        "interpretation": (
            "Current symbol/account minimum lot is executable under both the initial and validated risk limits."
            if arming_ready else
            "Bridge installation is healthy and disabled, but arming remains blocked because the broker minimum lot exceeds the locked risk contract."
        ),
    })

    if runtime_failed:
        decision = "MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_FAIL_CLOSED"
        required_next_action = "FIX_MT5_EA_INSTALLATION_ACCOUNT_OR_HEARTBEAT_CONTRACT"
    elif arming_failed:
        decision = "PASS_MT5_DEMO_BRIDGE_RUNTIME_DISABLED_ARMING_BLOCKED_VOLUME_CONTRACT"
        required_next_action = "OPEN_HIGHER_EQUITY_DEMO_OR_USE_LOWER_MINIMUM_VOLUME_SYMBOL_THEN_RERUN"
    else:
        decision = "PASS_MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_DISABLED_NO_ORDER"
        required_next_action = "EXPLICIT_DEMO_LOGIN_BOUND_ARMING_REVIEW"

    result = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": decision,
        "pass": runtime_pass,
        "runtime_installation_pass": runtime_pass,
        "arming_readiness_pass": arming_ready,
        "bridge_armed": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "checks": checks,
        "runtime_failed_checks": runtime_failed,
        "arming_failed_checks": arming_failed,
        "heartbeat": heartbeat,
        "volume_diagnostic": volume_diagnostic,
        "required_next_action": required_next_action,
    }
    report_dir = resolve(root, str(config["report_dir"]))
    write_json(report_dir / "mt5_demo_bridge_runtime_preflight.json", result)
    if runtime_failed:
        raise BridgeError(f"runtime installation preflight failed checks: {runtime_failed}")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("design", "preflight", "emit-candidate", "runtime-preflight"), nargs="?", default="design")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="config/xauusd_mt5_demo_bridge.json")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports/xauusd_mt5_demo_bridge"
    try:
        config = load_config(root, args.config)
        if args.command == "design":
            result = build_design(root, config)
        elif args.command == "preflight":
            result = build_install_preflight(root, config)
        elif args.command == "emit-candidate":
            result = emit_candidate(root, config)
        else:
            result = runtime_preflight(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        failure = report_dir / "mt5_demo_bridge_failure.json"
        if failure.exists():
            failure.unlink()
        return 0
    except Exception as exc:
        payload = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(),
            "decision": "MT5_DEMO_BRIDGE_FAIL_CLOSED",
            "pass": False,
            "bridge_armed": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json(report_dir / "mt5_demo_bridge_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
