"""
Stage32F-HF1 — AMarkets CSV Preflight Gate

Purpose:
    Decide whether it is worth running the heavy Stage32F wrapper before importing
    newly exported AMarkets/MT5 CSV files.

Design:
    - Reads CSV timestamps directly from H1/M1 export files.
    - Compares CSV max timestamps with the existing local SQLite DB max timestamps.
    - Reports whether the wrapper is recommended, probably low-value, or should be skipped.
    - Uses only Python standard library.

Typical use:
    python3 -m app.stage32f_amarkets_csv_preflight --csv-dir ~/Downloads

Explicit files are safer when Downloads contains many CSVs:
    python3 -m app.stage32f_amarkets_csv_preflight \
      --h1-csv ~/Downloads/XAUUSD_H1.csv \
      --m1-csv ~/Downloads/XAUUSD_M1.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPORT_DIR_DEFAULT = Path("data/reports/stage32f_amarkets_csv_preflight")
DB_DEFAULT = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TARGET_HOURS = [9, 12, 13, 14, 15]


@dataclass
class CsvProbe:
    path: str
    exists: bool
    timeframe_hint: str
    row_count: int = 0
    parsed_timestamp_count: int = 0
    min_timestamp: Optional[str] = None
    max_timestamp: Optional[str] = None
    delimiter: Optional[str] = None
    header: Optional[List[str]] = None
    error: Optional[str] = None


@dataclass
class DbProbe:
    path: str
    exists: bool
    table: Optional[str] = None
    timeframe_column: Optional[str] = None
    timestamp_column: Optional[str] = None
    latest_by_timeframe: Optional[Dict[str, str]] = None
    error: Optional[str] = None


@dataclass
class PreflightDecision:
    decision: str
    wrapper_recommended: bool
    reason: str
    h1_csv_max: Optional[str]
    h1_db_max: Optional[str]
    h1_advanced: Optional[bool]
    h1_advance_hours: Optional[float]
    target_hours: List[int]
    crossed_target_hours: List[int]
    next_command: str


def _expand(path: Path | str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def _normalize_header_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


def _try_parse_datetime(value: str) -> Optional[datetime]:
    if value is None:
        return None
    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return None

    # Numeric Unix timestamp support.
    if re.fullmatch(r"\d{10}(?:\.\d+)?", raw):
        try:
            return datetime.utcfromtimestamp(float(raw))
        except Exception:
            pass
    if re.fullmatch(r"\d{13}", raw):
        try:
            return datetime.utcfromtimestamp(int(raw) / 1000.0)
        except Exception:
            pass

    cleaned = raw.replace("T", " ").replace("Z", "").strip()
    cleaned = re.sub(r"([+-]\d{2}:?\d{2})$", "", cleaned).strip()
    cleaned = cleaned.split(".") if False else cleaned  # keep linter-simple no-op

    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y.%m.%d",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%H:%M:%S",
        "%H:%M",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            if fmt in ("%H:%M:%S", "%H:%M"):
                return None
            return parsed
        except ValueError:
            continue

    try:
        # Python can parse many ISO-like strings.
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo:
            parsed = parsed.astimezone(tz=None).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _combine_date_time(date_value: str, time_value: str) -> Optional[datetime]:
    return _try_parse_datetime(f"{date_value} {time_value}")


def _detect_delimiter(sample: str) -> str:
    candidates = [",", "\t", ";", "|"]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(candidates))
        return dialect.delimiter
    except Exception:
        scores = {d: sample.count(d) for d in candidates}
        return max(scores, key=scores.get) if scores else ","


def _looks_like_header(row: Sequence[str]) -> bool:
    joined = " ".join(str(c).lower() for c in row)
    markers = ["date", "time", "open", "high", "low", "close", "tick", "spread", "<date>", "<time>"]
    return any(m in joined for m in markers)


def _extract_timestamp_from_row(row: Sequence[str], header: Optional[Sequence[str]]) -> Optional[datetime]:
    cells = [str(c).strip() for c in row]
    if not cells:
        return None

    if header:
        normalized = [_normalize_header_name(h) for h in header]
        index_by_name = {name: i for i, name in enumerate(normalized)}

        datetime_keys = ["datetime", "timestamp", "utctime", "timeutc", "dateutc"]
        for key in datetime_keys:
            if key in index_by_name and index_by_name[key] < len(cells):
                parsed = _try_parse_datetime(cells[index_by_name[key]])
                if parsed:
                    return parsed

        date_idx = None
        time_idx = None
        for i, name in enumerate(normalized):
            if name in ("date", "dategmt", "dateutc") or name.endswith("date"):
                date_idx = i
            if name in ("time", "timegmt", "timeutc") or name.endswith("time"):
                time_idx = i
        if date_idx is not None and time_idx is not None and date_idx < len(cells) and time_idx < len(cells):
            parsed = _combine_date_time(cells[date_idx], cells[time_idx])
            if parsed:
                return parsed

        # Sometimes a single TIME column stores full datetime.
        if time_idx is not None and time_idx < len(cells):
            parsed = _try_parse_datetime(cells[time_idx])
            if parsed:
                return parsed

    # Fallbacks for headerless MT5-like exports.
    if len(cells) >= 2:
        parsed = _combine_date_time(cells[0], cells[1])
        if parsed:
            return parsed
    parsed = _try_parse_datetime(cells[0])
    if parsed:
        return parsed
    return None


def probe_csv(path: Path | str, timeframe_hint: str, max_rows: int = 0) -> CsvProbe:
    p = _expand(path)
    result = CsvProbe(path=str(p), exists=p.exists(), timeframe_hint=timeframe_hint)
    if not p.exists():
        result.error = "file_not_found"
        return result

    timestamps: List[datetime] = []
    try:
        sample = p.read_text(encoding="utf-8", errors="ignore")[:8192]
        delim = _detect_delimiter(sample)
        result.delimiter = "\\t" if delim == "\t" else delim
        with p.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.reader(f, delimiter=delim)
            first_row = next(reader, None)
            if first_row is None:
                result.error = "empty_csv"
                return result
            header: Optional[List[str]] = list(first_row) if _looks_like_header(first_row) else None
            result.header = header
            rows_iter: Iterable[Sequence[str]]
            if header is None:
                rows_iter = [first_row]
            else:
                rows_iter = []

            row_counter = 0
            for row in rows_iter:
                row_counter += 1
                parsed = _extract_timestamp_from_row(row, header)
                if parsed:
                    timestamps.append(parsed)
            for row in reader:
                if not row or not any(str(c).strip() for c in row):
                    continue
                row_counter += 1
                parsed = _extract_timestamp_from_row(row, header)
                if parsed:
                    timestamps.append(parsed)
                if max_rows and row_counter >= max_rows:
                    break

        result.row_count = row_counter
        result.parsed_timestamp_count = len(timestamps)
        if timestamps:
            result.min_timestamp = min(timestamps).replace(microsecond=0).isoformat(sep=" ")
            result.max_timestamp = max(timestamps).replace(microsecond=0).isoformat(sep=" ")
        else:
            result.error = "no_parseable_timestamps"
        return result
    except Exception as exc:
        result.error = f"csv_probe_error: {type(exc).__name__}: {exc}"
        return result


def _file_score(path: Path, timeframe: str) -> Tuple[int, float]:
    name = path.name.lower()
    score = 0
    if "xau" in name or "gold" in name:
        score += 4
    if timeframe == "H1":
        if any(tok in name for tok in ["h1", "1h", "_60", "-60", "period_h1", "hour"]):
            score += 6
        if any(tok in name for tok in ["m1", "1m", "_1", "period_m1", "minute"]):
            score -= 3
    elif timeframe == "M1":
        if any(tok in name for tok in ["m1", "1m", "period_m1", "minute"]):
            score += 6
        if any(tok in name for tok in ["h1", "1h", "_60", "period_h1", "hour"]):
            score -= 3
    if path.suffix.lower() == ".csv":
        score += 1
    return score, path.stat().st_mtime


def find_best_csv(csv_dir: Path | str, timeframe: str) -> Optional[Path]:
    directory = _expand(csv_dir)
    if not directory.exists() or not directory.is_dir():
        return None
    candidates = list(directory.glob("*.csv")) + list(directory.glob("*.CSV"))
    if not candidates:
        return None
    scored = sorted((( _file_score(p, timeframe), p) for p in candidates), reverse=True)
    # Require at least a weak positive match so random CSVs are not selected too easily.
    best_score, best_path = scored[0]
    if best_score[0] <= 1:
        return None
    return best_path


def _parse_dt_maybe(value: Optional[str]) -> Optional[datetime]:
    return _try_parse_datetime(value or "") if value else None


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r[1]) for r in rows]


def _choose_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    normalized = {_normalize_header_name(c): c for c in columns}
    for cand in candidates:
        key = _normalize_header_name(cand)
        if key in normalized:
            return normalized[key]
    for c in columns:
        n = _normalize_header_name(c)
        if any(_normalize_header_name(cand) in n for cand in candidates):
            return c
    return None


def probe_db(db_path: Path | str) -> DbProbe:
    p = _expand(db_path)
    result = DbProbe(path=str(p), exists=p.exists())
    if not p.exists():
        result.error = "db_not_found"
        return result
    try:
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        tables = [str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        table_preferences = ["bars", "candles", "ohlcv", "xauusd_bars", "price_bars"]
        candidate_tables = sorted(tables, key=lambda t: (0 if t in table_preferences else 1, t))
        chosen = None
        tf_col = None
        ts_col = None
        for table in candidate_tables:
            cols = _table_columns(conn, table)
            maybe_ts = _choose_column(cols, ["utc_time", "timestamp", "datetime", "time", "date_time", "bar_time"])
            maybe_tf = _choose_column(cols, ["timeframe", "tf", "period", "granularity"])
            if maybe_ts:
                chosen = table
                ts_col = maybe_ts
                tf_col = maybe_tf
                break
        if not chosen or not ts_col:
            result.error = "no_bars_like_table_found"
            return result
        result.table = chosen
        result.timestamp_column = ts_col
        result.timeframe_column = tf_col

        latest: Dict[str, str] = {}
        if tf_col:
            q = f"SELECT {tf_col} AS timeframe, MAX({ts_col}) AS max_ts FROM {chosen} GROUP BY {tf_col}"
            for row in conn.execute(q).fetchall():
                tf = str(row["timeframe"]).upper()
                max_ts = str(row["max_ts"])
                latest[tf] = max_ts
        else:
            max_ts = conn.execute(f"SELECT MAX({ts_col}) FROM {chosen}").fetchone()[0]
            latest["UNKNOWN"] = str(max_ts)
        result.latest_by_timeframe = latest
        return result
    except Exception as exc:
        result.error = f"db_probe_error: {type(exc).__name__}: {exc}"
        return result
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
        except Exception:
            pass


def _get_db_latest_for_tf(db_probe: DbProbe, wanted: str) -> Optional[str]:
    if not db_probe.latest_by_timeframe:
        return None
    wanted_norm = wanted.upper()
    aliases = {
        "H1": ["H1", "1H", "60", "60M", "M60", "HOURLY"],
        "M1": ["M1", "1M", "1", "MINUTE", "MINUTELY"],
    }.get(wanted_norm, [wanted_norm])
    latest = db_probe.latest_by_timeframe
    for alias in aliases:
        if alias in latest:
            return latest[alias]
    # weak contains match
    for key, value in latest.items():
        if wanted_norm in key or key in aliases:
            return value
    return None


def crossed_hours(start: datetime, end: datetime, target_hours: Sequence[int]) -> List[int]:
    if end <= start:
        return []
    crossed: List[int] = []
    current = start.replace(minute=0, second=0, microsecond=0)
    if current <= start:
        current += timedelta(hours=1)
    targets = set(int(h) for h in target_hours)
    while current <= end:
        if current.hour in targets and current.hour not in crossed:
            crossed.append(current.hour)
        current += timedelta(hours=1)
    return crossed


def decide(h1_csv: CsvProbe, db_probe: DbProbe, target_hours: Sequence[int]) -> PreflightDecision:
    next_cmd = "python3 -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper"
    h1_csv_dt = _parse_dt_maybe(h1_csv.max_timestamp)
    h1_db_raw = _get_db_latest_for_tf(db_probe, "H1")
    h1_db_dt = _parse_dt_maybe(h1_db_raw)

    if not h1_csv.exists or h1_csv.error:
        return PreflightDecision(
            decision="ERROR_NO_VALID_H1_CSV",
            wrapper_recommended=False,
            reason=f"H1 CSV could not be parsed: {h1_csv.error}",
            h1_csv_max=h1_csv.max_timestamp,
            h1_db_max=h1_db_raw,
            h1_advanced=None,
            h1_advance_hours=None,
            target_hours=list(target_hours),
            crossed_target_hours=[],
            next_command="Fix/select H1 CSV, then rerun preflight.",
        )

    if not h1_csv_dt:
        return PreflightDecision(
            decision="ERROR_H1_CSV_TIMESTAMP_UNREADABLE",
            wrapper_recommended=False,
            reason="H1 CSV exists, but no parseable timestamp was found.",
            h1_csv_max=h1_csv.max_timestamp,
            h1_db_max=h1_db_raw,
            h1_advanced=None,
            h1_advance_hours=None,
            target_hours=list(target_hours),
            crossed_target_hours=[],
            next_command="Use --h1-csv with the exact AMarkets H1 export file.",
        )

    if not db_probe.exists or db_probe.error or not h1_db_dt:
        return PreflightDecision(
            decision="RUN_WRAPPER_RECOMMENDED_NO_DB_BASELINE",
            wrapper_recommended=True,
            reason="CSV is readable, but DB baseline is unavailable; run wrapper to establish/import baseline.",
            h1_csv_max=h1_csv.max_timestamp,
            h1_db_max=h1_db_raw,
            h1_advanced=None,
            h1_advance_hours=None,
            target_hours=list(target_hours),
            crossed_target_hours=[],
            next_command=next_cmd,
        )

    delta = h1_csv_dt - h1_db_dt
    advanced = delta.total_seconds() > 0
    advance_hours = round(delta.total_seconds() / 3600.0, 3)
    crossed = crossed_hours(h1_db_dt, h1_csv_dt, target_hours)

    if not advanced:
        return PreflightDecision(
            decision="SKIP_H1_NOT_ADVANCED",
            wrapper_recommended=False,
            reason="The newest H1 timestamp in the CSV is not newer than the DB H1 timestamp.",
            h1_csv_max=h1_csv.max_timestamp,
            h1_db_max=h1_db_raw,
            h1_advanced=False,
            h1_advance_hours=advance_hours,
            target_hours=list(target_hours),
            crossed_target_hours=[],
            next_command="Do not run wrapper yet. Export a newer AMarkets H1 CSV first.",
        )

    if crossed:
        return PreflightDecision(
            decision="RUN_WRAPPER_RECOMMENDED",
            wrapper_recommended=True,
            reason="H1 CSV has advanced and crossed at least one tracked signal hour.",
            h1_csv_max=h1_csv.max_timestamp,
            h1_db_max=h1_db_raw,
            h1_advanced=True,
            h1_advance_hours=advance_hours,
            target_hours=list(target_hours),
            crossed_target_hours=crossed,
            next_command=next_cmd,
        )

    return PreflightDecision(
        decision="RUN_BUT_LOW_SAMPLE_PROBABILITY",
        wrapper_recommended=True,
        reason="H1 CSV has advanced, but no tracked signal hour was crossed; wrapper may only help if pending outcomes resolve.",
        h1_csv_max=h1_csv.max_timestamp,
        h1_db_max=h1_db_raw,
        h1_advanced=True,
        h1_advance_hours=advance_hours,
        target_hours=list(target_hours),
        crossed_target_hours=[],
        next_command=next_cmd,
    )


def write_report(report_dir: Path, h1: CsvProbe, m1: Optional[CsvProbe], db: DbProbe, decision: PreflightDecision) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "decision": asdict(decision),
        "h1_csv_probe": asdict(h1),
        "m1_csv_probe": asdict(m1) if m1 else None,
        "db_probe": asdict(db),
    }
    (report_dir / "stage32f_preflight.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# XAUUSD Stage32F-HF1 — AMarkets CSV Preflight Gate")
    lines.append("")
    lines.append(f"Generated UTC: {payload['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"DECISION = {decision.decision}")
    lines.append(f"WRAPPER_RECOMMENDED = {decision.wrapper_recommended}")
    lines.append(f"REASON = {decision.reason}")
    lines.append(f"NEXT_COMMAND = {decision.next_command}")
    lines.append("```")
    lines.append("")
    lines.append("## H1 CSV vs DB")
    lines.append("")
    lines.append("```text")
    lines.append(f"h1_csv_path = {h1.path}")
    lines.append(f"h1_csv_exists = {h1.exists}")
    lines.append(f"h1_csv_rows = {h1.row_count}")
    lines.append(f"h1_csv_min = {h1.min_timestamp}")
    lines.append(f"h1_csv_max = {h1.max_timestamp}")
    lines.append(f"h1_db_max = {decision.h1_db_max}")
    lines.append(f"h1_advanced = {decision.h1_advanced}")
    lines.append(f"h1_advance_hours = {decision.h1_advance_hours}")
    lines.append(f"target_hours = {decision.target_hours}")
    lines.append(f"crossed_target_hours = {decision.crossed_target_hours}")
    lines.append("```")
    lines.append("")
    if m1:
        lines.append("## M1 CSV probe")
        lines.append("")
        lines.append("```text")
        lines.append(f"m1_csv_path = {m1.path}")
        lines.append(f"m1_csv_exists = {m1.exists}")
        lines.append(f"m1_csv_rows = {m1.row_count}")
        lines.append(f"m1_csv_min = {m1.min_timestamp}")
        lines.append(f"m1_csv_max = {m1.max_timestamp}")
        lines.append(f"m1_error = {m1.error}")
        lines.append("```")
        lines.append("")
    lines.append("## DB probe")
    lines.append("")
    lines.append("```text")
    lines.append(f"db_path = {db.path}")
    lines.append(f"db_exists = {db.exists}")
    lines.append(f"db_table = {db.table}")
    lines.append(f"db_timeframe_column = {db.timeframe_column}")
    lines.append(f"db_timestamp_column = {db.timestamp_column}")
    lines.append(f"db_latest_by_timeframe = {db.latest_by_timeframe}")
    lines.append(f"db_error = {db.error}")
    lines.append("```")
    lines.append("")
    lines.append("## Operational rule")
    lines.append("")
    lines.append("```text")
    lines.append("If DECISION is SKIP_H1_NOT_ADVANCED, do not run the heavy wrapper.")
    lines.append("If DECISION is RUN_WRAPPER_RECOMMENDED, run Stage32F with --run-active-wrapper.")
    lines.append("If DECISION is RUN_BUT_LOW_SAMPLE_PROBABILITY, running is allowed but expected sample gain is low.")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `{report_dir / 'stage32f_preflight.md'}`")
    lines.append(f"- `{report_dir / 'stage32f_preflight.json'}`")
    (report_dir / "stage32f_preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_target_hours(text: str) -> List[int]:
    out: List[int] = []
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        value = int(part)
        if value < 0 or value > 23:
            raise argparse.ArgumentTypeError(f"Invalid hour: {value}")
        out.append(value)
    return sorted(set(out))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage32F-HF1 AMarkets CSV preflight gate")
    parser.add_argument("--csv-dir", default="~/Downloads", help="Directory to scan for AMarkets CSV files")
    parser.add_argument("--h1-csv", default=None, help="Explicit H1 CSV path; safest option")
    parser.add_argument("--m1-csv", default=None, help="Explicit M1 CSV path; optional")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Existing local SQLite DB path")
    parser.add_argument("--report-dir", default=str(REPORT_DIR_DEFAULT), help="Output report directory")
    parser.add_argument("--target-hours", default=",".join(str(x) for x in DEFAULT_TARGET_HOURS), help="Tracked UTC hours, comma-separated")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional debug cap for CSV rows; 0 means all rows")
    args = parser.parse_args(argv)

    target_hours = parse_target_hours(args.target_hours)

    h1_path = _expand(args.h1_csv) if args.h1_csv else find_best_csv(args.csv_dir, "H1")
    m1_path = _expand(args.m1_csv) if args.m1_csv else find_best_csv(args.csv_dir, "M1")

    if h1_path is None:
        h1_probe = CsvProbe(path=str(_expand(args.csv_dir)), exists=False, timeframe_hint="H1", error="no_h1_csv_found_in_csv_dir")
    else:
        h1_probe = probe_csv(h1_path, "H1", max_rows=args.max_rows)

    m1_probe = probe_csv(m1_path, "M1", max_rows=args.max_rows) if m1_path else None
    db_probe = probe_db(args.db)
    decision = decide(h1_probe, db_probe, target_hours)
    write_report(_expand(args.report_dir), h1_probe, m1_probe, db_probe, decision)

    print(f"DECISION={decision.decision}")
    print(f"WRAPPER_RECOMMENDED={decision.wrapper_recommended}")
    print(f"REASON={decision.reason}")
    print(f"H1_CSV_MAX={decision.h1_csv_max}")
    print(f"H1_DB_MAX={decision.h1_db_max}")
    print(f"CROSSED_TARGET_HOURS={decision.crossed_target_hours}")
    print(f"REPORT={_expand(args.report_dir) / 'stage32f_preflight.md'}")

    # Return 0 for all valid preflight decisions. CI/local scripts can parse the JSON.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
