#!/usr/bin/env python3
"""One-time, fail-closed MT5 demo qualification probe for XAUUSD.

This operator never calls a broker API. It writes an explicitly labelled candidate
and a short-lived, intent-bound probe permit into the existing MT5 Files bridge.
The MT5 EA remains the only component that can submit or close an order.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

UTC = timezone.utc
PROGRAM = "XAUUSD_MT5_DEMO_QUALIFICATION_PROBE_V1_2_ACCOUNTING_REPAIR"
EA_PROGRAM = "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR"
CANDIDATE_SCHEMA = "XAUUSD_DEMO_CANDIDATE_V1"
CANDIDATE_CLASS = "QUALIFICATION_PROBE_NOT_ALPHA"
PROBE_PERMIT_SCHEMA = "XAUUSD_DEMO_QUALIFICATION_PROBE_PERMIT_V1"
ARMING_PERMIT_SCHEMA = "XAUUSD_DEMO_ARMING_PERMIT_V1"
DEFAULT_CONFIG = "config/xauusd_mt5_demo_bridge.json"
DEFAULT_EXIT_SECONDS = 120
MIN_EXIT_SECONDS = 60
MAX_EXIT_SECONDS = 300
ENTRY_DELAY_SECONDS = 10
ENTRY_GRACE_SECONDS = 60
HEARTBEAT_MAX_AGE_SECONDS = 120


class ProbeError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProbeError(f"cannot read JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not object: {path}")
    return value


def parse_kv(path: Path) -> dict[str, str]:
    require(path.is_file(), f"key/value file missing: {path}")
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def bridge_dir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])


def report_dir(root: Path) -> Path:
    return root / "reports/xauusd_mt5_demo_qualification_probe"


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    require(bool(text), "empty event timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def event_guard(csv_path: Path, target: datetime) -> tuple[bool, list[dict[str, Any]]]:
    require(csv_path.is_file(), f"official event CSV missing: {csv_path}")
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
    return not matches, matches


def market_window_check(now: datetime) -> tuple[bool, str]:
    """Avoid weekend, rollover, and Friday-close risk for a plumbing-only probe."""
    current = now.astimezone(UTC)
    weekday = current.weekday()  # Monday=0
    minute = current.hour * 60 + current.minute
    if weekday >= 5:
        return False, "WEEKEND_BLOCK"
    if weekday <= 3 and 6 * 60 <= minute <= 18 * 60:
        return True, "MON_THU_0600_1800_UTC"
    if weekday == 4 and 6 * 60 <= minute <= 15 * 60:
        return True, "FRI_0600_1500_UTC"
    return False, "ROLLOVER_OR_FRIDAY_CLOSE_BLOCK"


def candidate_to_kv(payload: Mapping[str, Any]) -> str:
    order = [
        "schema_version", "candidate_class", "intent_id", "created_utc", "created_epoch",
        "expires_utc", "expires_epoch", "symbol", "side", "probability_up", "signal_utc",
        "signal_epoch", "target_entry_utc", "target_entry_epoch", "target_exit_utc",
        "target_exit_epoch", "entry_semantics", "exit_semantics", "exit_after_h1_bars",
        "probe_exit_after_seconds", "notional_to_equity", "event_guard_pass",
        "event_guard_reason", "spread_guard_bps", "bounded_preflight_sha256", "magic_number",
        "execution_mode", "requires_mt5_runtime_authorization", "python_order_authorized",
    ]
    return "\n".join(f"{key}={payload[key]}" for key in order) + "\n"


def probe_permit_text(payload: Mapping[str, Any], login: int, maximum_volume: float, expires_epoch: int) -> str:
    return "\n".join([
        f"schema_version={PROBE_PERMIT_SCHEMA}",
        "authorized=true",
        f"candidate_class={CANDIDATE_CLASS}",
        f"intent_id={payload['intent_id']}",
        f"allowed_demo_login={login}",
        f"magic_number={payload['magic_number']}",
        f"symbol={payload['symbol']}",
        f"expires_epoch={expires_epoch}",
        f"bounded_preflight_sha256={payload['bounded_preflight_sha256']}",
        f"probe_exit_after_seconds={payload['probe_exit_after_seconds']}",
        f"maximum_volume={maximum_volume:.8f}",
        "",
    ])


def load_config(root: Path, config_path: str) -> dict[str, Any]:
    return load_json(resolve(root, config_path))


def preflight(root: Path, config: Mapping[str, Any], now: datetime | None = None, exit_seconds: int = DEFAULT_EXIT_SECONDS) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    require(MIN_EXIT_SECONDS <= exit_seconds <= MAX_EXIT_SECONDS, "probe exit seconds outside 60..300")
    bdir = bridge_dir(config)
    heartbeat_path = bdir / str(config.get("heartbeat_file", "bridge_heartbeat.txt"))
    arming_path = bdir / str(config.get("arming_permit_file", "arming_permit.txt"))
    candidate_path = bdir / str(config.get("candidate_file", "demo_candidate.txt"))
    probe_permit_path = bdir / "qualification_probe_permit.txt"
    lockdown_path = bdir / "qualification_probe_lockdown.txt"
    active_state_path = bdir / "active_position.txt"

    heartbeat = parse_kv(heartbeat_path)
    arming = parse_kv(arming_path)
    age_seconds = max(0.0, current.timestamp() - heartbeat_path.stat().st_mtime)
    login = int(config.get("allowed_demo_login") or heartbeat.get("allowed_demo_login") or 0)
    magic = int(config["magic_number"])
    spread = float(heartbeat.get("spread_guard_bps") or 0.0)
    live_spread = 0.0
    bid = float(heartbeat.get("symbol_bid") or 0.0)
    ask = float(heartbeat.get("symbol_ask") or 0.0)
    if bid > 0 and ask >= bid:
        live_spread = (ask - bid) / ((ask + bid) / 2.0) * 10000.0
    window_ok, window_reason = market_window_check(current)

    entry = current + timedelta(seconds=ENTRY_DELAY_SECONDS)
    exit_at = entry + timedelta(seconds=exit_seconds)
    official_event_csv = resolve(root, str(config["official_event_csv"]))
    entry_event_ok, entry_events = event_guard(official_event_csv, entry)
    exit_event_ok, exit_events = event_guard(official_event_csv, exit_at)

    checks = {
        "market_window": window_ok,
        "heartbeat_fresh": age_seconds <= HEARTBEAT_MAX_AGE_SECONDS,
        "ea_program": heartbeat.get("program") == EA_PROGRAM,
        "ea_armed": heartbeat.get("armed") == "true",
        "ea_status": heartbeat.get("status") == "ARMED_RUNTIME_GUARDS_REQUIRED",
        "probe_supported": heartbeat.get("qualification_probe_supported") == "true",
        "demo_account": heartbeat.get("account_trade_mode") == "DEMO",
        "login_bound": int(heartbeat.get("account_login") or 0) == login == int(heartbeat.get("allowed_demo_login") or 0),
        "symbol": heartbeat.get("symbol") == config["expected_symbol"],
        "magic": int(heartbeat.get("magic_number") or 0) == magic,
        "volume_safe": heartbeat.get("target_volume_executable") == "true",
        "live_fallback_false": heartbeat.get("live_fallback_allowed") == "false",
        "arming_schema": arming.get("schema_version") == ARMING_PERMIT_SCHEMA,
        "arming_authorized": arming.get("authorized") == "true",
        "arming_login": int(arming.get("allowed_demo_login") or 0) == login,
        "arming_magic": int(arming.get("magic_number") or 0) == magic,
        "arming_unexpired": int(arming.get("expires_epoch") or 0) > int(current.timestamp()),
        "candidate_absent": not candidate_path.exists(),
        "probe_permit_absent": not probe_permit_path.exists(),
        "probe_lockdown_absent": not lockdown_path.exists(),
        "active_state_absent": not active_state_path.exists(),
        "entry_event_guard": entry_event_ok,
        "exit_event_guard": exit_event_ok,
        "live_spread_within_guard": 0.0 < live_spread <= spread + 1e-10,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(current),
        "decision": "PASS_QUALIFICATION_PROBE_PREFLIGHT_NO_ORDER" if not failed else "QUALIFICATION_PROBE_PREFLIGHT_FAIL_CLOSED",
        "pass": not failed,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "checks": checks,
        "failed_checks": failed,
        "market_window_reason": window_reason,
        "heartbeat_age_seconds": age_seconds,
        "live_spread_bps": live_spread,
        "locked_spread_guard_bps": spread,
        "entry_utc": iso_utc(entry),
        "exit_utc": iso_utc(exit_at),
        "entry_event_matches": entry_events,
        "exit_event_matches": exit_events,
        "paths": {
            "bridge_dir": str(bdir),
            "heartbeat": str(heartbeat_path),
            "arming_permit": str(arming_path),
            "candidate": str(candidate_path),
            "probe_permit": str(probe_permit_path),
            "lockdown": str(lockdown_path),
            "active_state": str(active_state_path),
        },
        "required_next_action": "EMIT_ONE_TIME_PROBE" if not failed else "FIX_FAILED_CHECKS_NO_ORDER",
    }
    write_json_atomic(report_dir(root) / "qualification_probe_preflight.json", result)
    if failed:
        raise ProbeError(f"qualification probe preflight failed: {failed}")
    return result


def emit(root: Path, config: Mapping[str, Any], side: str, now: datetime | None = None, exit_seconds: int = DEFAULT_EXIT_SECONDS) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    side = side.upper()
    require(side in {"LONG", "SHORT"}, "side must be LONG or SHORT")
    pf = preflight(root, config, now=current, exit_seconds=exit_seconds)
    bdir = bridge_dir(config)
    heartbeat = parse_kv(Path(pf["paths"]["heartbeat"]))
    arming = parse_kv(Path(pf["paths"]["arming_permit"]))
    login = int(heartbeat["account_login"])
    magic = int(config["magic_number"])
    entry = current + timedelta(seconds=ENTRY_DELAY_SECONDS)
    expires = entry + timedelta(seconds=ENTRY_GRACE_SECONDS)
    exit_at = entry + timedelta(seconds=exit_seconds)
    seed = f"{login}|{magic}|{int(current.timestamp())}|{side}|{exit_seconds}|{arming['bounded_preflight_sha256']}"
    intent_id = f"XAUUSD_QP_{int(current.timestamp())}_{hashlib.sha256(seed.encode()).hexdigest()[:12]}"
    payload: dict[str, Any] = {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_class": CANDIDATE_CLASS,
        "intent_id": intent_id,
        "created_utc": iso_utc(current),
        "created_epoch": int(current.timestamp()),
        "expires_utc": iso_utc(expires),
        "expires_epoch": int(expires.timestamp()),
        "symbol": config["expected_symbol"],
        "side": side,
        "probability_up": 0.5,
        "signal_utc": iso_utc(current),
        "signal_epoch": int(current.timestamp()),
        "target_entry_utc": iso_utc(entry),
        "target_entry_epoch": int(entry.timestamp()),
        "target_exit_utc": iso_utc(exit_at),
        "target_exit_epoch": int(exit_at.timestamp()),
        "entry_semantics": "QUALIFICATION_PROBE_IMMEDIATE_MARKET",
        "exit_semantics": "QUALIFICATION_PROBE_SECONDS",
        "exit_after_h1_bars": 0,
        "probe_exit_after_seconds": exit_seconds,
        "notional_to_equity": float(heartbeat["notional_to_equity"]),
        "event_guard_pass": True,
        "event_guard_reason": "QUALIFICATION_PROBE_OFFICIAL_EVENT_GUARD_PASSED",
        "spread_guard_bps": float(heartbeat["spread_guard_bps"]),
        "bounded_preflight_sha256": arming["bounded_preflight_sha256"],
        "magic_number": magic,
        "execution_mode": "DEMO_ONLY",
        "requires_mt5_runtime_authorization": True,
        "python_order_authorized": False,
    }
    candidate_text = candidate_to_kv(payload)
    probe_permit_expires = int((entry + timedelta(seconds=ENTRY_GRACE_SECONDS)).timestamp())
    maximum_volume = float(heartbeat["volume_min"])
    permit_text = probe_permit_text(payload, login, maximum_volume, probe_permit_expires)

    rdir = report_dir(root)
    outbox = rdir / "outbox"
    emit_summary_path = rdir / "qualification_probe_emit_summary.json"
    write_json_atomic(outbox / "qualification_probe_candidate.json", payload)
    write_text_atomic(outbox / "qualification_probe_candidate.txt", candidate_text)
    write_text_atomic(outbox / "qualification_probe_permit.txt", permit_text)

    # Persist the intent before touching the MT5 activation edge. If the process
    # stops after candidate activation, inspect can still recover the intent.
    prepared = {
        "program": PROGRAM,
        "generated_utc": iso_utc(current),
        "decision": "QUALIFICATION_PROBE_EMIT_PREPARED_NO_ORDER",
        "state": "PREPARED_NO_ORDER",
        "pass": False,
        "candidate_class": CANDIDATE_CLASS,
        "intent_id": intent_id,
        "side": side,
        "exit_after_seconds": exit_seconds,
        "candidate_sha256": sha256_bytes(candidate_text.encode("utf-8")),
        "probe_permit_sha256": sha256_bytes(permit_text.encode("utf-8")),
        "python_order_authorized": False,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "preflight": pf,
        "outputs": {
            "mt5_candidate": str(bdir / str(config.get("candidate_file", "demo_candidate.txt"))),
            "mt5_probe_permit": str(bdir / "qualification_probe_permit.txt"),
            "report_candidate": str(outbox / "qualification_probe_candidate.json"),
        },
        "required_next_action": "COMPLETE_ATOMIC_MT5_ACTIVATION_EDGE",
    }
    write_json_atomic(emit_summary_path, prepared)

    # Permit is written first; candidate is the final atomic activation edge.
    write_text_atomic(bdir / "qualification_probe_permit.txt", permit_text)
    write_text_atomic(bdir / str(config.get("candidate_file", "demo_candidate.txt")), candidate_text)

    result = dict(prepared)
    result.update({
        "generated_utc": iso_utc(),
        "decision": "PASS_QUALIFICATION_PROBE_EMITTED_MT5_RUNTIME_AUTHORIZATION_REQUIRED",
        "state": "EMITTED",
        "pass": True,
        "required_next_action": "WAIT_180_SECONDS_THEN_RUN_INSPECT",
    })
    write_json_atomic(emit_summary_path, result)
    return result


def read_journal(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            rows.append({str(k): str(v or "") for k, v in row.items() if k is not None})
    return rows


def recover_emit_context(root: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    rdir = report_dir(root)
    bdir = bridge_dir(config)
    summary_path = rdir / "qualification_probe_emit_summary.json"
    if summary_path.is_file():
        return load_json(summary_path), "emit_summary"

    outbox_candidate = rdir / "outbox/qualification_probe_candidate.json"
    if outbox_candidate.is_file():
        payload = load_json(outbox_candidate)
        return {
            "program": PROGRAM,
            "candidate_class": payload.get("candidate_class"),
            "intent_id": payload.get("intent_id"),
            "side": payload.get("side"),
            "state": "RECOVERED_FROM_OUTBOX",
            "pass": False,
        }, "outbox_candidate"

    candidate_path = bdir / str(config.get("candidate_file", "demo_candidate.txt"))
    if candidate_path.is_file():
        payload = parse_kv(candidate_path)
        return {
            "program": PROGRAM,
            "candidate_class": payload.get("candidate_class"),
            "intent_id": payload.get("intent_id"),
            "side": payload.get("side"),
            "state": "RECOVERED_FROM_MT5_CANDIDATE",
            "pass": False,
        }, "mt5_candidate"

    permit_path = bdir / "qualification_probe_permit.txt"
    if permit_path.is_file():
        payload = parse_kv(permit_path)
        return {
            "program": PROGRAM,
            "candidate_class": payload.get("candidate_class"),
            "intent_id": payload.get("intent_id"),
            "state": "RECOVERED_FROM_MT5_PERMIT",
            "pass": False,
        }, "mt5_probe_permit"
    return None, "none"


def inspect(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    rdir = report_dir(root)
    bdir = bridge_dir(config)
    emitted, emit_record_source = recover_emit_context(root, config)
    if emitted is None or not str(emitted.get("intent_id") or "").strip():
        result = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "QUALIFICATION_PROBE_NOT_EMITTED_NO_ORDER",
            "pass": False,
            "intent_id": None,
            "candidate_class": CANDIDATE_CLASS,
            "events": [],
            "checks": {"emit_intent_present": False},
            "failed_checks": ["emit_intent_present"],
            "current_order_allowed": False,
            "live_order_allowed": False,
            "emit_record_source": emit_record_source,
            "required_next_action": "RUN_PREFLIGHT_THEN_EMIT_INSIDE_SAFE_MARKET_WINDOW",
        }
        write_json_atomic(rdir / "qualification_probe_inspection.json", result)
        return result
    intent_id = str(emitted["intent_id"])
    journal_path = bdir / "qualification_probe_journal.tsv"
    receipt_path = bdir / "receipts" / f"{intent_id}.txt"
    duplicate_path = bdir / "receipts" / f"{intent_id}_DUPLICATE_BLOCKED.txt"
    lockdown_path = bdir / "qualification_probe_lockdown.txt"
    active_state_path = bdir / "active_position.txt"
    probe_permit_path = bdir / "qualification_probe_permit.txt"
    candidate_path = bdir / str(config.get("candidate_file", "demo_candidate.txt"))
    heartbeat_path = bdir / str(config.get("heartbeat_file", "bridge_heartbeat.txt"))

    rows = [row for row in read_journal(journal_path) if row.get("intent_id") == intent_id]
    events = [row.get("event", "") for row in rows]
    receipt = parse_kv(receipt_path) if receipt_path.is_file() else {}
    lockdown = parse_kv(lockdown_path) if lockdown_path.is_file() else {}
    entry_rows = [row for row in rows if row.get("event") == "OPEN_FILLED"]
    exit_rows = [row for row in rows if row.get("event") in {"RESOLVED", "EMERGENCY_FLAT"}]
    order_tickets = {row.get("order_ticket") for row in entry_rows if row.get("order_ticket") not in {None, "", "0"}}
    entry_deals = {row.get("deal_ticket") for row in entry_rows if row.get("deal_ticket") not in {None, "", "0"}}
    complete = bool(entry_rows and exit_rows and "DUPLICATE_BLOCKED" in events)
    exit_row = exit_rows[0] if len(exit_rows) == 1 else {}
    accounting_fields = ("requested_price", "fill_price", "slippage_bps", "profit", "commission", "swap", "fee")
    checks = {
        "candidate_class": emitted.get("candidate_class") == CANDIDATE_CLASS,
        "open_filled_once": len(entry_rows) == 1,
        "one_entry_order": len(order_tickets) == 1,
        "one_entry_deal": len(entry_deals) == 1,
        "controlled_exit_recorded": len(exit_rows) == 1,
        "duplicate_blocked": "DUPLICATE_BLOCKED" in events,
        "final_receipt_terminal": receipt.get("status") in {"RESOLVED", "EMERGENCY_FLAT"},
        "lockdown_present": lockdown.get("intent_id") == intent_id,
        "probe_permit_consumed": not probe_permit_path.exists(),
        "active_state_cleared": not active_state_path.exists(),
        "volume_is_minimum": all(abs(float(row.get("volume") or 0.0) - 0.01) < 1e-9 for row in entry_rows),
        "demo_only": all(row.get("account_trade_mode") == "DEMO" for row in rows if row.get("account_trade_mode")),
        "exit_requested_price_recorded": float(exit_row.get("requested_price") or 0.0) > 0.0,
        "exit_fill_price_recorded": float(exit_row.get("fill_price") or 0.0) > 0.0,
        "terminal_accounting_fields_recorded": all(exit_row.get(field) not in {None, ""} for field in accounting_fields),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    pass_value = complete and not failed
    decision = "PASS_DEMO_QUALIFICATION_PROBE_FULL_LIFECYCLE" if pass_value else "QUALIFICATION_PROBE_PENDING_OR_FAIL_CLOSED"
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": decision,
        "pass": pass_value,
        "intent_id": intent_id,
        "candidate_class": CANDIDATE_CLASS,
        "emit_record_source": emit_record_source,
        "emit_state": emitted.get("state"),
        "events": events,
        "checks": checks,
        "failed_checks": failed,
        "receipt": receipt,
        "lockdown": lockdown,
        "journal_rows": rows,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "paths": {
            "journal": str(journal_path),
            "receipt": str(receipt_path),
            "duplicate_marker": str(duplicate_path),
            "lockdown": str(lockdown_path),
            "active_state": str(active_state_path),
            "probe_permit": str(probe_permit_path),
            "candidate": str(candidate_path),
            "heartbeat": str(heartbeat_path),
        },
        "required_next_action": "COLLECT_EVIDENCE_THEN_MANUALLY_DISARM_EA" if pass_value else "DO_NOT_EMIT_ANOTHER_PROBE_INSPECT_RUNTIME_EVIDENCE",
    }
    write_json_atomic(rdir / "qualification_probe_inspection.json", result)
    return result


def collect(root: Path, config: Mapping[str, Any], output: Path | None = None) -> dict[str, Any]:
    result = inspect(root, config)
    if result["pass"] is not True:
        pending = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "QUALIFICATION_PROBE_EVIDENCE_NOT_READY",
            "pass": False,
            "intent_id": result.get("intent_id"),
            "failed_checks": result.get("failed_checks", []),
            "inspection_decision": result.get("decision"),
            "current_order_allowed": False,
            "live_order_allowed": False,
            "output_created": False,
            "required_next_action": result.get("required_next_action", "WAIT_FOR_COMPLETE_LIFECYCLE_THEN_COLLECT"),
        }
        write_json_atomic(report_dir(root) / "qualification_probe_collection_pending.json", pending)
        return pending
    rdir = report_dir(root)
    bdir = bridge_dir(config)
    runtime_log = bdir / "bridge_runtime.log"
    runtime_tail = rdir / "bridge_runtime_last_300_lines.log"
    if runtime_log.is_file():
        lines = runtime_log.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        write_text_atomic(runtime_tail, "\n".join(lines) + "\n")
    output_path = output or (Path.home() / "Downloads" / "XAUUSD_DEMO_QUALIFICATION_PROBE_EVIDENCE.zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates = [
        rdir / "qualification_probe_preflight.json",
        rdir / "qualification_probe_emit_summary.json",
        rdir / "qualification_probe_inspection.json",
        rdir / "outbox/qualification_probe_candidate.json",
        rdir / "outbox/qualification_probe_candidate.txt",
        rdir / "outbox/qualification_probe_permit.txt",
        runtime_tail,
        bdir / "qualification_probe_journal.tsv",
        Path(result["paths"]["receipt"]),
        Path(result["paths"]["duplicate_marker"]),
        Path(result["paths"]["lockdown"]),
        Path(result["paths"]["heartbeat"]),
    ]
    files = [path for path in candidates if path.is_file()]
    manifest = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": result["decision"],
        "intent_id": result["intent_id"],
        "files": [{"path": str(path), "sha256": sha256_file(path)} for path in files],
    }
    with ZipFile(output_path, "w", ZIP_DEFLATED) as archive:
        for path in files:
            prefix = "repo_evidence" if rdir in path.parents else "mt5_evidence"
            archive.write(path, f"{prefix}/{path.name}")
        archive.writestr("EVIDENCE_MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": "PASS_QUALIFICATION_PROBE_EVIDENCE_PACK_CREATED",
        "pass": True,
        "output": str(output_path),
        "sha256": sha256_file(output_path),
        "required_next_action": "SEND_EVIDENCE_ZIP_FOR_REVIEW_AND_RELOAD_EA_WITH_INP_ARMED_FALSE",
    }



def cleanup(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    inspection = load_json(report_dir(root) / "qualification_probe_inspection.json")
    require(inspection.get("pass") is True, "successful inspection required before cleanup")
    bdir = bridge_dir(config)
    heartbeat = parse_kv(bdir / str(config.get("heartbeat_file", "bridge_heartbeat.txt")))
    require(heartbeat.get("armed") == "false", "reload EA with InpArmed=false before cleanup")
    require(heartbeat.get("status") == "DISABLED_DEFAULT_NO_ORDER", "disabled EA heartbeat required before cleanup")
    require(not (bdir / "active_position.txt").exists(), "active position state still exists")
    removed = []
    for path in (
        bdir / str(config.get("candidate_file", "demo_candidate.txt")),
        bdir / "qualification_probe_permit.txt",
        bdir / "qualification_probe_lockdown.txt",
    ):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": "PASS_QUALIFICATION_PROBE_CLEANUP_DISABLED_NO_ORDER",
        "pass": True,
        "bridge_armed": False,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "removed": removed,
        "retained_evidence": [
            str(bdir / "qualification_probe_journal.tsv"),
            str(bdir / "receipts"),
            str(report_dir(root)),
        ],
        "required_next_action": "REVIEW_EVIDENCE_BEFORE_NORMAL_DEMO_QUALIFICATION_CONTINUES",
    }
    write_json_atomic(report_dir(root) / "qualification_probe_cleanup.json", result)
    return result

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("preflight", "emit", "inspect", "collect", "cleanup"))
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--side", choices=("LONG", "SHORT"), default="LONG")
    p.add_argument("--exit-seconds", type=int, default=DEFAULT_EXIT_SECONDS)
    p.add_argument("--output")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    rdir = report_dir(root)
    try:
        config = load_config(root, args.config)
        if args.command == "preflight":
            result = preflight(root, config, exit_seconds=args.exit_seconds)
        elif args.command == "emit":
            result = emit(root, config, args.side, exit_seconds=args.exit_seconds)
        elif args.command == "inspect":
            result = inspect(root, config)
        elif args.command == "collect":
            output = Path(args.output).expanduser().resolve() if args.output else None
            result = collect(root, config, output)
        else:
            result = cleanup(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("pass") is True else 2
    except Exception as exc:
        payload = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "QUALIFICATION_PROBE_FAIL_CLOSED",
            "pass": False,
            "current_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json_atomic(rdir / "qualification_probe_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
