"""Frozen Article 2 benchmark for fail-closed, point-in-time audit pipelines.

The module is deliberately dependency-light and contains no broker connector.
It evaluates three pre-registered architectures against isolated, deterministic
research-pipeline corruptions.  Article 1 trading outcomes are not re-estimated.
"""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

UTC = timezone.utc
ARMS = (
    "NAIVE_LATEST_STATE",
    "POINT_IN_TIME_FAIL_OPEN",
    "POINT_IN_TIME_PROVENANCE_FAIL_CLOSED",
)


@dataclass(frozen=True)
class FaultSpec:
    fault_id: str
    family: str
    expected_check: str
    description: str


@dataclass(frozen=True)
class ArmOutcome:
    arm: str
    case_id: str
    is_fault: bool
    accepted: bool
    detected: bool
    reasons: tuple[str, ...]
    checks: tuple[tuple[str, bool], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "case_id": self.case_id,
            "is_fault": self.is_fault,
            "accepted": self.accepted,
            "detected": self.detected,
            "reasons": list(self.reasons),
            "checks": [{"check_id": key, "pass": value} for key, value in self.checks],
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_aware_utc(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is timezone-naive")
    return parsed.astimezone(UTC)


def base_fixture() -> dict[str, Any]:
    features = [
        {
            "source_id": "CFTC_COT_WEEKLY",
            "observed_at": "2026-08-04T00:00:00Z",
            "available_at": "2026-08-07T19:30:00Z",
            "value": 112345,
            "schema_version": "1.0",
            "revision_policy": "point_in_time_vintage",
            "vintage_id": "2026-08-07T19:30:00Z",
        },
        {
            "source_id": "SCHEDULED_MACRO_EVENT_CALENDAR",
            "observed_at": "2026-08-10T12:30:00Z",
            "available_at": "2026-08-10T12:30:01Z",
            "value": 0.2,
            "schema_version": "1.0",
            "revision_policy": "append_only_release_snapshot",
            "vintage_id": "2026-08-10T12:30:01Z",
        },
        {
            "source_id": "GDELT_NEWS_PANEL_STAGE166F",
            "observed_at": "2026-08-10T13:00:00Z",
            "available_at": "2026-08-10T13:05:00Z",
            "value": 4,
            "schema_version": "1.0",
            "revision_policy": "closed_bucket_snapshot",
            "vintage_id": "2026-08-10T13:05:00Z",
        },
    ]
    bars = [
        {"timestamp": "2026-08-10T13:05:00Z", "gross_bps": 12.0, "cost_bps": 3.0, "net_bps": 9.0},
        {"timestamp": "2026-08-10T13:10:00Z", "gross_bps": -5.0, "cost_bps": 3.0, "net_bps": -8.0},
        {"timestamp": "2026-08-10T13:15:00Z", "gross_bps": 7.5, "cost_bps": 3.0, "net_bps": 4.5},
    ]
    config = {
        "schema_version": "article2-benchmark-v1",
        "bar_interval_minutes": 5,
        "max_artifact_age_hours": 72,
        "required_sources": ["CFTC_COT_WEEKLY", "GDELT_NEWS_PANEL_STAGE166F"],
        "cost_identity_tolerance_bps": 1e-9,
    }
    manifest = {
        "features_sha256": sha256_payload(features),
        "bars_sha256": sha256_payload(bars),
        "config_sha256": sha256_payload(config),
        "created_at": "2026-08-10T13:20:00Z",
    }
    return {
        "decision_time": "2026-08-10T13:20:00Z",
        "features": features,
        "bars": bars,
        "config": config,
        "manifest": manifest,
    }


FAULTS = (
    FaultSpec("FUTURE_DATA_LEAKAGE", "temporal", "AVAILABLE_NOT_AFTER_DECISION", "A feature becomes available after the decision timestamp."),
    FaultSpec("COT_PREPUBLICATION", "temporal", "AVAILABLE_NOT_AFTER_DECISION", "Tuesday COT state is used before Friday publication."),
    FaultSpec("TIMEZONE_SHIFT", "temporal", "TIMESTAMPS_AWARE_UTC", "An availability timestamp loses its UTC offset."),
    FaultSpec("SCHEMA_DRIFT", "schema", "REQUIRED_SCHEMA_FIELDS", "A required availability field disappears."),
    FaultSpec("MANIFEST_TAMPER", "provenance", "DATA_HASH_BINDING", "Feature bytes change without a manifest update."),
    FaultSpec("CONFIG_TAMPER", "provenance", "CONFIG_HASH_BINDING", "The frozen configuration changes without a manifest update."),
    FaultSpec("STALE_ARTIFACT", "freshness", "ARTIFACT_FRESHNESS", "An artifact predates the decision beyond the frozen age limit."),
    FaultSpec("MISSING_EVENT_CONTEXT", "completeness", "REQUIRED_SOURCE_COMPLETENESS", "A required event-guard source is absent."),
    FaultSpec("DUPLICATE_BAR", "market_data", "BAR_TIMESTAMP_UNIQUENESS", "A market-bar timestamp is duplicated."),
    FaultSpec("OFF_GRID_BAR", "market_data", "BAR_GRID_ALIGNMENT", "A bar timestamp falls outside the five-minute grid."),
    FaultSpec("COST_CONTRACT_CORRUPTION", "economics", "COST_IDENTITY", "Net return no longer equals gross return minus cost."),
    FaultSpec("REVISION_WITHOUT_VINTAGE", "temporal", "REVISION_VINTAGE_BINDING", "A revised macro value lacks a point-in-time vintage identifier."),
)


def apply_fault(fixture: Mapping[str, Any], fault_id: str) -> dict[str, Any]:
    case = copy.deepcopy(dict(fixture))
    if fault_id == "FUTURE_DATA_LEAKAGE":
        case["features"][1]["available_at"] = "2026-08-10T13:25:00Z"
    elif fault_id == "COT_PREPUBLICATION":
        case["decision_time"] = "2026-08-06T14:00:00Z"
    elif fault_id == "TIMEZONE_SHIFT":
        case["features"][1]["available_at"] = "2026-08-10T12:30:01"
    elif fault_id == "SCHEMA_DRIFT":
        del case["features"][1]["available_at"]
    elif fault_id == "MANIFEST_TAMPER":
        case["features"][1]["value"] = 999.0
    elif fault_id == "CONFIG_TAMPER":
        case["config"]["bar_interval_minutes"] = 1
    elif fault_id == "STALE_ARTIFACT":
        case["manifest"]["created_at"] = "2026-07-01T00:00:00Z"
    elif fault_id == "MISSING_EVENT_CONTEXT":
        case["features"] = [row for row in case["features"] if row["source_id"] != "GDELT_NEWS_PANEL_STAGE166F"]
        case["manifest"]["features_sha256"] = sha256_payload(case["features"])
    elif fault_id == "DUPLICATE_BAR":
        case["bars"][1]["timestamp"] = case["bars"][0]["timestamp"]
        case["manifest"]["bars_sha256"] = sha256_payload(case["bars"])
    elif fault_id == "OFF_GRID_BAR":
        case["bars"][1]["timestamp"] = "2026-08-10T13:12:00Z"
        case["manifest"]["bars_sha256"] = sha256_payload(case["bars"])
    elif fault_id == "COST_CONTRACT_CORRUPTION":
        case["bars"][0]["net_bps"] = 12.0
        case["manifest"]["bars_sha256"] = sha256_payload(case["bars"])
    elif fault_id == "REVISION_WITHOUT_VINTAGE":
        case["features"][1]["revision_policy"] = "revised_latest"
        case["features"][1]["vintage_id"] = ""
        case["manifest"]["features_sha256"] = sha256_payload(case["features"])
    else:
        raise KeyError(f"unknown fault: {fault_id}")
    return case


def _full_checks(fixture: Mapping[str, Any]) -> list[tuple[str, bool]]:
    config = fixture.get("config", {})
    manifest = fixture.get("manifest", {})
    features = fixture.get("features", [])
    bars = fixture.get("bars", [])
    required_feature_fields = {"source_id", "observed_at", "available_at", "value", "schema_version", "revision_policy", "vintage_id"}
    schema_ok = all(required_feature_fields.issubset(row) for row in features)

    timestamps_ok = True
    available_ok = True
    revision_ok = True
    try:
        decision_time = parse_aware_utc(str(fixture["decision_time"]))
        for row in features:
            observed = parse_aware_utc(str(row.get("observed_at", "")))
            available = parse_aware_utc(str(row.get("available_at", "")))
            available_ok = available_ok and observed <= available <= decision_time
            if "revis" in str(row.get("revision_policy", "")).lower():
                revision_ok = revision_ok and bool(str(row.get("vintage_id", "")).strip())
    except (KeyError, TypeError, ValueError):
        timestamps_ok = False
        available_ok = False

    feature_hash_ok = manifest.get("features_sha256") == sha256_payload(features)
    bars_hash_ok = manifest.get("bars_sha256") == sha256_payload(bars)
    config_hash_ok = manifest.get("config_sha256") == sha256_payload(config)

    freshness_ok = False
    try:
        created = parse_aware_utc(str(manifest.get("created_at", "")))
        decision = parse_aware_utc(str(fixture["decision_time"]))
        age = decision - created
        freshness_ok = timedelta(0) <= age <= timedelta(hours=float(config.get("max_artifact_age_hours", 0)))
    except (KeyError, TypeError, ValueError):
        freshness_ok = False

    present_sources = {str(row.get("source_id", "")) for row in features}
    required_sources = set(map(str, config.get("required_sources", [])))
    sources_ok = required_sources.issubset(present_sources)

    bar_times: list[datetime] = []
    bar_timestamps_ok = True
    try:
        bar_times = [parse_aware_utc(str(row["timestamp"])) for row in bars]
    except (KeyError, TypeError, ValueError):
        bar_timestamps_ok = False
    unique_ok = bar_timestamps_ok and len(bar_times) == len(set(bar_times))
    interval = int(config.get("bar_interval_minutes", 0) or 0)
    grid_ok = bar_timestamps_ok and interval > 0 and all(ts.second == 0 and ts.microsecond == 0 and ts.minute % interval == 0 for ts in bar_times)

    tolerance = float(config.get("cost_identity_tolerance_bps", 0.0) or 0.0)
    cost_ok = True
    try:
        cost_ok = all(abs(float(row["net_bps"]) - (float(row["gross_bps"]) - float(row["cost_bps"]))) <= tolerance for row in bars)
    except (KeyError, TypeError, ValueError):
        cost_ok = False

    return [
        ("REQUIRED_SCHEMA_FIELDS", schema_ok),
        ("TIMESTAMPS_AWARE_UTC", timestamps_ok and bar_timestamps_ok),
        ("AVAILABLE_NOT_AFTER_DECISION", available_ok),
        ("REVISION_VINTAGE_BINDING", revision_ok),
        ("DATA_HASH_BINDING", feature_hash_ok and bars_hash_ok),
        ("CONFIG_HASH_BINDING", config_hash_ok),
        ("ARTIFACT_FRESHNESS", freshness_ok),
        ("REQUIRED_SOURCE_COMPLETENESS", sources_ok),
        ("BAR_TIMESTAMP_UNIQUENESS", unique_ok),
        ("BAR_GRID_ALIGNMENT", grid_ok),
        ("COST_IDENTITY", cost_ok),
    ]


def _pit_fail_open_warnings(fixture: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    try:
        decision = parse_aware_utc(str(fixture["decision_time"]))
        for row in fixture.get("features", []):
            available = parse_aware_utc(str(row["available_at"]))
            if available > decision:
                warnings.append("AVAILABLE_NOT_AFTER_DECISION")
    except (KeyError, TypeError, ValueError):
        warnings.append("TEMPORAL_PARSE_WARNING")
    bars = fixture.get("bars", [])
    stamps = [str(row.get("timestamp", "")) for row in bars]
    if len(stamps) != len(set(stamps)):
        warnings.append("BAR_TIMESTAMP_UNIQUENESS")
    try:
        if any(abs(float(row["net_bps"]) - (float(row["gross_bps"]) - float(row["cost_bps"]))) > 1e-9 for row in bars):
            warnings.append("COST_IDENTITY")
    except (KeyError, TypeError, ValueError):
        warnings.append("COST_PARSE_WARNING")
    return tuple(sorted(set(warnings)))


def evaluate_arm(arm: str, fixture: Mapping[str, Any], case_id: str, is_fault: bool) -> ArmOutcome:
    if arm == "NAIVE_LATEST_STATE":
        return ArmOutcome(arm, case_id, is_fault, True, False, (), ())
    if arm == "POINT_IN_TIME_FAIL_OPEN":
        warnings = _pit_fail_open_warnings(fixture)
        return ArmOutcome(arm, case_id, is_fault, True, bool(warnings), warnings, ())
    if arm == "POINT_IN_TIME_PROVENANCE_FAIL_CLOSED":
        checks = tuple(_full_checks(fixture))
        reasons = tuple(check_id for check_id, passed in checks if not passed)
        return ArmOutcome(arm, case_id, is_fault, not reasons, bool(reasons), reasons, checks)
    raise KeyError(f"unknown benchmark arm: {arm}")


def build_cases(control_count: int = 3) -> list[tuple[str, bool, dict[str, Any]]]:
    clean = base_fixture()
    cases = [(f"CLEAN_CONTROL_{index:02d}", False, copy.deepcopy(clean)) for index in range(1, control_count + 1)]
    cases.extend((spec.fault_id, True, apply_fault(clean, spec.fault_id)) for spec in FAULTS)
    return cases


def outcome_digest(outcomes: Iterable[ArmOutcome]) -> str:
    return sha256_payload([item.as_dict() for item in outcomes])


def _runtime_profile(arm: str, cases: list[tuple[str, bool, dict[str, Any]]], repeats: int) -> dict[str, Any]:
    samples: list[int] = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        for case_id, is_fault, fixture in cases:
            evaluate_arm(arm, fixture, case_id, is_fault)
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, int(0.95 * len(ordered)) - 1))
    return {
        "repeats": repeats,
        "case_count": len(cases),
        "median_total_ns": int(statistics.median(ordered)),
        "p95_total_ns": int(ordered[p95_index]),
        "median_ns_per_case": float(statistics.median(ordered) / len(cases)),
    }


def run_benchmark(repeats: int = 100, control_count: int = 3) -> dict[str, Any]:
    if repeats < 2:
        raise ValueError("repeats must be at least 2")
    cases = build_cases(control_count=control_count)
    outcomes = [evaluate_arm(arm, fixture, case_id, is_fault) for arm in ARMS for case_id, is_fault, fixture in cases]
    repeated = [evaluate_arm(arm, fixture, case_id, is_fault) for arm in ARMS for case_id, is_fault, fixture in cases]
    deterministic = outcome_digest(outcomes) == outcome_digest(repeated)
    metrics: dict[str, Any] = {}
    for arm in ARMS:
        selected = [item for item in outcomes if item.arm == arm]
        faults = [item for item in selected if item.is_fault]
        controls = [item for item in selected if not item.is_fault]
        metrics[arm] = {
            "fault_count": len(faults),
            "control_count": len(controls),
            "fault_detection_rate": sum(item.detected for item in faults) / len(faults),
            "unsafe_acceptance_rate": sum(item.accepted for item in faults) / len(faults),
            "silent_acceptance_rate": sum(item.accepted and not item.detected for item in faults) / len(faults),
            "false_blocking_rate": sum(not item.accepted for item in controls) / len(controls),
            "runtime": _runtime_profile(arm, cases, repeats),
        }
    baseline_ns = metrics["NAIVE_LATEST_STATE"]["runtime"]["median_ns_per_case"]
    for arm in ARMS:
        current = metrics[arm]["runtime"]["median_ns_per_case"]
        metrics[arm]["runtime"]["overhead_ratio_vs_naive"] = current / baseline_ns if baseline_ns else None

    branch_values: dict[str, set[bool]] = {}
    full = [item for item in outcomes if item.arm == "POINT_IN_TIME_PROVENANCE_FAIL_CLOSED"]
    for item in full:
        for check_id, passed in item.checks:
            branch_values.setdefault(check_id, set()).add(passed)
    branch_rows = [
        {"check_id": key, "observed_pass": True in values, "observed_fail": False in values, "both_outcomes_covered": values == {True, False}}
        for key, values in sorted(branch_values.items())
    ]
    return {
        "schema_version": "article2-benchmark-v1",
        "arms": list(ARMS),
        "fault_specs": [spec.__dict__ for spec in FAULTS],
        "outcomes": [item.as_dict() for item in outcomes],
        "metrics": metrics,
        "deterministic_reproduction": deterministic,
        "deterministic_digest_sha256": outcome_digest(outcomes),
        "semantic_branch_coverage": {
            "covered": sum(row["both_outcomes_covered"] for row in branch_rows),
            "total": len(branch_rows),
            "rate": sum(row["both_outcomes_covered"] for row in branch_rows) / len(branch_rows),
            "branches": branch_rows,
        },
    }


def article2_gate(benchmark: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    full = benchmark["metrics"]["POINT_IN_TIME_PROVENANCE_FAIL_CLOSED"]
    if full["fault_detection_rate"] != 1.0:
        reasons.append("FULL_ARM_FAULT_DETECTION_BELOW_100_PERCENT")
    if full["unsafe_acceptance_rate"] != 0.0:
        reasons.append("FULL_ARM_UNSAFE_ACCEPTANCE_NONZERO")
    if full["false_blocking_rate"] != 0.0:
        reasons.append("FULL_ARM_FALSE_BLOCKING_NONZERO")
    if not benchmark.get("deterministic_reproduction"):
        reasons.append("NONDETERMINISTIC_OUTCOMES")
    if benchmark["semantic_branch_coverage"]["rate"] != 1.0:
        reasons.append("SEMANTIC_BRANCH_COVERAGE_BELOW_100_PERCENT")
    if len(benchmark.get("fault_specs", [])) < 10:
        reasons.append("FAULT_MATRIX_TOO_SMALL")
    if len(benchmark.get("arms", [])) != 3:
        reasons.append("THREE_ARM_BENCHMARK_MISSING")
    return not reasons, reasons


def no_execution_connector_tokens() -> bool:
    text = __import__("pathlib").Path(__file__).read_text(encoding="utf-8").lower()
    forbidden = (
        "order" + "send",
        "place" + "_order",
        "send" + "_order",
        "initialize" + "_terminal",
    )
    return all(token not in text for token in forbidden)
