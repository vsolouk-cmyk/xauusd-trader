#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(".").resolve()
RAW = ROOT / "data" / "macro_regime" / "raw"
OUT = ROOT / "reports" / "stage64_macro_data_acquisition"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

START_DATE = "2011-01-01"
START_TS = int(dt.datetime(2011, 1, 1, tzinfo=dt.timezone.utc).timestamp())
END_TS = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).timestamp())


def iso_next_day(date_s: str) -> str:
    d = dt.date.fromisoformat(date_s[:10])
    return (d + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"


def today_yyyymmdd() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%d")


def urlopen_text(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stage64-xauusd-data-fetch/1.1",
            "Accept": "text/csv,text/plain,application/json,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode("utf-8", errors="replace")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def fetch_fred_series(series_id: str, out_file: Path, value_col: str, source_label: str, proxy_method: str = "") -> dict:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={START_DATE}"
    text = urlopen_text(url)
    reader = csv.DictReader(io.StringIO(text))

    rows = []
    for r in reader:
        date_s = (r.get("observation_date") or r.get("DATE") or "").strip()
        value = (r.get(series_id) or "").strip()
        if not date_s or value in {"", "."}:
            continue
        try:
            float(value)
        except ValueError:
            continue

        row = {
            "date_utc": date_s,
            value_col: value,
            "source": source_label,
            "available_after_utc": iso_next_day(date_s),
        }
        if proxy_method:
            row["proxy_method"] = proxy_method
        rows.append(row)

    if not rows:
        raise RuntimeError(f"No rows parsed from FRED series {series_id}")

    if value_col == "value":
        fields = ["date_utc", "value", "source", "available_after_utc", "proxy_method"]
    else:
        fields = ["date_utc", value_col, "source", "available_after_utc"]

    write_csv(out_file, rows, fields)
    return {
        "target_file": str(out_file),
        "source": source_label,
        "rows": len(rows),
        "first_date": rows[0]["date_utc"],
        "last_date": rows[-1]["date_utc"],
        "status": "OK",
        "url": url,
    }


def yahoo_chart_url(symbol: str) -> str:
    enc = urllib.parse.quote(symbol, safe="")
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
        f"?period1={START_TS}&period2={END_TS}&interval=1d&events=history&includeAdjustedClose=true"
    )


def _is_num(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def fetch_yahoo_ohlc(symbols: Iterable[tuple[str, str]], out_file: Path) -> dict:
    errors = []
    for symbol, source_label in symbols:
        url = yahoo_chart_url(symbol)
        try:
            data = json.loads(urlopen_text(url))
            result = (data.get("chart") or {}).get("result") or []
            if not result:
                errors.append(f"{symbol}: no chart result")
                continue
            r0 = result[0]
            timestamps = r0.get("timestamp") or []
            quote = (((r0.get("indicators") or {}).get("quote") or [{}])[0])
            opens = quote.get("open") or []
            highs = quote.get("high") or []
            lows = quote.get("low") or []
            closes = quote.get("close") or []
            volumes = quote.get("volume") or []
            rows = []
            for i, ts in enumerate(timestamps):
                if not all(i < len(arr) for arr in [opens, highs, lows, closes]):
                    continue
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                if not all(_is_num(x) for x in [o, h, l, c]):
                    continue
                date_s = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
                vol = volumes[i] if i < len(volumes) and _is_num(volumes[i]) else 0
                rows.append({
                    "date_utc": date_s,
                    "open": f"{float(o):.10g}",
                    "high": f"{float(h):.10g}",
                    "low": f"{float(l):.10g}",
                    "close": f"{float(c):.10g}",
                    "volume": f"{float(vol):.10g}",
                    "source": source_label,
                    "available_after_utc": iso_next_day(date_s),
                    "instrument_symbol": symbol,
                })
            if len(rows) >= 1000:
                fields = ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc", "instrument_symbol"]
                write_csv(out_file, rows, fields)
                return {
                    "target_file": str(out_file),
                    "source": source_label,
                    "rows": len(rows),
                    "first_date": rows[0]["date_utc"],
                    "last_date": rows[-1]["date_utc"],
                    "status": "OK",
                    "url": url,
                }
            errors.append(f"{symbol}: too few rows parsed: {len(rows)}")
        except Exception as e:
            errors.append(f"{symbol}: {e}")
    raise RuntimeError("All Yahoo OHLC symbols failed: " + " | ".join(errors))


def fetch_yahoo_close(symbols: Iterable[tuple[str, str]], out_file: Path) -> dict:
    errors = []
    for symbol, source_label in symbols:
        url = yahoo_chart_url(symbol)
        try:
            data = json.loads(urlopen_text(url))
            result = (data.get("chart") or {}).get("result") or []
            if not result:
                errors.append(f"{symbol}: no chart result")
                continue
            r0 = result[0]
            timestamps = r0.get("timestamp") or []
            quote = (((r0.get("indicators") or {}).get("quote") or [{}])[0])
            closes = quote.get("close") or []
            rows = []
            for i, ts in enumerate(timestamps):
                if i >= len(closes):
                    continue
                c = closes[i]
                if not _is_num(c):
                    continue
                date_s = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()
                rows.append({
                    "date_utc": date_s,
                    "close": f"{float(c):.10g}",
                    "source": source_label,
                    "available_after_utc": iso_next_day(date_s),
                    "instrument_symbol": symbol,
                })
            if len(rows) >= 1000:
                fields = ["date_utc", "close", "source", "available_after_utc", "instrument_symbol"]
                write_csv(out_file, rows, fields)
                return {
                    "target_file": str(out_file),
                    "source": source_label,
                    "rows": len(rows),
                    "first_date": rows[0]["date_utc"],
                    "last_date": rows[-1]["date_utc"],
                    "status": "OK",
                    "url": url,
                }
            errors.append(f"{symbol}: too few rows parsed: {len(rows)}")
        except Exception as e:
            errors.append(f"{symbol}: {e}")
    raise RuntimeError("All Yahoo close symbols failed: " + " | ".join(errors))


def parse_stooq_ohlc(text: str, source_label: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        date_s = (r.get("Date") or r.get("date") or "").strip()
        if not date_s:
            continue
        open_ = (r.get("Open") or r.get("open") or "").strip()
        high = (r.get("High") or r.get("high") or "").strip()
        low = (r.get("Low") or r.get("low") or "").strip()
        close = (r.get("Close") or r.get("close") or "").strip()
        volume = (r.get("Volume") or r.get("volume") or "0").strip() or "0"
        try:
            [float(x) for x in [open_, high, low, close]]
        except ValueError:
            continue
        rows.append({
            "date_utc": date_s,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "source": source_label,
            "available_after_utc": iso_next_day(date_s),
        })
    return rows


def parse_stooq_close(text: str, source_label: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        date_s = (r.get("Date") or r.get("date") or "").strip()
        close = (r.get("Close") or r.get("close") or "").strip()
        if not date_s or not close:
            continue
        try:
            float(close)
        except ValueError:
            continue
        rows.append({
            "date_utc": date_s,
            "close": close,
            "source": source_label,
            "available_after_utc": iso_next_day(date_s),
        })
    return rows


def fetch_stooq(symbols: Iterable[str], out_file: Path, mode: str, source_prefix: str) -> dict:
    d1 = START_DATE.replace("-", "")
    d2 = today_yyyymmdd()
    errors = []
    for sym in symbols:
        url = f"https://stooq.com/q/d/l/?s={sym}&d1={d1}&d2={d2}&i=d"
        try:
            text = urlopen_text(url)
            if mode == "ohlc":
                rows = parse_stooq_ohlc(text, f"{source_prefix}:{sym}")
                fields = ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"]
            else:
                rows = parse_stooq_close(text, f"{source_prefix}:{sym}")
                fields = ["date_utc", "close", "source", "available_after_utc"]
            if len(rows) >= 1000:
                write_csv(out_file, rows, fields)
                return {
                    "target_file": str(out_file),
                    "source": f"{source_prefix}:{sym}",
                    "rows": len(rows),
                    "first_date": rows[0]["date_utc"],
                    "last_date": rows[-1]["date_utc"],
                    "status": "OK",
                    "url": url,
                }
            errors.append(f"{sym}: too few rows parsed: {len(rows)}")
        except Exception as e:
            errors.append(f"{sym}: {e}")
    raise RuntimeError("All Stooq symbols failed: " + " | ".join(errors))


def make_placeholder_files() -> list[dict]:
    placeholders = []
    files = [
        (
            RAW / "gold_etf_holdings_or_flows.csv",
            ["date_utc", "etf_id", "holdings_tonnes_or_flow", "source", "release_time_utc", "available_after_utc"],
        ),
        (
            RAW / "central_bank_gold_demand_monthly_quarterly.csv",
            ["period_start", "period_end", "demand_value", "unit", "source", "release_date_utc", "available_after_utc"],
        ),
        (
            RAW / "macro_event_calendar_archive.csv",
            ["scheduled_time_utc", "event_type", "importance", "country", "known_before_event", "source", "available_after_utc"],
        ),
    ]
    for path, fields in files:
        if not path.exists():
            write_csv(path, [], fields)
            status = "CREATED_HEADER_ONLY_PLACEHOLDER"
        else:
            status = "EXISTS_NOT_MODIFIED"
        placeholders.append({"target_file": str(path), "status": status})
    return placeholders


def main() -> int:
    results = []
    errors = []

    tasks = [
        (
            "gold_d1_ohlc_2011_present.csv",
            lambda: fetch_yahoo_ohlc(
                symbols=[
                    ("XAUUSD=X", "YAHOO_XAUUSD_SPOT_REFERENCE"),
                    ("GC=F", "YAHOO_GC_F_COMEX_GOLD_FUTURES_CONTINUOUS_REFERENCE"),
                ],
                out_file=RAW / "gold_d1_ohlc_2011_present.csv",
            ),
        ),
        (
            "dxy_daily_2011_present.csv",
            lambda: fetch_yahoo_close(
                symbols=[("DX-Y.NYB", "YAHOO_DX_Y_NYB_US_DOLLAR_INDEX_EXACT_REFERENCE")],
                out_file=RAW / "dxy_daily_2011_present.csv",
            ),
        ),
        (
            "real_yield_or_proxy_daily_2011_present.csv",
            lambda: fetch_fred_series(
                series_id="DFII10",
                out_file=RAW / "real_yield_or_proxy_daily_2011_present.csv",
                value_col="value",
                source_label="FRED_DFII10_10Y_TIPS_REAL_YIELD",
                proxy_method="DIRECT_10Y_TIPS_REAL_YIELD_DAILY",
            ),
        ),
        (
            "vix_daily_2011_present.csv",
            lambda: fetch_fred_series(
                series_id="VIXCLS",
                out_file=RAW / "vix_daily_2011_present.csv",
                value_col="close",
                source_label="FRED_VIXCLS",
            ),
        ),
    ]

    for name, fn in tasks:
        try:
            res = fn()
            print(f"OK: {name} rows={res.get('rows')} source={res.get('source')}")
            results.append(res)
        except Exception as e:
            print(f"FAIL: {name}: {e}", file=sys.stderr)
            errors.append({"target": name, "error": str(e)})

    # Fallbacks if exact/reference attempts fail.
    if not (RAW / "gold_d1_ohlc_2011_present.csv").exists():
        try:
            res = fetch_stooq(
                symbols=["xauusd", "xauusd.pl", "gc.f", "gc.f.us"],
                out_file=RAW / "gold_d1_ohlc_2011_present.csv",
                mode="ohlc",
                source_prefix="STOOQ_GOLD_REFERENCE",
            )
            print(f"OK_FALLBACK: gold rows={res.get('rows')} source={res.get('source')}")
            results.append(res)
        except Exception as e:
            print(f"FAIL_FALLBACK: gold Stooq fallback: {e}", file=sys.stderr)
            errors.append({"target": "gold_d1_ohlc_2011_present.csv stooq fallback", "error": str(e)})

    if not (RAW / "dxy_daily_2011_present.csv").exists():
        try:
            res = fetch_stooq(
                symbols=["dx.f", "dxy", "dxy.us"],
                out_file=RAW / "dxy_daily_2011_present.csv",
                mode="close",
                source_prefix="STOOQ_DOLLAR_INDEX_REFERENCE",
            )
            print(f"OK_FALLBACK: dxy rows={res.get('rows')} source={res.get('source')}")
            results.append(res)
        except Exception as e:
            print(f"FAIL_FALLBACK: dxy Stooq fallback: {e}", file=sys.stderr)
            errors.append({"target": "dxy_daily_2011_present.csv stooq fallback", "error": str(e)})

    if not (RAW / "dxy_daily_2011_present.csv").exists():
        try:
            res = fetch_fred_series(
                series_id="DTWEXBGS",
                out_file=RAW / "dxy_daily_2011_present.csv",
                value_col="close",
                source_label="FRED_DTWEXBGS_BROAD_DOLLAR_PROXY_NOT_DXY",
            )
            res["warning"] = "This is a broad USD index proxy, not exact DXY. Must be explicitly accepted before validation."
            print(f"OK_PROXY: dxy rows={res.get('rows')} source={res.get('source')}")
            results.append(res)
        except Exception as e:
            print(f"FAIL_PROXY: dxy FRED fallback: {e}", file=sys.stderr)
            errors.append({"target": "dxy_daily_2011_present.csv proxy fallback", "error": str(e)})

    placeholders = make_placeholder_files()

    summary = {
        "stage": "Stage64_LOCAL_MACRO_DATA_FETCH_NO_VALIDATION_LOADERFIX1",
        "status": "FETCH_COMPLETE_WITH_ERRORS" if errors else "FETCH_COMPLETE",
        "validation_allowed": False,
        "results": results,
        "errors": errors,
        "placeholders": placeholders,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_HISTORICAL_VALIDATION_SCAN",
        ],
    }

    with (OUT / "stage64_local_macro_data_fetch_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with (OUT / "stage64_local_macro_data_fetch_report.md").open("w", encoding="utf-8") as f:
        f.write("# Stage64 Local Macro Data Fetch Report - LoaderFix1\n\n")
        f.write(f"- status: `{summary['status']}`\n")
        f.write("- validation_allowed: `false`\n\n")
        f.write("## Results\n\n")
        for r in results:
            f.write(f"- `{r.get('target_file')}`: {r.get('status')} rows={r.get('rows')} source={r.get('source')}\n")
            if r.get("warning"):
                f.write(f"  - warning: {r.get('warning')}\n")
        f.write("\n## Errors\n\n")
        if errors:
            for e in errors:
                f.write(f"- `{e['target']}`: {e['error']}\n")
        else:
            f.write("- none\n")
        f.write("\n## Placeholders\n\n")
        for p in placeholders:
            f.write(f"- `{p['target_file']}`: {p['status']}\n")
        f.write("\n## Operational decision\n\n")
        f.write("No validation is authorized. Run Stage64D4 preflight after source files are present.\n")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
