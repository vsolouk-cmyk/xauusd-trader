from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_json_step(label: str, cmd: List[str]) -> Dict[str, Any]:
    print(f"\n=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        raise SystemExit(
            f"\nFAILED at step: {label}\n"
            f"Exit code: {result.returncode}\n"
            "Stop here. Do not continue until this is fixed."
        )

    text = result.stdout.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"Step {label} did not return parseable JSON output.")

    return json.loads(text[start : end + 1])


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def latest_normalized_for_interval(normalized_dir: Path, interval: str) -> Optional[Path]:
    files = sorted(normalized_dir.glob("normalized_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            df = pd.read_csv(path, nrows=5)
        except Exception:
            continue
        if "interval" in df.columns and len(df) > 0 and str(df["interval"].iloc[0]) == interval:
            return path
    return None


def cached_file_ok(
    path: Path,
    interval: str,
    min_rows: int,
    max_age_minutes: int,
) -> Tuple[bool, Dict[str, Any]]:
    try:
        df = pd.read_csv(path, usecols=["time_utc", "interval"])
    except Exception as exc:
        return False, {"reason": f"read_failed:{exc}"}

    if df.empty:
        return False, {"reason": "empty_csv"}

    if "interval" not in df.columns or str(df["interval"].iloc[0]) != interval:
        return False, {"reason": "interval_mismatch"}

    rows = int(len(df))
    if rows < int(min_rows):
        return False, {"reason": "insufficient_rows", "rows": rows, "min_rows": int(min_rows)}

    times = pd.to_datetime(df["time_utc"], utc=True, errors="coerce").dropna()
    if times.empty:
        return False, {"reason": "no_valid_timestamps", "rows": rows}

    end_utc = times.max()
    age_minutes = float((utc_now() - end_utc).total_seconds() / 60.0)

    if max_age_minutes > 0 and age_minutes > float(max_age_minutes):
        return False, {
            "reason": "cache_too_old",
            "rows": rows,
            "end_utc": end_utc.isoformat(),
            "age_minutes": age_minutes,
            "max_age_minutes": int(max_age_minutes),
        }

    return True, {
        "reason": "cache_hit",
        "rows": rows,
        "end_utc": end_utc.isoformat(),
        "age_minutes": age_minutes,
        "max_age_minutes": int(max_age_minutes),
    }


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 1 Snapshot Summary")
    lines.append("")
    lines.append(f"- Generated at UTC: `{summary['generated_at_utc']}`")
    lines.append(f"- Provider: `{summary['provider']}`")
    lines.append(f"- Symbol: `{summary['symbol']}`")
    lines.append(f"- Overall OK: `{summary['overall_ok']}`")
    lines.append(f"- Cache enabled: `{summary['cache']['enabled']}`")
    lines.append(f"- Cache hits: `{summary['cache']['hit_count']}`")
    lines.append(f"- Cache misses: `{summary['cache']['miss_count']}`")
    lines.append("")
    lines.append("## Interval quality")
    lines.append("")
    lines.append("| Interval | Source | OK | Rows | Missing ratio | Duplicate timestamps | Spread available | Start UTC | End UTC |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|---|")
    for item in summary["intervals"]:
        q = item["quality"]
        spread = q.get("spread", {})
        lines.append(
            "| {interval} | {source} | {ok} | {rows} | {missing:.6f} | {dupes} | {spread_available} | {start} | {end} |".format(
                interval=q.get("interval"),
                source=item.get("source_mode"),
                ok=q.get("ok"),
                rows=q.get("rows"),
                missing=float(q.get("missing_ratio_excluding_weekends", 0.0)),
                dupes=q.get("duplicate_timestamps"),
                spread_available=spread.get("available"),
                start=q.get("start_utc"),
                end=q.get("end_utc"),
            )
        )

    lines.append("")
    lines.append("## Cost model")
    lines.append("")
    lines.append("Twelve Data does not provide broker bid/ask spread in this pipeline.")
    lines.append("Baseline testing must use conservative assumed costs and later validate with MT5/broker feed.")
    lines.append("")
    for key, value in summary.get("cost_model", {}).items():
        lines.append(f"- `{key}`: `{value}`")

    lines.append("")
    lines.append("## Files")
    lines.append("")
    for item in summary["intervals"]:
        lines.append(f"- `{item['interval']}`")
        lines.append(f"  - source mode: `{item['source_mode']}`")
        lines.append(f"  - raw: `{item.get('raw_file')}`")
        lines.append(f"  - normalized: `{item['normalized_file']}`")
        lines.append(f"  - quality: `{item['quality_report_file']}`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 1 multi-interval data snapshot with cache-aware collection."
    )
    parser.add_argument("--config", default="configs/data_source.yaml")
    parser.add_argument("--intervals", default=None, help="Comma-separated intervals. Default: config intervals.")
    parser.add_argument("--outputsize", type=int, default=None)
    parser.add_argument("--force-refresh", action="store_true", help="Ignore local/GitHub restored cache and fetch fresh data.")
    parser.add_argument("--max-cache-age-minutes", type=int, default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    provider = cfg.get("provider", "twelvedata")
    symbol = cfg.get("symbol", "XAU/USD")
    raw_dir = Path(cfg.get("raw_dir", "data/raw"))
    normalized_dir = Path(cfg.get("normalized_dir", "data/normalized"))
    report_dir = Path(cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    cache_cfg = cfg.get("cache", {}) or {}
    cache_enabled = bool(cache_cfg.get("enabled", True))
    max_age_minutes = int(args.max_cache_age_minutes if args.max_cache_age_minutes is not None else cache_cfg.get("max_age_minutes", 720))
    min_rows_policy = str(cache_cfg.get("min_rows_policy", "requested_outputsize"))

    if args.intervals:
        intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    else:
        intervals = list(cfg.get("intervals", ["1min", "5min", "15min", "1h"]))

    outputsize = int(args.outputsize or cfg.get("outputsize", 500))

    if not intervals:
        raise SystemExit("No intervals configured for Stage 1.")
    if outputsize < 1 or outputsize > 5000:
        raise SystemExit("outputsize must be between 1 and 5000.")

    generated_at = datetime.now(timezone.utc).isoformat()
    interval_results: List[Dict[str, Any]] = []
    cache_hits = 0
    cache_misses = 0

    for interval in intervals:
        source_mode = "fresh"
        raw_file = None
        normalized_file = None
        cache_diagnostic: Dict[str, Any] = {}

        min_rows = outputsize if min_rows_policy == "requested_outputsize" else int(cache_cfg.get("min_rows", outputsize))

        cached_path = latest_normalized_for_interval(normalized_dir, interval) if cache_enabled and not args.force_refresh else None
        if cached_path:
            ok, diagnostic = cached_file_ok(cached_path, interval, min_rows=min_rows, max_age_minutes=max_age_minutes)
            cache_diagnostic = diagnostic
            if ok:
                source_mode = "cache"
                normalized_file = str(cached_path)
                cache_hits += 1
            else:
                cache_misses += 1
        else:
            if cache_enabled and not args.force_refresh:
                cache_diagnostic = {"reason": "no_cached_file"}
                cache_misses += 1

        if normalized_file is None:
            collect_payload = run_json_step(
                f"collect {interval}",
                [
                    sys.executable,
                    "-m",
                    "app.xauusd_collect",
                    "--interval",
                    interval,
                    "--outputsize",
                    str(outputsize),
                ],
            )

            created_raw = collect_payload.get("created", [])
            if len(created_raw) != 1:
                raise SystemExit(f"Expected exactly one raw file for {interval}, got: {created_raw}")
            raw_file = created_raw[0]

            normalize_payload = run_json_step(
                f"normalize {interval}",
                [
                    sys.executable,
                    "-m",
                    "app.xauusd_normalize",
                    "--input",
                    raw_file,
                ],
            )
            normalized_file = normalize_payload.get("output")
            if not normalized_file:
                raise SystemExit(f"Normalize step did not return output file for {interval}.")

        quality_payload = run_json_step(
            f"quality {interval}",
            [
                sys.executable,
                "-m",
                "app.xauusd_data_quality",
                "--input",
                normalized_file,
            ],
        )
        quality_report_file = quality_payload.get("report")
        if not quality_report_file:
            raise SystemExit(f"Quality step did not return report file for {interval}.")

        quality = read_json(Path(quality_report_file))

        interval_results.append(
            {
                "interval": interval,
                "source_mode": source_mode,
                "cache_diagnostic": cache_diagnostic,
                "raw_file": raw_file,
                "normalized_file": normalized_file,
                "quality_report_file": quality_report_file,
                "quality": quality,
            }
        )

    overall_ok = all(bool(item["quality"].get("ok")) for item in interval_results)
    summary = {
        "ok": overall_ok,
        "overall_ok": overall_ok,
        "stage": "stage1_multi_interval_snapshot",
        "generated_at_utc": generated_at,
        "provider": provider,
        "symbol": symbol,
        "intervals_requested": intervals,
        "outputsize_requested": outputsize,
        "cache": {
            "enabled": cache_enabled,
            "force_refresh": bool(args.force_refresh),
            "max_age_minutes": max_age_minutes,
            "hit_count": int(cache_hits),
            "miss_count": int(cache_misses),
        },
        "cost_model": cfg.get("cost_model", {}),
        "intervals": interval_results,
    }

    stamp = utc_stamp()
    summary_json = report_dir / f"stage1_snapshot_summary_{stamp}.json"
    summary_md = report_dir / f"stage1_snapshot_summary_{stamp}.md"

    write_json(summary_json, summary)
    write_markdown(summary_md, summary)

    print(
        json.dumps(
            {
                "ok": overall_ok,
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "interval_count": len(interval_results),
                "intervals": intervals,
                "cache": summary["cache"],
            },
            indent=2,
        )
    )

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
