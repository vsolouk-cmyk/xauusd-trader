from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from app.providers.twelvedata_client import TwelveDataClient
from app.xauusd_sqlite_store import INTERVAL_SECONDS, connect, ensure_schema, interval_stats, latest_time, optimize, trim_interval, upsert_candles


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


def should_skip_refresh(last_ts: Optional[pd.Timestamp], stale_after_minutes: int) -> tuple[bool, Optional[float]]:
    if last_ts is None:
        return False, None
    age_minutes = (pd.Timestamp.now(tz="UTC") - last_ts).total_seconds() / 60.0
    return age_minutes < stale_after_minutes, float(age_minutes)


def estimate_outputsize(interval: str, age_minutes: Optional[float], cfg: Dict[str, Any], force_full: bool) -> int:
    if force_full or age_minutes is None:
        return int(cfg.get("initial_outputsize", 5000))
    seconds = INTERVAL_SECONDS.get(interval, 60)
    expected_missing = int((float(age_minutes) * 60.0) / seconds) + int(cfg.get("overlap_bars", 20))
    return max(
        int(cfg.get("min_incremental_outputsize", 50)),
        min(int(cfg.get("max_incremental_outputsize", 500)), expected_missing),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh persistent SQLite XAUUSD candle store incrementally.")
    parser.add_argument("--config", default="configs/persistent_store.yaml")
    parser.add_argument("--intervals", default=None)
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    symbol = cfg.get("symbol", "XAU/USD")
    intervals = [x.strip() for x in args.intervals.split(",")] if args.intervals else list(cfg.get("intervals", ["1min", "5min", "15min", "1h"]))
    db_path = Path(cfg.get("db_path", "data/store/xauusd.sqlite"))
    manifest_path = Path(cfg.get("manifest_path", "data/store/manifest.json"))

    refresh_cfg = cfg.get("refresh", {}) or {}
    stale_after_minutes = int(refresh_cfg.get("stale_after_minutes", 90))
    max_rows = int(refresh_cfg.get("max_rows_per_interval", 20000))
    timezone_name = cfg.get("timezone", "UTC")

    con = connect(db_path)
    ensure_schema(con, intervals)

    client = TwelveDataClient()
    results = []
    fetched_any = False

    for interval in intervals:
        last_ts = latest_time(con, interval)
        skip, age_minutes = should_skip_refresh(last_ts, stale_after_minutes)

        if skip and not args.force_refresh:
            stats = interval_stats(con, interval)
            results.append(
                {
                    "interval": interval,
                    "action": "skip_fresh",
                    "age_minutes": age_minutes,
                    "rows": stats["rows"],
                    "start_utc": stats["start_utc"],
                    "end_utc": stats["end_utc"],
                    "new_rows": 0,
                }
            )
            continue

        outputsize = estimate_outputsize(interval, age_minutes, refresh_cfg, force_full=(last_ts is None or args.force_refresh))
        fetched_at_utc = datetime.now(timezone.utc).isoformat()

        payload = client.time_series(
            symbol=symbol,
            interval=interval,
            outputsize=outputsize,
            timezone=timezone_name,
            order="ASC",
        )
        df = normalize_twelvedata_response(payload, symbol=symbol, interval=interval, fetched_at_utc=fetched_at_utc)

        if last_ts is not None and not df.empty:
            # Keep overlap rows for upsert, but count only strictly newer rows separately in manifest.
            strictly_new_count = int((df["time_utc"] > last_ts).sum())
        else:
            strictly_new_count = int(len(df))

        inserted = upsert_candles(con, interval, df) if not df.empty else 0
        trimmed = trim_interval(con, interval, max_rows=max_rows)
        stats = interval_stats(con, interval)
        fetched_any = True

        results.append(
            {
                "interval": interval,
                "action": "refresh",
                "age_minutes_before_refresh": age_minutes,
                "requested_outputsize": outputsize,
                "api_rows": int(len(df)),
                "strictly_new_rows": strictly_new_count,
                "net_new_rows": inserted,
                "trimmed_rows": trimmed,
                "rows": stats["rows"],
                "start_utc": stats["start_utc"],
                "end_utc": stats["end_utc"],
            }
        )

    optimize(con)
    con.close()

    manifest = {
        "ok": True,
        "stage": "persistent_sqlite_store_refresh",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "symbol": symbol,
        "intervals": intervals,
        "fetched_any": fetched_any,
        "stale_after_minutes": stale_after_minutes,
        "max_rows_per_interval": max_rows,
        "results": results,
    }
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
