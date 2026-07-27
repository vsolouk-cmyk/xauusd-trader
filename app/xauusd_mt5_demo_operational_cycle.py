#!/usr/bin/env python3
"""Fail-closed local operational cycle for the bounded XAUUSD MT5 demo bridge.

Cycle:
1. verify armed EA heartbeat and active permit;
2. merge completed recent M5/H1 bars exported by MT5 into persistent AMarkets CSVs;
3. run frozen Stage180, controlled-paper preflight/run, and the existing candidate emitter;
4. preserve all MT5-side spread, account, volume, risk, idempotency, and qualification guards.

This module never calls a broker API and never sends an order.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc
PROGRAM = "XAUUSD_MT5_BOUNDED_DEMO_OPERATIONAL_CYCLE_V1"
EXPECTED_HEADER = ["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<SPREAD>", "<VOL>"]
EXPORTER_PROGRAM = "AMARKETS_RECENT_BAR_EXPORTER_EA_V1"
EXPORTER_DECISION = "PASS_RECENT_EXPORT"


class CycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class BarRow:
    timestamp: datetime
    values: list[str]


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CycleError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CycleError(f"cannot read JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not object: {path}")
    return value


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_kv(path: Path) -> dict[str, str]:
    require(path.is_file(), f"key/value file missing: {path}")
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def parse_dt(date_text: str, time_text: str) -> datetime:
    try:
        return datetime.strptime(f"{date_text.strip()} {time_text.strip()}", "%Y.%m.%d %H:%M").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CycleError(f"invalid MT5 timestamp: {date_text!r} {time_text!r}") from exc


def validate_ohlc(values: list[str], source: Path, row_number: int) -> None:
    try:
        open_, high, low, close = (float(values[i]) for i in (2, 3, 4, 5))
    except (ValueError, IndexError) as exc:
        raise CycleError(f"invalid OHLC at {source}:{row_number}") from exc
    require(all(math.isfinite(v) for v in (open_, high, low, close)), f"non-finite OHLC at {source}:{row_number}")
    require(high >= max(open_, close, low), f"high invariant failed at {source}:{row_number}")
    require(low <= min(open_, close, high), f"low invariant failed at {source}:{row_number}")


def read_recent(path: Path) -> list[BarRow]:
    require(path.is_file(), f"recent export missing: {path}")
    rows: dict[datetime, BarRow] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise CycleError(f"empty recent export: {path}") from exc
        require(header == EXPECTED_HEADER, f"unexpected header in {path}: {header}")
        for index, values in enumerate(reader, start=2):
            if not values or all(not item.strip() for item in values):
                continue
            require(len(values) == len(EXPECTED_HEADER), f"column count mismatch at {path}:{index}")
            validate_ohlc(values, path, index)
            ts = parse_dt(values[0], values[1])
            rows[ts] = BarRow(ts, values)
    ordered = [rows[key] for key in sorted(rows)]
    require(ordered, f"recent export has no rows: {path}")
    return ordered


def iter_existing(reader: Iterable[list[str]], source: Path) -> Iterable[BarRow]:
    previous: datetime | None = None
    for index, values in enumerate(reader, start=2):
        if not values or all(not item.strip() for item in values):
            continue
        require(len(values) == len(EXPECTED_HEADER), f"column count mismatch at {source}:{index}")
        validate_ohlc(values, source, index)
        ts = parse_dt(values[0], values[1])
        require(previous is None or ts > previous, f"existing CSV is not strictly increasing at {source}:{index}")
        previous = ts
        yield BarRow(ts, values)


def read_tail_rows(path: Path, maximum_rows: int = 8) -> list[BarRow]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        data = b""
        while position > 0 and data.count(b"\n") <= maximum_rows + 1:
            take = min(8192, position)
            position -= take
            handle.seek(position)
            data = handle.read(take) + data
    lines = data.splitlines()[-maximum_rows:]
    rows: list[BarRow] = []
    for raw in lines:
        values = raw.decode("utf-8-sig").split("\t")
        if values == EXPECTED_HEADER or not values or all(not item.strip() for item in values):
            continue
        require(len(values) == len(EXPECTED_HEADER), f"invalid tail row in {path}")
        validate_ohlc(values, path, -1)
        rows.append(BarRow(parse_dt(values[0], values[1]), values))
    require(rows, f"persistent CSV has no data rows: {path}")
    for left, right in zip(rows, rows[1:]):
        require(right.timestamp > left.timestamp, f"persistent CSV tail is not strictly increasing: {path}")
    return rows


def append_rows_with_rollback(target: Path, rows: list[BarRow]) -> None:
    original_size = target.stat().st_size
    try:
        with target.open("ab") as handle:
            for row in rows:
                line = "\t".join(row.values) + "\n"
                handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with target.open("r+b") as handle:
            handle.truncate(original_size)
            handle.flush()
            os.fsync(handle.fileno())
        raise


def merge_recent_atomic(target: Path, recent: Path, minimum_free_space_bytes: int) -> dict[str, Any]:
    require(target.is_file(), f"persistent target missing: {target}")
    recent_rows = read_recent(recent)
    recent_by_ts = {row.timestamp: row for row in recent_rows}
    target_tail = read_tail_rows(target)
    last_target = target_tail[-1]

    # Fast path: completed broker bars are immutable. Compare the available tail
    # overlap, then append only strictly newer rows. A mismatch falls back to a
    # full atomic merge so revisions are still handled safely.
    tail_overlap_matches = all(
        row.timestamp not in recent_by_ts or recent_by_ts[row.timestamp].values == row.values
        for row in target_tail
    )
    new_rows = [row for row in recent_rows if row.timestamp > last_target.timestamp]
    if tail_overlap_matches:
        if not new_rows:
            return {
                "target": str(target),
                "recent": str(recent),
                "mode": "NO_CHANGE_TAIL_MATCH",
                "changed": False,
                "recent_rows": len(recent_rows),
                "inserted_rows": 0,
                "replaced_rows": 0,
                "last_timestamp_naive": last_target.timestamp.isoformat(),
                "sha256": sha256_file(target),
            }
        require(new_rows[0].timestamp > last_target.timestamp, "append rows are not newer than persistent tail")
        append_rows_with_rollback(target, new_rows)
        verified_tail = read_tail_rows(target)
        require(verified_tail[-1].timestamp == new_rows[-1].timestamp, "append tail verification failed")
        return {
            "target": str(target),
            "recent": str(recent),
            "mode": "APPEND_WITH_ROLLBACK",
            "changed": True,
            "recent_rows": len(recent_rows),
            "inserted_rows": len(new_rows),
            "replaced_rows": 0,
            "first_appended_timestamp_naive": new_rows[0].timestamp.isoformat(),
            "last_timestamp_naive": new_rows[-1].timestamp.isoformat(),
            "sha256": sha256_file(target),
        }

    target_size = target.stat().st_size
    free = shutil.disk_usage(target.parent).free
    required_free = max(int(minimum_free_space_bytes), target_size + recent.stat().st_size + 16 * 1024 * 1024)
    require(free >= required_free, f"insufficient disk space for atomic merge: free={free} required={required_free}")

    tmp = target.with_name(target.name + ".demo_cycle.tmp")
    tmp.unlink(missing_ok=True)
    inserted = 0
    replaced = 0
    changed_replacements = 0
    existing_count = 0
    output_count = 0
    first_out: datetime | None = None
    last_out: datetime | None = None
    recent_index = 0

    try:
        with target.open("r", encoding="utf-8-sig", newline="") as src, tmp.open("w", encoding="utf-8", newline="") as dst:
            reader = csv.reader(src, delimiter="\t")
            writer = csv.writer(dst, delimiter="\t", lineterminator="\n")
            try:
                header = next(reader)
            except StopIteration as exc:
                raise CycleError(f"empty persistent CSV: {target}") from exc
            require(header == EXPECTED_HEADER, f"unexpected persistent header in {target}: {header}")
            writer.writerow(EXPECTED_HEADER)

            def write_row(row: BarRow) -> None:
                nonlocal output_count, first_out, last_out
                require(last_out is None or row.timestamp > last_out, f"merged output would not be strictly increasing at {row.timestamp.isoformat()}")
                writer.writerow(row.values)
                output_count += 1
                first_out = first_out or row.timestamp
                last_out = row.timestamp

            for existing in iter_existing(reader, target):
                existing_count += 1
                while recent_index < len(recent_rows) and recent_rows[recent_index].timestamp < existing.timestamp:
                    write_row(recent_rows[recent_index])
                    recent_index += 1
                    inserted += 1
                if recent_index < len(recent_rows) and recent_rows[recent_index].timestamp == existing.timestamp:
                    replacement = recent_rows[recent_index]
                    write_row(replacement)
                    if replacement.values != existing.values:
                        changed_replacements += 1
                    recent_index += 1
                    replaced += 1
                else:
                    write_row(existing)
            while recent_index < len(recent_rows):
                write_row(recent_rows[recent_index])
                recent_index += 1
                inserted += 1
            dst.flush()
            os.fsync(dst.fileno())
        require(output_count >= existing_count, "atomic merge unexpectedly reduced row count")
        changed = inserted > 0 or changed_replacements > 0
        if changed:
            os.replace(tmp, target)
        else:
            tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return {
        "target": str(target),
        "recent": str(recent),
        "mode": "FULL_ATOMIC_MERGE",
        "changed": changed,
        "existing_rows": existing_count,
        "recent_rows": len(recent_rows),
        "output_rows": output_count,
        "inserted_rows": inserted,
        "replaced_rows": replaced,
        "changed_replacements": changed_replacements,
        "first_timestamp_naive": first_out.isoformat() if first_out else None,
        "last_timestamp_naive": last_out.isoformat() if last_out else None,
        "sha256": sha256_file(target),
    }


def bridge_dir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])


def validate_armed_heartbeat(config: Mapping[str, Any]) -> dict[str, Any]:
    folder = bridge_dir(config)
    heartbeat_path = folder / str(config.get("heartbeat_file", "bridge_heartbeat.txt"))
    permit_path = folder / str(config.get("arming_permit_file", "arming_permit.txt"))
    heartbeat = parse_kv(heartbeat_path)
    permit = parse_kv(permit_path)
    age_minutes = (utc_now().timestamp() - heartbeat_path.stat().st_mtime) / 60.0
    checks = {
        "heartbeat_fresh": -1.0 <= age_minutes <= float(config.get("maximum_heartbeat_age_minutes", 5)),
        "program": heartbeat.get("program") == "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING",
        "armed": heartbeat.get("armed") == "true",
        "status": heartbeat.get("status") == "ARMED_RUNTIME_GUARDS_REQUIRED",
        "demo": heartbeat.get("account_trade_mode") == "DEMO",
        "login": int(heartbeat.get("account_login") or 0) == int(config["allowed_demo_login"]),
        "allowed_login": int(heartbeat.get("allowed_demo_login") or 0) == int(config["allowed_demo_login"]),
        "symbol": heartbeat.get("symbol") == config["expected_symbol"],
        "magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "permit_present": heartbeat.get("arming_permit_present") == "true",
        "permit_authorized": permit.get("authorized") == "true",
        "permit_unexpired": int(permit.get("expires_epoch") or 0) > int(utc_now().timestamp()),
        "volume_safe": heartbeat.get("minimum_volume_within_validated_ceiling") == "true",
        "target_executable": heartbeat.get("target_volume_executable") == "true",
        "live_fallback_false": heartbeat.get("live_fallback_allowed") == "false",
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"armed heartbeat validation failed: {failed}")
    return {"path": str(heartbeat_path), "age_minutes": age_minutes, "checks": checks, "heartbeat": heartbeat}



def validate_disabled_heartbeat(config: Mapping[str, Any]) -> dict[str, Any]:
    folder = bridge_dir(config)
    heartbeat_path = folder / str(config.get("heartbeat_file", "bridge_heartbeat.txt"))
    heartbeat = parse_kv(heartbeat_path)
    age_minutes = (utc_now().timestamp() - heartbeat_path.stat().st_mtime) / 60.0
    checks = {
        "heartbeat_fresh": -1.0 <= age_minutes <= float(config.get("maximum_heartbeat_age_minutes", 5)),
        "program": heartbeat.get("program") == "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING",
        "disabled": heartbeat.get("armed") == "false",
        "status": heartbeat.get("status") == "DISABLED_DEFAULT_NO_ORDER",
        "demo": heartbeat.get("account_trade_mode") == "DEMO",
        "login": int(heartbeat.get("account_login") or 0) == int(config["allowed_demo_login"]),
        "symbol": heartbeat.get("symbol") == config["expected_symbol"],
        "magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "permit_absent": heartbeat.get("arming_permit_present") == "false",
        "volume_safe": heartbeat.get("minimum_volume_within_validated_ceiling") == "true",
        "target_executable": heartbeat.get("target_volume_executable") == "true",
        "live_fallback_false": heartbeat.get("live_fallback_allowed") == "false",
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"disabled heartbeat validation failed: {failed}")
    return {"path": str(heartbeat_path), "age_minutes": age_minutes, "checks": checks, "heartbeat": heartbeat}

def validate_recent_export(config: Mapping[str, Any]) -> dict[str, Any]:
    source_dir = bridge_dir(config) / str(config["recent_source_subdir"])
    status_path = source_dir / str(config["recent_status_file"])
    m5 = source_dir / str(config["recent_m5_file"])
    h1 = source_dir / str(config["recent_h1_file"])
    status = parse_kv(status_path)
    age_minutes = (utc_now().timestamp() - status_path.stat().st_mtime) / 60.0
    checks = {
        "status_fresh": -1.0 <= age_minutes <= float(config.get("maximum_recent_export_age_minutes", 12)),
        "program": status.get("program") == EXPORTER_PROGRAM,
        "decision": status.get("decision") == EXPORTER_DECISION,
        "demo": status.get("account_trade_mode") == "DEMO",
        "login": int(status.get("account_login") or 0) == int(config["allowed_demo_login"]),
        "symbol": status.get("symbol") == config["expected_symbol"],
        "m5_exists": m5.is_file(),
        "h1_exists": h1.is_file(),
        "m5_rows": int(status.get("m5_rows") or 0) > 0,
        "h1_rows": int(status.get("h1_rows") or 0) > 0,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"recent exporter validation failed: {failed}")
    return {"source_dir": str(source_dir), "status_path": str(status_path), "age_minutes": age_minutes, "checks": checks, "status": status, "m5": m5, "h1": h1}


def run_capture(name: str, command: Sequence[str], root: Path) -> dict[str, Any]:
    print(f"[START] {name}: {' '.join(command)}", flush=True)
    started = utc_now()
    completed = subprocess.run(list(command), cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n", flush=True)
    require(completed.returncode == 0, f"{name} failed rc={completed.returncode}")
    return {
        "name": name,
        "command": list(command),
        "started_utc": iso_utc(started),
        "finished_utc": iso_utc(),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-12000:],
    }


def validate_controlled_summary(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve(root, str(config["controlled_paper_summary"]))
    payload = load_json(path)
    freshness = payload.get("operational_freshness") or (payload.get("run_result") or {}).get("freshness") or {}
    risk_state = payload.get("risk_state") or {}
    checks = {
        "program": payload.get("program") in set(config.get("accepted_controlled_programs", [])),
        "paper_only": payload.get("paper_log_only") is True,
        "direction": payload.get("direction_policy") == "BIDIRECTIONAL_PROBABILITY_TAILS",
        "orders_closed": all(payload.get(k) is False for k in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
        "freshness_pass": freshness.get("pass") is True,
        "freshness_decision": freshness.get("decision") == "PASS_OPERATIONAL_FRESHNESS_OPEN_MARKET",
        "hard_kill_false": risk_state.get("hard_kill_latched") is False,
        "weekly_pause_false": risk_state.get("weekly_pause_active") is False,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"controlled-paper validation failed: {failed}")
    return {"path": str(path), "sha256": sha256_file(path), "checks": checks, "freshness": freshness}



def prepare_arm_refresh(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    started = utc_now()
    heartbeat = validate_disabled_heartbeat(config)
    recent = validate_recent_export(config)
    minimum_free = int(config.get("minimum_free_space_bytes", 268435456))
    merges = {
        "m5": merge_recent_atomic(resolve(root, str(config["persistent_m5_csv"])), recent["m5"], minimum_free),
        "h1": merge_recent_atomic(resolve(root, str(config["persistent_h1_csv"])), recent["h1"], minimum_free),
    }

    alignment = resolve(root, str(config["alignment_refresh_app"]))
    fresh = resolve(root, str(config["fresh_dry_cycle_app"]))
    for label, path in (("alignment refresh app", alignment), ("fresh dry-cycle app", fresh)):
        require(path.is_file(), f"{label} missing: {path}")

    steps = [
        run_capture("Stage180 alignment refresh", [sys.executable, str(alignment)], root),
        run_capture("Login-bound fresh dry cycle", [sys.executable, str(fresh), "fresh-dry-cycle", "--root", str(root)], root),
    ]

    fresh_summary_path = root / "reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_fresh_dry_cycle_summary.json"
    fresh_summary = load_json(fresh_summary_path)
    checks = {
        "fresh_decision": fresh_summary.get("decision") == "PASS_LOGIN_BOUND_FRESH_DRY_CANDIDATE_CYCLE_NO_ORDER",
        "fresh_pass": fresh_summary.get("pass") is True,
        "bridge_disabled": fresh_summary.get("bridge_armed") is False,
        "permit_not_created": fresh_summary.get("active_arming_permit_created") is False,
        "candidate_not_written": fresh_summary.get("active_candidate_written") is False,
        "orders_closed": all(fresh_summary.get(k) is False for k in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"pre-arm fresh dry-cycle validation failed: {failed}")

    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "started_utc": iso_utc(started),
        "decision": "PASS_PRE_ARM_DATA_REFRESH_AND_FRESH_DRY_CYCLE_NO_ORDER",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": False,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "heartbeat": heartbeat,
        "recent_export": {k: v for k, v in recent.items() if k not in ("m5", "h1")},
        "merges": merges,
        "fresh_dry_checks": checks,
        "steps": steps,
        "required_next_action": "CREATE_LOGIN_BOUND_DEMO_ARMING_PERMIT",
    }
    report_dir = resolve(root, str(config["report_dir"]))
    write_json_atomic(report_dir / "pre_arm_refresh_summary.json", result)
    return result

def run_cycle(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    started = utc_now()
    heartbeat = validate_armed_heartbeat(config)
    recent = validate_recent_export(config)
    report_dir = resolve(root, str(config["report_dir"]))
    state_path = resolve(root, str(config.get("cycle_state_file", "reports/xauusd_mt5_demo_activation/operational_cycle_state.json")))
    recent_h1_sha256 = sha256_file(recent["h1"])
    previous_state = load_json(state_path) if state_path.is_file() else {}
    if previous_state.get("recent_h1_sha256") == recent_h1_sha256:
        result = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "started_utc": iso_utc(started),
            "decision": "PASS_NO_NEW_COMPLETED_H1_SKIP_HEAVY_CYCLE",
            "pass": True,
            "allowed_demo_login": int(config["allowed_demo_login"]),
            "bridge_armed": True,
            "current_order_allowed": False,
            "live_order_allowed": False,
            "heartbeat": heartbeat,
            "recent_export": {k: v for k, v in recent.items() if k not in ("m5", "h1")},
            "recent_h1_sha256": recent_h1_sha256,
            "required_next_action": "WAIT_FOR_NEXT_COMPLETED_H1_BAR",
        }
        write_json_atomic(report_dir / "operational_cycle_summary.json", result)
        return result

    minimum_free = int(config.get("minimum_free_space_bytes", 268435456))
    merges = {
        "m5": merge_recent_atomic(resolve(root, str(config["persistent_m5_csv"])), recent["m5"], minimum_free),
        "h1": merge_recent_atomic(resolve(root, str(config["persistent_h1_csv"])), recent["h1"], minimum_free),
    }

    stage180 = resolve(root, str(config["stage180_app"]))
    controlled = resolve(root, str(config["controlled_paper_app"]))
    bridge = resolve(root, str(config["bridge_app"]))
    for label, path in (("Stage180 app", stage180), ("controlled-paper app", controlled), ("bridge app", bridge)):
        require(path.is_file(), f"{label} missing: {path}")

    steps = [
        run_capture("Stage180 frozen-model refresh", [sys.executable, str(stage180)], root),
        run_capture("Controlled-paper preflight", [sys.executable, str(controlled), "preflight", "--root", str(root)], root),
        run_capture("Controlled-paper run", [sys.executable, str(controlled), "run", "--root", str(root)], root),
    ]
    controlled_evidence = validate_controlled_summary(root, config)
    steps.append(run_capture("MT5 demo candidate emission", [sys.executable, str(bridge), "emit-candidate", "--root", str(root)], root))
    candidate_summary_path = root / "reports/xauusd_mt5_demo_bridge/mt5_demo_bridge_candidate_summary.json"
    candidate = load_json(candidate_summary_path)
    allowed_decisions = {
        "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL",
        "WAIT_FOR_TARGET_ENTRY_WINDOW_NO_CANDIDATE",
        "BLOCK_DEMO_CANDIDATE_STALE_ENTRY_WINDOW",
        "BLOCK_MT5_DEMO_CANDIDATE_EVENT_BLACKOUT",
        "PASS_DEMO_CANDIDATE_EMITTED_RUNTIME_AUTHORIZATION_REQUIRED",
    }
    require(candidate.get("decision") in allowed_decisions, f"unexpected candidate decision: {candidate.get('decision')}")
    require(candidate.get("live_order_allowed") is False, "candidate emitter opened live boundary")

    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "started_utc": iso_utc(started),
        "decision": "PASS_BOUNDED_DEMO_OPERATIONAL_CYCLE",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": True,
        "live_order_allowed": False,
        "heartbeat": heartbeat,
        "recent_export": {k: v for k, v in recent.items() if k not in ("m5", "h1")},
        "merges": merges,
        "controlled_paper": controlled_evidence,
        "candidate_result": candidate,
        "steps": steps,
        "required_next_action": "CONTINUE_FIVE_MINUTE_LOCAL_CYCLE_UNTIL_30_DAYS_OR_10_RESOLVED_POSITIONS",
    }
    write_json_atomic(report_dir / "operational_cycle_summary.json", result)
    write_json_atomic(state_path, {
        "program": PROGRAM,
        "updated_utc": iso_utc(),
        "recent_h1_sha256": recent_h1_sha256,
        "recent_m5_sha256": sha256_file(recent["m5"]),
        "candidate_decision": candidate.get("decision"),
    })
    return result



class ExclusiveCycleLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise CycleError(f"another operational cycle is already running: {self.path}") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()}\nstarted_utc={iso_utc()}\n")
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
        return False

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("run", "prepare-arm"), nargs="?", default="run")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="config/xauusd_mt5_demo_activation.json")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports/xauusd_mt5_demo_activation"
    try:
        config = load_json(resolve(root, args.config))
        lock_path = resolve(root, str(config["report_dir"])) / "operational_cycle.lock"
        with ExclusiveCycleLock(lock_path):
            result = prepare_arm_refresh(root, config) if args.command == "prepare-arm" else run_cycle(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        payload = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "BOUNDED_DEMO_OPERATIONAL_CYCLE_FAIL_CLOSED",
            "pass": False,
            "current_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json_atomic(report_dir / "operational_cycle_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
