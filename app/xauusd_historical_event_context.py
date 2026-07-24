#!/usr/bin/env python3
"""Build bounded historical event context from the existing Stage113-116 pipeline.

This program performs no direct network access. Official downloads remain owned by
scripts/download_xauusd_official_data_batch.py. Stage113-115 unify, normalize and
convert those files into a timestamped event calendar. This consumer validates that
calendar, maps it one-to-one to the 146 evaluated commercial entries, persists the
runtime SQLite context, and can invoke the strict historical replay.

No broker, MT5, demo or live order path exists here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_HISTORICAL_EVENT_CONTEXT_V1_2_EXISTING_PIPELINE_BRIDGE"
UNIVERSE_VERSION = "USD_OFFICIAL_CORE_SCHEDULED_BLACKOUT_STAGE113_116_V1"
NEGATIVE_STATUS_TOKENS = ("UNEVALUATED", "MISSING", "UNAVAILABLE", "INCOMPLETE")


class ContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfficialEvent:
    event_time_utc: str
    source: str
    category: str
    title: str
    source_url: str
    source_year: int
    blackout_before_minutes: float
    blackout_after_minutes: float
    date_source: str = ""
    time_source: str = ""
    source_file: str = ""

    @property
    def dt(self) -> datetime:
        return parse_timestamp(self.event_time_utc)


def iso_utc(value: datetime | None = None) -> str:
    dt = value or datetime.now(tz=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    text = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    keys = keys or ["empty"]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in keys})
        temp_name = handle.name
    os.replace(temp_name, path)


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_status(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def classify_status(value: Any) -> str:
    status = normalized_status(value)
    if any(token in status for token in NEGATIVE_STATUS_TOKENS):
        return "MISSING"
    if status == "EVALUATED" or status.startswith("EVALUATED_"):
        return "EVALUATED"
    return "UNKNOWN"


def locate_execution_ledger(root: Path, configured: str | None) -> Path:
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return path.resolve()
        raise ContextError(f"configured execution ledger missing: {path}")
    for path in sorted(root.glob("reports/**/*execution_ledger.csv")):
        if "invalid" in str(path).lower():
            continue
        rows = read_csv_dicts(path)
        if len(rows) == 168 and rows and "entry_bucket_utc" in rows[0] and "status" in rows[0]:
            return path.resolve()
    raise ContextError("canonical 168-row commercial execution ledger not found")


def evaluated_entries(path: Path) -> list[dict[str, Any]]:
    rows = read_csv_dicts(path)
    entries: list[dict[str, Any]] = []
    for source_row, row in enumerate(rows, start=2):
        if classify_status(row.get("status")) != "EVALUATED":
            continue
        value = row.get("entry_bucket_utc") or row.get("entry_utc")
        if not value:
            raise ContextError(f"evaluated row lacks entry UTC: source_row={source_row}")
        dt = parse_timestamp(value)
        entries.append(
            {
                "source_row": source_row,
                "signal_utc": row.get("timestamp") or row.get("dt"),
                "entry_utc": iso_utc(dt),
                "entry_dt": dt,
                "probability_up": row.get("probability_up"),
            }
        )
    if len(entries) != 146:
        raise ContextError(f"expected 146 evaluated entries, found {len(entries)}")
    return entries


def load_official_events(path: Path, before: float, after: float) -> list[OfficialEvent]:
    if not path.is_file():
        raise ContextError(f"Stage115 timestamped official event calendar missing: {path}")
    rows = read_csv_dicts(path)
    events: list[OfficialEvent] = []
    errors: list[str] = []
    for line_no, row in enumerate(rows, start=2):
        value = row.get("event_time_utc")
        source = str(row.get("source") or "").strip().upper()
        category = str(row.get("category") or "").strip()
        title = str(row.get("title") or "").strip()
        if not value or source not in {"BLS", "BEA", "FED"} or not category or not title:
            errors.append(f"line={line_no} missing required event fields")
            continue
        try:
            dt = parse_timestamp(value)
        except Exception as exc:
            errors.append(f"line={line_no} invalid timestamp: {exc}")
            continue
        events.append(
            OfficialEvent(
                event_time_utc=iso_utc(dt),
                source=source,
                category=category,
                title=title,
                source_url=str(row.get("source_url") or ""),
                source_year=dt.year,
                blackout_before_minutes=float(row.get("blackout_before_minutes") or before),
                blackout_after_minutes=float(row.get("blackout_after_minutes") or after),
                date_source=str(row.get("date_source") or ""),
                time_source=str(row.get("time_source") or ""),
                source_file=str(row.get("source_file") or ""),
            )
        )
    if errors:
        raise ContextError("timestamped official event calendar schema errors: " + "; ".join(errors[:10]))
    if not events:
        raise ContextError("timestamped official event calendar has no usable core events")
    unique: dict[tuple[str, str, str], OfficialEvent] = {}
    for event in events:
        unique[(event.event_time_utc, event.source, event.category)] = event
    return sorted(unique.values(), key=lambda item: (item.event_time_utc, item.source, item.category))


def expected_minimum(source: str, year: int, max_entry: datetime) -> int:
    full = {"BLS": 40, "FED": 7, "BEA": 18}[source]
    if year < max_entry.year:
        return full
    covered_months = max(1, max_entry.month)
    return max(1, int(full * covered_months / 12.0 * 0.75))


def coverage_audit(events: Sequence[OfficialEvent], required_years: set[int], max_entry: datetime) -> dict[str, Any]:
    counts: Counter[tuple[str, int]] = Counter((event.source, event.source_year) for event in events)
    rows: list[dict[str, Any]] = []
    passed = True
    for source in ("BLS", "FED", "BEA"):
        for year in sorted(required_years):
            actual = counts.get((source, year), 0)
            minimum = expected_minimum(source, year, max_entry)
            ok = actual >= minimum
            passed = passed and ok
            rows.append(
                {
                    "source": source,
                    "year": year,
                    "actual_events": actual,
                    "minimum_events": minimum,
                    "pass": ok,
                }
            )
    category_counts = Counter(event.category for event in events)
    required_categories = {
        "BLS_EMPLOYMENT_SITUATION",
        "BLS_CPI",
        "BLS_PPI",
        "BLS_JOLTS",
        "BLS_ECI",
        "BEA_GDP",
        "BEA_PERSONAL_INCOME_OUTLAYS",
        "FOMC_STATEMENT",
    }
    missing_categories = sorted(category for category in required_categories if category_counts.get(category, 0) == 0)
    if missing_categories:
        passed = False
    return {
        "pass": passed,
        "rows": rows,
        "counts_by_source": dict(Counter(event.source for event in events)),
        "counts_by_category": dict(category_counts),
        "missing_required_categories": missing_categories,
    }


def context_rows(entries: Sequence[Mapping[str, Any]], events: Sequence[OfficialEvent]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entry in entries:
        entry_dt = entry["entry_dt"]
        active: list[tuple[float, OfficialEvent]] = []
        nearest: tuple[float, OfficialEvent] | None = None
        for event in events:
            delta = (event.dt - entry_dt).total_seconds() / 60.0
            distance = abs(delta)
            if nearest is None or distance < nearest[0]:
                nearest = (distance, event)
            if -event.blackout_after_minutes <= delta <= event.blackout_before_minutes:
                active.append((delta, event))
        active_events = [event for _, event in sorted(active, key=lambda item: abs(item[0]))]
        output.append(
            {
                "source_row": entry["source_row"],
                "signal_utc": entry.get("signal_utc"),
                "entry_utc": entry["entry_utc"],
                "utc_time": entry["entry_utc"],
                "has_block_event": 1 if active_events else 0,
                "active_event_count": len(active_events),
                "nearest_event_minutes": nearest[0] if nearest else None,
                "nearest_event_time_utc": nearest[1].event_time_utc if nearest else None,
                "nearest_event_title": nearest[1].title if nearest else None,
                "event_titles": " | ".join(event.title for event in active_events),
                "source_names": " | ".join(sorted({event.source for event in active_events})),
                "event_times_utc": " | ".join(event.event_time_utc for event in active_events),
                "core_coverage_complete": 1,
                "universe_version": UNIVERSE_VERSION,
            }
        )
    return output


def persist_sqlite(
    path: Path,
    events: Sequence[OfficialEvent],
    rows: Sequence[Mapping[str, Any]],
    audits: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE official_events("
            "event_time_utc TEXT, source TEXT, category TEXT, title TEXT, source_url TEXT, "
            "source_year INTEGER, blackout_before_minutes REAL, blackout_after_minutes REAL, "
            "date_source TEXT, time_source TEXT, source_file TEXT, "
            "PRIMARY KEY(event_time_utc,source,category))"
        )
        conn.execute(
            "CREATE TABLE macro_context_h1("
            "utc_time TEXT PRIMARY KEY, source_row INTEGER, signal_utc TEXT, has_block_event INTEGER NOT NULL, "
            "active_event_count INTEGER NOT NULL, nearest_event_minutes REAL, nearest_event_time_utc TEXT, "
            "nearest_event_title TEXT, event_titles TEXT, source_names TEXT, event_times_utc TEXT, "
            "core_coverage_complete INTEGER NOT NULL, universe_version TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE source_pipeline_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, payload_json TEXT NOT NULL)")
        conn.execute("CREATE TABLE summary(singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload_json TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO official_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    event.event_time_utc,
                    event.source,
                    event.category,
                    event.title,
                    event.source_url,
                    event.source_year,
                    event.blackout_before_minutes,
                    event.blackout_after_minutes,
                    event.date_source,
                    event.time_source,
                    event.source_file,
                )
                for event in events
            ],
        )
        conn.executemany(
            "INSERT INTO macro_context_h1 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    row["utc_time"],
                    row["source_row"],
                    row.get("signal_utc"),
                    row["has_block_event"],
                    row["active_event_count"],
                    row.get("nearest_event_minutes"),
                    row.get("nearest_event_time_utc"),
                    row.get("nearest_event_title"),
                    row.get("event_titles"),
                    row.get("source_names"),
                    row.get("event_times_utc"),
                    row["core_coverage_complete"],
                    row["universe_version"],
                )
                for row in rows
            ],
        )
        conn.executemany(
            "INSERT INTO source_pipeline_audit(payload_json) VALUES(?)",
            [(json.dumps(dict(row), sort_keys=True),) for row in audits],
        )
        conn.execute("INSERT INTO summary VALUES(1,?)", (json.dumps(summary, sort_keys=True),))
        conn.commit()
    finally:
        conn.close()


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("program") != "XAUUSD_HISTORICAL_EVENT_CONTEXT":
        raise ContextError("event-context config program mismatch")
    if payload.get("source_mode") != "EXISTING_STAGE113_116_PIPELINE_ONLY":
        raise ContextError("event-context source_mode must remain EXISTING_STAGE113_116_PIPELINE_ONLY")
    if payload.get("allow_direct_network_fetch") is not False:
        raise ContextError("direct network fetch must remain disabled in event-context consumer")
    return payload


def build(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    ledger = locate_execution_ledger(root, config.get("execution_ledger"))
    entries = evaluated_entries(ledger)
    required_years = {entry["entry_dt"].year for entry in entries}
    max_entry = max(entry["entry_dt"] for entry in entries)
    before = float(config.get("blackout_before_minutes", 60.0))
    after = float(config.get("blackout_after_minutes", 60.0))

    event_path = Path(str(config["official_events_csv"])).expanduser()
    if not event_path.is_absolute():
        event_path = root / event_path
    events = [event for event in load_official_events(event_path, before, after) if event.source_year in required_years]
    coverage = coverage_audit(events, required_years, max_entry)

    report_dir = root / str(config["report_dir"])
    failure_path = report_dir / "historical_event_context_failure.json"
    summary_path = report_dir / "historical_event_context_summary.json"
    pipeline_summary = root / str(config.get("pipeline_summary") or "reports/xauusd_fundamental_unify_normalize_pipeline/xauusd_fundamental_unify_normalize_pipeline_summary.json")
    stage115_summary = root / str(config.get("stage115_summary") or "reports/stage115_feature_grade_macro_fundamental_builder/stage115_feature_grade_macro_fundamental_builder_summary.json")
    audits = [
        {
            "source_mode": "EXISTING_STAGE113_116_PIPELINE_ONLY",
            "network_access_attempted": False,
            "official_events_csv": str(event_path),
            "official_events_csv_sha256": sha256_file(event_path),
            "pipeline_summary": str(pipeline_summary),
            "pipeline_summary_exists": pipeline_summary.is_file(),
            "pipeline_summary_sha256": sha256_file(pipeline_summary) if pipeline_summary.is_file() else None,
            "stage115_summary": str(stage115_summary),
            "stage115_summary_exists": stage115_summary.is_file(),
            "stage115_summary_sha256": sha256_file(stage115_summary) if stage115_summary.is_file() else None,
        }
    ]

    if not coverage["pass"]:
        failure = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(),
            "decision": "HISTORICAL_EVENT_CONTEXT_FAIL_CLOSED_INCOMPLETE_EXISTING_PIPELINE_COVERAGE",
            "pass": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "source_mode": "EXISTING_STAGE113_116_PIPELINE_ONLY",
            "network_access_attempted": False,
            "coverage": coverage,
            "required_years": sorted(required_years),
            "pipeline_audit": audits,
            "required_next_action": "REFRESH_EXISTING_STAGE116_DOWNLOADER_AND_STAGE113_115_PIPELINE_THEN_RERUN",
        }
        write_json(failure_path, failure)
        raise ContextError(json.dumps(failure, ensure_ascii=False))

    rows = context_rows(entries, events)
    if len(rows) != 146 or len({row["utc_time"] for row in rows}) != 146:
        raise ContextError("historical entry-context rows are not an exact 146-row one-to-one mapping")

    blocked = sum(int(row["has_block_event"]) for row in rows)
    sqlite_path = root / str(config["sqlite_path"])
    events_csv = report_dir / "official_core_events.csv"
    context_csv = report_dir / "historical_entry_event_context.csv"
    audit_json = report_dir / "official_pipeline_source_audit.json"
    summary = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": "PASS_EXISTING_PIPELINE_HISTORICAL_EVENT_CONTEXT_CORE_BLACKOUT",
        "pass": True,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "universe_version": UNIVERSE_VERSION,
        "scope": "SCHEDULED_USD_CORE_BLACKOUT_ONLY_NOT_EVENT_SURPRISE",
        "event_surprise_layer_complete": False,
        "source_mode": "EXISTING_STAGE113_116_PIPELINE_ONLY",
        "allow_direct_network_fetch": False,
        "network_access_attempted": False,
        "source_execution_ledger": str(ledger),
        "source_execution_ledger_sha256": sha256_file(ledger),
        "source_official_events_csv": str(event_path),
        "source_official_events_csv_sha256": sha256_file(event_path),
        "evaluated_entry_rows": len(rows),
        "required_years": sorted(required_years),
        "minimum_entry_utc": min(row["entry_utc"] for row in rows),
        "maximum_entry_utc": max(row["entry_utc"] for row in rows),
        "official_event_count": len(events),
        "event_counts_by_source": dict(Counter(event.source for event in events)),
        "event_counts_by_category": dict(Counter(event.category for event in events)),
        "blocked_entry_rows": blocked,
        "clear_entry_rows": len(rows) - blocked,
        "core_coverage_complete": True,
        "coverage": coverage,
        "blackout_before_minutes": before,
        "blackout_after_minutes": after,
        "pipeline_audit": audits,
        "outputs": {
            "sqlite": str(sqlite_path),
            "events_csv": str(events_csv),
            "entry_context_csv": str(context_csv),
            "source_audit": str(audit_json),
            "summary": str(summary_path),
        },
    }
    write_csv(events_csv, [asdict(event) for event in events])
    write_csv(context_csv, rows)
    write_json(audit_json, {"program": PROGRAM_VERSION, "audits": audits})
    write_json(summary_path, summary)
    if failure_path.exists():
        failure_path.unlink()
    persist_sqlite(sqlite_path, events, rows, audits, summary)
    return summary


def run_replay(root: Path, config: Mapping[str, Any]) -> int:
    replay_script = root / "app/xauusd_controlled_paper_historical_replay.py"
    replay_config = root / str(config.get("replay_config") or "config/xauusd_controlled_paper_replay.json")
    command = [sys.executable, str(replay_script), "--root", str(root), "--config", str(replay_config)]
    return subprocess.run(command, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/xauusd_historical_event_context.json")
    parser.add_argument("--run-replay", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    report_dir = root / "reports/xauusd_historical_event_context"
    try:
        config = load_config(config_path)
        summary = build(root, config)
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
        if args.run_replay:
            return run_replay(root, config)
        return 0
    except Exception as exc:
        failure_path = report_dir / "historical_event_context_failure.json"
        if not failure_path.exists():
            payload = {
                "program": PROGRAM_VERSION,
                "generated_utc": iso_utc(),
                "decision": "HISTORICAL_EVENT_CONTEXT_FAIL_CLOSED",
                "pass": False,
                "broker_order_allowed": False,
                "demo_order_allowed": False,
                "live_order_allowed": False,
                "source_mode": "EXISTING_STAGE113_116_PIPELINE_ONLY",
                "network_access_attempted": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            write_json(failure_path, payload)
        print(failure_path.read_text(encoding="utf-8"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
