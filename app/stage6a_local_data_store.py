#!/usr/bin/env python3
"""
Stage 6A v2 — Local Persistent Data Store

Purpose:
- Persist AMarkets/MT5 H1 and M1 CSV exports into SQLite.
- Persist MT5 EA dry-run signals into SQLite.
- Persist Stage 5C dry-run outcomes into SQLite.
- Optionally fetch/import Twelve Data H1/M1 into the same SQLite.

v2 fixes:
- Twelve Data fetch errors are captured in the report instead of crashing.
- Placeholder API keys such as YOUR_KEY_HERE are rejected early.
- Optional --twelve-allow-insecure-ssl exists only as a last-resort diagnostic.
- Supports optional local Twelve Data JSON import via --twelve-json-dir.

Hard rules:
- No order sending.
- No demo/paper/live authorization.
- AMarkets/MT5 remains execution source of truth.
- Twelve Data is reference/secondary unless later explicitly validated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v2"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"

DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_H1 = Path("~/Downloads/amarkets_xauusd_1h.csv").expanduser()
DEFAULT_M1 = Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEFAULT_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEFAULT_OUTCOMES = Path("data/reports/stage5c_live_outcome_tracker/stage5c_live_outcomes.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage6a_local_store")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_key(k: str) -> str:
    return str(k).lower().strip().strip("<>").replace("_", "").replace(" ", "")


def pick_col(cols: Sequence[str], names: Sequence[str]) -> Optional[str]:
    mapping = {norm_key(c): c for c in cols}
    for n in names:
        if norm_key(n) in mapping:
            return mapping[norm_key(n)]
    return None


def parse_time(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d", "%Y.%m.%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_float(v, default=None):
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def parse_int(v, default=None):
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).strip()))
    except Exception:
        return default


def detect_delimiter(text: str) -> str:
    sample = text[:8192]
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def read_dict_csv(path: Path) -> Tuple[List[dict], List[str], str, str]:
    if not path.exists():
        return [], [], "missing", ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return [], [], "empty", ""
    delim = detect_delimiter(text)
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    cols = list(rows[0].keys()) if rows else []
    clean = [{str(k).strip(): ("" if v is None else str(v).strip()) for k, v in r.items() if k is not None} for r in rows]
    return clean, cols, "ok", delim


def file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS import_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_utc TEXT NOT NULL,
        tool_version TEXT NOT NULL,
        source TEXT NOT NULL,
        dataset TEXT NOT NULL,
        timeframe TEXT,
        path TEXT,
        sha256 TEXT,
        rows_seen INTEGER NOT NULL DEFAULT 0,
        rows_inserted INTEGER NOT NULL DEFAULT 0,
        rows_updated INTEGER NOT NULL DEFAULT 0,
        rows_bad INTEGER NOT NULL DEFAULT 0,
        start_utc TEXT,
        end_utc TEXT,
        metadata_json TEXT
    );

    CREATE TABLE IF NOT EXISTS bars (
        source TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        utc_time TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        tick_volume REAL,
        spread REAL,
        real_volume REAL,
        source_time TEXT,
        imported_utc TEXT NOT NULL,
        raw_json TEXT,
        PRIMARY KEY (source, symbol, timeframe, utc_time)
    );

    CREATE TABLE IF NOT EXISTS dryrun_signals (
        strategy_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal_closed_h1_utc TEXT NOT NULL,
        signal_closed_h1_server TEXT,
        logged_at_gmt TEXT,
        session_utc TEXT,
        close_h1 REAL,
        sma10 REAL,
        distance_usd REAL,
        direction TEXT,
        planned_entry_model TEXT,
        tp_usd REAL,
        sl_usd REAL,
        time_exit_h1_bars INTEGER,
        dry_run_only TEXT,
        imported_utc TEXT NOT NULL,
        raw_json TEXT,
        PRIMARY KEY (strategy_id, symbol, signal_closed_h1_utc, direction)
    );

    CREATE TABLE IF NOT EXISTS dryrun_outcomes (
        strategy_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        signal_closed_h1_utc TEXT NOT NULL,
        entry_utc TEXT,
        entry_price REAL,
        tp_price REAL,
        sl_price REAL,
        exit_utc TEXT,
        exit_price REAL,
        status TEXT,
        reason TEXT,
        session_utc TEXT,
        net_usd_x1 REAL,
        m1_bars_checked INTEGER,
        imported_utc TEXT NOT NULL,
        raw_json TEXT,
        PRIMARY KEY (strategy_id, symbol, signal_closed_h1_utc)
    );

    CREATE INDEX IF NOT EXISTS idx_bars_symbol_tf_time ON bars(symbol, timeframe, utc_time);
    CREATE INDEX IF NOT EXISTS idx_signals_time ON dryrun_signals(signal_closed_h1_utc);
    CREATE INDEX IF NOT EXISTS idx_outcomes_time ON dryrun_outcomes(signal_closed_h1_utc);
    """)
    conn.commit()


def log_import_run(conn: sqlite3.Connection, source: str, dataset: str, timeframe: str, path: str, sha256: Optional[str],
                   rows_seen: int, rows_inserted: int, rows_bad: int, start_utc: Optional[str], end_utc: Optional[str], meta: Dict):
    conn.execute(
        """
        INSERT INTO import_runs
        (created_utc, tool_version, source, dataset, timeframe, path, sha256,
         rows_seen, rows_inserted, rows_bad, start_utc, end_utc, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now_iso(), TOOL_VERSION, source, dataset, timeframe, path, sha256,
         rows_seen, rows_inserted, rows_bad, start_utc, end_utc, json.dumps(meta, ensure_ascii=False)),
    )


def import_mt5_bars(conn, csv_path: Path, source: str, symbol: str, timeframe: str, server_offset_hours: float) -> Dict:
    rows, cols, status, delim = read_dict_csv(csv_path)
    if status != "ok":
        return {"dataset": "bars", "source": source, "timeframe": timeframe, "status": status, "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    date_col = pick_col(cols, ["date", "<DATE>"])
    time_col = pick_col(cols, ["time", "<TIME>", "datetime", "timestamp"])
    combined_col = pick_col(cols, ["datetime", "timestamp", "timegmt", "time_utc"])
    open_col = pick_col(cols, ["open", "<OPEN>"])
    high_col = pick_col(cols, ["high", "<HIGH>"])
    low_col = pick_col(cols, ["low", "<LOW>"])
    close_col = pick_col(cols, ["close", "<CLOSE>"])
    tick_vol_col = pick_col(cols, ["tickvol", "tick_volume", "<TICKVOL>", "volume"])
    spread_col = pick_col(cols, ["spread", "<SPREAD>"])
    real_vol_col = pick_col(cols, ["vol", "real_volume", "<VOL>"])

    values, bad = [], 0
    start_utc = end_utc = None
    imported_utc = now_iso()
    offset = timedelta(hours=server_offset_hours)

    for r in rows:
        if date_col and time_col and date_col != time_col:
            raw_time = f"{r.get(date_col, '')} {r.get(time_col, '')}".strip()
        elif combined_col:
            raw_time = r.get(combined_col, "")
        else:
            raw_time = r.get(time_col or "", "")

        t_server = parse_time(raw_time)
        o, h, l, c = parse_float(r.get(open_col or "")), parse_float(r.get(high_col or "")), parse_float(r.get(low_col or "")), parse_float(r.get(close_col or ""))
        if t_server is None or o is None or h is None or l is None or c is None:
            bad += 1
            continue

        t_utc = (t_server - offset).astimezone(timezone.utc).replace(microsecond=0).isoformat()
        start_utc = t_utc if start_utc is None or t_utc < start_utc else start_utc
        end_utc = t_utc if end_utc is None or t_utc > end_utc else end_utc
        values.append((source, symbol, timeframe, t_utc, o, h, l, c,
                       parse_float(r.get(tick_vol_col or "")), parse_float(r.get(spread_col or "")), parse_float(r.get(real_vol_col or "")),
                       raw_time, imported_utc, json.dumps(r, ensure_ascii=False)))

    conn.executemany("""
        INSERT OR REPLACE INTO bars
        (source, symbol, timeframe, utc_time, open, high, low, close, tick_volume, spread, real_volume, source_time, imported_utc, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, values)
    log_import_run(conn, source, "bars", timeframe, str(csv_path), file_sha256(csv_path), len(rows), len(values), bad, start_utc, end_utc, {"delimiter": "TAB" if delim == "\t" else delim, "columns": cols})
    conn.commit()
    return {"dataset": "bars", "source": source, "symbol": symbol, "timeframe": timeframe, "status": "ok", "rows_seen": len(rows), "rows_inserted_or_replaced": len(values), "rows_bad": bad, "start_utc": start_utc, "end_utc": end_utc}


def import_signals(conn, csv_path: Path, server_offset_hours: float) -> Dict:
    rows, cols, status, delim = read_dict_csv(csv_path)
    if status != "ok":
        return {"dataset": "dryrun_signals", "source": "mt5_ea", "status": status, "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    values, bad = [], 0
    start_utc = end_utc = None
    imported_utc = now_iso()
    offset = timedelta(hours=server_offset_hours)

    for r in rows:
        strategy_id = r.get("strategy_id") or STRATEGY_ID
        symbol = r.get("symbol") or "XAUUSD"
        direction = r.get("direction") or "long"
        server_raw = r.get("signal_closed_h1_time_server") or ""
        t_server = parse_time(server_raw)
        if t_server is None:
            bad += 1
            continue
        t_utc = (t_server - offset).astimezone(timezone.utc).replace(microsecond=0).isoformat()
        start_utc = t_utc if start_utc is None or t_utc < start_utc else start_utc
        end_utc = t_utc if end_utc is None or t_utc > end_utc else end_utc
        values.append((strategy_id, symbol, t_utc, server_raw, r.get("logged_at_gmt"), r.get("session_utc"),
                       parse_float(r.get("close_h1")), parse_float(r.get("sma10")), parse_float(r.get("distance_usd")),
                       direction, r.get("planned_entry_model"), parse_float(r.get("tp_usd")), parse_float(r.get("sl_usd")),
                       parse_int(r.get("time_exit_h1_bars")), r.get("dry_run_only"), imported_utc, json.dumps(r, ensure_ascii=False)))

    conn.executemany("""
        INSERT OR REPLACE INTO dryrun_signals
        (strategy_id, symbol, signal_closed_h1_utc, signal_closed_h1_server, logged_at_gmt, session_utc,
         close_h1, sma10, distance_usd, direction, planned_entry_model, tp_usd, sl_usd, time_exit_h1_bars,
         dry_run_only, imported_utc, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, values)
    log_import_run(conn, "mt5_ea", "dryrun_signals", "event", str(csv_path), file_sha256(csv_path), len(rows), len(values), bad, start_utc, end_utc, {"delimiter": "TAB" if delim == "\t" else delim, "columns": cols})
    conn.commit()
    return {"dataset": "dryrun_signals", "source": "mt5_ea", "status": "ok", "rows_seen": len(rows), "rows_inserted_or_replaced": len(values), "rows_bad": bad, "start_utc": start_utc, "end_utc": end_utc}


def import_outcomes(conn, csv_path: Path) -> Dict:
    rows, cols, status, delim = read_dict_csv(csv_path)
    if status != "ok":
        return {"dataset": "dryrun_outcomes", "source": "stage5c", "status": status, "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    values, bad = [], 0
    start_utc = end_utc = None
    imported_utc = now_iso()

    for r in rows:
        symbol = r.get("symbol") or "XAUUSD"
        closed_raw = r.get("closed_h1_utc") or r.get("signal_closed_h1_utc")
        t = parse_time(closed_raw or "")
        if t is None:
            bad += 1
            continue
        closed_utc = t.replace(microsecond=0).isoformat()
        start_utc = closed_utc if start_utc is None or closed_utc < start_utc else start_utc
        end_utc = closed_utc if end_utc is None or closed_utc > end_utc else end_utc
        values.append((STRATEGY_ID, symbol, closed_utc, r.get("entry_utc"), parse_float(r.get("entry_price")),
                       parse_float(r.get("tp_price")), parse_float(r.get("sl_price")), r.get("exit_utc"), parse_float(r.get("exit_price")),
                       r.get("status"), r.get("reason"), r.get("session_utc"), parse_float(r.get("net_usd_x1")), parse_int(r.get("m1_bars_checked")),
                       imported_utc, json.dumps(r, ensure_ascii=False)))

    conn.executemany("""
        INSERT OR REPLACE INTO dryrun_outcomes
        (strategy_id, symbol, signal_closed_h1_utc, entry_utc, entry_price, tp_price, sl_price,
         exit_utc, exit_price, status, reason, session_utc, net_usd_x1, m1_bars_checked,
         imported_utc, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, values)
    log_import_run(conn, "stage5c", "dryrun_outcomes", "event", str(csv_path), file_sha256(csv_path), len(rows), len(values), bad, start_utc, end_utc, {"delimiter": "TAB" if delim == "\t" else delim, "columns": cols})
    conn.commit()
    return {"dataset": "dryrun_outcomes", "source": "stage5c", "status": "ok", "rows_seen": len(rows), "rows_inserted_or_replaced": len(values), "rows_bad": bad, "start_utc": start_utc, "end_utc": end_utc}


def invalid_api_key(api_key: str) -> bool:
    s = (api_key or "").strip()
    return not s or s.upper() in {"YOUR_KEY_HERE", "YOUR_API_KEY", "TWELVE_DATA_API_KEY", "PASTE_KEY_HERE"} or len(s) < 10


def fetch_twelve_data(interval: str, api_key: str, outputsize: int, allow_insecure_ssl: bool = False) -> Tuple[Optional[dict], Optional[str]]:
    params = {
        "symbol": "XAU/USD",
        "interval": interval,
        "apikey": api_key,
        "format": "JSON",
        "outputsize": str(outputsize),
        "timezone": "UTC",
        "order": "ASC",
    }
    url = "https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(params)
    context = None
    if allow_insecure_ssl:
        context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(url, timeout=30, context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except ssl.SSLCertVerificationError as e:
        return None, f"ssl_certificate_verify_failed: {e}"
    except urllib.error.URLError as e:
        return None, f"url_error: {e}"
    except TimeoutError as e:
        return None, f"timeout: {e}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def import_twelve_values(conn, values_raw: List[dict], timeframe: str, interval: str, path_label: str, meta: Dict) -> Dict:
    imported_utc = now_iso()
    rows, bad = [], 0
    start_utc = end_utc = None

    for r in values_raw:
        t = parse_time(r.get("datetime") or r.get("time") or "")
        o, h, l, c = parse_float(r.get("open")), parse_float(r.get("high")), parse_float(r.get("low")), parse_float(r.get("close"))
        if t is None or o is None or h is None or l is None or c is None:
            bad += 1
            continue
        iso = t.replace(microsecond=0).isoformat()
        start_utc = iso if start_utc is None or iso < start_utc else start_utc
        end_utc = iso if end_utc is None or iso > end_utc else end_utc
        rows.append(("twelve_data", "XAUUSD", timeframe, iso, o, h, l, c, None, None, None, r.get("datetime"), imported_utc, json.dumps(r, ensure_ascii=False)))

    conn.executemany("""
        INSERT OR REPLACE INTO bars
        (source, symbol, timeframe, utc_time, open, high, low, close, tick_volume, spread, real_volume, source_time, imported_utc, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    log_import_run(conn, "twelve_data", "bars", timeframe, path_label, None, len(values_raw), len(rows), bad, start_utc, end_utc, {"interval": interval, "meta": meta})
    conn.commit()

    return {"dataset": "bars", "source": "twelve_data", "symbol": "XAUUSD", "timeframe": timeframe, "status": "ok", "rows_seen": len(values_raw), "rows_inserted_or_replaced": len(rows), "rows_bad": bad, "start_utc": start_utc, "end_utc": end_utc}


def import_twelve_data(conn, interval: str, timeframe: str, api_key: str, outputsize: int, allow_insecure_ssl: bool) -> Dict:
    if invalid_api_key(api_key):
        return {"dataset": "bars", "source": "twelve_data", "timeframe": timeframe, "status": "invalid_or_placeholder_api_key", "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    data, err = fetch_twelve_data(interval, api_key, outputsize, allow_insecure_ssl=allow_insecure_ssl)
    if err:
        return {"dataset": "bars", "source": "twelve_data", "timeframe": timeframe, "status": "fetch_error", "error": err, "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    if data is None:
        return {"dataset": "bars", "source": "twelve_data", "timeframe": timeframe, "status": "fetch_error_empty_response", "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}
    if data.get("status") == "error":
        return {"dataset": "bars", "source": "twelve_data", "timeframe": timeframe, "status": "api_error", "error": data.get("message") or data.get("code"), "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0}

    values_raw = data.get("values") or []
    return import_twelve_values(conn, values_raw, timeframe, interval, "api://twelvedata/time_series", data.get("meta", {}))


def import_twelve_json_dir(conn, json_dir: Path) -> List[Dict]:
    results = []
    specs = [
        ("1h", "1h", ["twelve_xauusd_1h.json", "xauusd_1h.json", "twelve_data_1h.json"]),
        ("1min", "1m", ["twelve_xauusd_1m.json", "xauusd_1m.json", "twelve_data_1m.json"]),
    ]
    for interval, timeframe, names in specs:
        found = None
        for n in names:
            p = json_dir / n
            if p.exists():
                found = p
                break
        if found is None:
            results.append({"dataset": "bars", "source": "twelve_data_json", "timeframe": timeframe, "status": "missing_json_file", "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0})
            continue

        try:
            data = json.loads(found.read_text(encoding="utf-8", errors="replace"))
            if data.get("status") == "error":
                results.append({"dataset": "bars", "source": "twelve_data_json", "timeframe": timeframe, "status": "api_error_in_json", "error": data.get("message") or data.get("code"), "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0})
                continue
            values_raw = data.get("values") or []
            r = import_twelve_values(conn, values_raw, timeframe, interval, str(found), data.get("meta", {}))
            r["source"] = "twelve_data_json"
            results.append(r)
        except Exception as e:
            results.append({"dataset": "bars", "source": "twelve_data_json", "timeframe": timeframe, "status": "json_import_error", "error": f"{type(e).__name__}: {e}", "rows_seen": 0, "rows_inserted_or_replaced": 0, "rows_bad": 0})
    return results


def db_counts(conn) -> Dict[str, int]:
    out = {}
    for table in ("bars", "dryrun_signals", "dryrun_outcomes", "import_runs"):
        out[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return out


def write_report(out_dir: Path, db_path: Path, results: List[Dict], counts: Dict[str, int]):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"tool_version": TOOL_VERSION, "generated_utc": now_iso(), "db_path": str(db_path), "results": results, "counts": counts, "hard_rule": "Persistence only. No orders."}
    (out_dir / "stage6a_local_store.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 6A Local Persistent Data Store",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: this imports local/reference data into SQLite only. It does not authorize demo, paper, or live orders.",
        "",
        "## Database",
        f"- path: `{db_path}`",
        "",
        "## Import results",
        "| Dataset | Source | Timeframe | Status | Rows seen | Rows inserted/replaced | Rows bad | Start UTC | End UTC | Error |",
        "|---|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('dataset','')} | {r.get('source','')} | {r.get('timeframe','')} | {r.get('status','')} | "
            f"{r.get('rows_seen',0)} | {r.get('rows_inserted_or_replaced',0)} | {r.get('rows_bad',0)} | "
            f"{r.get('start_utc','') or ''} | {r.get('end_utc','') or ''} | {str(r.get('error','')).replace('|','/')} |"
        )
    lines += [
        "",
        "## DB counts",
        f"- bars: `{counts.get('bars',0)}`",
        f"- dryrun_signals: `{counts.get('dryrun_signals',0)}`",
        f"- dryrun_outcomes: `{counts.get('dryrun_outcomes',0)}`",
        f"- import_runs: `{counts.get('import_runs',0)}`",
        "",
        "## Decision",
        "- Use this SQLite store as local persistent evidence.",
        "- AMarkets/MT5 remains the execution feed. Twelve Data is reference/secondary unless later explicitly validated.",
        "- Twelve fetch failures should not block local broker persistence.",
    ]
    (out_dir / "stage6a_local_store.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--h1-csv", default=str(DEFAULT_H1))
    ap.add_argument("--m1-csv", default=str(DEFAULT_M1))
    ap.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS))
    ap.add_argument("--outcomes-csv", default=str(DEFAULT_OUTCOMES))
    ap.add_argument("--server-utc-offset-hours", type=float, default=2.0)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--skip-mt5", action="store_true")
    ap.add_argument("--skip-signals", action="store_true")
    ap.add_argument("--skip-outcomes", action="store_true")
    ap.add_argument("--fetch-twelve", action="store_true")
    ap.add_argument("--twelve-outputsize", type=int, default=5000)
    ap.add_argument("--twelve-json-dir", default="")
    ap.add_argument("--twelve-allow-insecure-ssl", action="store_true", help="Last-resort diagnostic only. Prefer fixing local certificates.")
    args = ap.parse_args()

    conn = connect_db(Path(args.db))
    init_db(conn)

    results = []
    if not args.skip_mt5:
        results.append(import_mt5_bars(conn, Path(args.h1_csv).expanduser(), "amarkets_mt5", args.symbol, "1h", args.server_utc_offset_hours))
        results.append(import_mt5_bars(conn, Path(args.m1_csv).expanduser(), "amarkets_mt5", args.symbol, "1m", args.server_utc_offset_hours))
    if not args.skip_signals:
        results.append(import_signals(conn, Path(args.signals_csv).expanduser(), args.server_utc_offset_hours))
    if not args.skip_outcomes:
        results.append(import_outcomes(conn, Path(args.outcomes_csv).expanduser()))

    if args.fetch_twelve:
        api_key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
        results.append(import_twelve_data(conn, "1h", "1h", api_key, args.twelve_outputsize, args.twelve_allow_insecure_ssl))
        results.append(import_twelve_data(conn, "1min", "1m", api_key, args.twelve_outputsize, args.twelve_allow_insecure_ssl))

    if args.twelve_json_dir:
        results.extend(import_twelve_json_dir(conn, Path(args.twelve_json_dir).expanduser()))

    counts = db_counts(conn)
    write_report(Path(args.out_dir), Path(args.db), results, counts)
    conn.close()

    print("Stage 6A local persistent data store: DONE")
    print(f"DB: {args.db}")
    for r in results:
        msg = f"{r.get('source')} {r.get('dataset')} {r.get('timeframe','')}: status={r.get('status')} rows={r.get('rows_inserted_or_replaced',0)} bad={r.get('rows_bad',0)}"
        if r.get("error"):
            msg += f" error={r.get('error')}"
        print(msg)
    print(f"Report: {Path(args.out_dir) / 'stage6a_local_store.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
