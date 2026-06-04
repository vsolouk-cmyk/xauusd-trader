from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml

from app.providers.twelvedata_client import TwelveDataClient
from app.xauusd_sqlite_store import connect, ensure_schema, interval_stats, latest_time, optimize, trim_interval, upsert_candles


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def add_session_tags(df: pd.DataFrame) -> pd.DataFrame:
    hours = df["time_utc"].dt.hour
    df["session_utc"] = "other"
    df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
    df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
    df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
    df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"
    return df


def normalize_twelvedata_response(payload: Dict[str, Any], symbol: str, interval: str, fetched_at_utc: str) -> pd.DataFrame:
    values = payload.get("values", []) or []
    rows: List[Dict[str, Any]] = []

    for item in values:
        try:
            rows.append(
                {
                    "time_utc": item.get("datetime"),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume", 0) or 0),
                    "symbol": symbol,
                    "interval": interval,
                    "provider": "twelvedata",
                    "fetched_at_utc": fetched_at_utc,
                }
            )
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")
    df = add_session_tags(df)
    return df


def earliest_time(con, interval: str) -> pd.Timestamp | None:
    stats = interval_stats(con, interval)
    start = stats.get("start_utc")
    if not start:
        return None
    return pd.to_datetime(start, utc=True)


def fmt_dt(ts: pd.Timestamp) -> str:
    # Twelve Data accepts "YYYY-MM-DD HH:MM:SS".
    return ts.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill older XAUUSD candles into SQLite store.")
    parser.add_argument("--config", default="configs/backfill.yaml")
    parser.add_argument("--intervals", default=None, help="Comma-separated intervals to backfill.")
    parser.add_argument("--requests-per-interval", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Run even if table is empty by falling back to normal latest outputsize.")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    symbol = cfg.get("symbol", "XAU/USD")
    timezone_name = cfg.get("timezone", "UTC")
    db_path = Path(cfg.get("db_path", "data/store/xauusd.sqlite"))
    manifest_path = Path(cfg.get("manifest_path", "data/store/backfill_manifest.json"))

    backfill_cfg = cfg.get("backfill", {}) or {}
    outputsize = int(backfill_cfg.get("outputsize", 5000))
    sleep_seconds = float(backfill_cfg.get("sleep_seconds_between_requests", 8))
    requests_per_interval = int(args.requests_per_interval or backfill_cfg.get("requests_per_interval", 1))
    chunk_days = backfill_cfg.get("chunk_days", {}) or {}
    max_rows = int(backfill_cfg.get("max_rows_per_interval", 20000))

    intervals = [x.strip() for x in args.intervals.split(",")] if args.intervals else list(cfg.get("intervals", ["15min", "1h"]))

    con = connect(db_path)
    ensure_schema(con, intervals)
    client = TwelveDataClient()

    results = []
    total_api_calls = 0

    for interval in intervals:
        interval_results = []
        for request_no in range(1, requests_per_interval + 1):
            start = earliest_time(con, interval)

            if start is None:
                if not args.force:
                    interval_results.append(
                        {
                            "request_no": request_no,
                            "action": "skip_empty_table",
                            "reason": "table has no rows; run app.xauusd_store_refresh first or pass --force",
                        }
                    )
                    break

                payload = client.time_series(
                    symbol=symbol,
                    interval=interval,
                    outputsize=outputsize,
                    timezone=timezone_name,
                    order="ASC",
                )
                requested_range = {"mode": "latest_seed"}
            else:
                days = int(chunk_days.get(interval, 45))
                end_ts = start - pd.Timedelta(seconds=1)
                start_ts = start - pd.Timedelta(days=days)

                payload = client.time_series(
                    symbol=symbol,
                    interval=interval,
                    outputsize=outputsize,
                    timezone=timezone_name,
                    order="ASC",
                    start_date=fmt_dt(start_ts),
                    end_date=fmt_dt(end_ts),
                )
                requested_range = {
                    "mode": "older_chunk",
                    "start_date": fmt_dt(start_ts),
                    "end_date": fmt_dt(end_ts),
                    "chunk_days": days,
                }

            total_api_calls += 1
            fetched_at_utc = datetime.now(timezone.utc).isoformat()
            df = normalize_twelvedata_response(payload, symbol=symbol, interval=interval, fetched_at_utc=fetched_at_utc)

            before = interval_stats(con, interval)
            inserted = upsert_candles(con, interval, df) if not df.empty else 0
            trimmed = trim_interval(con, interval, max_rows=max_rows)
            after = interval_stats(con, interval)

            interval_results.append(
                {
                    "request_no": request_no,
                    "action": "backfill",
                    "requested_range": requested_range,
                    "api_rows": int(len(df)),
                    "net_new_rows": int(inserted),
                    "trimmed_rows": int(trimmed),
                    "before": before,
                    "after": after,
                }
            )

            # If API returned no useful rows, do not hammer earlier ranges.
            if df.empty or inserted == 0:
                break

            if sleep_seconds > 0 and request_no < requests_per_interval:
                time.sleep(sleep_seconds)

        results.append({"interval": interval, "requests": interval_results})

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    optimize(con)
    con.close()

    manifest = {
        "ok": True,
        "stage": "historical_sqlite_backfill",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "symbol": symbol,
        "intervals": intervals,
        "requests_per_interval": requests_per_interval,
        "total_api_calls": total_api_calls,
        "max_rows_per_interval": max_rows,
        "results": results,
    }
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
