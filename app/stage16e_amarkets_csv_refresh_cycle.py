#!/usr/bin/env python3
"""
Stage 16E v2 — AMarkets CSV Refresh + True-Forward Cycle

v2 fix:
- Existing local DB bars table may contain a NOT NULL column named imported_utc.
- v1 inserted ingested_at but did not populate imported_utc.
- v2 dynamically detects the bars schema and populates imported_utc when present.

Purpose:
- Import/merge updated AMarkets MT5 CSV files into the local SQLite bars table.
- Then run Stage 16D cycle so Stage 16C can collect true-forward shadow signals
  using fresh post-collector-start data.

Hard rules:
- Data refresh + research shadow cycle only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v2_imported_utc_fix"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage16e_amarkets_csv_refresh_cycle")
DEFAULT_STAGE16C_OUT = Path("data/reports/stage16c_true_forward_shadow_collector")


@dataclass
class ImportResult:
    path: str
    status: str
    reason: str
    rows_read: int = 0
    rows_clean: int = 0
    rows_upserted: int = 0
    symbol: str = "XAUUSD"
    timeframe: str = ""
    first_utc: str = ""
    last_utc: str = ""


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def normalize_col(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_columns(conn: sqlite3.Connection, table: str) -> Dict[str, Dict]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    out = {}
    for r in rows:
        out[str(r["name"])] = dict(r)
    return out


def latest_bar_utc(conn: sqlite3.Connection) -> Optional[str]:
    try:
        row = conn.execute(
            """
            SELECT MAX(utc_time) AS latest
            FROM bars
            WHERE source='amarkets_mt5' AND symbol='XAUUSD'
            """
        ).fetchone()
        return str(row["latest"]) if row and row["latest"] else None
    except Exception:
        return None


def ensure_bars_table(conn: sqlite3.Connection) -> Dict[str, Dict]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bars (
            source TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            utc_time TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            imported_utc TEXT,
            ingested_at TEXT,
            PRIMARY KEY (source, symbol, timeframe, utc_time)
        )
        """
    )
    cols = get_table_columns(conn, "bars")
    required = {"source", "symbol", "timeframe", "utc_time", "open", "high", "low", "close"}
    missing = required - set(cols.keys())
    if missing:
        raise RuntimeError(f"Existing bars table is missing required columns: {sorted(missing)}")

    # Add optional metadata columns when possible. If existing schema already has imported_utc NOT NULL, this preserves it.
    cols = get_table_columns(conn, "bars")
    if "volume" not in cols:
        conn.execute("ALTER TABLE bars ADD COLUMN volume REAL")
    cols = get_table_columns(conn, "bars")
    if "ingested_at" not in cols:
        conn.execute("ALTER TABLE bars ADD COLUMN ingested_at TEXT")
    cols = get_table_columns(conn, "bars")
    # imported_utc may already exist as NOT NULL in older schema. If it does not exist, add it nullable for future compatibility.
    if "imported_utc" not in cols:
        conn.execute("ALTER TABLE bars ADD COLUMN imported_utc TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bars_source_symbol_tf_time ON bars(source, symbol, timeframe, utc_time)"
    )
    conn.commit()
    return get_table_columns(conn, "bars")


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(errors="ignore", encoding="utf-8")[:4096]
    if "\t" in sample and sample.count("\t") >= sample.count(","):
        return "\t"
    try:
        dialect = csv.Sniffer().sniff(sample)
        return dialect.delimiter
    except Exception:
        return ","


def read_csv_flexible(path: Path) -> pd.DataFrame:
    delim = detect_delimiter(path)
    errors = []
    for enc in ["utf-8-sig", "utf-16", "utf-16le", "latin1"]:
        try:
            return pd.read_csv(path, sep=delim, encoding=enc)
        except Exception as e:
            errors.append(f"{enc}: {str(e)[:120]}")
    raise RuntimeError("; ".join(errors))


def map_ohlc_columns(df: pd.DataFrame) -> Dict[str, str]:
    nmap = {normalize_col(c): c for c in df.columns}

    def find(cands: Sequence[str], contains_any: Sequence[str] = ()) -> Optional[str]:
        for c in cands:
            if normalize_col(c) in nmap:
                return nmap[normalize_col(c)]
        for orig in df.columns:
            n = normalize_col(orig)
            if any(k in n for k in contains_any):
                return orig
        return None

    date_col = find(["date", "<date>", "datetime", "utc_time", "timestamp"], ["date"])
    time_col = find(["time", "<time>"], [])
    if date_col == time_col:
        time_col = None

    open_col = find(["open", "<open>"], ["open"])
    high_col = find(["high", "<high>"], ["high"])
    low_col = find(["low", "<low>"], ["low"])
    close_col = find(["close", "<close>"], ["close"])
    vol_col = find(["tickvol", "<tickvol>", "volume", "vol", "<vol>"], ["volume", "tickvol"])

    missing = [name for name, col in {
        "date_or_datetime": date_col,
        "open": open_col,
        "high": high_col,
        "low": low_col,
        "close": close_col,
    }.items() if col is None]
    if missing:
        raise RuntimeError(f"Missing OHLC columns: {missing}; columns={list(df.columns)}")

    return {
        "date": date_col,
        "time": time_col or "",
        "open": open_col,
        "high": high_col,
        "low": low_col,
        "close": close_col,
        "volume": vol_col or "",
    }


def parse_datetime(df: pd.DataFrame, cols: Dict[str, str]) -> pd.Series:
    date_col = cols["date"]
    time_col = cols.get("time") or ""
    if time_col and time_col in df.columns:
        raw = df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip()
    else:
        raw = df[date_col].astype(str).str.strip()
    return pd.to_datetime(raw, utc=True, errors="coerce")


def infer_timeframe_from_name(path: Path) -> Optional[str]:
    s = path.name.upper()
    patterns = [
        (r"(^|[^A-Z0-9])1M([^A-Z0-9]|$)", "1m"),
        (r"(^|[^A-Z0-9])M1([^A-Z0-9]|$)", "1m"),
        (r"(^|[^A-Z0-9])5M([^A-Z0-9]|$)", "5m"),
        (r"(^|[^A-Z0-9])M5([^A-Z0-9]|$)", "5m"),
        (r"(^|[^A-Z0-9])15M([^A-Z0-9]|$)", "15m"),
        (r"(^|[^A-Z0-9])M15([^A-Z0-9]|$)", "15m"),
        (r"(^|[^A-Z0-9])30M([^A-Z0-9]|$)", "30m"),
        (r"(^|[^A-Z0-9])M30([^A-Z0-9]|$)", "30m"),
        (r"(^|[^A-Z0-9])1H([^A-Z0-9]|$)", "1h"),
        (r"(^|[^A-Z0-9])H1([^A-Z0-9]|$)", "1h"),
        (r"(^|[^A-Z0-9])4H([^A-Z0-9]|$)", "4h"),
        (r"(^|[^A-Z0-9])H4([^A-Z0-9]|$)", "4h"),
        (r"(^|[^A-Z0-9])D1([^A-Z0-9]|$)", "1d"),
    ]
    for pat, tf in patterns:
        if re.search(pat, s):
            return tf
    return None


def infer_timeframe_from_rows(dt: pd.Series) -> str:
    x = pd.Series(pd.to_datetime(dt, utc=True, errors="coerce")).dropna().sort_values().drop_duplicates()
    if len(x) < 5:
        return "unknown"
    delta = x.diff().dropna().median()
    minutes = round(delta / pd.Timedelta(minutes=1))
    mapping = {
        1: "1m",
        5: "5m",
        15: "15m",
        30: "30m",
        60: "1h",
        240: "4h",
        1440: "1d",
    }
    return mapping.get(int(minutes), f"{int(minutes)}m")


def infer_symbol(path: Path, default_symbol: str) -> str:
    s = path.name.upper()
    if "XAU" in s or "GOLD" in s:
        return "XAUUSD"
    return default_symbol


def clean_ohlc(df: pd.DataFrame, cols: Dict[str, str], path: Path, default_symbol: str) -> Tuple[pd.DataFrame, str, str]:
    out = pd.DataFrame()
    out["utc_time"] = parse_datetime(df, cols)
    out["open"] = pd.to_numeric(df[cols["open"]], errors="coerce")
    out["high"] = pd.to_numeric(df[cols["high"]], errors="coerce")
    out["low"] = pd.to_numeric(df[cols["low"]], errors="coerce")
    out["close"] = pd.to_numeric(df[cols["close"]], errors="coerce")
    if cols.get("volume") and cols["volume"] in df.columns:
        out["volume"] = pd.to_numeric(df[cols["volume"]], errors="coerce")
    else:
        out["volume"] = None

    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"])
    out = out[(out["high"] >= out[["open", "close", "low"]].max(axis=1)) & (out["low"] <= out[["open", "close", "high"]].min(axis=1))]
    out = out.sort_values("utc_time").drop_duplicates("utc_time", keep="last")
    symbol = infer_symbol(path, default_symbol)
    tf = infer_timeframe_from_name(path) or infer_timeframe_from_rows(out["utc_time"])
    return out, symbol, tf


def upsert_bars(conn: sqlite3.Connection, bars: pd.DataFrame, symbol: str, timeframe: str, imported_utc: str) -> int:
    if bars.empty:
        return 0

    cols_info = get_table_columns(conn, "bars")
    base_cols = ["source", "symbol", "timeframe", "utc_time", "open", "high", "low", "close"]
    optional_cols = []
    for c in ["volume", "imported_utc", "ingested_at"]:
        if c in cols_info:
            optional_cols.append(c)

    insert_cols = base_cols + optional_cols
    placeholders = ", ".join(["?"] * len(insert_cols))
    col_sql = ", ".join(quote_ident(c) for c in insert_cols)

    records = []
    for _, r in bars.iterrows():
        row = {
            "source": "amarkets_mt5",
            "symbol": symbol,
            "timeframe": timeframe,
            "utc_time": pd.to_datetime(r["utc_time"], utc=True).isoformat(),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]) if pd.notna(r.get("volume")) else None,
            "imported_utc": imported_utc,
            "ingested_at": imported_utc,
        }
        records.append(tuple(row[c] for c in insert_cols))

    conn.executemany(
        f"""
        INSERT OR REPLACE INTO bars ({col_sql})
        VALUES ({placeholders})
        """,
        records,
    )
    conn.commit()
    return len(records)


def discover_csvs(paths: Sequence[Path], filename_contains: str, recursive: bool, max_files: int) -> List[Path]:
    found: List[Path] = []
    needles = [x.strip().lower() for x in filename_contains.split(",") if x.strip()]

    for item in paths:
        item = item.expanduser()
        if item.is_file() and item.suffix.lower() == ".csv":
            if not needles or any(n in item.name.lower() for n in needles):
                found.append(item)
            continue
        if not item.exists() or not item.is_dir():
            continue
        it = item.rglob("*.csv") if recursive else item.glob("*.csv")
        for p in it:
            name = p.name.lower()
            if needles and not any(n in name for n in needles):
                continue
            if any(part in str(p).lower() for part in ["data/reports", ".git", "__pycache__"]):
                continue
            found.append(p)

    found = sorted(set(found), key=lambda p: str(p))
    return found[:max_files]


def import_one(conn: sqlite3.Connection, path: Path, default_symbol: str, min_rows: int, imported_utc: str) -> ImportResult:
    try:
        raw = read_csv_flexible(path)
        rows_read = int(len(raw))
        if rows_read < min_rows:
            return ImportResult(str(path), "skipped", f"rows below min_rows={min_rows}", rows_read=rows_read)
        cols = map_ohlc_columns(raw)
        clean, symbol, timeframe = clean_ohlc(raw, cols, path, default_symbol)
        if len(clean) < min_rows:
            return ImportResult(str(path), "skipped", f"clean rows below min_rows={min_rows}", rows_read=rows_read, rows_clean=len(clean), symbol=symbol, timeframe=timeframe)
        if timeframe == "unknown":
            return ImportResult(str(path), "skipped", "could not infer timeframe", rows_read=rows_read, rows_clean=len(clean), symbol=symbol, timeframe=timeframe)
        n = upsert_bars(conn, clean, symbol, timeframe, imported_utc)
        return ImportResult(
            str(path),
            "imported",
            "ok",
            rows_read=rows_read,
            rows_clean=int(len(clean)),
            rows_upserted=int(n),
            symbol=symbol,
            timeframe=timeframe,
            first_utc=pd.to_datetime(clean["utc_time"].min(), utc=True).isoformat(),
            last_utc=pd.to_datetime(clean["utc_time"].max(), utc=True).isoformat(),
        )
    except Exception as e:
        return ImportResult(str(path), "error", str(e)[:500])


def run_stage16d(timeout_sec: int, scan_days: int) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage16d_true_forward_collection_cycle",
        "--scan-days",
        str(scan_days),
    ]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_sec)
        return {
            "cmd": " ".join(cmd),
            "returncode": int(proc.returncode),
            "status": "ok" if proc.returncode == 0 else "failed",
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "status": "exception",
            "stdout_tail": "",
            "stderr_tail": str(e)[-4000:],
        }


def read_stage16d_report() -> Dict:
    p = Path("data/reports/stage16d_true_forward_collection_cycle/stage16d_true_forward_collection_cycle.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(
    db: Path,
    out_dir: Path,
    csv_paths: Sequence[Path],
    filename_contains: str,
    recursive: bool,
    min_rows: int,
    max_files: int,
    default_symbol: str,
    timeout_sec: int,
    scan_days: int,
    no_cycle: bool,
) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        cols_info = ensure_bars_table(conn)
        before_latest = latest_bar_utc(conn)
        csvs = discover_csvs(csv_paths, filename_contains, recursive, max_files=max_files)
        results = [import_one(conn, p, default_symbol, min_rows, generated) for p in csvs]
        after_latest = latest_bar_utc(conn)
        bars_cols = sorted(cols_info.keys())
    finally:
        conn.close()

    cycle_result = {"status": "skipped", "reason": "--no-cycle"} if no_cycle else run_stage16d(timeout_sec=timeout_sec, scan_days=scan_days)
    stage16d_report = {} if no_cycle else read_stage16d_report()

    imported = [r for r in results if r.status == "imported"]
    skipped = [r for r in results if r.status == "skipped"]
    errors = [r for r in results if r.status == "error"]

    report_json = out_dir / "stage16e_amarkets_csv_refresh_cycle.json"
    report_md = out_dir / "stage16e_amarkets_csv_refresh_cycle.md"
    import_csv = out_dir / "stage16e_import_results.csv"

    res_df = pd.DataFrame([r.__dict__ for r in results])
    res_df.to_csv(import_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "csv_paths": [str(x) for x in csv_paths],
            "filename_contains": filename_contains,
            "recursive": bool(recursive),
            "min_rows": int(min_rows),
            "max_files": int(max_files),
            "default_symbol": default_symbol,
            "timeout_sec": int(timeout_sec),
            "scan_days": int(scan_days),
            "no_cycle": bool(no_cycle),
        },
        "schema": {
            "bars_columns": bars_cols,
            "has_imported_utc": "imported_utc" in bars_cols,
            "has_ingested_at": "ingested_at" in bars_cols,
        },
        "bar_state": {
            "before_latest_bar_utc": before_latest,
            "after_latest_bar_utc": after_latest,
            "latest_changed": before_latest != after_latest,
        },
        "import_summary": {
            "files_discovered": int(len(csvs)),
            "files_imported": int(len(imported)),
            "files_skipped": int(len(skipped)),
            "files_error": int(len(errors)),
            "rows_upserted": int(sum(r.rows_upserted for r in imported)),
        },
        "cycle_result": cycle_result,
        "stage16d_final_decision": stage16d_report.get("final_decision"),
        "stage16d_bar_state": stage16d_report.get("bar_state", {}),
        "stage16d_journal_counts": stage16d_report.get("journal_counts", {}),
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    report_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 16E AMarkets CSV Refresh + True-Forward Cycle",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: data refresh + research shadow cycle only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Schema compatibility",
        f"- bars_has_imported_utc: `{'imported_utc' in bars_cols}`",
        f"- bars_has_ingested_at: `{'ingested_at' in bars_cols}`",
        "",
        "## Bar state",
        f"- before_latest_bar_utc: `{before_latest}`",
        f"- after_latest_bar_utc: `{after_latest}`",
        f"- latest_changed: `{before_latest != after_latest}`",
        "",
        "## Import summary",
        f"- files_discovered: `{len(csvs)}`",
        f"- files_imported: `{len(imported)}`",
        f"- files_skipped: `{len(skipped)}`",
        f"- files_error: `{len(errors)}`",
        f"- rows_upserted: `{sum(r.rows_upserted for r in imported)}`",
        "",
        "## Imported files",
        "| File | Timeframe | Rows clean | Rows upserted | First UTC | Last UTC |",
        "|---|---|---:|---:|---|---|",
    ]
    if imported:
        for r in imported[:30]:
            lines.append(f"| `{Path(r.path).name}` | `{r.timeframe}` | {r.rows_clean} | {r.rows_upserted} | `{r.first_utc}` | `{r.last_utc}` |")
    else:
        lines.append("| none | none | 0 | 0 | none | none |")

    lines += ["", "## Errors"]
    if errors:
        for r in errors[:20]:
            lines.append(f"- `{r.path}`: {r.reason}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Stage16D cycle result",
        f"- cycle_status: `{cycle_result.get('status')}`",
        f"- cycle_returncode: `{cycle_result.get('returncode')}`",
        f"- stage16d_final_decision: `{stage16d_report.get('final_decision')}`",
        "",
        "## Stage16D bar state",
    ]
    bs = stage16d_report.get("bar_state", {}) if isinstance(stage16d_report, dict) else {}
    if bs:
        for k, v in bs.items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    lines += ["", "## Stage16D journal counts"]
    jc = stage16d_report.get("journal_counts", {}) if isinstance(stage16d_report, dict) else {}
    if jc:
        for k, v in jc.items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    if cycle_result.get("stderr_tail"):
        lines += ["", "## Cycle stderr tail", "```text", str(cycle_result.get("stderr_tail"))[-2000:], "```"]

    lines += [
        "",
        "## Interpretation",
        "- If files_imported is positive but after_latest_bar_utc is unchanged, the CSVs did not contain newer bars.",
        "- If after_latest_bar_utc is after collector_start_utc and valid_forward_rows is zero, collection is active and waiting.",
        "- Any signal remains research shadow only.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- import_csv: `{import_csv}`",
        f"- json: `{report_json}`",
        f"- md: `{report_md}`",
    ]
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 16E v2 AMarkets CSV refresh + cycle: DONE")
    print(f"before_latest={before_latest}")
    print(f"after_latest={after_latest}")
    print(f"files_imported={len(imported)} rows_upserted={sum(r.rows_upserted for r in imported)}")
    print(f"stage16d_final_decision={stage16d_report.get('final_decision')}")
    print(f"Report: {report_md}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--csv-dir", action="append", default=[], help="Directory containing AMarkets MT5 CSV files. Can be repeated.")
    p.add_argument("--csv-file", action="append", default=[], help="Exact CSV file path. Can be repeated.")
    p.add_argument("--filename-contains", default="xau,gold", help="Comma-separated filename filters. Use empty string to disable.")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--min-rows", type=int, default=100)
    p.add_argument("--max-files", type=int, default=20)
    p.add_argument("--default-symbol", default="XAUUSD")
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--scan-days", type=int, default=10)
    p.add_argument("--no-cycle", action="store_true")
    args = p.parse_args()

    paths = [Path(x).expanduser() for x in args.csv_file]
    paths += [Path(x).expanduser() for x in args.csv_dir]
    if not paths:
        paths = [
            Path("data/imports/amarkets"),
            Path("data/import/amarkets"),
            Path("data/raw/amarkets"),
            Path("data/amarkets"),
            Path("~/Downloads").expanduser(),
        ]

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        csv_paths=paths,
        filename_contains=str(args.filename_contains),
        recursive=bool(args.recursive),
        min_rows=int(args.min_rows),
        max_files=int(args.max_files),
        default_symbol=str(args.default_symbol),
        timeout_sec=int(args.timeout_sec),
        scan_days=int(args.scan_days),
        no_cycle=bool(args.no_cycle),
    )


if __name__ == "__main__":
    raise SystemExit(main())
