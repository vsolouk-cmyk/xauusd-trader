#!/usr/bin/env python3
"""Explicit, login-bound arming operator for the bounded XAUUSD MT5 demo bridge.

The operator creates or removes only the file-based arming permit. It never calls
an MT5/broker API and never emits an order. Actual order eligibility remains inside
MT5 and requires the EA to be manually reloaded with InpArmed=true and the exact
allowed demo login.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

UTC = timezone.utc
PROGRAM = "XAUUSD_MT5_BOUNDED_DEMO_EXPLICIT_ARMING_V1"
PERMIT_SCHEMA = "XAUUSD_DEMO_ARMING_PERMIT_V1"
RUNTIME_PROGRAM = "XAUUSD_MT5_BOUNDED_DEMO_BRIDGE_V1_1_VOLUME_DIAGNOSTIC_LOGGING"
RUNTIME_DECISION = "PASS_MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_DISABLED_NO_ORDER"
FRESH_DECISION = "PASS_LOGIN_BOUND_FRESH_DRY_CANDIDATE_CYCLE_NO_ORDER"
FRESH_NEXT = "READY_FOR_EXPLICIT_DEMO_ARMING_REVIEW_NO_FORWARD_SIGNAL_WAIT"
BOUNDED_DECISION = "PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH"


class ArmingError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArmingError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ArmingError(f"cannot read JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not object: {path}")
    return value


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
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


def bridge_dir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])


def permit_path(config: Mapping[str, Any]) -> Path:
    return bridge_dir(config) / str(config.get("arming_permit_file", "arming_permit.txt"))


def candidate_path(config: Mapping[str, Any]) -> Path:
    return bridge_dir(config) / str(config.get("candidate_file", "demo_candidate.txt"))


def heartbeat_path(config: Mapping[str, Any]) -> Path:
    return bridge_dir(config) / str(config.get("heartbeat_file", "bridge_heartbeat.txt"))


def run_checked(command: Sequence[str], root: Path) -> None:
    print(f"[START] {' '.join(command)}", flush=True)
    completed = subprocess.run(list(command), cwd=str(root), text=True)
    require(completed.returncode == 0, f"command failed rc={completed.returncode}: {' '.join(command)}")


def validate_disabled_runtime(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve(root, str(config["runtime_preflight"]))
    payload = load_json(path)
    heartbeat = payload.get("heartbeat") or {}
    login = int(config["allowed_demo_login"])
    checks = {
        "program": payload.get("program") == RUNTIME_PROGRAM,
        "decision": payload.get("decision") == RUNTIME_DECISION,
        "pass": payload.get("pass") is True,
        "arming_ready": payload.get("arming_readiness_pass") is True,
        "runtime_failed_empty": payload.get("runtime_failed_checks") == [],
        "arming_failed_empty": payload.get("arming_failed_checks") == [],
        "account_demo": heartbeat.get("account_trade_mode") == "DEMO",
        "login": int(heartbeat.get("account_login") or 0) == login,
        "symbol": heartbeat.get("symbol") == config["expected_symbol"],
        "magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "disabled": str(heartbeat.get("armed")).lower() == "false",
        "permit_absent": str(heartbeat.get("arming_permit_present")).lower() == "false",
        "volume_safe": str(heartbeat.get("minimum_volume_within_validated_ceiling")).lower() == "true",
        "target_executable": str(heartbeat.get("target_volume_executable")).lower() == "true",
        "orders_closed": all(payload.get(k) is False for k in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"disabled runtime validation failed: {failed}")
    return {"path": str(path), "sha256": sha256_file(path), "checks": checks, "heartbeat": heartbeat}


def validate_pre_arm_refresh(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve(root, str(config["pre_arm_refresh_summary"]))
    payload = load_json(path)
    checks = {
        "decision": payload.get("decision") == "PASS_PRE_ARM_DATA_REFRESH_AND_FRESH_DRY_CYCLE_NO_ORDER",
        "pass": payload.get("pass") is True,
        "bridge_disabled": payload.get("bridge_armed") is False,
        "orders_closed": all(payload.get(k) is False for k in ("current_order_allowed", "live_order_allowed")),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"pre-arm refresh validation failed: {failed}")
    return {"path": str(path), "sha256": sha256_file(path), "checks": checks}


def validate_fresh_dry(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_fresh_dry_cycle_summary.json"
    payload = load_json(path)
    checks = {
        "decision": payload.get("decision") == FRESH_DECISION,
        "pass": payload.get("pass") is True,
        "login": int(payload.get("allowed_demo_login") or 0) == int(config["allowed_demo_login"]),
        "next": payload.get("required_next_action") == FRESH_NEXT,
        "bridge_disabled": payload.get("bridge_armed") is False,
        "permit_absent": payload.get("active_arming_permit_created") is False,
        "candidate_absent": payload.get("active_candidate_written") is False,
        "orders_closed": all(payload.get(k) is False for k in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"fresh dry-cycle validation failed: {failed}")
    return {"path": str(path), "sha256": sha256_file(path), "checks": checks}


def validate_bounded(root: Path, config: Mapping[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path = resolve(root, str(config["bounded_demo_preflight"]))
    payload = load_json(path)
    checks = {
        "decision": payload.get("decision") == BOUNDED_DECISION,
        "pass": payload.get("pass") is True,
        "orders_closed": all(payload.get(k) is False for k in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"bounded preflight validation failed: {failed}")
    design = payload.get("design_contract") or {}
    qualification = design.get("qualification_contract") or payload.get("qualification_contract") or {}
    risk = design.get("risk_contract") or payload.get("risk_contract") or {}
    require(int(qualification.get("maximum_calendar_days") or config["qualification_calendar_days"]) == int(config["qualification_calendar_days"]), "calendar bound mismatch")
    require(int(qualification.get("maximum_resolved_positions") or config["qualification_resolved_positions"]) == int(config["qualification_resolved_positions"]), "resolved-position bound mismatch")
    require(int(risk.get("maximum_concurrent_positions") or 0) == 1, "maximum concurrent position is not one")
    require(int(risk.get("daily_new_positions_cap") or 0) == 1, "daily new-position cap is not one")
    return path, payload, sha256_file(path)


def permit_text(config: Mapping[str, Any], bounded_hash: str, expires_epoch: int) -> str:
    return "\n".join([
        f"schema_version={PERMIT_SCHEMA}",
        "authorized=true",
        f"allowed_demo_login={int(config['allowed_demo_login'])}",
        f"magic_number={int(config['magic_number'])}",
        f"expires_epoch={expires_epoch}",
        f"bounded_preflight_sha256={bounded_hash}",
        "",
    ])


def armed_inputs_text(config: Mapping[str, Any], expires_utc: str) -> str:
    return "\n".join([
        "Attach/reload the existing XAUUSD_BoundedDemoBridge EA on an XAUUSD H1 chart with:",
        "",
        "InpArmed=true",
        f"InpAllowedDemoLogin={int(config['allowed_demo_login'])}",
        f"InpExpectedSymbol={config['expected_symbol']}",
        f"InpMagicNumber={int(config['magic_number'])}",
        f"InpBridgeFolder={config['mt5_bridge_subdir']}",
        f"InpArmingPermitFile={config.get('arming_permit_file', 'arming_permit.txt')}",
        "InpQualificationProbePermitFile=qualification_probe_permit.txt",
        "InpQualificationProbeLockdownFile=qualification_probe_lockdown.txt",
        "InpProbeMinimumExitSeconds=60",
        "InpProbeMaximumExitSeconds=300",
        "InpPollSeconds=1",
        "InpMaximumSlippagePoints=50",
        "InpNotionalToEquity=0.03925991017190415",
        "InpValidatedMaximumNotionalRatio=0.1570396406876166",
        "InpSpreadGuardBps=3.0764778059487488",
        "InpDailyNewPositionsCap=1",
        "InpWeeklyLossPausePct=2.0",
        "InpHardDrawdownKillPct=8.0",
        "InpMaximumResolvedPositions=10",
        "InpMaximumCalendarDays=30",
        "",
        f"Permit expiry UTC: {expires_utc}",
        "Live-account fallback remains forbidden.",
        "",
    ])


def arm(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    ppath = permit_path(config)
    cpath = candidate_path(config)
    require(not ppath.exists(), f"active permit already exists: {ppath}")
    require(not cpath.exists(), f"active candidate exists before arming: {cpath}")

    bridge_app = resolve(root, str(config["bridge_app"]))
    operational_app = resolve(root, str(config["operational_cycle_app"]))
    require(bridge_app.is_file(), f"bridge app missing: {bridge_app}")
    require(operational_app.is_file(), f"operational-cycle app missing: {operational_app}")

    run_checked([sys.executable, str(bridge_app), "runtime-preflight", "--root", str(root)], root)
    runtime = validate_disabled_runtime(root, config)
    run_checked([sys.executable, str(operational_app), "prepare-arm", "--root", str(root)], root)
    pre_arm_refresh = validate_pre_arm_refresh(root, config)
    fresh = validate_fresh_dry(root, config)
    bounded_path, _, bounded_hash = validate_bounded(root, config)

    now = utc_now()
    hours = float(config.get("permit_valid_hours", 720))
    require(0 < hours <= 24 * int(config["qualification_calendar_days"]), "permit duration exceeds qualification bound")
    expires = now + timedelta(hours=hours)
    expires_epoch = int(expires.timestamp())
    text = permit_text(config, bounded_hash, expires_epoch)

    report_dir = resolve(root, str(config["report_dir"]))
    report_permit = report_dir / "arming_permit_ACTIVE_COPY.txt"
    inputs_path = report_dir / f"XAUUSD_BoundedDemoBridge_LOGIN_{int(config['allowed_demo_login'])}_ARMED_INPUTS.txt"
    write_text_atomic(report_permit, text)
    write_text_atomic(inputs_path, armed_inputs_text(config, iso_utc(expires)))
    write_text_atomic(ppath, text)

    # Re-read the active file to catch partial/incorrect writes before reporting success.
    parsed = parse_kv(ppath)
    checks = {
        "schema": parsed.get("schema_version") == PERMIT_SCHEMA,
        "authorized": parsed.get("authorized") == "true",
        "login": int(parsed.get("allowed_demo_login") or 0) == int(config["allowed_demo_login"]),
        "magic": int(parsed.get("magic_number") or 0) == int(config["magic_number"]),
        "expiry": int(parsed.get("expires_epoch") or 0) == expires_epoch,
        "bounded_hash": parsed.get("bounded_preflight_sha256") == bounded_hash,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        ppath.unlink(missing_ok=True)
        raise ArmingError(f"active permit post-write validation failed: {failed}")

    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(now),
        "decision": "PASS_DEMO_ARMING_PERMIT_CREATED_AWAIT_MT5_INPUT_RELOAD",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "expected_symbol": config["expected_symbol"],
        "magic_number": int(config["magic_number"]),
        "permit_expires_utc": iso_utc(expires),
        "permit_expires_epoch": expires_epoch,
        "qualification_calendar_days": int(config["qualification_calendar_days"]),
        "qualification_resolved_positions": int(config["qualification_resolved_positions"]),
        "active_permit_created": True,
        "mt5_runtime_armed": False,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "checks": checks,
        "evidence": {
            "runtime": runtime,
            "pre_arm_refresh": pre_arm_refresh,
            "fresh_dry_cycle": fresh,
            "bounded_preflight": {"path": str(bounded_path), "sha256": bounded_hash},
        },
        "outputs": {
            "active_mt5_permit": str(ppath),
            "report_permit_copy": str(report_permit),
            "armed_inputs": str(inputs_path),
        },
        "required_next_action": "RELOAD_EXISTING_MT5_EA_WITH_ARMED_INPUTS_THEN_RUN_VERIFY",
    }
    write_json_atomic(report_dir / "explicit_demo_arming_summary.json", result)
    return result


def verify(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    ppath = permit_path(config)
    heartbeat = parse_kv(heartbeat_path(config))
    permit = parse_kv(ppath)
    now_epoch = int(utc_now().timestamp())
    checks = {
        "permit_schema": permit.get("schema_version") == PERMIT_SCHEMA,
        "permit_authorized": permit.get("authorized") == "true",
        "permit_login": int(permit.get("allowed_demo_login") or 0) == int(config["allowed_demo_login"]),
        "permit_magic": int(permit.get("magic_number") or 0) == int(config["magic_number"]),
        "permit_unexpired": int(permit.get("expires_epoch") or 0) > now_epoch,
        "ea_program": heartbeat.get("program") == "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR",
        "ea_armed": heartbeat.get("armed") == "true",
        "ea_status": heartbeat.get("status") == "ARMED_RUNTIME_GUARDS_REQUIRED",
        "ea_demo": heartbeat.get("account_trade_mode") == "DEMO",
        "ea_login": int(heartbeat.get("account_login") or 0) == int(config["allowed_demo_login"]),
        "ea_allowed_login": int(heartbeat.get("allowed_demo_login") or 0) == int(config["allowed_demo_login"]),
        "ea_symbol": heartbeat.get("symbol") == config["expected_symbol"],
        "ea_magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "ea_permit_present": heartbeat.get("arming_permit_present") == "true",
        "volume_safe": heartbeat.get("minimum_volume_within_validated_ceiling") == "true",
        "target_executable": heartbeat.get("target_volume_executable") == "true",
        "live_fallback_false": heartbeat.get("live_fallback_allowed") == "false",
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"armed runtime verification failed: {failed}")
    report_dir = resolve(root, str(config["report_dir"]))
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": "PASS_DEMO_BRIDGE_ARMED_RUNTIME_GUARDS_ACTIVE",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": True,
        "demo_candidate_order_path_armed": True,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "checks": checks,
        "heartbeat": heartbeat,
        "required_next_action": "RUN_OPERATIONAL_CYCLE_ONCE_THEN_LOAD_LAUNCHAGENT",
    }
    write_json_atomic(report_dir / "explicit_demo_arming_verification.json", result)
    return result


def disarm(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    removed: list[str] = []
    for path in (permit_path(config), candidate_path(config)):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    report_dir = resolve(root, str(config["report_dir"]))
    disabled_inputs = report_dir / f"XAUUSD_BoundedDemoBridge_LOGIN_{int(config['allowed_demo_login'])}_DISABLED_INPUTS.txt"
    write_text_atomic(disabled_inputs, "\n".join([
        "InpArmed=false",
        f"InpAllowedDemoLogin={int(config['allowed_demo_login'])}",
        f"InpExpectedSymbol={config['expected_symbol']}",
        f"InpMagicNumber={int(config['magic_number'])}",
        "# Reload the EA with InpArmed=false. Existing positions remain managed by the EA.",
        "",
    ]))
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": "DEMO_BRIDGE_PERMIT_REMOVED_RELOAD_EA_DISABLED",
        "pass": True,
        "removed": removed,
        "bridge_runtime_armed": False,
        "current_order_allowed": False,
        "live_order_allowed": False,
        "disabled_inputs": str(disabled_inputs),
        "required_next_action": "RELOAD_EA_WITH_INP_ARMED_FALSE",
    }
    write_json_atomic(report_dir / "explicit_demo_disarm_summary.json", result)
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("arm", "verify", "disarm"))
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="config/xauusd_mt5_demo_activation.json")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports/xauusd_mt5_demo_activation"
    try:
        config = load_json(resolve(root, args.config))
        if args.command == "arm":
            result = arm(root, config)
        elif args.command == "verify":
            result = verify(root, config)
        else:
            result = disarm(root, config)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        payload = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "DEMO_EXPLICIT_ARMING_FAIL_CLOSED",
            "pass": False,
            "current_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json_atomic(report_dir / "explicit_demo_arming_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
