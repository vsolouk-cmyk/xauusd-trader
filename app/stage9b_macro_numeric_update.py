#!/usr/bin/env python3
"""
Stage 9B — Macro Numeric Data Update

v2 SSL-resilient version.

Purpose:
- Fetch structured numeric macro/market series on a regular schedule.
- Run locally or in GitHub Actions.
- Store outputs as CSV + local SQLite tables.
- Degrade gracefully if API keys/network/SSL are unavailable.

Primary source:
- FRED series/observations API.

SSL modes:
- default: normal certificate verification.
- certifi: use certifi CA bundle if certifi is installed.
- insecure: disable certificate verification. Local fallback only; not recommended for GitHub.

Hard rules:
- Data collection only.
- No trading signal.
- No EA change.
- No order/demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


TOOL_VERSION = "v2_ssl_resilience"

DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/macro")
DEFAULT_REPORT_DIR = Path("data/reports/stage9b_macro_numeric_update")


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    label: str
    category: str
    gold_driver: str
    update_frequency: str
    units_hint: str


SERIES: List[FredSeries] = [
    FredSeries("DGS10", "US 10Y Treasury yield", "rates", "real_yield_pressure_proxy", "daily", "percent"),
    FredSeries("DGS2", "US 2Y Treasury yield", "rates", "fed_path_pressure_proxy", "daily", "percent"),
    FredSeries("DFII10", "US 10Y TIPS real yield", "real_yields", "real_yield_pressure", "daily", "percent"),
    FredSeries("DTWEXBGS", "Nominal Broad US Dollar Index", "usd", "usd_pressure", "daily", "index"),
    FredSeries("DCOILWTICO", "WTI crude oil spot price", "oil", "oil_inflation_pressure", "daily", "usd_per_barrel"),
    FredSeries("DCOILBRENTEU", "Brent crude oil spot price", "oil", "oil_inflation_pressure", "daily", "usd_per_barrel"),
    FredSeries("CPIAUCSL", "CPI All Urban Consumers", "inflation", "inflation_pressure", "monthly", "index"),
    FredSeries("PPIACO", "Producer Price Index All Commodities", "inflation", "inflation_pressure", "monthly", "index"),
    FredSeries("PAYEMS", "Nonfarm Payrolls", "labor", "growth_fed_path", "monthly", "thousands"),
    FredSeries("UNRATE", "Unemployment Rate", "labor", "growth_fed_path", "monthly", "percent"),
    FredSeries("FEDFUNDS", "Effective Federal Funds Rate", "policy", "fed_policy", "monthly", "percent"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_float(v: str) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == ".":
        return None
    try:
        return float(s)
    except Exception:
        return None


def build_ssl_context(ssl_mode: str) -> Tuple[Optional[ssl.SSLContext], str]:
    mode = (ssl_mode or "default").strip().lower()

    if mode == "default" or mode == "auto":
        return None, "default"

    if mode == "certifi":
        try:
            import certifi  # type: ignore
            return ssl.create_default_context(cafile=certifi.where()), "certifi"
        except Exception as e:
            raise RuntimeError(f"certifi SSL mode requested but certifi is unavailable: {type(e).__name__}: {e}") from e

    if mode == "insecure":
        return ssl._create_unverified_context(), "insecure"

    raise ValueError(f"Unknown ssl mode: {ssl_mode}. Use default, certifi, insecure, or auto.")


def fetch_url(url: str, timeout: int, ssl_mode: str) -> Tuple[str, str]:
    ctx, effective = build_ssl_context(ssl_mode)
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-trader-stage9b/2.0"})

    if ctx is None:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8"), effective

    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8"), effective


def fetch_url_auto(url: str, timeout: int, allow_insecure_fallback: bool) -> Tuple[str, str, List[str]]:
    attempts = ["default", "certifi"]
    if allow_insecure_fallback:
        attempts.append("insecure")

    warnings = []
    last_error = None
    for mode in attempts:
        try:
            raw, effective = fetch_url(url, timeout, mode)
            if mode == "insecure":
                warnings.append("Used insecure SSL mode. Local fallback only; not preferred for production/GitHub.")
            return raw, effective, warnings
        except Exception as e:
            last_error = e
            warnings.append(f"SSL/network attempt failed with mode={mode}: {type(e).__name__}: {e}")

    raise RuntimeError("; ".join(warnings) + (f"; final_error={last_error}" if last_error else ""))


def fetch_fred_series(series: FredSeries, api_key: str, start_date: str, timeout: int, ssl_mode: str, allow_insecure_fallback: bool) -> Dict:
    params = {
        "series_id": series.series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "sort_order": "asc",
    }
    url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)

    warnings: List[str] = []
    if ssl_mode == "auto":
        raw, effective_ssl_mode, warnings = fetch_url_auto(url, timeout, allow_insecure_fallback)
    else:
        raw, effective_ssl_mode = fetch_url(url, timeout, ssl_mode)

    data = json.loads(raw)
    if "error_code" in data or "error_message" in data:
        raise RuntimeError(f"FRED API error: {data.get('error_code')} {data.get('error_message')}")

    observations = []
    for obs in data.get("observations", []):
        value = parse_float(obs.get("value"))
        observations.append({
            "source": "FRED",
            "series_id": series.series_id,
            "date": obs.get("date"),
            "value": value,
            "realtime_start": obs.get("realtime_start"),
            "realtime_end": obs.get("realtime_end"),
            "label": series.label,
            "category": series.category,
            "gold_driver": series.gold_driver,
            "update_frequency": series.update_frequency,
            "units_hint": series.units_hint,
            "fetched_utc": now_iso(),
            "ssl_mode": effective_ssl_mode,
        })
    return {"status": "ok", "series": asdict(series), "observations": observations, "effective_ssl_mode": effective_ssl_mode, "warnings": warnings}


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_numeric_observations (
            source TEXT NOT NULL,
            series_id TEXT NOT NULL,
            obs_date TEXT NOT NULL,
            value REAL,
            realtime_start TEXT,
            realtime_end TEXT,
            label TEXT,
            category TEXT,
            gold_driver TEXT,
            update_frequency TEXT,
            units_hint TEXT,
            fetched_utc TEXT,
            ssl_mode TEXT,
            PRIMARY KEY (source, series_id, obs_date, realtime_start, realtime_end)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_update_runs (
            run_id TEXT PRIMARY KEY,
            tool_version TEXT,
            source TEXT,
            status TEXT,
            series_requested INTEGER,
            series_ok INTEGER,
            observations_written INTEGER,
            generated_utc TEXT,
            message TEXT
        )
    """)
    conn.commit()


def upsert_observations(conn: sqlite3.Connection, rows: List[Dict]) -> int:
    n = 0
    for r in rows:
        conn.execute("""
            INSERT OR REPLACE INTO macro_numeric_observations (
                source, series_id, obs_date, value, realtime_start, realtime_end,
                label, category, gold_driver, update_frequency, units_hint, fetched_utc, ssl_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["source"], r["series_id"], r["date"], r["value"], r["realtime_start"], r["realtime_end"],
            r["label"], r["category"], r["gold_driver"], r["update_frequency"], r["units_hint"], r["fetched_utc"],
            r.get("ssl_mode", ""),
        ))
        n += 1
    conn.commit()
    return n


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run_update(start_date: str, out_dir: Path, report_dir: Path, db_path: Path, strict: bool = False, ssl_mode: str = "auto", allow_insecure_fallback: bool = False, timeout: int = 30) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    generated = now_iso()
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    all_rows: List[Dict] = []
    series_results: List[Dict] = []
    errors: List[str] = []
    warnings: List[str] = []

    if not api_key:
        errors.append("FRED_API_KEY is missing. Numeric update skipped but report/artifact created.")
        status = "missing_api_key"
    else:
        status = "ok"
        for s in SERIES:
            try:
                res = fetch_fred_series(s, api_key, start_date, timeout, ssl_mode, allow_insecure_fallback)
                rows = res["observations"]
                all_rows.extend(rows)
                warnings.extend([f"{s.series_id}: {w}" for w in res.get("warnings", [])])
                series_results.append({
                    "series_id": s.series_id,
                    "label": s.label,
                    "status": "ok",
                    "observations": len(rows),
                    "latest_date": rows[-1]["date"] if rows else "",
                    "latest_value": rows[-1]["value"] if rows else None,
                    "ssl_mode": res.get("effective_ssl_mode", ""),
                })
            except Exception as e:
                status = "partial_error"
                errors.append(f"{s.series_id}: {type(e).__name__}: {e}")
                series_results.append({
                    "series_id": s.series_id,
                    "label": s.label,
                    "status": "error",
                    "observations": 0,
                    "latest_date": "",
                    "latest_value": None,
                    "ssl_mode": "",
                    "error": f"{type(e).__name__}: {e}",
                })

    write_csv(out_dir / "macro_numeric_observations.csv", all_rows)
    write_csv(report_dir / "macro_numeric_series_status.csv", series_results)

    by_series: Dict[str, List[Dict]] = {}
    for r in all_rows:
        by_series.setdefault(r["series_id"], []).append(r)
    for sid, rows in by_series.items():
        write_csv(out_dir / "series" / f"{sid}.csv", rows)

    obs_written = 0
    try:
        conn = sqlite3.connect(db_path)
        ensure_tables(conn)
        obs_written = upsert_observations(conn, all_rows)
        run_id = f"stage9b_numeric_{generated}"
        conn.execute("""
            INSERT OR REPLACE INTO macro_update_runs (
                run_id, tool_version, source, status, series_requested, series_ok,
                observations_written, generated_utc, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, TOOL_VERSION, "FRED", status, len(SERIES),
            len([x for x in series_results if x.get("status") == "ok"]),
            obs_written, generated, "; ".join((errors + warnings)[:20])
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        errors.append(f"SQLite write failed: {type(e).__name__}: {e}")
        if status == "ok":
            status = "db_error"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "status": status,
        "start_date": start_date,
        "ssl_mode_requested": ssl_mode,
        "allow_insecure_fallback": allow_insecure_fallback,
        "series_requested": len(SERIES),
        "series_ok": len([x for x in series_results if x.get("status") == "ok"]),
        "observations_fetched": len(all_rows),
        "observations_written_sqlite": obs_written,
        "out_dir": str(out_dir),
        "report_dir": str(report_dir),
        "db_path": str(db_path),
        "errors": errors,
        "warnings": warnings,
        "series_results": series_results,
    }
    (report_dir / "macro_numeric_update.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9B Macro Numeric Update",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "## Status",
        f"- status: `{status}`",
        f"- start_date: `{start_date}`",
        f"- ssl_mode_requested: `{ssl_mode}`",
        f"- allow_insecure_fallback: `{allow_insecure_fallback}`",
        f"- series_requested: `{len(SERIES)}`",
        f"- series_ok: `{payload['series_ok']}`",
        f"- observations_fetched: `{len(all_rows)}`",
        f"- observations_written_sqlite: `{obs_written}`",
        "",
        "## Series status",
        "| Series | Label | Status | SSL mode | Observations | Latest date | Latest value |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for r in series_results:
        lines.append(f"| {r['series_id']} | {r['label']} | {r['status']} | {r.get('ssl_mode','')} | {r['observations']} | {r['latest_date']} | {r['latest_value']} |")
    if warnings:
        lines += ["", "## Warnings"]
        for w in warnings[:30]:
            lines.append(f"- `{w}`")
    if errors:
        lines += ["", "## Errors"]
        for e in errors[:30]:
            lines.append(f"- `{e}`")
    lines += [
        "",
        "## Decision",
        "- This is data collection only.",
        "- No EA/order workflow changes are authorized.",
        "- Prefer default/certifi SSL. Use insecure only as a local fallback when macOS/Python certificate store is broken.",
    ]
    (report_dir / "macro_numeric_update.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 9B macro numeric update: DONE")
    print(f"status={status} observations={len(all_rows)} report={report_dir / 'macro_numeric_update.md'}")

    if strict and status != "ok":
        return 2
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start-date", default="2022-01-01")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--strict", action="store_true")
    p.add_argument("--ssl-mode", default=os.environ.get("FRED_SSL_MODE", "auto"), choices=["auto", "default", "certifi", "insecure"])
    p.add_argument("--allow-insecure-ssl", action="store_true", default=os.environ.get("FRED_ALLOW_INSECURE_SSL", "").strip() == "1")
    p.add_argument("--timeout", type=int, default=30)
    args = p.parse_args()

    return run_update(
        args.start_date,
        Path(args.out_dir),
        Path(args.report_dir),
        Path(args.db),
        args.strict,
        args.ssl_mode,
        args.allow_insecure_ssl,
        args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
