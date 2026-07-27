#!/usr/bin/env python3
"""Login-bound review and dry candidate preview for the disabled XAUUSD MT5 demo bridge.

This module never writes an active arming permit, never writes the active MT5
candidate filename, and never calls a broker API.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

UTC = timezone.utc
PROGRAM = "XAUUSD_MT5_DEMO_LOGIN_BOUND_FRESH_DRY_CYCLE_V1_1_NO_ORDER"
RUNTIME_PROGRAM = "XAUUSD_MT5_BOUNDED_DEMO_BRIDGE_V1_1_VOLUME_DIAGNOSTIC_LOGGING"
BOUNDED_PROGRAM = "XAUUSD_BOUNDED_DEMO_DESIGN_V1_1_RISK_SOURCE_PROVENANCE_REPAIR_NO_ORDER"
BOUNDED_DECISION = "PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH"
PREVIEW_SCHEMA = "XAUUSD_DEMO_ARMING_PERMIT_PREVIEW_V1_NOT_EXECUTABLE"


class ReviewError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ReviewError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReviewError(f"cannot read JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not object: {path}")
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_bridge(root: Path, config: Mapping[str, Any]):
    path = resolve(root, str(config["bridge_app"]))
    require(path.is_file(), f"bridge app missing: {path}")
    spec = importlib.util.spec_from_file_location("xauusd_mt5_demo_bridge_runtime", path)
    require(spec is not None and spec.loader is not None, f"cannot load bridge app: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def mt5_bridge_dir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["mt5_files_dir"])).expanduser() / str(config["mt5_bridge_subdir"])


def active_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    folder = mt5_bridge_dir(config)
    return {
        "arming_permit": folder / "arming_permit.txt",
        "candidate": folder / "demo_candidate.txt",
    }


def quarantine_candidate(config: Mapping[str, Any], report_dir: Path) -> str | None:
    candidate = active_paths(config)["candidate"]
    if not candidate.is_file():
        return None
    quarantine = report_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    target = quarantine / f"demo_candidate.{stamp}.quarantined.txt"
    shutil.move(str(candidate), str(target))
    return str(target)


def validate_runtime(root: Path, config: Mapping[str, Any], now: datetime | None = None) -> tuple[Path, dict[str, Any], dict[str, bool]]:
    path = resolve(root, str(config["runtime_preflight"]))
    require(path.is_file(), f"runtime preflight missing: {path}")
    payload = load_json(path)
    heartbeat = payload.get("heartbeat") or {}
    expected_login = int(config["allowed_demo_login"])
    accepted = set(str(value) for value in config.get("accepted_runtime_decisions", []))
    checks = {
        "program": payload.get("program") == RUNTIME_PROGRAM,
        "decision": payload.get("decision") in accepted,
        "pass": payload.get("pass") is True,
        "runtime_installation_pass": payload.get("runtime_installation_pass") is True,
        "arming_readiness_pass": payload.get("arming_readiness_pass") is True,
        "runtime_failed_checks_empty": payload.get("runtime_failed_checks") == [],
        "arming_failed_checks_empty": payload.get("arming_failed_checks") == [],
        "bridge_disabled": payload.get("bridge_armed") is False,
        "orders_forbidden": all(payload.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
        "account_demo": heartbeat.get("account_trade_mode") == "DEMO",
        "login_bound": int(heartbeat.get("account_login") or 0) == expected_login,
        "symbol": heartbeat.get("symbol") == str(config["expected_symbol"]),
        "magic": int(heartbeat.get("magic_number") or 0) == int(config["magic_number"]),
        "ea_disabled": heartbeat.get("status") == "DISABLED_DEFAULT_NO_ORDER" and str(heartbeat.get("armed")).lower() == "false",
        "active_permit_absent": str(heartbeat.get("arming_permit_present")).lower() == "false" and not active_paths(config)["arming_permit"].is_file(),
        "volume_ready": heartbeat.get("volume_contract_decision") == "READY_UNDER_LOCKED_VOLUME_CONTRACT",
        "target_volume_executable": str(heartbeat.get("target_volume_executable")).lower() == "true",
        "minimum_volume_safe": str(heartbeat.get("minimum_volume_within_validated_ceiling")).lower() == "true",
    }
    generated = parse_time(payload.get("generated_utc"))
    age_hours = ((now or utc_now()).astimezone(UTC) - generated).total_seconds() / 3600.0
    checks["runtime_preflight_fresh"] = -0.1 <= age_hours <= float(config.get("maximum_runtime_preflight_age_hours", 72))
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"runtime review failed checks: {failed}")
    return path, payload, checks


def validate_bounded(root: Path, config: Mapping[str, Any]) -> tuple[Path, dict[str, Any], dict[str, bool]]:
    path = resolve(root, str(config["bounded_demo_preflight"]))
    require(path.is_file(), f"bounded preflight missing: {path}")
    payload = load_json(path)
    checks = {
        "program": payload.get("program") == BOUNDED_PROGRAM,
        "decision": payload.get("decision") == BOUNDED_DECISION,
        "pass": payload.get("pass") is True,
        "orders_forbidden": all(payload.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
        "calendar_horizon": payload.get("operational_checks", {}).get("official_event_calendar_through_exit_horizon") is True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"bounded review failed checks: {failed}")
    return path, payload, checks


def validate_bridge_config(root: Path, config: Mapping[str, Any]) -> tuple[Path, dict[str, Any], dict[str, bool]]:
    path = resolve(root, str(config["bridge_config"]))
    require(path.is_file(), f"bridge config missing: {path}")
    payload = load_json(path)
    arming = payload.get("arming") or {}
    checks = {
        "arming_disabled": arming.get("enabled") is False,
        "allowed_login_still_zero": int(arming.get("allowed_demo_login") or 0) == 0,
        "demo_required": arming.get("require_demo_account") is True,
        "live_fallback_false": arming.get("live_account_fallback_allowed") is False,
        "symbol": payload.get("expected_symbol") == config.get("expected_symbol"),
        "magic": int(payload.get("magic_number") or 0) == int(config["magic_number"]),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"bridge config review failed checks: {failed}")
    return path, payload, checks


def staged_permit_preview(config: Mapping[str, Any], bounded_hash: str, now: datetime) -> str:
    expiry = int((now + timedelta(hours=float(config.get("permit_preview_valid_hours", 24)))).timestamp())
    return "\n".join([
        f"schema_version={PREVIEW_SCHEMA}",
        "authorized=false",
        f"allowed_demo_login={int(config['allowed_demo_login'])}",
        f"magic_number={int(config['magic_number'])}",
        f"expires_epoch={expiry}",
        f"bounded_preflight_sha256={bounded_hash}",
        "order_authorized=false",
        "active_mt5_permit=false",
        "",
    ])


def reviewed_inputs(config: Mapping[str, Any]) -> str:
    return "\n".join([
        "InpArmed=false",
        f"InpAllowedDemoLogin={int(config['allowed_demo_login'])}",
        f"InpExpectedSymbol={config['expected_symbol']}",
        f"InpMagicNumber={int(config['magic_number'])}",
        "InpArmingPermitFile=arming_permit.txt",
        "# No active permit is created by this package.",
        "# Do not set InpArmed=true during the dry-cycle phase.",
        "",
    ])


def build_review(root: Path, config: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    runtime_path, runtime, runtime_checks = validate_runtime(root, config, current)
    bounded_path, bounded, bounded_checks = validate_bounded(root, config)
    bridge_config_path, _, bridge_checks = validate_bridge_config(root, config)
    report_dir = resolve(root, str(config["report_dir"]))
    quarantined = quarantine_candidate(config, report_dir)
    require(not active_paths(config)["arming_permit"].is_file(), "active arming permit exists after review")
    bounded_hash = sha256_file(bounded_path)
    permit_preview_path = report_dir / "staged_arming_permit_PREVIEW_ONLY.txt"
    inputs_path = report_dir / f"XAUUSD_BoundedDemoBridge_LOGIN_{int(config['allowed_demo_login'])}_DISABLED_INPUTS.txt"
    write_text(permit_preview_path, staged_permit_preview(config, bounded_hash, current))
    write_text(inputs_path, reviewed_inputs(config))
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(current),
        "decision": "PASS_LOGIN_BOUND_ARMING_REVIEW_DRY_ONLY_NO_ORDER",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": False,
        "active_arming_permit_created": False,
        "active_candidate_written": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "checks": {
            "runtime": runtime_checks,
            "bounded": bounded_checks,
            "bridge_config": bridge_checks,
        },
        "runtime_decision_accepted": runtime.get("decision"),
        "runtime_arming_readiness_pass": runtime.get("arming_readiness_pass"),
        "quarantined_active_candidate": quarantined,
        "source_hashes": {
            "runtime_preflight": sha256_file(runtime_path),
            "bounded_demo_preflight": bounded_hash,
            "bridge_config": sha256_file(bridge_config_path),
        },
        "outputs": {
            "reviewed_disabled_inputs": str(inputs_path),
            "staged_non_executable_permit_preview": str(permit_preview_path),
        },
        "required_next_action": "RUN_LOGIN_BOUND_DRY_CANDIDATE_CYCLE_NO_ORDER",
    }
    write_json(report_dir / "mt5_demo_login_bound_arming_review.json", result)
    return result


def build_preview_payload(bridge: Any, root: Path, bridge_config: Mapping[str, Any], bounded_path: Path, bounded: Mapping[str, Any], waiting: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    signal_epoch = int(waiting["signal_timestamp_ms"]) // 1000
    design = bounded["design_contract"]
    signal_contract = design["signal_contract"]
    h1 = bridge.h1_contract(
        resolve(root, str(bridge_config["aligned_db"])),
        str(bridge_config["aligned_h1_table"]),
        signal_epoch,
        int(signal_contract["entry_offset_h1_rows"]),
        int(signal_contract["exit_offset_h1_rows"]),
    )
    target_entry = datetime.fromtimestamp(h1.entry_epoch, tz=UTC)
    event_ok, event_reason, matches = bridge.event_guard(resolve(root, str(bridge_config["official_event_csv"])), target_entry)
    current_epoch = int(now.timestamp())
    grace = int((bridge_config.get("candidate") or {}).get("entry_grace_seconds", 60))
    max_lead = int((bridge_config.get("candidate") or {}).get("maximum_lead_seconds", 3900))
    lead = h1.entry_epoch - current_epoch
    if lead > max_lead:
        return {"status": "WAIT_FOR_TARGET_ENTRY_WINDOW", "candidate_previewed": False, "lead_seconds": lead, "maximum_lead_seconds": max_lead}
    if current_epoch > h1.entry_epoch + grace:
        return {"status": "STALE_ENTRY_WINDOW_BLOCKED", "candidate_previewed": False, "target_entry_utc": iso_utc(target_entry)}
    if not event_ok:
        return {"status": "EVENT_BLACKOUT_BLOCKED", "candidate_previewed": False, "event_matches": matches}
    bounded_hash = sha256_file(bounded_path)
    risk = design["risk_contract"]
    seed = f"{waiting['signal_key']}|{waiting['side']}|{bounded_hash}|{bridge_config['magic_number']}|DRY"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "status": "CANDIDATE_PREVIEW_READY_NOT_EMITTED",
        "candidate_previewed": True,
        "preview": {
            "schema_version": "XAUUSD_DEMO_CANDIDATE_DRY_PREVIEW_V1_NOT_EXECUTABLE",
            "intent_id": f"DRY_{waiting['signal_key']}_{digest[:12]}",
            "synthetic": False,
            "created_utc": iso_utc(now),
            "symbol": str(bridge_config["expected_symbol"]),
            "side": str(waiting["side"]),
            "probability_up": float(waiting["probability_up"]),
            "signal_utc": str(waiting["signal_utc"]),
            "target_entry_utc": iso_utc(target_entry),
            "target_exit_utc": iso_utc(datetime.fromtimestamp(h1.projected_exit_epoch, tz=UTC)),
            "exit_after_h1_bars": h1.exit_after_h1_bars,
            "notional_to_equity": float(risk["initial_demo_notional_to_equity"]),
            "spread_guard_bps": float(risk["observed_entry_spread_guard_bps"]),
            "event_guard_pass": True,
            "event_guard_reason": event_reason,
            "execution_mode": "DRY_PREVIEW_ONLY",
            "python_order_authorized": False,
            "mt5_candidate_file_authorized": False,
        },
    }




def controlled_freshness_payload(controlled: Mapping[str, Any]) -> Mapping[str, Any]:
    value = controlled.get("operational_freshness")
    if isinstance(value, Mapping):
        return value
    run_result = controlled.get("run_result") or {}
    value = run_result.get("freshness")
    return value if isinstance(value, Mapping) else {}


def validate_controlled_freshness(
    root: Path,
    bridge_config: Mapping[str, Any],
    config: Mapping[str, Any],
    now: datetime,
    not_before: datetime | None = None,
) -> dict[str, Any]:
    summary_path = resolve(root, str(bridge_config["controlled_paper_summary"]))
    require(summary_path.is_file(), f"controlled-paper summary missing: {summary_path}")
    controlled = load_json(summary_path)
    generated = parse_time(controlled.get("generated_utc"))
    freshness = controlled_freshness_payload(controlled)
    run_result = controlled.get("run_result") or {}
    latest_h1_text = run_result.get("latest_h1_utc") or (freshness.get("timestamps_utc") or {}).get("aligned_h1")
    latest_h1 = parse_time(latest_h1_text)
    summary_age = (now - generated).total_seconds() / 60.0
    h1_age = (now - latest_h1).total_seconds() / 60.0
    max_summary_age = float(config.get("maximum_controlled_summary_age_minutes_open_market", 180))
    max_h1_age = float(config.get("maximum_aligned_h1_age_minutes_open_market", 180))
    checks = {
        "program": controlled.get("program") == "XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY",
        "orders_forbidden": all(controlled.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")),
        "paper_log_only": controlled.get("paper_log_only") is True,
        "freshness_pass": freshness.get("pass") is True,
        "freshness_decision": freshness.get("decision") == "PASS_OPERATIONAL_FRESHNESS_OPEN_MARKET",
        "market_expected_open": freshness.get("market_expected_open") is True,
        "summary_age": -1.0 <= summary_age <= max_summary_age,
        "aligned_h1_age": -15.0 <= h1_age <= max_h1_age,
        "generated_after_refresh_start": not_before is None or generated >= not_before - timedelta(seconds=30),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"controlled-paper freshness failed checks: {failed}")
    return {
        "path": str(summary_path),
        "sha256": sha256_file(summary_path),
        "generated_utc": iso_utc(generated),
        "latest_h1_utc": iso_utc(latest_h1),
        "summary_age_minutes": summary_age,
        "aligned_h1_age_minutes": h1_age,
        "checks": checks,
    }


def stage180_candidates(root: Path, config: Mapping[str, Any]) -> list[Path]:
    found: dict[str, Path] = {}
    explicit = str(config.get("stage180_script") or "").strip()
    if explicit:
        path = resolve(root, explicit).resolve()
        if path.is_file():
            found[str(path)] = path
    for pattern in config.get("stage180_script_globs", ["app/stage180*.py"]):
        for path in root.glob(str(pattern)):
            if path.is_file() and "__pycache__" not in path.parts:
                found[str(path.resolve())] = path.resolve()
    return sorted(found.values(), key=lambda p: str(p))


def discover_stage180_script(root: Path, config: Mapping[str, Any]) -> Path:
    candidates = stage180_candidates(root, config)
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        score = 0
        if "STAGE180_FROZEN_MODEL_SHADOW" in text:
            score += 2
        if "PASS_STAGE180_FROZEN_ALIGNMENT_REFRESH" in text:
            score += 2
        if "stage180_summary.json" in text:
            score += 1
        if score >= 3:
            scored.append((score, path))
    require(scored, "Stage180 runner discovery failed: no matching app/stage180*.py")
    best_score = max(score for score, _ in scored)
    best = [path for score, path in scored if score == best_score]
    require(len(best) == 1, f"Stage180 runner discovery ambiguous: {[str(path) for path in best]}")
    return best[0]


def stream_command(name: str, command: Sequence[str], root: Path, tail_limit: int = 24000) -> dict[str, Any]:
    print(f"[START] {name}: {' '.join(command)}", flush=True)
    started = utc_now()
    process = subprocess.Popen(
        list(command), cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    chunks: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            chunks.append(line)
            joined = "".join(chunks)
            if len(joined) > tail_limit:
                chunks = [joined[-tail_limit:]]
    finally:
        process.stdout.close()
    returncode = process.wait()
    elapsed = (utc_now() - started).total_seconds()
    result = {
        "name": name,
        "command": list(command),
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": "".join(chunks)[-tail_limit:],
    }
    require(returncode == 0, f"external step failed: {json.dumps(result, ensure_ascii=False)}")
    print(f"[DONE ] {name} elapsed={elapsed:.2f}s", flush=True)
    return result


def validate_stage180_freshness(root: Path, config: Mapping[str, Any], now: datetime, not_before: datetime) -> dict[str, Any]:
    path = resolve(root, str(config.get("stage180_summary", "reports/stage180_frozen_model_shadow/stage180_summary.json")))
    require(path.is_file(), f"Stage180 summary missing: {path}")
    payload = load_json(path)
    generated = parse_time(payload.get("generated_utc"))
    latest_h1 = parse_time(payload.get("aligned_last_complete_bar_utc"))
    age_minutes = (now - latest_h1).total_seconds() / 60.0
    checks = {
        "decision": payload.get("decision") == "STAGE180_FROZEN_MODEL_SHADOW_ACTIVE_NO_ORDER",
        "generated_after_refresh_start": generated >= not_before - timedelta(seconds=30),
        "aligned_h1_fresh": -15.0 <= age_minutes <= float(config.get("maximum_aligned_h1_age_minutes_open_market", 180)),
        "orders_forbidden": all(payload.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed", "paper_order_allowed", "execution_allowed")),
        "shadow_allowed": payload.get("shadow_observation_allowed") is True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f"Stage180 freshness failed checks: {failed}")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "generated_utc": iso_utc(generated),
        "latest_h1_utc": iso_utc(latest_h1),
        "aligned_h1_age_minutes": age_minutes,
        "checks": checks,
    }


def dry_cycle(
    root: Path,
    config: Mapping[str, Any],
    now: datetime | None = None,
    controlled_not_before: datetime | None = None,
) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    review = build_review(root, config, current)
    bridge = load_bridge(root, config)
    bridge_config = load_json(resolve(root, str(config["bridge_config"])))
    bounded_path = resolve(root, str(config["bounded_demo_preflight"]))
    bounded = load_json(bounded_path)
    controlled_summary_path = resolve(root, str(bridge_config["controlled_paper_summary"]))
    controlled_preflight_path = resolve(root, str(bridge_config["controlled_paper_preflight"]))
    ledger_path = resolve(root, str(bridge_config["controlled_paper_ledger"]))
    for label, path in (("controlled-paper summary", controlled_summary_path), ("controlled-paper preflight", controlled_preflight_path), ("controlled-paper ledger", ledger_path)):
        require(path.is_file(), f"{label} missing: {path}")
    controlled = load_json(controlled_summary_path)
    controlled_preflight = load_json(controlled_preflight_path)
    controlled_freshness = validate_controlled_freshness(root, bridge_config, config, current, controlled_not_before)
    require(controlled.get("program") == bridge.CONTROLLED_PROGRAM, "controlled-paper program mismatch")
    require(controlled.get("direction_policy") == "BIDIRECTIONAL_PROBABILITY_TAILS", "controlled-paper direction mismatch")
    require(controlled.get("paper_log_only") is True, "controlled-paper must remain paper-only")
    require(all(controlled.get(key) is False for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed")), "controlled-paper order boundary is open")
    risk_state = controlled.get("risk_state") or {}
    require(risk_state.get("hard_kill_latched") is False, "controlled-paper hard kill is latched")
    require(risk_state.get("weekly_pause_active") is False, "controlled-paper weekly pause is active")
    require(controlled_preflight.get("program") == bridge.CONTROLLED_PROGRAM, "controlled-paper preflight program mismatch")
    require(controlled_preflight.get("decision") == bridge.CONTROLLED_PREFLIGHT_DECISION and controlled_preflight.get("pass") is True, "controlled-paper preflight is not passed")
    waiting = bridge.latest_waiting_signal(ledger_path)
    if waiting is None:
        preview_result = {"status": "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL", "candidate_previewed": False}
    else:
        preview_result = build_preview_payload(bridge, root, bridge_config, bounded_path, bounded, waiting, current)
    active = active_paths(config)
    require(not active["arming_permit"].is_file(), "dry cycle detected active arming permit")
    require(not active["candidate"].is_file(), "dry cycle wrote or left active MT5 candidate")
    report_dir = resolve(root, str(config["report_dir"]))
    preview_path = report_dir / "mt5_demo_dry_candidate_preview.json"
    write_json(preview_path, preview_result)
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(current),
        "decision": "PASS_LOGIN_BOUND_DRY_CANDIDATE_CYCLE_FRESH_SOURCE_NO_ORDER",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": False,
        "active_arming_permit_created": False,
        "active_candidate_written": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "review_decision": review["decision"],
        "controlled_source_freshness": controlled_freshness,
        "dry_cycle": preview_result,
        "outputs": {
            "review": str(report_dir / "mt5_demo_login_bound_arming_review.json"),
            "candidate_preview": str(preview_path),
        },
        "required_next_action": (
            "READY_FOR_EXPLICIT_DEMO_ARMING_REVIEW_NO_FORWARD_SIGNAL_WAIT"
            if preview_result.get("status") == "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL"
            else "REVIEW_FRESH_DRY_CYCLE_RESULT_BEFORE_ANY_ACTIVE_PERMIT_OR_ARMING"
        ),
    }
    write_json(report_dir / "mt5_demo_login_bound_dry_cycle_summary.json", result)
    return result


def fresh_dry_cycle(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    started = utc_now()
    active = active_paths(config)
    require(not active["arming_permit"].is_file(), "fresh dry cycle blocked by active arming permit")
    require(not active["candidate"].is_file(), "fresh dry cycle blocked by active candidate")
    stage180_script = discover_stage180_script(root, config)
    controlled_app = resolve(root, str(config.get("controlled_paper_app", "app/xauusd_controlled_paper.py")))
    require(controlled_app.is_file(), f"controlled-paper app missing: {controlled_app}")
    steps = [
        stream_command("Stage180 frozen-model refresh", [sys.executable, str(stage180_script)], root),
    ]
    stage180_evidence = validate_stage180_freshness(root, config, utc_now(), started)
    steps.append(stream_command("Controlled-paper preflight", [sys.executable, str(controlled_app), "preflight", "--root", str(root)], root))
    steps.append(stream_command("Controlled-paper fresh run", [sys.executable, str(controlled_app), "run", "--root", str(root)], root))
    bridge_config = load_json(resolve(root, str(config["bridge_config"])))
    controlled_evidence = validate_controlled_freshness(root, bridge_config, config, utc_now(), started)
    dry = dry_cycle(root, config, utc_now(), controlled_not_before=started)
    report_dir = resolve(root, str(config["report_dir"]))
    result = {
        "program": PROGRAM,
        "generated_utc": iso_utc(),
        "decision": "PASS_LOGIN_BOUND_FRESH_DRY_CANDIDATE_CYCLE_NO_ORDER",
        "pass": True,
        "allowed_demo_login": int(config["allowed_demo_login"]),
        "bridge_armed": False,
        "active_arming_permit_created": False,
        "active_candidate_written": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "stage180_script": str(stage180_script),
        "refresh_steps": steps,
        "stage180_freshness": stage180_evidence,
        "controlled_source_freshness": controlled_evidence,
        "dry_cycle": dry["dry_cycle"],
        "dry_cycle_decision": dry["decision"],
        "required_next_action": dry["required_next_action"],
        "outputs": {
            "fresh_summary": str(report_dir / "mt5_demo_login_bound_fresh_dry_cycle_summary.json"),
            "dry_summary": str(report_dir / "mt5_demo_login_bound_dry_cycle_summary.json"),
            "candidate_preview": str(report_dir / "mt5_demo_dry_candidate_preview.json"),
        },
    }
    require(not active["arming_permit"].is_file(), "fresh dry cycle created active permit")
    require(not active["candidate"].is_file(), "fresh dry cycle created active candidate")
    write_json(report_dir / "mt5_demo_login_bound_fresh_dry_cycle_summary.json", result)
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("review", "dry-cycle", "fresh-dry-cycle"), nargs="?", default="review")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="config/xauusd_mt5_demo_login_bound_review.json")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports/xauusd_mt5_demo_bridge"
    try:
        config = load_json(resolve(root, args.config))
        result = build_review(root, config) if args.command == "review" else (fresh_dry_cycle(root, config) if args.command == "fresh-dry-cycle" else dry_cycle(root, config))
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        failure = report_dir / "mt5_demo_login_bound_review_failure.json"
        if failure.exists():
            failure.unlink()
        return 0
    except Exception as exc:
        payload = {
            "program": PROGRAM,
            "generated_utc": iso_utc(),
            "decision": "MT5_DEMO_LOGIN_BOUND_REVIEW_FAIL_CLOSED",
            "pass": False,
            "bridge_armed": False,
            "active_arming_permit_created": False,
            "active_candidate_written": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_json(report_dir / "mt5_demo_login_bound_review_failure.json", payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
