from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml


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


def latest_csv(normalized_dir: Path) -> Path:
    files = sorted(normalized_dir.glob("normalized_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No normalized CSV files found in {normalized_dir}")
    return files[0]


def is_likely_weekend_closure(prev_ts: pd.Timestamp, curr_ts: pd.Timestamp, gap_sec: float) -> bool:
    # Gold/FX-style instruments normally close around the weekend.
    if gap_sec < 12 * 3600:
        return False
    prev_wd = int(prev_ts.weekday())  # Monday=0
    curr_wd = int(curr_ts.weekday())
    return prev_wd in {4, 5} and curr_wd in {6, 0}


def quality_report(csv_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    df = pd.read_csv(csv_path)
    if df.empty:
        return {"ok": False, "reason": "empty_csv", "file": str(csv_path)}

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    df = df.sort_values("time_utc")

    interval = str(df["interval"].iloc[0])
    expected_sec = INTERVAL_SECONDS.get(interval)

    duplicate_timestamps = int(df["time_utc"].duplicated().sum())

    non_weekend_gap_seconds = []
    weekend_gap_seconds = []
    estimated_missing_intervals = 0

    if expected_sec:
        times = df["time_utc"].tolist()
        for prev_ts, curr_ts in zip(times[:-1], times[1:]):
            gap_sec = float((curr_ts - prev_ts).total_seconds())
            if gap_sec > expected_sec * 1.5:
                if is_likely_weekend_closure(prev_ts, curr_ts, gap_sec):
                    weekend_gap_seconds.append(gap_sec)
                else:
                    non_weekend_gap_seconds.append(gap_sec)
                    estimated_missing_intervals += max(0, int(round(gap_sec / expected_sec)) - 1)

    rows = int(len(df))
    missing_ratio = float(estimated_missing_intervals / max(rows + estimated_missing_intervals, 1))

    spread_available = bool(df.get("spread_available", pd.Series([False])).fillna(False).any())
    spread_stats = {
        "available": spread_available,
        "note": "Twelve Data Stage 0 does not provide broker bid/ask spread in this pipeline. Use conservative assumed costs and validate later with MT5/broker feed.",
    }

    session_counts = {}
    if "session_utc" in df.columns:
        session_counts = {str(k): int(v) for k, v in df["session_utc"].value_counts(dropna=False).items()}

    quality_cfg = config.get("quality", {}) or {}
    max_missing_ratio = float(quality_cfg.get("max_missing_ratio", 0.02))
    max_duplicate_timestamps = int(quality_cfg.get("max_duplicate_timestamps", 0))

    ok = (
        rows > 0
        and duplicate_timestamps <= max_duplicate_timestamps
        and missing_ratio <= max_missing_ratio
    )

    return {
        "ok": ok,
        "file": str(csv_path),
        "rows": rows,
        "provider": str(df["provider"].iloc[0]),
        "symbol": str(df["symbol"].iloc[0]),
        "interval": interval,
        "start_utc": df["time_utc"].iloc[0].isoformat(),
        "end_utc": df["time_utc"].iloc[-1].isoformat(),
        "duplicate_timestamps": duplicate_timestamps,
        "expected_seconds": expected_sec,
        "estimated_missing_intervals_excluding_weekends": int(estimated_missing_intervals),
        "missing_ratio_excluding_weekends": missing_ratio,
        "first_non_weekend_large_gaps_seconds": [float(x) for x in non_weekend_gap_seconds[:20]],
        "weekend_gaps_count": int(len(weekend_gap_seconds)),
        "first_weekend_gaps_seconds": [float(x) for x in weekend_gap_seconds[:10]],
        "spread": spread_stats,
        "session_counts": session_counts,
        "cost_model": config.get("cost_model", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 0 quality checks on normalized XAUUSD data.")
    parser.add_argument("--config", default="configs/data_source.yaml")
    parser.add_argument("--input", default=None)
    parser.add_argument("--normalized-dir", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    normalized_dir = Path(args.normalized_dir or cfg.get("normalized_dir", "data/normalized"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else latest_csv(normalized_dir)
    report = quality_report(input_path, cfg)

    out_path = report_dir / f"quality_{input_path.stem}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(json.dumps({"ok": report["ok"], "report": str(out_path), "summary": report}, indent=2))
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
