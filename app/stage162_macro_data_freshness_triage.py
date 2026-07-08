#!/usr/bin/env python3
"""Stage162: Macro/fundamental data freshness triage for XAUUSD.

Read-only diagnostic. It does not write MT5 KV, does not create signals, and does not
alter order routing. It checks whether the official-data download/unify/normalize
pipeline produced content-fresh macro/regime features, rather than merely files with
fresh modification times.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas is required for Stage162: {exc}")


DATE_HINTS = ("date", "time", "timestamp", "utc", "period", "observation")


@dataclass
class FileProbe:
    label: str
    path: str
    required: bool
    max_stale_days: float
    exists: bool = False
    size_bytes: int = 0
    row_count: int = 0
    columns: str = ""
    selected_date_column: str = ""
    latest_time_utc: str = ""
    age_days: Optional[float] = None
    freshness_status: str = "MISSING"
    error: str = ""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        fieldnames = sorted({k for r in rows for k in r.keys()}) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def safe_stat(path: Path) -> Tuple[bool, int]:
    try:
        st = path.stat()
        return True, int(st.st_size)
    except FileNotFoundError:
        return False, 0


def parse_datetime_series(series: pd.Series) -> pd.Series:
    # Normalize common numeric year/month/day strings is handled by pandas best effort.
    s = series.astype("string").str.strip()
    s = s.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA})
    parsed = pd.to_datetime(s, errors="coerce", utc=True)
    return parsed


def pick_latest_datetime(df: pd.DataFrame) -> Tuple[str, Optional[datetime], int]:
    if df.empty:
        return "", None, 0
    candidates: List[str] = []
    for c in df.columns:
        cl = str(c).lower()
        if any(h in cl for h in DATE_HINTS):
            candidates.append(c)
    # fallback: first few object-ish columns
    if not candidates:
        for c in df.columns[: min(12, len(df.columns))]:
            if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
                candidates.append(c)
    best_col = ""
    best_latest: Optional[pd.Timestamp] = None
    best_count = 0
    for c in candidates:
        try:
            parsed = parse_datetime_series(df[c])
            count = int(parsed.notna().sum())
            if count <= 0:
                continue
            latest = parsed.max()
            if pd.isna(latest):
                continue
            if best_latest is None or latest > best_latest or (latest == best_latest and count > best_count):
                best_col = str(c)
                best_latest = latest
                best_count = count
        except Exception:
            continue
    if best_latest is None:
        return "", None, 0
    return best_col, best_latest.to_pydatetime(), best_count


def read_csv_robust(path: Path) -> pd.DataFrame:
    # Try common separators. AMarkets is tab-delimited; macro features are usually comma.
    errors = []
    for sep in [None, ",", "\t", ";"]:
        try:
            if sep is None:
                return pd.read_csv(path, sep=None, engine="python", low_memory=False)
            return pd.read_csv(path, sep=sep, low_memory=False)
        except Exception as exc:
            errors.append(f"sep={sep!r}:{type(exc).__name__}:{exc}")
    raise RuntimeError("; ".join(errors[-3:]))


def probe_file(label: str, path: Path, required: bool, max_stale_days: float, ref_now: datetime) -> FileProbe:
    p = FileProbe(label=label, path=str(path), required=required, max_stale_days=max_stale_days)
    p.exists, p.size_bytes = safe_stat(path)
    if not p.exists:
        p.freshness_status = "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
        return p
    if p.size_bytes <= 10:
        p.freshness_status = "EMPTY_OR_TINY_REQUIRED" if required else "EMPTY_OR_TINY_OPTIONAL"
        return p
    try:
        df = read_csv_robust(path)
        p.row_count = int(len(df))
        p.columns = "|".join(map(str, df.columns[:50]))
        col, latest, valid_count = pick_latest_datetime(df)
        p.selected_date_column = col
        if latest is None:
            p.freshness_status = "NO_PARSEABLE_DATE_REQUIRED" if required else "NO_PARSEABLE_DATE_OPTIONAL"
            return p
        p.latest_time_utc = latest.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        age = (ref_now - latest.astimezone(timezone.utc)).total_seconds() / 86400.0
        p.age_days = round(age, 4)
        if p.row_count <= 0:
            p.freshness_status = "NO_ROWS_REQUIRED" if required else "NO_ROWS_OPTIONAL"
        elif age < -1.0:
            p.freshness_status = "FUTURE_DATED_CHECK_TIMEZONE"
        elif age <= max_stale_days:
            p.freshness_status = "FRESH"
        else:
            p.freshness_status = "STALE_REQUIRED" if required else "STALE_OPTIONAL"
    except Exception as exc:
        p.error = f"{type(exc).__name__}: {exc}"
        p.freshness_status = "READ_ERROR_REQUIRED" if required else "READ_ERROR_OPTIONAL"
    return p


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def default_targets(root: Path, inbox: Path) -> List[Tuple[str, Path, bool, float]]:
    feature = root / "data/fundamental_event_inbox/features"
    normalized = root / "data/fundamental_event_inbox/normalized"
    reports = root / "reports"
    return [
        ("feature_stage115_daily_macro_panel", feature / "stage115_daily_macro_feature_panel.csv", True, 5.0),
        ("feature_stage115_fred_wide", feature / "stage115_fred_macro_daily_wide.csv", True, 5.0),
        ("feature_stage116_dollar_pressure", feature / "stage116_validated_dollar_pressure.csv", True, 5.0),
        ("feature_stage115_cot_gold_weekly", feature / "stage115_cot_gold_weekly_features.csv", True, 14.0),
        ("feature_stage115_event_calendar", feature / "stage115_unified_event_calendar_features.csv", True, 60.0),
        ("feature_stage117_joined_h1_macro_dataset", feature / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv", True, 10.0),
        ("feature_stage115_spdr_candidates", feature / "stage115_spdr_gld_feature_candidates.csv", False, 10.0),
        ("feature_stage116_spdr_validated", feature / "stage116_validated_spdr_gld_long.csv", False, 10.0),
        ("feature_stage116_wgc_etf_validated", feature / "stage116_validated_wgc_gold_etf_long.csv", False, 45.0),
        ("feature_stage116_wgc_central_bank_validated", feature / "stage116_validated_wgc_central_bank_gold_long.csv", False, 120.0),
        ("normalized_fred_macro", normalized / "fred_macro_normalized.csv", True, 5.0),
        ("normalized_dxy_reference", normalized / "dxy_reference_normalized.csv", True, 5.0),
        ("pipeline_summary", reports / "xauusd_fundamental_unify_normalize_pipeline/xauusd_fundamental_unify_normalize_pipeline_summary.json", True, 2.0),
        ("stage116_summary", reports / "stage116_source_specific_wgc_spdr_dxy_validator/stage116_source_specific_wgc_spdr_dxy_validator_summary.json", True, 2.0),
        ("download_latest_summary", inbox / "_logs/download_xauusd_official_data_batch_latest_summary.json", False, 2.0),
    ]


def probe_json_mtime(label: str, path: Path, required: bool, max_stale_days: float, ref_now: datetime) -> FileProbe:
    p = FileProbe(label=label, path=str(path), required=required, max_stale_days=max_stale_days)
    p.exists, p.size_bytes = safe_stat(path)
    if not p.exists:
        p.freshness_status = "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
        return p
    try:
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        p.latest_time_utc = mtime.isoformat().replace("+00:00", "Z")
        p.selected_date_column = "file_mtime"
        age = (ref_now - mtime).total_seconds() / 86400.0
        p.age_days = round(age, 4)
        p.row_count = 1
        p.freshness_status = "FRESH" if age <= max_stale_days else ("STALE_REQUIRED" if required else "STALE_OPTIONAL")
    except Exception as exc:
        p.error = f"{type(exc).__name__}: {exc}"
        p.freshness_status = "READ_ERROR_REQUIRED" if required else "READ_ERROR_OPTIONAL"
    return p


def diagnose(probes: List[FileProbe]) -> Tuple[str, str, str, List[str]]:
    required_bad = [p for p in probes if p.required and p.freshness_status != "FRESH"]
    optional_bad = [p for p in probes if (not p.required) and p.freshness_status not in ("FRESH", "MISSING_OPTIONAL", "EMPTY_OR_TINY_OPTIONAL", "STALE_OPTIONAL")]
    issues: List[str] = []
    for p in required_bad:
        issues.append(f"{p.label}:{p.freshness_status}:latest={p.latest_time_utc or 'NA'}:age_days={p.age_days}")
    if required_bad:
        decision = "STAGE162_MACRO_CONTENT_STALE_OR_INCOMPLETE_REPAIR_REQUIRED"
        severity = "HIGH"
        recommended = "REPAIR_DOWNLOAD_OR_PIPELINE_BEFORE_MACRO_AWARE_DEMO_CLASSIFICATION"
    else:
        decision = "STAGE162_MACRO_CONTENT_FRESH_READY_FOR_STAGE161_RECLASSIFICATION"
        severity = "INFO" if not optional_bad else "WARN"
        recommended = "RERUN_STAGE161_MACRO_AWARE_CLASSIFIER_AND_REVIEW_LABELS"
    return decision, severity, recommended, issues


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--inbox", default=str(Path.home() / "Downloads/xauusd_fundamental_event_inbox"))
    ap.add_argument("--out", default="reports/stage162_macro_data_freshness_triage")
    ap.add_argument("--max-core-stale-days", type=float, default=5.0, help="Default core daily freshness threshold; target-specific thresholds still apply")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    inbox = Path(args.inbox).expanduser().resolve()
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    ref_now = now_utc()

    probes: List[FileProbe] = []
    for label, path, required, max_days in default_targets(root, inbox):
        if path.suffix.lower() == ".json":
            probes.append(probe_json_mtime(label, path, required, max_days, ref_now))
        else:
            probes.append(probe_file(label, path, required, max_days, ref_now))

    decision, severity, recommended, issues = diagnose(probes)

    file_rows = [asdict(p) for p in probes]
    write_csv(out_dir / "stage162_macro_file_freshness.csv", file_rows, list(asdict(probes[0]).keys()) if probes else None)
    stale_rows = [asdict(p) for p in probes if p.freshness_status != "FRESH"]
    write_csv(out_dir / "stage162_macro_stale_root_cause_candidates.csv", stale_rows, list(asdict(probes[0]).keys()) if probes else None)

    summary = {
        "stage": "Stage162_MACRO_DATA_FRESHNESS_TRIAGE",
        "generated_utc": ref_now.isoformat().replace("+00:00", "Z"),
        "status": "STAGE162_COMPLETE_MACRO_DATA_FRESHNESS_TRIAGE_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended,
        "root": str(root),
        "inbox": str(inbox),
        "required_file_count": sum(1 for p in probes if p.required),
        "required_fresh_count": sum(1 for p in probes if p.required and p.freshness_status == "FRESH"),
        "required_bad_count": sum(1 for p in probes if p.required and p.freshness_status != "FRESH"),
        "optional_issue_count": sum(1 for p in probes if (not p.required) and p.freshness_status not in ("FRESH", "MISSING_OPTIONAL", "EMPTY_OR_TINY_OPTIONAL", "STALE_OPTIONAL")),
        "issues": issues,
        "freshness_status_counts": {s: sum(1 for p in probes if p.freshness_status == s) for s in sorted({p.freshness_status for p in probes})},
        "outputs": {
            "summary_json": str(out_dir / "stage162_macro_data_freshness_triage_summary.json"),
            "file_freshness_csv": str(out_dir / "stage162_macro_file_freshness.csv"),
            "stale_root_cause_candidates_csv": str(out_dir / "stage162_macro_stale_root_cause_candidates.csv"),
        },
        "next": [
            "If required_bad_count is non-zero, inspect stage162_macro_stale_root_cause_candidates.csv before rerunning Stage161.",
            "If normalized sources are fresh but feature files are stale, rerun Stage115/116/117 pipeline steps.",
            "If normalized sources are stale, rerun scripts/download_xauusd_official_data_batch.py and the full pipeline.",
            "Keep Stage157 freeze active until Stage161 produces a small macro-supported family set.",
        ],
    }
    write_json(out_dir / "stage162_macro_data_freshness_triage_summary.json", summary)

    status_rows = [{"key": k, "value": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v} for k, v in summary.items() if k in ("stage", "status", "decision", "severity", "recommended_action", "required_bad_count")]
    write_csv(out_dir / "stage162_macro_data_freshness_triage_status_kv.csv", status_rows, ["key", "value"])
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
