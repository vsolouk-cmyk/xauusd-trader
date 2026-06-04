from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from app.providers.twelvedata_client import TwelveDataClient, TwelveDataError


INTERVAL_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "45min": 2700,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1day": 86400,
}


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_name(value: str) -> str:
    return str(value).replace("/", "_").replace(" ", "_").replace(":", "_").replace("-", "_")


def store_path(store_dir: Path, symbol: str, interval: str) -> Path:
    return store_dir / f"store_{safe_name(symbol)}_{safe_name(interval)}.csv"


def parse_twelvedata_values(payload: Dict[str, Any], symbol: str, interval: str) -> pd.DataFrame:
    values = payload.get("values", []) or []
    meta = payload.get("meta", {}) or {}
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
                    "symbol": meta.get("symbol") or symbol,
                    "interval": meta.get("interval") or interval,
                    "provider": "twelvedata",
                    "source_file": "persistent_store_incremental",
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "spread_available": False,
                    "spread_close": None,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")

    hours = df["time_utc"].dt.hour
    df["session_utc"] = "other"
    df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
    df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
    df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
    df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"

    return df


def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"])
    return df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")


def write_csv_atomic(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def interval_seconds(interval: str) -> int:
    if interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported interval: {interval}")
    return int(INTERVAL_SECONDS[interval])


def should_refresh(existing: pd.DataFrame, max_staleness_minutes: int) -> Tuple[bool, Dict[str, Any]]:
    if existing.empty:
        return True, {"reason": "empty_or_missing_store"}

    last_ts = pd.to_datetime(existing["time_utc"], utc=True).max()
    age_minutes = float((utc_now() - last_ts).total_seconds() / 60.0)
    if age_minutes > float(max_staleness_minutes):
        return True, {"reason": "stale_store", "last_time_utc": last_ts.isoformat(), "age_minutes": age_minutes}

    return False, {"reason": "fresh_store", "last_time_utc": last_ts.isoformat(), "age_minutes": age_minutes}


def make_start_date(existing: pd.DataFrame, interval: str, overlap_bars: int) -> Optional[str]:
    if existing.empty:
        return None
    last_ts = pd.to_datetime(existing["time_utc"], utc=True).max()
    start = last_ts - pd.Timedelta(seconds=interval_seconds(interval) * int(overlap_bars))
    # Twelve Data accepts ISO-like strings; keep UTC without timezone suffix to avoid provider parser ambiguity.
    return start.strftime("%Y-%m-%d %H:%M:%S")


def refresh_one(
    client: TwelveDataClient,
    symbol: str,
    interval: str,
    path: Path,
    timezone_name: str,
    bootstrap_outputsize: int,
    incremental_outputsize: int,
    max_rows: int,
    max_staleness_minutes: int,
    overlap_bars: int,
    force_refresh: bool,
) -> Dict[str, Any]:
    existing = load_existing(path)
    refresh_needed, diagnostic = should_refresh(existing, max_staleness_minutes=max_staleness_minutes)
    if force_refresh:
        refresh_needed = True
        diagnostic = {**diagnostic, "force_refresh": True}

    before_rows = int(len(existing))
    before_last = None if existing.empty else pd.to_datetime(existing["time_utc"], utc=True).max().isoformat()

    if not refresh_needed:
        return {
            "interval": interval,
            "action": "skip_fresh",
            "path": str(path),
            "before_rows": before_rows,
            "after_rows": before_rows,
            "new_rows": 0,
            "before_last_utc": before_last,
            "after_last_utc": before_last,
            "diagnostic": diagnostic,
        }

    start_date = make_start_date(existing, interval=interval, overlap_bars=overlap_bars)
    outputsize = int(incremental_outputsize if start_date else bootstrap_outputsize)

    payload = client.time_series(
        symbol=symbol,
        interval=interval,
        outputsize=outputsize,
        timezone=timezone_name,
        order="ASC",
        start_date=start_date,
    )
    incoming = parse_twelvedata_values(payload, symbol=symbol, interval=interval)

    if existing.empty:
        merged = incoming
    elif incoming.empty:
        merged = existing
    else:
        merged = pd.concat([existing, incoming], ignore_index=True)

    if not merged.empty:
        merged["time_utc"] = pd.to_datetime(merged["time_utc"], utc=True, errors="coerce")
        merged = merged.dropna(subset=["time_utc"])
        merged = merged.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")
        if int(max_rows) > 0 and len(merged) > int(max_rows):
            merged = merged.tail(int(max_rows)).copy()

    after_rows = int(len(merged))
    after_last = None if merged.empty else pd.to_datetime(merged["time_utc"], utc=True).max().isoformat()
    new_rows = max(0, after_rows - before_rows)

    write_csv_atomic(path, merged)

    return {
        "interval": interval,
        "action": "refresh",
        "path": str(path),
        "before_rows": before_rows,
        "after_rows": after_rows,
        "new_rows": int(new_rows),
        "before_last_utc": before_last,
        "after_last_utc": after_last,
        "start_date_used": start_date,
        "outputsize_used": outputsize,
        "incoming_rows": int(len(incoming)),
        "diagnostic": diagnostic,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent rolling XAUUSD data store refresh.")
    parser.add_argument("--config", default="configs/persistent_store.yaml")
    parser.add_argument("--intervals", default=None)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--max-staleness-minutes", type=int, default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    symbol = str(cfg.get("symbol", "XAU/USD"))
    timezone_name = str(cfg.get("timezone", "UTC"))
    store_dir = Path(cfg.get("store_dir", "data/store"))
    manifest_path = Path(cfg.get("manifest_path", "data/store/manifest.json"))

    if args.intervals:
        intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    else:
        intervals = list(cfg.get("intervals", ["1min", "5min", "15min", "1h"]))

    bootstrap_outputsize = int(cfg.get("bootstrap_outputsize", 5000))
    incremental_outputsize = int(cfg.get("incremental_outputsize", 500))
    max_rows = int(cfg.get("max_rows_per_interval", 20000))
    max_staleness_minutes = int(args.max_staleness_minutes if args.max_staleness_minutes is not None else cfg.get("max_staleness_minutes", 90))
    overlap_bars = int(cfg.get("overlap_bars", 3))

    client = TwelveDataClient()
    results = []
    for interval in intervals:
        result = refresh_one(
            client=client,
            symbol=symbol,
            interval=interval,
            path=store_path(store_dir, symbol, interval),
            timezone_name=timezone_name,
            bootstrap_outputsize=bootstrap_outputsize,
            incremental_outputsize=incremental_outputsize,
            max_rows=max_rows,
            max_staleness_minutes=max_staleness_minutes,
            overlap_bars=overlap_bars,
            force_refresh=bool(args.force_refresh),
        )
        results.append(result)

    manifest = {
        "ok": True,
        "stage": "persistent_store_refresh",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "intervals": intervals,
        "store_dir": str(store_dir),
        "max_rows_per_interval": max_rows,
        "max_staleness_minutes": max_staleness_minutes,
        "overlap_bars": overlap_bars,
        "results": results,
        "refreshed_count": int(sum(1 for r in results if r["action"] == "refresh")),
        "skipped_count": int(sum(1 for r in results if r["action"] == "skip_fresh")),
    }
    write_json_atomic(manifest_path, manifest)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TwelveDataError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        raise SystemExit(2)
