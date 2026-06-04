from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from app.xauusd_sqlite_store import connect, ensure_schema, interval_stats, optimize, upsert_candles


def normalize_columns(df: pd.DataFrame, symbol: str, interval: str, provider: str) -> pd.DataFrame:
    rename_map = {}
    lower = {str(c).lower().strip(): c for c in df.columns}

    candidates = {
        "time_utc": ["time_utc", "datetime", "date", "time", "timestamp"],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c"],
        "volume": ["volume", "vol", "tick_volume"],
    }

    for target, names in candidates.items():
        for name in names:
            if name in lower:
                rename_map[lower[name]] = target
                break

    work = df.rename(columns=rename_map).copy()

    required = ["time_utc", "open", "high", "low", "close"]
    missing = [c for c in required if c not in work.columns]
    if missing:
        raise ValueError(f"CSV missing required columns after normalization: {missing}. Existing columns: {list(df.columns)}")

    work["time_utc"] = pd.to_datetime(work["time_utc"], utc=True)
    for col in ["open", "high", "low", "close"]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    if "volume" not in work.columns:
        work["volume"] = 0.0
    work["volume"] = pd.to_numeric(work["volume"], errors="coerce").fillna(0.0)

    work = work.dropna(subset=["time_utc", "open", "high", "low", "close"])
    work = work.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")

    work["symbol"] = symbol
    work["interval"] = interval
    work["provider"] = provider
    work["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()

    hours = work["time_utc"].dt.hour
    work["session_utc"] = "other"
    work.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
    work.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
    work.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
    work.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"

    return work


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import second-source OHLC CSV into SQLite store.")
    parser.add_argument("--csv", required=True, help="Path to second-source CSV file.")
    parser.add_argument("--db", default="data/second_source/second_source.sqlite")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--symbol", default="XAU/USD")
    parser.add_argument("--provider", default="second_source")
    parser.add_argument("--manifest", default="data/second_source/manifest.json")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    raw = pd.read_csv(csv_path)
    df = normalize_columns(raw, symbol=args.symbol, interval=args.interval, provider=args.provider)

    db_path = Path(args.db)
    con = connect(db_path)
    ensure_schema(con, [args.interval])
    inserted = upsert_candles(con, args.interval, df)
    optimize(con)
    stats = interval_stats(con, args.interval)
    con.close()

    manifest = {
        "ok": True,
        "stage": "second_source_csv_import",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "csv": str(csv_path),
        "db_path": str(db_path),
        "symbol": args.symbol,
        "interval": args.interval,
        "provider": args.provider,
        "input_rows": int(len(raw)),
        "normalized_rows": int(len(df)),
        "net_new_rows": int(inserted),
        "stats": stats,
    }
    write_json(Path(args.manifest), manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
