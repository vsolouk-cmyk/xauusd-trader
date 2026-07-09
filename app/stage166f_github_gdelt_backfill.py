#!/usr/bin/env python3
"""
Stage166F GitHub GDELT Backfill Collector

Runs safely in GitHub Actions to bypass local TLS/route failures and creates
historical current-event shock panels for XAUUSD/gold research.

This script never authorizes demo/live orders and never writes MT5 files.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage166F_GITHUB_GDELT_BACKFILL"
GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

PROFILE_SPECS = [
    {
        "profile": "geopolitical_escalation",
        "query": '(gold OR XAUUSD OR "safe haven") (war OR missile OR attack OR invasion OR escalation OR military OR conflict OR "air strike" OR strike)',
        "gold_long_weight": 1.0,
        "gold_short_weight": 0.0,
        "cols": {"geopolitical_escalation_score": 1.0},
    },
    {
        "profile": "deescalation",
        "query": '(gold OR XAUUSD OR "safe haven") (ceasefire OR truce OR peace OR de-escalation OR deescalation OR talks OR negotiation)',
        "gold_long_weight": 0.0,
        "gold_short_weight": 1.0,
        "cols": {"deescalation_score": 1.0},
    },
    {
        "profile": "macro_policy_hawkish",
        "query": '(gold OR XAUUSD OR dollar OR treasury OR "real yield") (hawkish OR "rate hike" OR "higher rates" OR tightening OR inflation)',
        "gold_long_weight": 0.0,
        "gold_short_weight": 1.0,
        "cols": {"macro_policy_hawkish_score": 1.0},
    },
    {
        "profile": "macro_policy_dovish",
        "query": '(gold OR XAUUSD OR dollar OR treasury OR "real yield") (dovish OR "rate cut" OR easing OR recession OR slowdown)',
        "gold_long_weight": 1.0,
        "gold_short_weight": 0.0,
        "cols": {"macro_policy_dovish_score": 1.0},
    },
    {
        "profile": "inflation_energy_shock",
        "query": '(gold OR XAUUSD OR inflation OR oil OR energy) (oil shock OR "energy prices" OR crude OR inflation OR supply shock OR sanctions)',
        "gold_long_weight": 0.8,
        "gold_short_weight": 0.0,
        "cols": {"inflation_energy_shock_score": 1.0},
    },
    {
        "profile": "market_stress",
        "query": '(gold OR XAUUSD OR "safe haven") (bank crisis OR default OR credit stress OR volatility OR selloff OR panic OR systemic)',
        "gold_long_weight": 1.0,
        "gold_short_weight": 0.0,
        "cols": {"market_stress_score": 1.0},
    },
    {
        "profile": "central_bank_gold",
        "query": '(gold OR bullion) (central bank OR reserves OR purchase OR buying OR holdings)',
        "gold_long_weight": 0.8,
        "gold_short_weight": 0.0,
        "cols": {"central_bank_gold_score": 1.0},
    },
]

BASE_PANEL_COLS = [
    "time_bucket_utc",
    "event_count",
    "gold_long_pressure",
    "gold_short_pressure",
    "shock_abs",
    "geopolitical_escalation_score",
    "deescalation_score",
    "macro_policy_hawkish_score",
    "macro_policy_dovish_score",
    "inflation_energy_shock_score",
    "market_stress_score",
    "central_bank_gold_score",
    "net_gold_event_pressure",
    "event_shock_regime",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def gdelt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def iso_hour(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def chunk_ranges(start: datetime, end: datetime, chunk_days: int) -> List[Tuple[datetime, datetime]]:
    out: List[Tuple[datetime, datetime]] = []
    cur = start
    delta = timedelta(days=max(1, int(chunk_days)))
    while cur < end:
        nxt = min(cur + delta, end)
        out.append((cur, nxt))
        cur = nxt
    return out


def build_tasks(start: datetime, end: datetime, chunk_days: int, max_queries: int) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for spec in PROFILE_SPECS:
        for a, b in chunk_ranges(start, end, chunk_days):
            tasks.append({"profile": spec["profile"], "query": spec["query"], "start": a, "end": b, "spec": spec})
    if max_queries and max_queries > 0:
        tasks = tasks[:max_queries]
    return tasks


def build_gdelt_url(query: str, start: datetime, end: datetime, fmt: str = "csv") -> str:
    params = {
        "query": query,
        "mode": "timelinevolraw",
        "format": fmt,
        "startdatetime": gdelt_dt(start),
        "enddatetime": gdelt_dt(end),
    }
    return GDELT_DOC_ENDPOINT + "?" + urllib.parse.urlencode(params)


def fetch_url(url: str, timeout: float, user_agent: str) -> Tuple[bool, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        return True, data, ""
    except Exception as e:  # noqa: BLE001
        return False, b"", f"{type(e).__name__}: {e}"


def parse_gdelt_timestamp(value: Any) -> Optional[datetime]:
    s = str(value).strip().strip('"')
    if not s:
        return None
    # GDELT commonly returns YYYYMMDDHHMMSS or ISO-like strings.
    for fmt in ["%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        # Last-resort pandas-free ISO parse.
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def parse_csv_points(data: bytes) -> List[Tuple[datetime, float]]:
    text = data.decode("utf-8", errors="replace")
    # Some GDELT CSVs are headered. If not, try two-column fallback.
    sample = text[:2048]
    points: List[Tuple[datetime, float]] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = [f or "" for f in (reader.fieldnames or [])]
        if fieldnames:
            lower = {f.lower(): f for f in fieldnames}
            time_col = None
            value_col = None
            for k in ["datetime", "date", "time", "timestamp"]:
                if k in lower:
                    time_col = lower[k]
                    break
            for k in ["value", "count", "vol", "volume", "mentions"]:
                if k in lower:
                    value_col = lower[k]
                    break
            if time_col is None:
                time_col = fieldnames[0]
            if value_col is None and len(fieldnames) > 1:
                value_col = fieldnames[1]
            if time_col and value_col:
                for row in reader:
                    dt = parse_gdelt_timestamp(row.get(time_col, ""))
                    try:
                        val = float(str(row.get(value_col, "0")).strip().replace(",", ""))
                    except Exception:
                        val = 0.0
                    if dt is not None and math.isfinite(val):
                        points.append((dt, val))
                if points:
                    return points
    except Exception:
        pass
    try:
        reader2 = csv.reader(io.StringIO(text))
        for row in reader2:
            if len(row) < 2:
                continue
            dt = parse_gdelt_timestamp(row[0])
            try:
                val = float(str(row[1]).strip().replace(",", ""))
            except Exception:
                continue
            if dt is not None and math.isfinite(val):
                points.append((dt, val))
    except Exception:
        pass
    return points


def walk_json_points(obj: Any) -> List[Tuple[datetime, float]]:
    points: List[Tuple[datetime, float]] = []
    if isinstance(obj, dict):
        if any(k.lower() in {"datetime", "date", "time", "timestamp"} for k in obj) and any(k.lower() in {"value", "count", "vol", "volume"} for k in obj):
            time_val = None
            val_val = None
            for k, v in obj.items():
                if k.lower() in {"datetime", "date", "time", "timestamp"} and time_val is None:
                    time_val = v
                if k.lower() in {"value", "count", "vol", "volume"} and val_val is None:
                    val_val = v
            dt = parse_gdelt_timestamp(time_val)
            try:
                val = float(val_val)
            except Exception:
                val = 0.0
            if dt is not None and math.isfinite(val):
                points.append((dt, val))
        for v in obj.values():
            points.extend(walk_json_points(v))
    elif isinstance(obj, list):
        for v in obj:
            points.extend(walk_json_points(v))
    return points


def parse_json_points(data: bytes) -> List[Tuple[datetime, float]]:
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return []
    return walk_json_points(obj)


def fetch_task(task: Dict[str, Any], timeout: float, user_agent: str, raw_dir: Path, skip_network: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile = task["profile"]
    start = task["start"]
    end = task["end"]
    spec = task["spec"]
    url = build_gdelt_url(task["query"], start, end, fmt="csv")
    status: Dict[str, Any] = {
        "profile": profile,
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "end_utc": end.isoformat().replace("+00:00", "Z"),
        "url": url,
        "ok": False,
        "bytes": 0,
        "point_count": 0,
        "error": "",
    }
    if skip_network:
        status["error"] = "SKIP_NETWORK"
        return [], status
    ok, data, err = fetch_url(url, timeout, user_agent)
    status["ok"] = ok
    status["bytes"] = len(data)
    status["error"] = err
    rows: List[Dict[str, Any]] = []
    if ok and data:
        raw_name = f"gdelt_{profile}_{gdelt_dt(start)}_{gdelt_dt(end)}.csv"
        (raw_dir / raw_name).write_bytes(data)
        points = parse_csv_points(data)
        if not points:
            # Try JSON fallback once if CSV shape changed.
            json_url = build_gdelt_url(task["query"], start, end, fmt="json")
            ok2, data2, err2 = fetch_url(json_url, timeout, user_agent)
            status["json_fallback_ok"] = ok2
            status["json_fallback_error"] = err2
            status["json_fallback_bytes"] = len(data2)
            if ok2 and data2:
                (raw_dir / raw_name.replace(".csv", ".json")).write_bytes(data2)
                points = parse_json_points(data2)
        for dt, val in points:
            if val <= 0:
                continue
            row = {
                "time_bucket_utc": iso_hour(dt),
                "profile": profile,
                "event_count": float(val),
                "gold_long_pressure": float(val) * float(spec.get("gold_long_weight", 0.0)),
                "gold_short_pressure": float(val) * float(spec.get("gold_short_weight", 0.0)),
                "source": "gdelt_doc_timelinevolraw",
            }
            for col, w in spec.get("cols", {}).items():
                row[col] = float(val) * float(w)
            rows.append(row)
    status["point_count"] = len(rows)
    return rows, status


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def build_dense_panel(points: Sequence[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    hourly: Dict[str, Dict[str, Any]] = {}
    cur = start.replace(minute=0, second=0, microsecond=0)
    end_hour = end.replace(minute=0, second=0, microsecond=0)
    while cur <= end_hour:
        k = iso_hour(cur)
        hourly[k] = {c: 0.0 for c in BASE_PANEL_COLS if c != "time_bucket_utc" and c != "event_shock_regime"}
        hourly[k]["time_bucket_utc"] = k
        hourly[k]["event_shock_regime"] = "NO_EVENT"
        cur += timedelta(hours=1)
    for p in points:
        k = str(p.get("time_bucket_utc", ""))
        if k not in hourly:
            continue
        for col in BASE_PANEL_COLS:
            if col in {"time_bucket_utc", "event_shock_regime"}:
                continue
            try:
                hourly[k][col] = float(hourly[k].get(col, 0.0)) + float(p.get(col, 0.0) or 0.0)
            except Exception:
                pass
    out: List[Dict[str, Any]] = []
    for k in sorted(hourly):
        r = hourly[k]
        long_p = float(r.get("gold_long_pressure", 0.0) or 0.0)
        short_p = float(r.get("gold_short_pressure", 0.0) or 0.0)
        net = long_p - short_p
        shock = abs(net) + float(r.get("event_count", 0.0) or 0.0) * 0.1
        r["net_gold_event_pressure"] = net
        r["shock_abs"] = shock
        if shock <= 0:
            regime = "NO_EVENT"
        elif net > 0:
            regime = "GOLD_LONG_EVENT_PRESSURE"
        elif net < 0:
            regime = "GOLD_SHORT_EVENT_PRESSURE"
        else:
            regime = "MIXED_EVENT_PRESSURE"
        r["event_shock_regime"] = regime
        # Stable float rounding for smaller CSVs.
        for c, v in list(r.items()):
            if isinstance(v, float):
                r[c] = round(v, 6)
        out.append(r)
    return out


def summarize_health(panel: Sequence[Dict[str, Any]], split_date: Optional[str]) -> Dict[str, Any]:
    nonzero = [r for r in panel if float(r.get("shock_abs", 0.0) or 0.0) > 0]
    train_nonzero = None
    holdout_nonzero = None
    if split_date:
        split_dt = parse_ymd(split_date)
        train_nonzero = sum(1 for r in nonzero if parse_gdelt_timestamp(r["time_bucket_utc"]) and parse_gdelt_timestamp(r["time_bucket_utc"]) < split_dt)
        holdout_nonzero = sum(1 for r in nonzero if parse_gdelt_timestamp(r["time_bucket_utc"]) and parse_gdelt_timestamp(r["time_bucket_utc"]) >= split_dt)
    return {
        "panel_rows": len(panel),
        "panel_nonzero_shock_rows": len(nonzero),
        "split_date": split_date,
        "train_nonzero_shock_hours": train_nonzero,
        "holdout_nonzero_shock_hours": holdout_nonzero,
        "historical_trainable_candidate": bool((train_nonzero or 0) >= 500) if split_date else None,
    }


def run_fetch(args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = Path(args.output_dir).expanduser().resolve()
    ensure_dir(out_dir)
    raw_dir = out_dir / "raw_gdelt"
    ensure_dir(raw_dir)
    start = parse_ymd(args.start_date)
    if args.end_date:
        end = parse_ymd(args.end_date) + timedelta(days=1)
    else:
        end = datetime.now(timezone.utc)
    tasks = build_tasks(start, end, int(args.chunk_days), int(args.max_queries))

    all_points: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    t0 = time.time()
    if int(args.max_workers) <= 1:
        for task in tasks:
            rows, st = fetch_task(task, args.timeout_seconds, args.user_agent, raw_dir, args.skip_network)
            all_points.extend(rows)
            statuses.append(st)
    else:
        with ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as ex:
            futs = [ex.submit(fetch_task, task, args.timeout_seconds, args.user_agent, raw_dir, args.skip_network) for task in tasks]
            for fut in as_completed(futs):
                rows, st = fut.result()
                all_points.extend(rows)
                statuses.append(st)
    statuses = sorted(statuses, key=lambda x: (x.get("profile", ""), x.get("start_utc", "")))
    all_points = sorted(all_points, key=lambda x: (x.get("time_bucket_utc", ""), x.get("profile", "")))
    panel = build_dense_panel(all_points, start, end)
    health = summarize_health(panel, args.split_date)

    point_fields = [
        "time_bucket_utc", "profile", "event_count", "gold_long_pressure", "gold_short_pressure",
        "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
        "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score",
        "central_bank_gold_score", "source",
    ]
    write_csv(out_dir / "stage166f_gdelt_points.csv", all_points, point_fields)
    write_csv(out_dir / "stage166f_fetch_status.csv", statuses, ["profile", "start_utc", "end_utc", "ok", "bytes", "point_count", "error", "json_fallback_ok", "json_fallback_bytes", "json_fallback_error", "url"])
    write_csv(out_dir / "stage166f_current_event_intraday_panel.csv", panel, BASE_PANEL_COLS)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "mode": "fetch",
        "start_date": args.start_date,
        "end_date": args.end_date or end.date().isoformat(),
        "chunk_days": int(args.chunk_days),
        "max_workers": int(args.max_workers),
        "max_queries": int(args.max_queries),
        "timeout_seconds": float(args.timeout_seconds),
        "task_count": len(tasks),
        "fetch_ok_count": sum(1 for s in statuses if s.get("ok")),
        "fetch_point_count": len(all_points),
        "elapsed_seconds": round(time.time() - t0, 3),
        "health": health,
        "outputs": {
            "fetch_status_csv": str(out_dir / "stage166f_fetch_status.csv"),
            "points_csv": str(out_dir / "stage166f_gdelt_points.csv"),
            "intraday_panel_csv": str(out_dir / "stage166f_current_event_intraday_panel.csv"),
            "summary_json": str(out_dir / "stage166f_gdelt_backfill_summary.json"),
        },
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "decision": "STAGE166F_GDELT_ARTIFACT_READY" if len(all_points) > 0 else "STAGE166F_NO_GDELT_POINTS_CHECK_ACTIONS_NETWORK_OR_QUERY",
    }
    write_json(out_dir / "stage166f_gdelt_backfill_summary.json", summary)
    write_json(out_dir / "stage166f_artifact_manifest.json", {"files": summary["outputs"], "raw_dir": str(raw_dir)})
    return summary


def run_install_artifact(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    artifact_dir = Path(args.artifact_dir).expanduser().resolve()
    panel_src = artifact_dir / "stage166f_current_event_intraday_panel.csv"
    if not panel_src.exists():
        raise FileNotFoundError(str(panel_src))
    compat_dir = root / "reports" / "stage166_current_event_shock_overlay"
    ensure_dir(compat_dir)
    compat_panel = compat_dir / "stage166_current_event_intraday_panel.csv"
    backup = None
    if compat_panel.exists() and args.backup_existing_compatible_panel:
        backup = compat_panel.with_suffix(".pre_stage166f_backup.csv")
        shutil.copy2(compat_panel, backup)
    if args.write_stage166_compatible_panel:
        shutil.copy2(panel_src, compat_panel)
    # Copy full artifact to repo reports for lineage.
    report_dir = root / "reports" / "stage166f_github_gdelt_backfill"
    ensure_dir(report_dir)
    for p in artifact_dir.iterdir():
        if p.is_file():
            shutil.copy2(p, report_dir / p.name)
    # Lightweight health from panel rows.
    with panel_src.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    health = summarize_health(rows, args.split_date)
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "mode": "install_artifact",
        "root": str(root),
        "artifact_dir": str(artifact_dir),
        "write_stage166_compatible_panel": bool(args.write_stage166_compatible_panel),
        "compatible_stage166_panel_csv": str(compat_panel),
        "compatible_stage166_panel_backup": str(backup) if backup else None,
        "health": health,
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "decision": "STAGE166F_COMPATIBLE_PANEL_INSTALLED_RERUN_STAGE167" if args.write_stage166_compatible_panel else "STAGE166F_ARTIFACT_IMPORTED_NO_COMPATIBLE_WRITE",
    }
    write_json(report_dir / "stage166f_local_install_summary.json", summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage166F GitHub GDELT backfill collector/importer")
    sub = p.add_subparsers(dest="mode", required=True)

    f = sub.add_parser("fetch", help="Fetch GDELT data; intended for GitHub Actions")
    f.add_argument("--output-dir", required=True)
    f.add_argument("--start-date", default="2022-01-01")
    f.add_argument("--end-date", default="")
    f.add_argument("--split-date", default="2025-08-13")
    f.add_argument("--chunk-days", type=int, default=180)
    f.add_argument("--max-workers", type=int, default=4)
    f.add_argument("--max-queries", type=int, default=0, help="0 means no cap")
    f.add_argument("--timeout-seconds", type=float, default=20.0)
    f.add_argument("--user-agent", default="xauusd-stage166f-github-actions/1.0")
    f.add_argument("--skip-network", action="store_true")

    i = sub.add_parser("install-artifact", help="Install downloaded GitHub artifact locally into Stage166-compatible panel")
    i.add_argument("--root", required=True)
    i.add_argument("--artifact-dir", required=True)
    i.add_argument("--split-date", default="2025-08-13")
    i.add_argument("--write-stage166-compatible-panel", action="store_true")
    i.add_argument("--backup-existing-compatible-panel", action="store_true")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.mode == "fetch":
        summary = run_fetch(args)
    elif args.mode == "install-artifact":
        summary = run_install_artifact(args)
    else:
        raise ValueError(args.mode)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
