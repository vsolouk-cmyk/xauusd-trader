#!/usr/bin/env python3
"""Stage166G — status-aware persistent GDELT store.

Keeps a persistent long-form point store keyed by (time_bucket_utc, profile).
Only successful incoming query ranges replace prior values. Failed ranges retain
prior observations, preventing HTTP 429/timeout runs from erasing known data.
The DOC API's rolling search window is treated as an acquisition constraint;
old observations are retained locally for reproducibility.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stage166f_github_gdelt_backfill import (  # noqa: E402
    BASE_PANEL_COLS,
    build_dense_panel,
    parse_gdelt_timestamp,
)

POINT_FIELDS = [
    "time_bucket_utc", "profile", "event_count", "gold_long_pressure", "gold_short_pressure",
    "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
    "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score",
    "central_bank_gold_score", "source",
]
STATUS_FIELDS = [
    "run_generated_utc", "profile", "start_utc", "end_utc", "ok", "bytes", "point_count",
    "error", "json_fallback_ok", "json_fallback_bytes", "json_fallback_error", "url",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: Optional[datetime] = None) -> str:
    x = (dt or utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    return x.isoformat().replace("+00:00", "Z")


def detect_sep(path: Path) -> str:
    line = path.open("r", encoding="utf-8-sig", errors="replace").readline()
    return max(["\t", ",", ";", "|"], key=line.count)


def read_csv(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        r = csv.DictReader(f, delimiter=detect_sep(path))
        return list(r), list(r.fieldnames or [])


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def as_bool(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "ok"}


def in_range(ts: str, start: str, end: str) -> bool:
    dt = parse_gdelt_timestamp(ts)
    a = parse_gdelt_timestamp(start)
    b = parse_gdelt_timestamp(end)
    return bool(dt and a and b and a <= dt < b)


def load_prior_points(prior_dir: Path) -> List[Dict[str, str]]:
    for name in ["stage166g_persistent_gdelt_points.csv", "stage166f_gdelt_points.csv"]:
        rows, _ = read_csv(prior_dir / name)
        if rows:
            return rows
    return []


def load_prior_ledger(prior_dir: Path) -> List[Dict[str, str]]:
    rows, _ = read_csv(prior_dir / "stage166g_fetch_ledger.csv")
    return rows


def merge_points(
    prior: List[Dict[str, str]],
    incoming: List[Dict[str, str]],
    statuses: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    by_key: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in prior:
        k = (str(row.get("time_bucket_utc") or ""), str(row.get("profile") or ""))
        if all(k):
            by_key[k] = row

    successful = [s for s in statuses if as_bool(s.get("ok"))]
    failed = [s for s in statuses if not as_bool(s.get("ok"))]

    removed = 0
    for st in successful:
        profile = str(st.get("profile") or "")
        start = str(st.get("start_utc") or "")
        end = str(st.get("end_utc") or "")
        doomed = [k for k in by_key if k[1] == profile and in_range(k[0], start, end)]
        for k in doomed:
            by_key.pop(k, None)
        removed += len(doomed)

    added = 0
    for row in incoming:
        k = (str(row.get("time_bucket_utc") or ""), str(row.get("profile") or ""))
        if all(k):
            by_key[k] = row
            added += 1

    merged = [by_key[k] for k in sorted(by_key)]
    return merged, {
        "prior_point_rows": len(prior),
        "incoming_point_rows": len(incoming),
        "merged_point_rows": len(merged),
        "successful_task_count": len(successful),
        "failed_task_count": len(failed),
        "prior_rows_replaced_in_successful_ranges": removed,
        "incoming_rows_upserted": added,
        "failed_ranges_retained_prior_data": True,
    }


def build_panel(points: List[Dict[str, str]], prior_manifest: Dict[str, Any], statuses: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], str, str]:
    starts = [parse_gdelt_timestamp(str(s.get("start_utc") or "")) for s in statuses]
    ends = [parse_gdelt_timestamp(str(s.get("end_utc") or "")) for s in statuses]
    starts = [x for x in starts if x]
    ends = [x for x in ends if x]
    prior_start = parse_gdelt_timestamp(prior_manifest.get("valid_start_utc")) if prior_manifest else None
    point_times = [parse_gdelt_timestamp(str(r.get("time_bucket_utc") or "")) for r in points]
    point_times = [x for x in point_times if x]
    start = prior_start or (min(starts) if starts else (min(point_times) if point_times else utc_now() - timedelta(days=7)))
    end = max(ends) if ends else utc_now()
    if end <= start:
        end = start + timedelta(hours=1)
    panel = build_dense_panel(points, start, end)
    return panel, utc_iso(start), utc_iso(end)


def write_daily_shards(out_dir: Path, points: List[Dict[str, str]]) -> int:
    shard_root = out_dir / "shards"
    if shard_root.exists():
        shutil.rmtree(shard_root)
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in points:
        dt = parse_gdelt_timestamp(str(row.get("time_bucket_utc") or ""))
        if dt:
            grouped[dt.strftime("%Y-%m-%d")].append(row)
    for day, rows in sorted(grouped.items()):
        y, m, _ = day.split("-")
        write_csv(shard_root / y / m / f"{day}.csv", sorted(rows, key=lambda r: (r.get("time_bucket_utc", ""), r.get("profile", ""))), POINT_FIELDS)
    return len(grouped)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prior-dir", default="")
    p.add_argument("--incoming-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--freeze-lag-hours", type=float, default=72.0)
    a = p.parse_args()

    prior_dir = Path(a.prior_dir).expanduser().resolve() if a.prior_dir else Path("/__missing__")
    incoming_dir = Path(a.incoming_dir).expanduser().resolve()
    out_dir = Path(a.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    incoming_points, _ = read_csv(incoming_dir / "stage166f_gdelt_points.csv")
    statuses, status_fields = read_csv(incoming_dir / "stage166f_fetch_status.csv")
    if not statuses:
        raise SystemExit("incoming fetch status missing or empty")
    prior_points = load_prior_points(prior_dir)
    prior_ledger = load_prior_ledger(prior_dir)
    prior_manifest_path = prior_dir / "stage166g_persistent_manifest.json"
    prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8")) if prior_manifest_path.exists() else {}

    generated = utc_iso()
    merged_points, metrics = merge_points(prior_points, incoming_points, statuses)
    panel, valid_start, valid_end = build_panel(merged_points, prior_manifest, statuses)

    ledger_rows = list(prior_ledger)
    for row in statuses:
        enriched = dict(row)
        enriched["run_generated_utc"] = generated
        ledger_rows.append(enriched)

    # Bound ledger growth while preserving recent diagnostics.
    ledger_rows = ledger_rows[-5000:]

    write_csv(out_dir / "stage166g_persistent_gdelt_points.csv", merged_points, POINT_FIELDS)
    write_csv(out_dir / "stage166g_fetch_ledger.csv", ledger_rows, STATUS_FIELDS)
    write_csv(out_dir / "stage166f_current_event_intraday_panel.csv", panel, BASE_PANEL_COLS)
    write_csv(out_dir / "stage166f_fetch_status.csv", statuses, status_fields or STATUS_FIELDS[1:])
    write_csv(out_dir / "stage166f_gdelt_points.csv", incoming_points, POINT_FIELDS)

    for name in ["stage166f_gdelt_backfill_summary.json", "stage166f_artifact_manifest.json"]:
        src = incoming_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    shard_count = write_daily_shards(out_dir, merged_points)
    freeze_through = utc_now() - timedelta(hours=float(a.freeze_lag_hours))
    manifest = {
        "stage": "Stage166G_GDELT_PERSISTENT_STATUS_AWARE_STORE",
        "generated_utc": generated,
        "valid_start_utc": valid_start,
        "valid_end_utc": valid_end,
        "freeze_lag_hours": float(a.freeze_lag_hours),
        "frozen_through_utc": utc_iso(freeze_through),
        "daily_shard_count": shard_count,
        "panel_rows": len(panel),
        **metrics,
        "source_contract": {
            "api": "GDELT DOC 2.0 timelinevolraw",
            "rolling_search_window": "last_3_months",
            "persistence_reason": "older windows cannot be reconstructed reliably through the same API",
            "failed_fetch_policy": "retain prior data; never replace with synthetic zero rows",
        },
    }
    write_json(out_dir / "stage166g_persistent_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
