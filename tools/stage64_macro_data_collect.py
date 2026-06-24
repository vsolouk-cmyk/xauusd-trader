#!/usr/bin/env python3
"""
Stage64 macro-regime source acquisition helper.

Purpose:
- Fetch only acquisition/input data for Stage64 macro-regime research.
- Produce raw CSV files that match Stage64D3 schemas.
- Produce manual templates for sources that should not be scraped blindly.
- Produce manifests/reports for auditability.

This script never creates trading signals and never authorizes validation or orders.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UTC = dt.timezone.utc


def utc_now_iso() -> str:
    return dt.datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: str) -> dt.date:
    value = (value or "").strip()
    return dt.date.fromisoformat(value[:10])


def date_to_utc_midnight(d: dt.date) -> str:
    return dt.datetime(d.year, d.month, d.day, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def next_utc_day_available_after(d: dt.date) -> str:
    return date_to_utc_midnight(d + dt.timedelta(days=1))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def fetch_text(url: str, *, timeout: int = 45, attempts: int = 3, delay: float = 2.0) -> str:
    last_exc: Optional[BaseException] = None
    headers = {"User-Agent": "xauusd-stage64-data-acquisition/1.0"}
    for i in range(attempts):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            return data.decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if i + 1 < attempts:
                time.sleep(delay)
    raise RuntimeError(f"Failed to fetch URL after {attempts} attempts: {url} :: {last_exc}")


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
            count += 1
    return count


def fetch_stooq_daily(symbol: str, start_date: str, source_label: str, *, output_schema: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    d1 = start_date.replace("-", "")
    d2 = dt.datetime.now(tz=UTC).date().strftime("%Y%m%d")
    params = urlencode({"s": symbol, "i": "d", "d1": d1, "d2": d2})
    url = f"https://stooq.com/q/d/l/?{params}"
    text = fetch_text(url)
    rows_raw = list(csv.DictReader(io.StringIO(text)))
    rows: List[Dict[str, Any]] = []
    for rr in rows_raw:
        date_raw = rr.get("Date") or rr.get("date") or rr.get("DATE")
        if not date_raw or date_raw.lower().startswith("no data"):
            continue
        try:
            d = parse_date(date_raw)
        except ValueError:
            continue
        close = rr.get("Close") or rr.get("close") or ""
        if close in ("", "N/D", "No data"):
            continue
        if output_schema == "ohlc":
            rows.append({
                "date_utc": date_to_utc_midnight(d),
                "open": rr.get("Open") or rr.get("open") or "",
                "high": rr.get("High") or rr.get("high") or "",
                "low": rr.get("Low") or rr.get("low") or "",
                "close": close,
                "volume": rr.get("Volume") or rr.get("volume") or "",
                "source": source_label,
                "available_after_utc": next_utc_day_available_after(d),
            })
        else:
            rows.append({
                "date_utc": date_to_utc_midnight(d),
                "close": close,
                "source": source_label,
                "available_after_utc": next_utc_day_available_after(d),
            })
    meta = {"provider": "stooq", "symbol": symbol, "url_used": url, "rows_raw": len(rows_raw), "rows_output": len(rows)}
    return rows, meta


def fetch_fred_series(series_id: str, start_date: str, source_label: str, *, api_key: str = "", allow_graph_fallback: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {"provider": "fred", "series_id": series_id}
    if api_key:
        params = urlencode({
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date,
        })
        url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
        text = fetch_text(url)
        payload = json.loads(text)
        observations = payload.get("observations", [])
        for obs in observations:
            val = str(obs.get("value", "")).strip()
            if val in ("", "."):
                continue
            try:
                d = parse_date(str(obs.get("date", "")))
            except ValueError:
                continue
            rows.append({
                "date_utc": date_to_utc_midnight(d),
                "value": val,
                "source": source_label,
                "available_after_utc": next_utc_day_available_after(d),
            })
        meta.update({"endpoint_mode": "fred_api", "url_used": "FRED_API_OBSERVATIONS", "rows_raw": len(observations), "rows_output": len(rows)})
        return rows, meta

    if not allow_graph_fallback:
        raise RuntimeError(f"FRED_API_KEY missing and graph fallback disabled for {series_id}")

    params = urlencode({"id": series_id, "observation_start": start_date})
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?{params}"
    text = fetch_text(url)
    reader = csv.DictReader(io.StringIO(text))
    raw_count = 0
    for rr in reader:
        raw_count += 1
        date_raw = rr.get("observation_date") or rr.get("DATE") or rr.get("date")
        val = rr.get(series_id) or rr.get(series_id.upper()) or rr.get(series_id.lower()) or ""
        val = str(val).strip()
        if val in ("", "."):
            continue
        try:
            d = parse_date(str(date_raw))
        except ValueError:
            continue
        if d < parse_date(start_date):
            continue
        rows.append({
            "date_utc": date_to_utc_midnight(d),
            "value": val,
            "source": source_label,
            "available_after_utc": next_utc_day_available_after(d),
        })
    meta.update({"endpoint_mode": "fred_graph_csv_fallback", "url_used": "FRED_GRAPH_CSV", "rows_raw": raw_count, "rows_output": len(rows)})
    return rows, meta


def fred_rows_to_target(rows: List[Dict[str, Any]], target: Dict[str, Any]) -> List[Dict[str, Any]]:
    target_file = str(target.get("target_file", ""))
    if "real_yield_or_proxy" in target_file:
        return [
            {
                "date_utc": r["date_utc"],
                "value": r["value"],
                "source": r["source"],
                "available_after_utc": r["available_after_utc"],
                "proxy_method": target.get("proxy_method", "FRED_SERIES_DIRECT"),
            }
            for r in rows
        ]
    return [
        {
            "date_utc": r["date_utc"],
            "close": r["value"],
            "source": r["source"],
            "available_after_utc": r["available_after_utc"],
        }
        for r in rows
    ]


def write_manual_template(target: Dict[str, Any], path: Path) -> int:
    cols = list(target.get("required_columns", []))
    sample: Dict[str, str] = {c: "" for c in cols}
    # One commented-like sample row is not valid CSV comment; keep blank data only if no actual data.
    return write_csv(path, cols, [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64 macro-regime data acquisition helper")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64_macro_data_acquisition_sources.json")
    ap.add_argument("--out", default="reports/stage64_macro_data_acquisition")
    ap.add_argument("--raw-dir", default="data/macro_regime/raw")
    ap.add_argument("--start-date", default=None)
    ap.add_argument("--offline-template-only", action="store_true", help="Do not fetch network sources; create templates and manifests only.")
    ap.add_argument("--allow-fred-graph-fallback", action="store_true", default=True)
    ap.add_argument("--attempts", type=int, default=3)
    ns = ap.parse_args()

    root = Path(ns.root).resolve()
    config_path = root / ns.config
    out_dir = root / ns.out
    raw_dir = root / ns.raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    start_date = ns.start_date or config.get("policy", {}).get("start_date", "2011-01-01")
    fred_key = os.environ.get("FRED_API_KEY", "").strip()

    acquisition_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for target in config.get("targets", []):
        target_rel = target["target_file"]
        target_path = root / target_rel
        provider = target.get("provider")
        auto_fetch = bool(target.get("auto_fetch"))
        required_columns = list(target.get("required_columns", []))
        status = "NOT_STARTED"
        row_count = 0
        meta: Dict[str, Any] = {}
        try:
            if ns.offline_template_only or not auto_fetch:
                row_count = write_manual_template(target, target_path)
                status = "TEMPLATE_CREATED" if not auto_fetch else "OFFLINE_TEMPLATE_CREATED"
                meta = {"provider": provider, "auto_fetch": auto_fetch, "offline_template_only": ns.offline_template_only}
            elif provider == "stooq":
                output_schema = "ohlc" if "open" in required_columns else "close"
                rows, meta = fetch_stooq_daily(str(target["symbol"]), start_date, str(target["source_label"]), output_schema=output_schema)
                row_count = write_csv(target_path, required_columns, rows)
                status = "FETCHED"
            elif provider == "fred":
                rows_raw, meta = fetch_fred_series(str(target["series_id"]), start_date, str(target["source_label"]), api_key=fred_key, allow_graph_fallback=ns.allow_fred_graph_fallback)
                rows = fred_rows_to_target(rows_raw, target)
                row_count = write_csv(target_path, required_columns, rows)
                status = "FETCHED"
            else:
                row_count = write_manual_template(target, target_path)
                status = "TEMPLATE_CREATED_UNKNOWN_PROVIDER"
        except Exception as exc:  # noqa: BLE001 - audit-friendly error capture
            status = "ERROR"
            errors.append({"manifest_id": target.get("manifest_id"), "target_file": target_rel, "error": repr(exc)})

        acquisition_rows.append({
            "manifest_id": target.get("manifest_id"),
            "priority": target.get("priority"),
            "provider": provider,
            "target_file": target_rel,
            "auto_fetch": auto_fetch,
            "status": status,
            "rows_written": row_count,
            "required_columns": ";".join(required_columns),
            "lag_rule_id": target.get("lag_rule_id"),
            "metadata_json": json.dumps(meta, ensure_ascii=False, sort_keys=True),
        })

    manifest_csv = out_dir / "stage64_macro_data_acquisition_manifest.csv"
    write_csv(manifest_csv, ["manifest_id", "priority", "provider", "target_file", "auto_fetch", "status", "rows_written", "required_columns", "lag_rule_id", "metadata_json"], acquisition_rows)

    summary = {
        "stage": "Stage64D3A_MACRO_REGIME_SOURCE_ACQUISITION_TOOLKIT_NO_PROMOTION",
        "status": "SOURCE_ACQUISITION_RUN_COMPLETE" if not errors else "SOURCE_ACQUISITION_RUN_COMPLETE_WITH_ERRORS",
        "promotion": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": False,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "config": str(config_path),
        "out": str(out_dir),
        "offline_template_only": ns.offline_template_only,
        "counts": {
            "targets": len(config.get("targets", [])),
            "fetched": sum(1 for r in acquisition_rows if r["status"] == "FETCHED"),
            "templates": sum(1 for r in acquisition_rows if "TEMPLATE" in str(r["status"])),
            "errors": len(errors),
        },
        "errors": errors,
        "outputs": {
            "acquisition_manifest_csv": str(manifest_csv.relative_to(root)) if manifest_csv.is_relative_to(root) else str(manifest_csv),
            "raw_dir": str(raw_dir.relative_to(root)) if raw_dir.is_relative_to(root) else str(raw_dir),
        },
        "next_allowed_step": "RUN_STAGE64D4_SOURCE_FILE_IMPORT_PREFLIGHT_NO_ORDER_AFTER_FILES_PRESENT"
    }
    (out_dir / "stage64_macro_data_acquisition_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report = [
        "# Stage64 Macro-Regime Source Acquisition Run",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        f"Status: `{summary['status']}`",
        "",
        "This run only collects or templates raw macro-regime source files. It does not validate a thesis and does not authorize any order path.",
        "",
        "## Counts",
        "",
        f"- targets: {summary['counts']['targets']}",
        f"- fetched: {summary['counts']['fetched']}",
        f"- templates: {summary['counts']['templates']}",
        f"- errors: {summary['counts']['errors']}",
        "",
        "## Raw output directory",
        "",
        f"`{ns.raw_dir}`",
        "",
        "## Next",
        "",
        "Run Stage64D4 source-file import preflight after the required source files are present.",
    ]
    (out_dir / "stage64_macro_data_acquisition_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
