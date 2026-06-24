#!/usr/bin/env python3
"""
Stage47B3 TwelveData M5 history backfill for XAUUSD research.

Purpose:
- Build enough M5 normalized history for Stage47B liquidity-sweep reversal rerun.
- Do not promote, trade, paper-live, or live-trade anything.
- Use bounded, explicit REST backfill windows and normalized CSV output.

Environment:
- TWELVEDATA_API_KEY is required unless --smoke-test or --dry-run is used.

Outputs:
- data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_<UTC>.csv
- reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_summary.json
- reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_report.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage47B3_TWELVEDATA_M5_HISTORY_BACKFILL"
PATCH = "Stage47B3_TWELVEDATA_WINDOWED_HISTORY_BACKFILL_NO_PROMOTION"
DEFAULT_SYMBOL = "XAU/USD"
DEFAULT_INTERVAL = "5min"
EXPECTED_MINUTES = 5.0


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_z(x: dt.datetime) -> str:
    if x.tzinfo is None:
        x = x.replace(tzinfo=dt.timezone.utc)
    return x.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def td_datetime(x: dt.datetime) -> str:
    if x.tzinfo is None:
        x = x.replace(tzinfo=dt.timezone.utc)
    x = x.astimezone(dt.timezone.utc).replace(microsecond=0)
    return x.strftime("%Y-%m-%d %H:%M:%S")


def parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # TwelveData typically returns e.g. '2026-06-02 12:25:00'
    candidates = [s, s.replace(" ", "T", 1)]
    for c in candidates:
        try:
            parsed = dt.datetime.fromisoformat(c)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)
        except ValueError:
            pass
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"none", "nan", "null"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def safe_symbol_slug(symbol: str) -> str:
    out = []
    for ch in symbol:
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "XAU_USD"


def session_utc(ts: dt.datetime) -> str:
    h = ts.hour
    # Simple UTC session tags, compatible with current normalized files.
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "late_us"


@dataclass(frozen=True)
class Candle:
    ts: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    provider: str = "twelvedata"
    source_file: str = "twelvedata_api"
    fetched_at_utc: str = ""
    spread_available: str = "False"
    spread_close: str = ""
    session: str = ""

    def as_row(self) -> Dict[str, str]:
        return {
            "time_utc": iso_z(self.ts),
            "open": f"{self.open:.8f}".rstrip("0").rstrip("."),
            "high": f"{self.high:.8f}".rstrip("0").rstrip("."),
            "low": f"{self.low:.8f}".rstrip("0").rstrip("."),
            "close": f"{self.close:.8f}".rstrip("0").rstrip("."),
            "volume": f"{self.volume:.8f}".rstrip("0").rstrip(".") if self.volume else "0.0",
            "symbol": self.symbol,
            "interval": self.interval,
            "provider": self.provider,
            "source_file": self.source_file,
            "fetched_at_utc": self.fetched_at_utc,
            "spread_available": self.spread_available,
            "spread_close": self.spread_close,
            "session_utc": self.session or session_utc(self.ts),
        }


def build_windows(start: dt.datetime, end: dt.datetime, chunk_days: float) -> List[Tuple[dt.datetime, dt.datetime]]:
    if start >= end:
        return []
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")
    out: List[Tuple[dt.datetime, dt.datetime]] = []
    cur = start
    step = dt.timedelta(days=chunk_days)
    while cur < end:
        nxt = min(cur + step, end)
        if nxt <= cur:
            break
        out.append((cur, nxt))
        if len(out) > 10000:
            raise RuntimeError("too many windows generated")
        cur = nxt
    return out


def read_existing_normalized_csvs(root: Path, timeframe: str, symbol: str) -> Tuple[List[Candle], Dict[str, Any]]:
    normalized_dir = root / "data" / "normalized"
    patterns = [
        str(normalized_dir / "normalized_*XAU*5min*.csv"),
        str(normalized_dir / "*XAU*5min*.csv"),
    ]
    files: List[str] = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    files = sorted(set(files))
    candles: List[Candle] = []
    file_metas = []
    for fp in files:
        raw = 0
        accepted = 0
        try:
            with open(fp, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw += 1
                    interval = (row.get("interval") or row.get("timeframe") or "").strip().lower()
                    if interval not in {"5min", "m5", "5m"}:
                        continue
                    sym = (row.get("symbol") or "").strip().upper().replace(" ", "")
                    if sym and sym not in {"XAU/USD", "XAUUSD", "XAU_USD"}:
                        continue
                    ts = parse_ts(row.get("time_utc") or row.get("timestamp_utc") or row.get("ts") or row.get("datetime"))
                    o = to_float(row.get("open"))
                    h = to_float(row.get("high"))
                    l = to_float(row.get("low"))
                    c = to_float(row.get("close"))
                    v = to_float(row.get("volume")) or 0.0
                    if ts is None or o is None or h is None or l is None or c is None:
                        continue
                    if h < max(o, c) or l > min(o, c):
                        continue
                    accepted += 1
                    candles.append(Candle(
                        ts=ts, open=o, high=h, low=l, close=c, volume=v,
                        symbol=symbol, interval=DEFAULT_INTERVAL, provider=row.get("provider") or "twelvedata",
                        source_file=Path(fp).name,
                        fetched_at_utc=row.get("fetched_at_utc") or "",
                        session=row.get("session_utc") or session_utc(ts),
                    ))
        except Exception as exc:  # defensive; audit should continue across files
            file_metas.append({"path": fp, "error": repr(exc), "raw_rows": raw, "accepted_rows": accepted})
            continue
        file_metas.append({"path": fp, "raw_rows": raw, "accepted_rows": accepted})
    return candles, {"existing_files": files, "file_metas": file_metas, "existing_candle_rows": len(candles)}


def normalize_api_values(values: Iterable[Dict[str, Any]], *, symbol: str, interval: str, fetched_at: str, source_file: str) -> Tuple[List[Candle], Dict[str, Any]]:
    candles: List[Candle] = []
    raw = 0
    parse_fail = 0
    bad_ohlc = 0
    for item in values:
        raw += 1
        ts = parse_ts(item.get("datetime") or item.get("time") or item.get("timestamp") or item.get("time_utc"))
        o = to_float(item.get("open"))
        h = to_float(item.get("high"))
        l = to_float(item.get("low"))
        c = to_float(item.get("close"))
        v = to_float(item.get("volume")) or 0.0
        if ts is None or o is None or h is None or l is None or c is None:
            parse_fail += 1
            continue
        if h < max(o, c) or l > min(o, c):
            bad_ohlc += 1
            continue
        candles.append(Candle(
            ts=ts, open=o, high=h, low=l, close=c, volume=v,
            symbol=symbol, interval=interval, provider="twelvedata", source_file=source_file,
            fetched_at_utc=fetched_at, session=session_utc(ts),
        ))
    return candles, {"raw_values": raw, "accepted_values": len(candles), "parse_fail_values": parse_fail, "bad_ohlc_values": bad_ohlc}


def fetch_twelvedata_window(api_key: str, symbol: str, interval: str, start: dt.datetime, end: dt.datetime, outputsize: int, timeout: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    base = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "start_date": td_datetime(start),
        "end_date": td_datetime(end),
        "outputsize": str(outputsize),
        "timezone": "UTC",
        "apikey": api_key,
        "format": "JSON",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    safe_params = dict(params)
    safe_params["apikey"] = "***"
    meta: Dict[str, Any] = {"url_params": safe_params, "start_utc": iso_z(start), "end_utc": iso_z(end)}
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-research-stage47b3/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            meta["http_status"] = getattr(resp, "status", None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        meta.update({"http_status": exc.code, "error": f"HTTPError: {exc.code}", "body_limited": body[:500]})
        return [], meta
    except Exception as exc:
        meta.update({"error": repr(exc)})
        return [], meta
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        meta.update({"error": f"JSONDecodeError: {exc}", "body_limited": body[:500]})
        return [], meta
    if isinstance(data, dict) and data.get("status") == "error":
        meta.update({"provider_status": "error", "provider_message": data.get("message"), "provider_code": data.get("code")})
        return [], meta
    values = data.get("values") if isinstance(data, dict) else None
    if not isinstance(values, list):
        meta.update({"error": "NO_VALUES_LIST_IN_RESPONSE", "response_keys": list(data.keys()) if isinstance(data, dict) else None})
        return [], meta
    meta.update({"provider_status": data.get("status") if isinstance(data, dict) else None, "values_count": len(values)})
    return values, meta


def dedupe_sort(candles: Iterable[Candle]) -> List[Candle]:
    by_ts: Dict[dt.datetime, Candle] = {}
    for c in candles:
        by_ts[c.ts] = c
    return [by_ts[k] for k in sorted(by_ts)]


def gap_summary(candles: List[Candle]) -> Dict[str, Any]:
    if len(candles) < 2:
        return {
            "expected_gap_minutes": EXPECTED_MINUTES,
            "gap_count_gt_1_5x": 0,
            "gap_count_gt_3x": 0,
            "max_gap_minutes": None,
            "median_gap_minutes": None,
        }
    diffs = [(candles[i].ts - candles[i-1].ts).total_seconds() / 60.0 for i in range(1, len(candles))]
    diffs_sorted = sorted(diffs)
    median = diffs_sorted[len(diffs_sorted)//2]
    return {
        "expected_gap_minutes": EXPECTED_MINUTES,
        "gap_count_gt_1_5x": sum(1 for x in diffs if x > EXPECTED_MINUTES * 1.5),
        "gap_count_gt_3x": sum(1 for x in diffs if x > EXPECTED_MINUTES * 3.0),
        "max_gap_minutes": max(diffs) if diffs else None,
        "median_gap_minutes": median,
    }


def write_csv(path: Path, candles: List[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["time_utc", "open", "high", "low", "close", "volume", "symbol", "interval", "provider", "source_file", "fetched_at_utc", "spread_available", "spread_close", "session_utc"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for c in candles:
            writer.writerow(c.as_row())


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stage47B3 TwelveData M5 History Backfill",
        "",
        f"- status: `{summary.get('status')}`",
        f"- symbol: `{summary.get('symbol')}`",
        f"- interval: `{summary.get('interval')}`",
        f"- fetched_windows: `{summary.get('fetched_windows')}`",
        f"- failed_windows: `{summary.get('failed_windows')}`",
        f"- rows_before_dedup: `{summary.get('rows_before_dedup')}`",
        f"- unique_rows_after_dedup: `{summary.get('unique_rows_after_dedup')}`",
        f"- start_utc: `{summary.get('start_utc')}`",
        f"- end_utc: `{summary.get('end_utc')}`",
        f"- coverage_days: `{summary.get('coverage_days')}`",
        f"- min_rows_required: `{summary.get('min_rows_required')}`",
        f"- min_days_required: `{summary.get('min_days_required')}`",
        f"- stop_reason: `{summary.get('stop_reason')}`",
        f"- normalized_csv: `{summary.get('normalized_csv')}`",
        "",
        "Research-only output. No promotion, EA, paper-live, or live action is allowed from this stage.",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_smoke(root: Path, out_dir: Path) -> Dict[str, Any]:
    base = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    fetched_at = iso_z(utc_now())
    candles = []
    price = 2000.0
    for i in range(600):
        ts = base + dt.timedelta(minutes=5*i)
        o = price
        c = price + (0.5 if i % 2 == 0 else -0.25)
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        price = c
        candles.append(Candle(ts=ts, open=o, high=h, low=l, close=c, fetched_at_utc=fetched_at, source_file="smoke"))
    normalized_path = out_dir / "stage47b3_smoke_m5.csv"
    write_csv(normalized_path, candles)
    merged = dedupe_sort(candles + candles[:100])
    summary = finalize_summary(
        root=root, symbol=DEFAULT_SYMBOL, interval=DEFAULT_INTERVAL,
        windows=[], fetched_windows=0, failed_windows=0,
        rows_before_dedup=len(candles)+100, candles=merged,
        normalized_csv=normalized_path, include_existing=True,
        min_rows=500, min_days=1.0, chunk_metas=[{"smoke": True}], existing_meta={"smoke": True},
        dry_run=False, smoke_test=True,
    )
    write_json(out_dir / "stage47b3_twelvedata_m5_history_backfill_summary.json", summary)
    write_report(out_dir / "stage47b3_twelvedata_m5_history_backfill_report.md", summary)
    return summary


def finalize_summary(*, root: Path, symbol: str, interval: str, windows: List[Tuple[dt.datetime, dt.datetime]], fetched_windows: int, failed_windows: int, rows_before_dedup: int, candles: List[Candle], normalized_csv: Path, include_existing: bool, min_rows: int, min_days: float, chunk_metas: List[Dict[str, Any]], existing_meta: Dict[str, Any], dry_run: bool, smoke_test: bool) -> Dict[str, Any]:
    unique_rows = len(candles)
    start_utc = iso_z(candles[0].ts) if candles else None
    end_utc = iso_z(candles[-1].ts) if candles else None
    coverage_days = ((candles[-1].ts - candles[0].ts).total_seconds() / 86400.0) if len(candles) >= 2 else 0.0
    if dry_run:
        status = "DRY_RUN_COMPLETE_NO_PROMOTION"
        stop_reason = None
    elif unique_rows < min_rows:
        status = "INSUFFICIENT_HISTORY_STOP_NO_PROMOTION"
        stop_reason = f"unique_rows_lt_min_rows_{min_rows}"
    elif coverage_days < min_days:
        status = "INSUFFICIENT_HISTORY_STOP_NO_PROMOTION"
        stop_reason = f"coverage_days_lt_min_days_{min_days}"
    else:
        status = "DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION"
        stop_reason = None
    return {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "symbol": symbol,
        "interval": interval,
        "root": str(root),
        "include_existing": include_existing,
        "dry_run": dry_run,
        "smoke_test": smoke_test,
        "windows_planned": len(windows),
        "fetched_windows": fetched_windows,
        "failed_windows": failed_windows,
        "rows_before_dedup": rows_before_dedup,
        "unique_rows_after_dedup": unique_rows,
        "duplicates_removed": max(0, rows_before_dedup - unique_rows),
        "start_utc": start_utc,
        "end_utc": end_utc,
        "coverage_days": coverage_days,
        "min_rows_required": min_rows,
        "min_days_required": min_days,
        "stop_reason": stop_reason,
        "gap_summary": gap_summary(candles),
        "normalized_csv": str(normalized_csv),
        "chunk_metas_limited": chunk_metas[:20],
        "existing_meta": existing_meta,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage47B3 TwelveData M5 history backfill")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, choices=["5min"])
    parser.add_argument("--days", type=float, default=90.0)
    parser.add_argument("--chunk-days", type=float, default=7.0)
    parser.add_argument("--outputsize", type=int, default=5000)
    parser.add_argument("--sleep-sec", type=float, default=8.0)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--min-rows", type=int, default=5000)
    parser.add_argument("--min-days", type=float, default=20.0)
    parser.add_argument("--include-existing", action="store_true", default=True)
    parser.add_argument("--no-include-existing", dest="include_existing", action="store_false")
    parser.add_argument("--out", default="reports/stage47b3")
    parser.add_argument("--normalized-out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)

    root = Path.cwd()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.smoke_test:
        summary = run_smoke(root, out_dir)
        print(json.dumps({"stage": STAGE, "status": summary["status"], "unique_rows_after_dedup": summary["unique_rows_after_dedup"], "out": str(out_dir)}, ensure_ascii=False))
        return 0

    now = utc_now()
    end = now.replace(second=0, microsecond=0)
    start = end - dt.timedelta(days=args.days)
    windows = build_windows(start, end, args.chunk_days)

    normalized_out = Path(args.normalized_out) if args.normalized_out else root / "data" / "normalized" / f"normalized_twelvedata_{safe_symbol_slug(args.symbol)}_{args.interval}_backfill_{now.strftime('%Y%m%dT%H%M%SZ')}.csv"

    if args.dry_run:
        summary = finalize_summary(
            root=root, symbol=args.symbol, interval=args.interval, windows=windows,
            fetched_windows=0, failed_windows=0, rows_before_dedup=0, candles=[],
            normalized_csv=normalized_out, include_existing=args.include_existing,
            min_rows=args.min_rows, min_days=args.min_days,
            chunk_metas=[{"start_utc": iso_z(a), "end_utc": iso_z(b)} for a, b in windows[:20]],
            existing_meta={}, dry_run=True, smoke_test=False,
        )
        write_json(out_dir / "stage47b3_twelvedata_m5_history_backfill_summary.json", summary)
        write_report(out_dir / "stage47b3_twelvedata_m5_history_backfill_report.md", summary)
        print(json.dumps({"stage": STAGE, "status": summary["status"], "windows_planned": len(windows), "out": str(out_dir)}, ensure_ascii=False))
        return 0

    api_key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        summary = finalize_summary(
            root=root, symbol=args.symbol, interval=args.interval, windows=windows,
            fetched_windows=0, failed_windows=0, rows_before_dedup=0, candles=[],
            normalized_csv=normalized_out, include_existing=args.include_existing,
            min_rows=args.min_rows, min_days=args.min_days,
            chunk_metas=[{"error": "TWELVEDATA_API_KEY_NOT_SET"}],
            existing_meta={}, dry_run=False, smoke_test=False,
        )
        summary["status"] = "NO_API_KEY_STOP_NO_PROMOTION"
        summary["stop_reason"] = "TWELVEDATA_API_KEY_NOT_SET"
        write_json(out_dir / "stage47b3_twelvedata_m5_history_backfill_summary.json", summary)
        write_report(out_dir / "stage47b3_twelvedata_m5_history_backfill_report.md", summary)
        print(json.dumps({"stage": STAGE, "status": summary["status"], "out": str(out_dir)}, ensure_ascii=False))
        return 0

    all_candles: List[Candle] = []
    existing_meta: Dict[str, Any] = {}
    if args.include_existing:
        existing_candles, existing_meta = read_existing_normalized_csvs(root, args.interval, args.symbol)
        all_candles.extend(existing_candles)

    fetched_windows = 0
    failed_windows = 0
    chunk_metas: List[Dict[str, Any]] = []
    fetched_at = iso_z(now)
    # Fetch older-to-newer, but later dedupe makes order irrelevant.
    for idx, (a, b) in enumerate(windows, start=1):
        values, meta = fetch_twelvedata_window(api_key, args.symbol, args.interval, a, b, args.outputsize, args.timeout_sec)
        meta["window_index"] = idx
        if values:
            source_file = f"twelvedata_{safe_symbol_slug(args.symbol)}_{args.interval}_window{idx}_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
            candles, norm_meta = normalize_api_values(values, symbol=args.symbol, interval=args.interval, fetched_at=fetched_at, source_file=source_file)
            meta.update(norm_meta)
            all_candles.extend(candles)
            fetched_windows += 1
        else:
            failed_windows += 1
        chunk_metas.append(meta)
        if idx < len(windows) and args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    rows_before = len(all_candles)
    merged = dedupe_sort(all_candles)
    if merged:
        write_csv(normalized_out, merged)

    summary = finalize_summary(
        root=root, symbol=args.symbol, interval=args.interval, windows=windows,
        fetched_windows=fetched_windows, failed_windows=failed_windows,
        rows_before_dedup=rows_before, candles=merged, normalized_csv=normalized_out,
        include_existing=args.include_existing, min_rows=args.min_rows, min_days=args.min_days,
        chunk_metas=chunk_metas, existing_meta=existing_meta, dry_run=False, smoke_test=False,
    )
    write_json(out_dir / "stage47b3_twelvedata_m5_history_backfill_summary.json", summary)
    write_report(out_dir / "stage47b3_twelvedata_m5_history_backfill_report.md", summary)
    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "unique_rows_after_dedup": summary["unique_rows_after_dedup"],
        "coverage_days": summary["coverage_days"],
        "normalized_csv": str(normalized_out),
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
