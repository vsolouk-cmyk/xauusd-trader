from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.providers.twelvedata_client import TwelveDataClient, TwelveDataError


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def collect_twelvedata(
    symbol: str,
    interval: str,
    outputsize: int,
    timezone_name: str,
    raw_dir: Path,
) -> Path:
    client = TwelveDataClient()
    data = client.time_series(
        symbol=symbol,
        interval=interval,
        outputsize=outputsize,
        timezone=timezone_name,
        order="ASC",
    )

    payload = {
        "provider": "twelvedata",
        "source": "twelvedata_rest_time_series",
        "symbol_requested": symbol,
        "interval_requested": interval,
        "outputsize_requested": outputsize,
        "timezone_requested": timezone_name,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "response": data,
    }

    filename = f"twelvedata_{safe_name(symbol)}_{safe_name(interval)}_{utc_stamp()}.json"
    out_path = raw_dir / filename
    write_json(out_path, payload)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect XAUUSD candles from the configured data provider.")
    parser.add_argument("--config", default="configs/data_source.yaml")
    parser.add_argument("--provider", default=None, choices=["twelvedata"])
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default=None)
    parser.add_argument("--outputsize", type=int, default=None)
    parser.add_argument("--timezone", default=None)
    parser.add_argument("--all-config-intervals", action="store_true")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))

    provider = args.provider or cfg.get("provider", "twelvedata")
    symbol = args.symbol or cfg.get("symbol", "XAU/USD")
    outputsize = int(args.outputsize or cfg.get("outputsize", 500))
    timezone_name = args.timezone or cfg.get("timezone", "UTC")
    raw_dir = Path(cfg.get("raw_dir", "data/raw"))

    if outputsize < 1 or outputsize > 5000:
        raise ValueError("outputsize must be between 1 and 5000.")

    if args.all_config_intervals:
        intervals: List[str] = list(cfg.get("intervals", ["1min", "5min", "15min", "1h"]))
    else:
        intervals = [args.interval or "1min"]

    created = []
    if provider == "twelvedata":
        for interval in intervals:
            created.append(
                str(
                    collect_twelvedata(
                        symbol=symbol,
                        interval=interval,
                        outputsize=outputsize,
                        timezone_name=timezone_name,
                        raw_dir=raw_dir,
                    )
                )
            )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    print(json.dumps({"ok": True, "provider": provider, "created": created}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TwelveDataError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        raise SystemExit(2)
