from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yaml


def safe_name(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def latest_raw_file(raw_dir: Path, pattern: str = "*.json") -> Path:
    files = sorted(raw_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No raw files found in {raw_dir} matching {pattern}")
    return files[0]


def add_session_tags(df: pd.DataFrame) -> pd.DataFrame:
    # Session = recurring market time window. In Stage 0 we use UTC hour tags only.
    hours = df["time_utc"].dt.hour
    df["session_utc"] = "other"
    df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
    df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
    df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
    df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"
    return df


def normalize_twelvedata(path: Path, payload: Dict[str, Any]) -> pd.DataFrame:
    response = payload.get("response", {})
    values = response.get("values", [])
    meta = response.get("meta", {}) or {}

    rows: List[Dict[str, Any]] = []
    for item in values:
        rows.append(
            {
                "time_utc": item.get("datetime"),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0) or 0),
                "symbol": meta.get("symbol") or payload.get("symbol_requested"),
                "interval": meta.get("interval") or payload.get("interval_requested"),
                "provider": "twelvedata",
                "source_file": path.name,
                "fetched_at_utc": payload.get("fetched_at_utc"),
                "spread_available": False,
                "spread_close": None,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last")
    df = add_session_tags(df)
    return df


def normalize_payload(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    provider = payload.get("provider") or payload.get("source")
    if provider == "twelvedata":
        return normalize_twelvedata(path, payload)

    raise ValueError(f"Unsupported raw provider/source in {path}: {provider!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize raw XAUUSD JSON candles into CSV.")
    parser.add_argument("--config", default="configs/data_source.yaml")
    parser.add_argument("--input", default=None)
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    raw_dir = Path(args.raw_dir or cfg.get("raw_dir", "data/raw"))
    out_dir = Path(args.out_dir or cfg.get("normalized_dir", "data/normalized"))
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else latest_raw_file(raw_dir)
    df = normalize_payload(input_path)

    if df.empty:
        raise RuntimeError(f"No candles found in {input_path}")

    symbol = safe_name(str(df["symbol"].iloc[0]))
    interval = safe_name(str(df["interval"].iloc[0]))
    provider = safe_name(str(df["provider"].iloc[0]))
    stamp = input_path.stem.split("_")[-1]
    out_path = out_dir / f"normalized_{provider}_{symbol}_{interval}_{stamp}.csv"

    df.to_csv(out_path, index=False)
    print(json.dumps({"ok": True, "input": str(input_path), "output": str(out_path), "rows": len(df)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
