from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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
            "Stop here. Do not continue Stage 1 until this is fixed."
        )

    # Each pipeline step prints JSON as its final/output payload.
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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 1 Snapshot Summary")
    lines.append("")
    lines.append(f"- Generated at UTC: `{summary['generated_at_utc']}`")
    lines.append(f"- Provider: `{summary['provider']}`")
    lines.append(f"- Symbol: `{summary['symbol']}`")
    lines.append(f"- Overall OK: `{summary['overall_ok']}`")
    lines.append("")
    lines.append("## Interval quality")
    lines.append("")
    lines.append("| Interval | OK | Rows | Missing ratio | Duplicate timestamps | Spread available | Start UTC | End UTC |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---|")
    for item in summary["intervals"]:
        q = item["quality"]
        spread = q.get("spread", {})
        lines.append(
            "| {interval} | {ok} | {rows} | {missing:.6f} | {dupes} | {spread_available} | {start} | {end} |".format(
                interval=q.get("interval"),
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
    lines.append("Twelve Data Stage 1 does not provide broker bid/ask spread in this pipeline.")
    lines.append("Baseline testing must therefore use conservative assumed costs and later validate with MT5/broker feed.")
    lines.append("")
    cost_model = summary.get("cost_model", {})
    for key, value in cost_model.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.append("")
    lines.append("## Files")
    lines.append("")
    for item in summary["intervals"]:
        lines.append(f"- `{item['interval']}`")
        lines.append(f"  - raw: `{item['raw_file']}`")
        lines.append(f"  - normalized: `{item['normalized_file']}`")
        lines.append(f"  - quality: `{item['quality_report_file']}`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 1 multi-interval data snapshot: collect -> normalize -> quality -> aggregate summary."
    )
    parser.add_argument("--config", default="configs/data_source.yaml")
    parser.add_argument(
        "--intervals",
        default=None,
        help="Comma-separated intervals. Default: config intervals.",
    )
    parser.add_argument("--outputsize", type=int, default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    provider = cfg.get("provider", "twelvedata")
    symbol = cfg.get("symbol", "XAU/USD")
    report_dir = Path(cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

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

    for interval in intervals:
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
            },
            indent=2,
        )
    )

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
