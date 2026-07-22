#!/usr/bin/env python3
"""Historical-as-of replay for the frozen XAUUSD commercial formulation.

The replay consumes the canonical Commercial Closure execution ledger, proves
its bidirectional probability-tail side contract, validates exact AMarkets H1
``i+1`` entry and ``i+24`` exit semantics, ties the ledger back to the saved
commercial summary, and then applies the controlled-paper risk guards without
waiting for future signals.

No broker library is imported and no order path exists in this module.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import statistics
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V5_SOURCE_PROVEN_COST_CONTRACT_REPAIR"
LOCKED = {
    "upper_probability_threshold": 0.60,
    "lower_probability_threshold": 0.40,
    "entry_offset_h1_rows": 1,
    "exit_offset_h1_rows": 24,
    "maximum_notional_to_equity": 0.1570396406876166,
    "maximum_concurrent_positions": 1,
    "daily_new_positions_cap": 1,
    "weekly_loss_pause_equity_pct": 2.0,
    "hard_drawdown_kill_switch_equity_pct": 8.0,
    "observed_entry_spread_guard_bps": 3.0764778059487488,
    "expected_signals": 168,
    "expected_evaluated": 146,
    "expected_missing": 22,
    "stress_8_floor_bps": 8.0,
    "stress_10_floor_bps": 10.0,
    "stress_8_spread_addon_bps": 4.0,
    "stress_10_spread_addon_bps": 6.0,
}
NEGATIVE_STATUS_TOKENS = (
    "UNEVALUATED",
    "MISSING",
    "NO_COVERAGE",
    "UNAVAILABLE",
    "INCOMPLETE",
    "SIGNAL_H1_TIMESTAMP_MISSING",
)


class ReplayError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)
    if value is None or isinstance(value, bool):
        raise ValueError(f"invalid timestamp: {value!r}")
    if isinstance(value, (int, float)):
        number = float(value)
        if abs(number) >= 1e14:
            number /= 1_000_000.0
        elif abs(number) >= 1e11:
            number /= 1_000.0
        return datetime.fromtimestamp(number, tz=UTC)
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    try:
        return parse_timestamp(float(text))
    except ValueError:
        pass
    normalized = text.replace("/", "-")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"unparseable timestamp: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def timestamp_ms(value: Any) -> int:
    return int(round(parse_timestamp(value).timestamp() * 1000.0))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp = handle.name
    os.replace(temp, path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
        temp = handle.name
    os.replace(temp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReplayError(f"JSON object required: {path}")
    return payload


def normalized_status(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def classify_status(value: Any) -> str:
    status = normalized_status(value)
    if any(token in status for token in NEGATIVE_STATUS_TOKENS):
        return "MISSING"
    if status == "EVALUATED" or status.startswith("EVALUATED_"):
        return "EVALUATED"
    return "UNKNOWN"


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    lookup = {str(key).lower(): value for key, value in row.items()}
    for alias in aliases:
        value = lookup.get(alias.lower())
        if value not in (None, ""):
            return value
    return None


def canonical_rank(path: Path) -> tuple[int, int, str]:
    text = str(path).lower()
    penalty = 0
    for token in ("invalid", "archive", "backup", "old", "deprecated", "clock_horizon"):
        if token in text:
            penalty += 100
    bonus = -50 if "commercial_closure_sprint" in text and "invalid" not in text else 0
    return (penalty + bonus, len(path.parts), str(path))


def resolve_configured_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def locate_execution_ledger(root: Path, configured: str | None = None) -> Path:
    if configured:
        path = resolve_configured_path(root, configured)
        if not path.is_file():
            raise ReplayError(f"configured execution ledger missing: {path}")
        return path
    matches = [path.resolve() for path in root.glob("reports/**/*execution_ledger.csv") if path.is_file()]
    matches += [path.resolve() for path in root.glob("data/**/*execution_ledger.csv") if path.is_file()]
    matches = sorted(set(matches), key=canonical_rank)
    if not matches:
        raise ReplayError("commercial closure execution ledger not found")
    for path in matches:
        rows = read_csv(path)
        headers = set(rows[0].keys()) if rows else set()
        if len(rows) == LOCKED["expected_signals"] and {
            "status",
            "normal_net_bps",
            "entry_open",
            "exit_close",
            "direction",
            "probability_up",
        }.issubset(headers):
            return path
    raise ReplayError(f"no canonical 168-row execution ledger found; candidates={[str(p) for p in matches]}")


def locate_commercial_summary(root: Path, configured: str | None = None) -> Path:
    if configured:
        path = resolve_configured_path(root, configured)
        if not path.is_file():
            raise ReplayError(f"configured commercial summary missing: {path}")
        return path
    matches = [path.resolve() for path in root.glob("reports/**/commercial_closure_summary.json") if path.is_file()]
    matches += [path.resolve() for path in root.glob("data/**/commercial_closure_summary.json") if path.is_file()]
    matches = sorted(set(matches), key=canonical_rank)
    for path in matches:
        try:
            payload = read_json(path)
        except Exception:
            continue
        if (
            payload.get("candidate") == "logistic__direction_24h"
            and int(payload.get("signals_total", -1)) == LOCKED["expected_signals"]
            and int(payload.get("execution_evaluated_trades", -1)) == LOCKED["expected_evaluated"]
        ):
            return path
    raise ReplayError(f"canonical commercial closure summary not found; candidates={[str(p) for p in matches]}")


def dynamic_import(path: Path, name: str = "xauusd_cp_runtime") -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReplayError(f"cannot import runtime module: {path}")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def normalize_direction_metadata(value: Any) -> str:
    """Normalize the ledger's ``direction`` field as metadata only.

    The Commercial Closure ledger's executable side is encoded by the frozen
    probability tails and proved by signed execution P&L.  The generic
    ``direction`` column is not a side contract and must never override those
    two stronger pieces of evidence.
    """
    token = normalized_status(value)
    return token or "<EMPTY>"


def side_from_probability(probability_up: float) -> str:
    if probability_up + 1e-12 >= LOCKED["upper_probability_threshold"]:
        return "LONG"
    if probability_up - 1e-12 <= LOCKED["lower_probability_threshold"]:
        return "SHORT"
    return "NEUTRAL"


@dataclass(frozen=True)
class ReplaySignal:
    source_row: int
    signal_ms: int
    signal_utc: str
    entry_ms: int
    entry_utc: str
    exit_ms: int
    exit_utc: str
    probability_up: float
    side: str
    direction_metadata: str
    observed_spread_bps: float
    execution_gross_bps: float
    normal_net_bps: float
    severe_net_bps: float
    stress_8_net_bps: float
    stress_10_net_bps: float
    entry_open: float
    exit_close: float
    source_period: str
    fold: str


@dataclass
class TrackState:
    name: str
    event_mode: str
    equity: float = 1.0
    peak_equity: float = 1.0
    hard_kill: bool = False
    active: list[ReplaySignal] | None = None
    entries_by_date: Counter | None = None
    weekly_pnl: defaultdict | None = None
    rows: list[dict[str, Any]] | None = None
    equity_curve: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.active = []
        self.entries_by_date = Counter()
        self.weekly_pnl = defaultdict(float)
        self.rows = []
        self.equity_curve = []

    def resolve_until(self, now_ms: int) -> None:
        remaining: list[ReplaySignal] = []
        for signal in sorted(self.active or [], key=lambda item: item.exit_ms):
            if signal.exit_ms > now_ms:
                remaining.append(signal)
                continue
            pnl_fraction = signal.normal_net_bps / 10000.0 * LOCKED["maximum_notional_to_equity"]
            before = self.equity
            self.equity *= 1.0 + pnl_fraction
            self.peak_equity = max(self.peak_equity, self.equity)
            drawdown = max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)
            if drawdown >= LOCKED["hard_drawdown_kill_switch_equity_pct"]:
                self.hard_kill = True
            week = parse_timestamp(signal.exit_utc).isocalendar()
            week_key = f"{week.year}-W{week.week:02d}"
            self.weekly_pnl[week_key] += pnl_fraction * 100.0
            self.rows.append(
                {
                    "track": self.name,
                    "source_row": signal.source_row,
                    "signal_utc": signal.signal_utc,
                    "entry_utc": signal.entry_utc,
                    "exit_utc": signal.exit_utc,
                    "side": signal.side,
                    "direction_metadata": signal.direction_metadata,
                    "probability_up": signal.probability_up,
                    "status": "RESOLVED",
                    "reason": "",
                    "execution_gross_bps": signal.execution_gross_bps,
                    "normal_net_bps": signal.normal_net_bps,
                    "severe_net_bps": signal.severe_net_bps,
                    "stress_8_net_bps": signal.stress_8_net_bps,
                    "stress_10_net_bps": signal.stress_10_net_bps,
                    "equity_before": before,
                    "equity_after": self.equity,
                    "drawdown_pct": drawdown,
                }
            )
            self.equity_curve.append(
                {
                    "track": self.name,
                    "exit_utc": signal.exit_utc,
                    "equity": self.equity,
                    "peak_equity": self.peak_equity,
                    "drawdown_pct": drawdown,
                }
            )
        self.active = remaining

    def process(self, signal: ReplaySignal, event_allowed: bool, event_reason: str) -> None:
        self.resolve_until(signal.signal_ms)
        week = parse_timestamp(signal.entry_utc).isocalendar()
        week_key = f"{week.year}-W{week.week:02d}"
        reason = ""
        if self.hard_kill:
            reason = "HARD_DRAWDOWN_KILL_SWITCH_ACTIVE"
        elif self.weekly_pnl[week_key] <= -LOCKED["weekly_loss_pause_equity_pct"]:
            reason = "WEEKLY_LOSS_PAUSE_ACTIVE"
        elif len(self.active or []) >= LOCKED["maximum_concurrent_positions"]:
            reason = "MAX_CONCURRENT_POSITION_GUARD"
        elif self.entries_by_date[signal.entry_utc[:10]] >= LOCKED["daily_new_positions_cap"]:
            reason = "DAILY_NEW_POSITION_CAP"
        elif signal.observed_spread_bps > LOCKED["observed_entry_spread_guard_bps"]:
            reason = "SPREAD_GUARD"
        elif self.event_mode == "STRICT" and not event_allowed:
            reason = event_reason
        if reason:
            self.rows.append(
                {
                    "track": self.name,
                    "source_row": signal.source_row,
                    "signal_utc": signal.signal_utc,
                    "entry_utc": signal.entry_utc,
                    "exit_utc": signal.exit_utc,
                    "side": signal.side,
                    "direction_metadata": signal.direction_metadata,
                    "probability_up": signal.probability_up,
                    "status": "BLOCKED",
                    "reason": reason,
                    "execution_gross_bps": signal.execution_gross_bps,
                    "normal_net_bps": signal.normal_net_bps,
                    "severe_net_bps": signal.severe_net_bps,
                    "stress_8_net_bps": signal.stress_8_net_bps,
                    "stress_10_net_bps": signal.stress_10_net_bps,
                    "equity_before": self.equity,
                    "equity_after": self.equity,
                    "drawdown_pct": max(
                        0.0,
                        (self.peak_equity - self.equity) / self.peak_equity * 100.0,
                    ),
                }
            )
            return
        self.entries_by_date[signal.entry_utc[:10]] += 1
        self.active.append(signal)

    def finish(self) -> None:
        self.resolve_until(2**63 - 1)


def load_runtime_context(root: Path, config: Mapping[str, Any]) -> tuple[Any, Any, Any, list[Any]]:
    runtime_path = root / "app/xauusd_controlled_paper.py"
    if not runtime_path.is_file():
        raise ReplayError(f"controlled-paper runtime missing: {runtime_path}")
    runtime = dynamic_import(runtime_path)
    db_path = root / config["aligned_db"]
    market = runtime.MarketDatabase(db_path)
    h1_spec, _m5_spec, _diagnostics = market.discover()
    h1_bars = market.load_all(h1_spec)
    if not h1_bars:
        market.close()
        raise ReplayError("aligned H1 table is empty")
    return runtime, market, h1_spec, h1_bars


def extract_timestamp(row: Mapping[str, Any], aliases: Sequence[str]) -> int:
    value = first_present(row, aliases)
    if value in (None, ""):
        raise ReplayError(f"timestamp field missing; aliases={aliases}")
    return timestamp_ms(value)


def bps_diff(actual: float, expected: float) -> float:
    return abs(actual / expected - 1.0) * 10000.0 if expected else float("inf")


def absolute_close(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def additive_max_drawdown_bps(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for value in values:
        cumulative += float(value)
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def profit_factor(values: Sequence[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def metric_block(values: Sequence[float]) -> dict[str, Any]:
    clean = [float(value) for value in values]
    return {
        "trades": len(clean),
        "mean_bps": statistics.mean(clean) if clean else None,
        "median_bps": statistics.median(clean) if clean else None,
        "win_rate": sum(value > 0 for value in clean) / len(clean) if clean else None,
        "profit_factor": profit_factor(clean),
        "total_bps": sum(clean),
        "max_drawdown_bps": additive_max_drawdown_bps(clean),
    }


def source_proven_stress_contract(
    execution_gross_bps: float,
    observed_spread_bps: float,
    stress_8_net_bps: float,
    stress_10_net_bps: float,
    *,
    tolerance_bps: float,
) -> dict[str, Any]:
    """Validate the exact frozen Commercial Closure stress formula.

    Source: ``app/commercial_closure_sprint.py`` lines 560-565 in the
    forensic package supplied on 2026-07-22.
    """
    stress_8_cost_bps = max(
        LOCKED["stress_8_floor_bps"],
        observed_spread_bps + LOCKED["stress_8_spread_addon_bps"],
    )
    stress_10_cost_bps = max(
        LOCKED["stress_10_floor_bps"],
        observed_spread_bps + LOCKED["stress_10_spread_addon_bps"],
    )
    expected_8 = execution_gross_bps - stress_8_cost_bps
    expected_10 = execution_gross_bps - stress_10_cost_bps
    return {
        "pass": (
            abs(expected_8 - stress_8_net_bps) <= tolerance_bps
            and abs(expected_10 - stress_10_net_bps) <= tolerance_bps
        ),
        "stress_8_cost_bps": stress_8_cost_bps,
        "stress_10_cost_bps": stress_10_cost_bps,
        "expected_stress_8_net_bps": expected_8,
        "expected_stress_10_net_bps": expected_10,
        "stress_8_parity": abs(expected_8 - stress_8_net_bps) <= tolerance_bps,
        "stress_10_parity": abs(expected_10 - stress_10_net_bps) <= tolerance_bps,
        "spread_plus_slippage_branch": (
            observed_spread_bps + LOCKED["stress_8_spread_addon_bps"]
            > LOCKED["stress_8_floor_bps"]
            or observed_spread_bps + LOCKED["stress_10_spread_addon_bps"]
            > LOCKED["stress_10_floor_bps"]
        ),
    }


def validate_and_build_signals(
    rows: Sequence[Mapping[str, Any]],
    h1_bars: Sequence[Any],
    *,
    gross_parity_tolerance_bps: float = 0.25,
    price_parity_tolerance_bps: float = 0.10,
    net_parity_tolerance_bps: float = 0.01,
) -> tuple[list[ReplaySignal], list[dict[str, Any]], dict[str, Any]]:
    counts = Counter(classify_status(row.get("status")) for row in rows)
    expected = {
        "signals": len(rows) == LOCKED["expected_signals"],
        "evaluated": counts["EVALUATED"] == LOCKED["expected_evaluated"],
        "missing": counts["MISSING"] == LOCKED["expected_missing"],
        "unknown": counts["UNKNOWN"] == 0,
    }
    if not all(expected.values()):
        raise ReplayError(f"historical ledger count/status contract failed: counts={dict(counts)}, checks={expected}")

    index = {int(bar.timestamp_ms): i for i, bar in enumerate(h1_bars)}
    signals: list[ReplaySignal] = []
    missing: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    side_counts: Counter = Counter()
    direction_metadata_counts: Counter = Counter()
    direction_metadata_vs_side: Counter = Counter()
    stress_contract_discriminating_rows: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=2):
        kind = classify_status(row.get("status"))
        signal_value = first_present(row, ("timestamp", "dt", "signal_timestamp", "signal_utc"))
        signal_ms = timestamp_ms(signal_value) if signal_value not in (None, "") else None
        if kind == "MISSING":
            missing.append(
                {
                    "source_row": row_number,
                    "signal_utc": iso_utc(parse_timestamp(signal_value)) if signal_value not in (None, "") else "",
                    "status": row.get("status", ""),
                    "source_period": row.get("source_period", ""),
                    "fold": row.get("fold", ""),
                }
            )
            continue

        assert signal_ms is not None
        signal_i = index.get(signal_ms)
        if signal_i is None or signal_i + LOCKED["exit_offset_h1_rows"] >= len(h1_bars):
            mismatches.append(
                {
                    "source_row": row_number,
                    "signal_utc": iso_utc(parse_timestamp(signal_ms)),
                    "reasons": ["SIGNAL_OR_FUTURE_H1_ROW_MISSING"],
                }
            )
            continue

        expected_entry = h1_bars[signal_i + LOCKED["entry_offset_h1_rows"]]
        expected_exit = h1_bars[signal_i + LOCKED["exit_offset_h1_rows"]]
        try:
            entry_ms = extract_timestamp(row, ("entry_bucket_timestamp", "entry_bucket_utc", "entry_utc"))
            exit_ms = extract_timestamp(row, ("exit_bucket_timestamp", "exit_bucket_utc", "exit_utc"))
        except ReplayError as exc:
            mismatches.append({"source_row": row_number, "reasons": [str(exc)]})
            continue

        direction_metadata = normalize_direction_metadata(row.get("direction"))
        entry_open = finite_float(row.get("entry_open"))
        exit_close = finite_float(row.get("exit_close"))
        observed = finite_float(row.get("observed_spread_bps"))
        execution_gross = finite_float(row.get("m5_gross_bps"))
        research_gross = finite_float(row.get("research_gross_bps"))
        normal_cost = finite_float(row.get("normal_execution_cost_bps"))
        severe_cost = finite_float(row.get("severe_execution_cost_bps"))
        normal = finite_float(row.get("normal_net_bps"))
        severe = finite_float(row.get("severe_net_bps"))
        stress8 = finite_float(row.get("stress_8bps_net_bps"))
        stress10 = finite_float(row.get("stress_10bps_net_bps"))
        probability = finite_float(row.get("probability_up"))
        required_numbers = (
            entry_open,
            exit_close,
            observed,
            execution_gross,
            research_gross,
            normal_cost,
            severe_cost,
            normal,
            severe,
            stress8,
            stress10,
            probability,
        )
        errors: list[str] = []
        if entry_ms != int(expected_entry.timestamp_ms):
            errors.append("ENTRY_NOT_I_PLUS_1")
        if exit_ms != int(expected_exit.timestamp_ms):
            errors.append("EXIT_NOT_I_PLUS_24")
        if entry_open is None or bps_diff(entry_open, float(expected_entry.open)) > price_parity_tolerance_bps:
            errors.append("ENTRY_OPEN_PARITY")
        if exit_close is None or bps_diff(exit_close, float(expected_exit.close)) > price_parity_tolerance_bps:
            errors.append("EXIT_CLOSE_PARITY")
        if any(value is None for value in required_numbers):
            errors.append("NONFINITE_EXECUTION_FIELD")

        side = side_from_probability(probability) if probability is not None else "UNKNOWN"
        if side == "NEUTRAL":
            errors.append("EVALUATED_PROBABILITY_INSIDE_NEUTRAL_BAND")
        elif side == "UNKNOWN":
            errors.append("EVALUATED_PROBABILITY_MISSING")

        if entry_open is not None and exit_close is not None and execution_gross is not None and side in {"LONG", "SHORT"}:
            sign = 1.0 if side == "LONG" else -1.0
            derived_gross = sign * (exit_close / entry_open - 1.0) * 10000.0
            if abs(derived_gross - execution_gross) > gross_parity_tolerance_bps:
                errors.append("SIDE_ADJUSTED_GROSS_PARITY")
        else:
            derived_gross = None

        if execution_gross is not None and normal_cost is not None and normal is not None:
            if abs((execution_gross - normal_cost) - normal) > net_parity_tolerance_bps:
                errors.append("NORMAL_NET_COST_PARITY")
        if execution_gross is not None and severe_cost is not None and severe is not None:
            if abs((execution_gross - severe_cost) - severe) > net_parity_tolerance_bps:
                errors.append("SEVERE_NET_COST_PARITY")
        # Source-proven frozen Commercial Closure contract from
        # app/commercial_closure_sprint.py lines 560-565:
        #   stress8  = m5_gross - max(8,  observed_spread + 4)
        #   stress10 = m5_gross - max(10, observed_spread + 6)
        # This is validated row-by-row. No contract inference or synthetic
        # alternatives are permitted.
        if None not in (execution_gross, observed, stress8, stress10):
            stress_check = source_proven_stress_contract(
                execution_gross,
                observed,
                stress8,
                stress10,
                tolerance_bps=net_parity_tolerance_bps,
            )
            if not stress_check["stress_8_parity"]:
                errors.append("STRESS_8_SOURCE_CONTRACT_PARITY")
            if not stress_check["stress_10_parity"]:
                errors.append("STRESS_10_SOURCE_CONTRACT_PARITY")
            if stress_check["spread_plus_slippage_branch"]:
                stress_contract_discriminating_rows.append({
                    "source_row": row_number,
                    "signal_utc": iso_utc(parse_timestamp(signal_ms)),
                    "observed_spread_bps": observed,
                    "execution_gross_bps": execution_gross,
                    "research_gross_bps": research_gross,
                    "stress_8_cost_bps": stress_check["stress_8_cost_bps"],
                    "stress_10_cost_bps": stress_check["stress_10_cost_bps"],
                    "stress_8_net_bps": stress8,
                    "stress_10_net_bps": stress10,
                })

        horizon = str(row.get("horizon_semantics") or "").strip()
        if not horizon:
            errors.append("HORIZON_SEMANTICS_MISSING")

        if errors:
            mismatches.append(
                {
                    "source_row": row_number,
                    "signal_utc": iso_utc(parse_timestamp(signal_ms)),
                    "side_from_probability_tail": side,
                    "direction_metadata": direction_metadata,
                    "probability_up": probability,
                    "derived_side_gross_bps": derived_gross,
                    "ledger_execution_gross_bps": execution_gross,
                    "ledger_research_gross_bps": research_gross,
                    "observed_spread_bps": observed,
                    "reasons": errors,
                }
            )
            continue

        side_counts[side] += 1
        direction_metadata_counts[direction_metadata] += 1
        mapped_metadata_side = {
            "LONG": "LONG", "BUY": "LONG", "UP": "LONG", "1": "LONG", "TRUE": "LONG",
            "SHORT": "SHORT", "SELL": "SHORT", "DOWN": "SHORT", "0": "SHORT", "FALSE": "SHORT",
        }.get(direction_metadata)
        if mapped_metadata_side is None:
            direction_metadata_vs_side["UNMAPPED"] += 1
        elif mapped_metadata_side == side:
            direction_metadata_vs_side["MATCH"] += 1
        else:
            direction_metadata_vs_side["CONFLICT"] += 1
        signals.append(
            ReplaySignal(
                source_row=row_number,
                signal_ms=signal_ms,
                signal_utc=iso_utc(parse_timestamp(signal_ms)),
                entry_ms=entry_ms,
                entry_utc=iso_utc(parse_timestamp(entry_ms)),
                exit_ms=exit_ms,
                exit_utc=iso_utc(parse_timestamp(exit_ms)),
                probability_up=float(probability),
                side=side,
                direction_metadata=direction_metadata,
                observed_spread_bps=float(observed),
                execution_gross_bps=float(execution_gross),
                normal_net_bps=float(normal),
                severe_net_bps=float(severe),
                stress_8_net_bps=float(stress8),
                stress_10_net_bps=float(stress10),
                entry_open=float(entry_open),
                exit_close=float(exit_close),
                source_period=str(row.get("source_period") or ""),
                fold=str(row.get("fold") or ""),
            )
        )

    if mismatches:
        raise ReplayError(
            f"exact historical semantics/probability-tail-side/parity failed for {len(mismatches)} rows; "
            f"examples={mismatches[:8]}"
        )
    if len(signals) != LOCKED["expected_evaluated"]:
        raise ReplayError(f"validated evaluated-trade count mismatch: {len(signals)}")
    detected_stress_contract = (
        "EXECUTION_GROSS_FLOOR_OR_OBSERVED_SPREAD_PLUS_SLIPPAGE"
    )
    stress_execution_grounded = True
    stress_spread_preserving = True
    stress_commercial_parity = True

    return (
        sorted(signals, key=lambda item: item.signal_ms),
        missing,
        {
            "status_counts": dict(counts),
            "count_checks": expected,
            "evaluated_side_counts": dict(side_counts),
            "evaluated_direction_counts": dict(side_counts),
            "execution_side_source": "PROBABILITY_TAILS_ONLY",
            "direction_column_role": "NON_EXECUTION_METADATA_NOT_USED_FOR_SIDE",
            "direction_metadata_counts": dict(direction_metadata_counts),
            "direction_metadata_vs_probability_side": dict(direction_metadata_vs_side),
            "bidirectional_probability_contract": {
                "long": f"probability_up >= {LOCKED['upper_probability_threshold']}",
                "short": f"probability_up <= {LOCKED['lower_probability_threshold']}",
                "neutral_band_is_not_evaluated": True,
                "pass": True,
            },
            "stress_cost_contract": {
                "detected_contract": detected_stress_contract,
                "source_proven": True,
                "source_generator": "app/commercial_closure_sprint.py",
                "source_generator_lines": "560-565",
                "discriminating_row_count": len(stress_contract_discriminating_rows),
                "discriminating_examples": stress_contract_discriminating_rows[:8],
                "execution_grounded": stress_execution_grounded,
                "observed_spread_preserved": stress_spread_preserving,
                "commercial_execution_parity_pass": stress_commercial_parity,
                "required_contract": detected_stress_contract,
                "stress_8_formula": (
                    "m5_gross_bps - max(8.0, observed_spread_bps + 4.0)"
                ),
                "stress_10_formula": (
                    "m5_gross_bps - max(10.0, observed_spread_bps + 6.0)"
                ),
            },
        },
    )


def close_enough(actual: Any, expected: Any, tolerance: float) -> bool:
    if actual is None or expected is None:
        return actual is expected
    try:
        a = float(actual)
        e = float(expected)
    except (TypeError, ValueError):
        return actual == expected
    if math.isinf(a) or math.isinf(e):
        return a == e
    return abs(a - e) <= tolerance


def commercial_reference_parity(
    signals: Sequence[ReplaySignal],
    commercial_summary: Mapping[str, Any],
    *,
    tolerance: float = 1e-5,
) -> dict[str, Any]:
    actual_blocks = {
        "execution_metrics": metric_block([signal.normal_net_bps for signal in signals]),
        "severe_execution_metrics": metric_block([signal.severe_net_bps for signal in signals]),
        "stress_8bps_metrics": metric_block([signal.stress_8_net_bps for signal in signals]),
        "stress_10bps_metrics": metric_block([signal.stress_10_net_bps for signal in signals]),
    }
    fields = (
        "trades",
        "mean_bps",
        "median_bps",
        "win_rate",
        "profit_factor",
        "total_bps",
        "max_drawdown_bps",
    )
    checks: dict[str, bool] = {
        "candidate": commercial_summary.get("candidate") == "logistic__direction_24h",
        "signals_total": int(commercial_summary.get("signals_total", -1)) == LOCKED["expected_signals"],
        "execution_evaluated_trades": int(commercial_summary.get("execution_evaluated_trades", -1))
        == LOCKED["expected_evaluated"],
    }
    comparisons: dict[str, Any] = {}
    for block_name, actual in actual_blocks.items():
        expected = commercial_summary.get(block_name)
        if not isinstance(expected, Mapping):
            checks[f"{block_name}.present"] = False
            comparisons[block_name] = {"actual": actual, "expected": expected}
            continue
        block_checks: dict[str, bool] = {}
        for field in fields:
            field_tolerance = 0.0 if field == "trades" else tolerance
            block_checks[field] = close_enough(actual.get(field), expected.get(field), field_tolerance)
            checks[f"{block_name}.{field}"] = block_checks[field]
        comparisons[block_name] = {
            "actual": actual,
            "expected": {field: expected.get(field) for field in fields},
            "checks": block_checks,
        }
    passed = all(checks.values())
    result = {"pass": passed, "checks": checks, "comparisons": comparisons}
    if not passed:
        failures = [key for key, value in checks.items() if not value]
        raise ReplayError(f"commercial closure metric parity failed: failures={failures[:20]}")
    return result


def current_forward_policy_diagnostic(
    signals: Sequence[ReplaySignal], runtime_config: Mapping[str, Any]
) -> dict[str, Any]:
    direction_policy = str(runtime_config.get("direction") or "").strip().upper()
    side_counts = Counter(signal.side for signal in signals)
    if direction_policy == "LONG_ONLY":
        eligible = [signal for signal in signals if signal.side == "LONG"]
        parity = side_counts.get("SHORT", 0) == 0
        excluded_reason = "REFERENCE_CONTAINS_SHORT_TRADES_BUT_FORWARD_LOGGER_IS_LONG_ONLY"
    elif direction_policy in {"BIDIRECTIONAL", "LONG_SHORT"}:
        eligible = list(signals)
        parity = True
        excluded_reason = ""
    else:
        eligible = []
        parity = False
        excluded_reason = f"UNSUPPORTED_FORWARD_DIRECTION_POLICY:{direction_policy or 'MISSING'}"
    return {
        "pass": parity,
        "forward_direction_policy": direction_policy,
        "historical_reference_direction_counts": dict(side_counts),
        "historical_reference_trade_count": len(signals),
        "forward_policy_eligible_trade_count": len(eligible),
        "excluded_reference_trade_count": len(signals) - len(eligible),
        "excluded_reason": excluded_reason,
        "eligible_reference_metrics": metric_block([signal.normal_net_bps for signal in eligible]),
        "interpretation": (
            "Historical replay is valid independently of this check. Demo/live design remains blocked "
            "until the forward logger side policy matches the frozen commercial formulation."
        ),
    }


def event_evidence(
    runtime: Any, root: Path, runtime_config: Mapping[str, Any], entry_ms: int
) -> tuple[bool, str, dict[str, Any]]:
    guard = runtime.EventGuard(root, runtime_config["event_guard"])
    allowed, reason, detail = guard.evaluate(entry_ms)
    return bool(allowed), str(reason), dict(detail)


def max_drawdown_pct(curve: Sequence[Mapping[str, Any]]) -> float:
    return max((float(row["drawdown_pct"]) for row in curve), default=0.0)


def summarize_track(track: TrackState) -> dict[str, Any]:
    resolved = [row for row in track.rows or [] if row["status"] == "RESOLVED"]
    blocked = [row for row in track.rows or [] if row["status"] == "BLOCKED"]
    normal = [float(row["normal_net_bps"]) for row in resolved]
    severe = [float(row["severe_net_bps"]) for row in resolved]
    stress8 = [float(row["stress_8_net_bps"]) for row in resolved]
    stress10 = [float(row["stress_10_net_bps"]) for row in resolved]
    return {
        "track": track.name,
        "event_mode": track.event_mode,
        "resolved_positions": len(resolved),
        "resolved_direction_counts": dict(Counter(row["side"] for row in resolved)),
        "blocked_signals": len(blocked),
        "blocked_reasons": dict(Counter(row["reason"] for row in blocked)),
        "normal_mean_bps": statistics.mean(normal) if normal else None,
        "normal_median_bps": statistics.median(normal) if normal else None,
        "normal_win_rate": sum(value > 0 for value in normal) / len(normal) if normal else None,
        "normal_profit_factor": profit_factor(normal),
        "severe_mean_bps": statistics.mean(severe) if severe else None,
        "stress_8_mean_bps": statistics.mean(stress8) if stress8 else None,
        "stress_10_mean_bps": statistics.mean(stress10) if stress10 else None,
        "final_equity": track.equity,
        "max_drawdown_pct": max_drawdown_pct(track.equity_curve or []),
        "hard_kill_latched": track.hard_kill,
    }


def persist_sqlite(
    path: Path,
    source_rows: Sequence[Mapping[str, Any]],
    replay_rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE source_signals(row_number INTEGER PRIMARY KEY, row_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE replay_events("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, track TEXT, source_row INTEGER, "
            "signal_utc TEXT, entry_utc TEXT, exit_utc TEXT, side TEXT, probability_up REAL, "
            "status TEXT, reason TEXT, execution_gross_bps REAL, normal_net_bps REAL, "
            "severe_net_bps REAL, stress_8_net_bps REAL, stress_10_net_bps REAL, "
            "equity_before REAL, equity_after REAL, drawdown_pct REAL, row_json TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE summary(singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload_json TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO source_signals(row_number,row_json) VALUES(?,?)",
            [
                (i, json.dumps(dict(row), sort_keys=True))
                for i, row in enumerate(source_rows, start=2)
            ],
        )
        for row in replay_rows:
            conn.execute(
                "INSERT INTO replay_events("
                "track,source_row,signal_utc,entry_utc,exit_utc,side,probability_up,status,reason,"
                "execution_gross_bps,normal_net_bps,severe_net_bps,stress_8_net_bps,stress_10_net_bps,"
                "equity_before,equity_after,drawdown_pct,row_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get("track"),
                    row.get("source_row"),
                    row.get("signal_utc"),
                    row.get("entry_utc"),
                    row.get("exit_utc"),
                    row.get("side"),
                    row.get("probability_up"),
                    row.get("status"),
                    row.get("reason"),
                    row.get("execution_gross_bps"),
                    row.get("normal_net_bps"),
                    row.get("severe_net_bps"),
                    row.get("stress_8_net_bps"),
                    row.get("stress_10_net_bps"),
                    row.get("equity_before"),
                    row.get("equity_after"),
                    row.get("drawdown_pct"),
                    json.dumps(dict(row), sort_keys=True),
                ),
            )
        conn.execute(
            "INSERT INTO summary(singleton,payload_json) VALUES(1,?)",
            (json.dumps(summary, sort_keys=True),),
        )
        conn.commit()
    finally:
        conn.close()


def run(root: Path, config_path: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    config = read_json(config_path)
    ledger_path = locate_execution_ledger(root, config.get("execution_ledger"))
    commercial_summary_path = locate_commercial_summary(root, config.get("commercial_summary"))
    source_rows = read_csv(ledger_path)
    commercial_summary = read_json(commercial_summary_path)
    runtime, market, h1_spec, h1_bars = load_runtime_context(root, config)
    try:
        signals, missing, validation = validate_and_build_signals(
            source_rows,
            h1_bars,
            gross_parity_tolerance_bps=float(config.get("gross_parity_tolerance_bps", 0.25)),
            price_parity_tolerance_bps=float(config.get("price_parity_tolerance_bps", 0.10)),
            net_parity_tolerance_bps=float(config.get("net_parity_tolerance_bps", 0.01)),
        )
        reference_parity = commercial_reference_parity(
            signals,
            commercial_summary,
            tolerance=float(config.get("commercial_metric_tolerance", 1e-5)),
        )
        runtime_config = runtime.load_config(root, root / "config/xauusd_controlled_paper.json")
        forward_policy = current_forward_policy_diagnostic(signals, runtime_config)
        historical_event_config = copy.deepcopy(runtime_config)
        if bool(config.get("historical_event_guard", {}).get("prefer_macro_context_db", True)):
            historical_event_config.setdefault("event_guard", {})["csv_candidates"] = []

        core = TrackState("COMMERCIAL_REFERENCE_CORE_REPLAY", "REPORT_ONLY")
        strict = TrackState("COMMERCIAL_REFERENCE_STRICT_EVENT_REPLAY", "STRICT")
        long_only = TrackState("CURRENT_LONG_ONLY_POLICY_DIAGNOSTIC", "REPORT_ONLY")
        event_reasons: Counter = Counter()
        event_details: list[dict[str, Any]] = []
        for signal in signals:
            allowed, reason, detail = event_evidence(
                runtime, root, historical_event_config, signal.entry_ms
            )
            event_reasons[reason] += 1
            if len(event_details) < 20 and not allowed:
                event_details.append(
                    {
                        "signal_utc": signal.signal_utc,
                        "entry_utc": signal.entry_utc,
                        "side": signal.side,
                        "reason": reason,
                        "detail": detail,
                    }
                )
            core.process(signal, allowed, reason)
            strict.process(signal, allowed, reason)
            if signal.side == "LONG":
                long_only.process(signal, allowed, reason)
        core.finish()
        strict.finish()
        long_only.finish()
    finally:
        market.close()

    core_summary = summarize_track(core)
    strict_summary = summarize_track(strict)
    long_only_summary = summarize_track(long_only)
    event_missing_reasons = {
        "EVENT_DATA_ABSENT_FAIL_CLOSED",
        "EVENT_CONTEXT_ROW_MISSING_FAIL_CLOSED",
    }
    missing_event_count = sum(event_reasons[reason] for reason in event_missing_reasons)
    event_coverage_complete = missing_event_count == 0

    stress_contract = validation["stress_cost_contract"]
    if core_summary["hard_kill_latched"]:
        decision = "BLOCK_HISTORICAL_ASOF_REPLAY_HARD_DRAWDOWN_KILL"
        passed = False
    elif not stress_contract["commercial_execution_parity_pass"]:
        decision = "PASS_HISTORICAL_REPLAY_BLOCK_COMMERCIAL_STRESS_COST_PARITY"
        passed = True
    elif not forward_policy["pass"]:
        decision = "PASS_HISTORICAL_COMMERCIAL_REPLAY_BLOCK_FORWARD_POLICY_PARITY"
        passed = True
    elif event_coverage_complete and not strict_summary["hard_kill_latched"]:
        decision = "PASS_FULL_HISTORICAL_ASOF_REPLAY_NO_FORWARD_WAIT"
        passed = True
    else:
        decision = "PASS_CORE_HISTORICAL_ASOF_REPLAY_EVENT_COVERAGE_INCOMPLETE"
        passed = True

    report_dir = root / config["report_dir"]
    sqlite_path = root / config["replay_ledger"]
    all_replay_rows = sorted(
        (core.rows or []) + (strict.rows or []) + (long_only.rows or []),
        key=lambda row: (row["track"], row["signal_utc"], row["source_row"]),
    )
    all_curve = sorted(
        (core.equity_curve or []) + (strict.equity_curve or []) + (long_only.equity_curve or []),
        key=lambda row: (row["track"], row["exit_utc"]),
    )
    summary = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(utc_now()),
        "decision": decision,
        "pass": passed,
        "broker_api_present": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "controlled_paper_promotion_allowed": False,
        "forward_wait_required_for_replay": False,
        "source_execution_ledger": str(ledger_path),
        "source_execution_ledger_sha256": sha256_file(ledger_path),
        "commercial_summary": str(commercial_summary_path),
        "commercial_summary_sha256": sha256_file(commercial_summary_path),
        "aligned_db": str((root / config["aligned_db"]).resolve()),
        "h1_table": h1_spec.table,
        "h1_rows": len(h1_bars),
        "locked_contract": LOCKED,
        "validation": {
            **validation,
            "exact_h1_i_plus_1_i_plus_24": True,
            "validated_evaluated_trades": len(signals),
            "missing_execution_evidence": len(missing),
            "commercial_reference_metric_parity": reference_parity,
        },
        "current_forward_policy_parity": forward_policy,
        "event_evidence": {
            "coverage_complete": event_coverage_complete,
            "missing_context_count": missing_event_count,
            "reason_counts": dict(event_reasons),
            "examples": event_details,
            "interpretation": (
                "Event coverage is a bounded historical-data requirement, not a forward-wait requirement."
            ),
        },
        "commercial_reference_core_replay": core_summary,
        "commercial_reference_strict_event_replay": strict_summary,
        "current_long_only_policy_diagnostic": long_only_summary,
        "required_next_action": (
            "REPAIR_COMMERCIAL_CLOSURE_STRESS_COST_BASIS_TO_EXECUTION_GROSS_AND_OBSERVED_SPREAD"
            if not stress_contract["commercial_execution_parity_pass"]
            else (
                "RECONCILE_FORWARD_LOGGER_DIRECTION_POLICY_WITH_FROZEN_COMMERCIAL_FORMULATION_BEFORE_DEMO_DESIGN"
                if not forward_policy["pass"]
                else "NO_FORWARD_WAIT_REQUIRED_FOR_HISTORICAL_REPLAY"
            )
        ),
        "outputs": {
            "summary": str(report_dir / "historical_asof_replay_summary.json"),
            "replay_events": str(report_dir / "historical_asof_replay_events.csv"),
            "missing_signals": str(report_dir / "historical_asof_missing_signals.csv"),
            "equity_curve": str(report_dir / "historical_asof_equity_curve.csv"),
            "sqlite": str(sqlite_path),
        },
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    write_csv(report_dir / "historical_asof_replay_events.csv", all_replay_rows)
    write_csv(report_dir / "historical_asof_missing_signals.csv", missing)
    write_csv(report_dir / "historical_asof_equity_curve.csv", all_curve)
    write_json(report_dir / "historical_asof_replay_summary.json", summary)
    decision_md = f"""# XAUUSD Controlled-Paper Historical-As-Of Replay

Decision: `{decision}`

- Forward wait required: `False`
- Historical ledger rows: `{len(source_rows)}`
- Exact execution-evaluated trades: `{len(signals)}`
- Probability-tail side counts: `{validation['evaluated_side_counts']}`
- Missing historical execution evidence: `{len(missing)}`
- Commercial summary metric parity: `{reference_parity['pass']}`
- Detected stress-cost contract: `{stress_contract['detected_contract']}`
- Commercial execution stress-cost parity: `{stress_contract['commercial_execution_parity_pass']}`
- Current forward policy parity: `{forward_policy['pass']}`
- Commercial-reference core resolved positions: `{core_summary['resolved_positions']}`
- Commercial-reference core blocked signals: `{core_summary['blocked_signals']}`
- Commercial-reference core final normalized equity: `{core_summary['final_equity']:.8f}`
- Commercial-reference core maximum drawdown: `{core_summary['max_drawdown_pct']:.6f}%`
- Event coverage complete: `{event_coverage_complete}`

## Boundary

The historical replay no longer waits for a future signal. It proves the saved commercial ledger as a bidirectional probability-tail formulation; the generic direction column is metadata, not execution side. The current forward logger remains blocked from demo/live promotion when its direction policy does not match that frozen formulation.
"""
    atomic_write(report_dir / "historical_asof_replay_decision.md", decision_md)
    persist_sqlite(sqlite_path, source_rows, all_replay_rows, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/xauusd_controlled_paper_replay.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    try:
        summary = run(root, config_path)
    except Exception as exc:
        failure = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(utc_now()),
            "decision": "HISTORICAL_ASOF_REPLAY_FAIL_CLOSED",
            "pass": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        report_dir = root / "reports/xauusd_controlled_paper_replay"
        write_json(report_dir / "historical_asof_replay_failure.json", failure)
        print(json.dumps(failure, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary.get("pass") else 3


if __name__ == "__main__":
    raise SystemExit(main())
