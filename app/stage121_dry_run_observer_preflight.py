#!/usr/bin/env python3
"""
Stage121 dry-run observer preflight for XAUUSD macro/SPDR observer-design candidates.

Reports-only stage:
- Does not write MT5/MQL5/Files.
- Does not modify active observer files.
- Does not touch EA, broker, paper/live/order surfaces.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import operator
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


STAGE = "Stage121_DRY_RUN_OBSERVER_PREFLIGHT"
STATUS_OK = "STAGE121_COMPLETE_DRY_RUN_PREFLIGHT_READY_NO_UPDATE"
STATUS_BLOCKED = "STAGE121_BLOCKED_PREFLIGHT_INPUTS_MISSING_NO_UPDATE"
DECISION_OK = "STAGE121_DRY_RUN_PREFLIGHT_REPORT_READY_NO_OBSERVER_UPDATE"
DECISION_BLOCKED = "STAGE121_PREFLIGHT_BLOCKED_NO_OBSERVER_UPDATE"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE121",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE121",
    "NO_OBSERVER_BRIDGE_WRITE",
    "NO_MT5_MQL5_FILES_WRITE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

COMPARISON_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass
class Condition:
    feature: str
    op_text: str
    value: float

    def evaluate(self, frame: pd.DataFrame) -> pd.Series:
        if self.feature not in frame.columns:
            return pd.Series([False] * len(frame), index=frame.index)
        vals = pd.to_numeric(frame[self.feature], errors="coerce")
        return COMPARISON_OPS[self.op_text](vals, self.value)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def write_json(path: Path, obj: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: List[dict], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        fieldnames = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_time_column(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "utc_time",
        "time_utc",
        "timestamp",
        "datetime",
        "date_time",
        "bar_time",
        "time",
        "date",
    ]
    lowered = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in lowered:
            return lowered[c]
    for c in df.columns:
        lc = c.lower()
        if "utc" in lc and ("time" in lc or "date" in lc):
            return c
    return None


def coerce_timestamp(df: pd.DataFrame) -> Tuple[pd.DataFrame, Optional[str]]:
    out = df.copy()
    time_col = detect_time_column(out)
    if time_col is None:
        return out, None
    out["_stage121_timestamp"] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    return out, time_col


def load_stage120_preflight_queue(stage120_dir: Path) -> pd.DataFrame:
    path = stage120_dir / "stage120_stage121_preflight_queue.csv"
    df = read_csv_if_exists(path)
    if df.empty:
        return df
    if "is_stage121_preflight_candidate" in df.columns:
        mask = df["is_stage121_preflight_candidate"].astype(str).str.lower().isin(["true", "1", "yes"])
        df = df.loc[mask].copy()
    return df


def parse_required_features(value: object) -> List[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return [x.strip() for x in str(value).split(";") if x.strip()]


def parse_condition_text(text: object) -> List[Condition]:
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return []
    parts = [p.strip() for p in str(text).split(";") if p.strip()]
    conditions: List[Condition] = []
    pattern = re.compile(r"^\s*([A-Za-z0-9_./:-]+)\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*$")
    for part in parts:
        m = pattern.match(part)
        if not m:
            continue
        conditions.append(Condition(m.group(1), m.group(2), float(m.group(3))))
    return conditions


def find_joined_or_split_dataset(root: Path, stage117_dir: Path) -> Tuple[pd.DataFrame, str]:
    candidates = [
        root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        root / "reports/stage117_segmented_macro_cot_dollar_discovery/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ]
    for path in candidates:
        df = read_csv_if_exists(path)
        if not df.empty:
            return df, str(path)

    split_paths = [
        ("selection", stage117_dir / "stage117_selection_rows.csv"),
        ("validation", stage117_dir / "stage117_validation_rows.csv"),
        ("tail_forward_proxy", stage117_dir / "stage117_tail_forward_proxy_rows.csv"),
    ]
    frames = []
    for split_name, path in split_paths:
        df = read_csv_if_exists(path)
        if not df.empty:
            df = df.copy()
            if "stage121_split" not in df.columns:
                df["stage121_split"] = split_name
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True, sort=False), "stage117_split_rows_combined"

    return pd.DataFrame(), "NOT_FOUND"


def apply_event_spacing(df: pd.DataFrame, spacing_hours: float) -> pd.DataFrame:
    if df.empty or "_stage121_timestamp" not in df.columns:
        return df.copy()
    clean = df.dropna(subset=["_stage121_timestamp"]).sort_values("_stage121_timestamp").copy()
    if clean.empty:
        return clean
    keep_indices = []
    last_ts = None
    min_delta = pd.Timedelta(hours=float(spacing_hours))
    for idx, row in clean.iterrows():
        ts = row["_stage121_timestamp"]
        if last_ts is None or ts - last_ts >= min_delta:
            keep_indices.append(idx)
            last_ts = ts
    return clean.loc[keep_indices].copy()


def feature_coverage(df: pd.DataFrame, features: List[str]) -> List[dict]:
    rows = []
    total = len(df)
    for f in features:
        if f not in df.columns:
            rows.append({
                "feature": f,
                "present": False,
                "non_null_rows": 0,
                "total_rows": total,
                "coverage_pct": 0.0,
            })
            continue
        non_null = pd.to_numeric(df[f], errors="coerce").notna().sum()
        rows.append({
            "feature": f,
            "present": True,
            "non_null_rows": int(non_null),
            "total_rows": int(total),
            "coverage_pct": round(float(non_null / total * 100.0), 4) if total else 0.0,
        })
    return rows


def evaluate_rule(row: pd.Series, dataset: pd.DataFrame) -> Tuple[pd.DataFrame, dict, List[dict]]:
    rule_id = str(row.get("observer_design_rule_id", row.get("source_rule_id", "UNKNOWN_RULE")))
    source_rule_id = str(row.get("source_rule_id", rule_id))
    required_features = parse_required_features(row.get("required_features", ""))
    conditions = parse_condition_text(row.get("condition_text", ""))

    if dataset.empty:
        metrics = {
            "observer_design_rule_id": rule_id,
            "source_rule_id": source_rule_id,
            "preflight_status": "BLOCKED_NO_DATASET",
            "raw_signal_rows": 0,
            "spaced_signal_rows": 0,
            "expected_raw_all_events": row.get("raw_all_events", ""),
            "raw_event_count_delta_pct": "",
            "missing_required_features": ";".join(required_features),
            "condition_parse_count": len(conditions),
            "event_spacing_hours": row.get("event_spacing_hours", ""),
            "candidate_only": row.get("candidate_only", ""),
        }
        return pd.DataFrame(), metrics, feature_coverage(dataset, required_features)

    mask = pd.Series([True] * len(dataset), index=dataset.index)
    for cond in conditions:
        mask = mask & cond.evaluate(dataset)

    raw = dataset.loc[mask].copy()
    spacing_hours = pd.to_numeric(pd.Series([row.get("event_spacing_hours", 120)]), errors="coerce").iloc[0]
    if pd.isna(spacing_hours):
        spacing_hours = 120.0
    spaced = apply_event_spacing(raw, float(spacing_hours))

    missing = [f for f in required_features if f not in dataset.columns]
    coverage_rows = feature_coverage(dataset, required_features)

    expected_raw = pd.to_numeric(pd.Series([row.get("raw_all_events", None)]), errors="coerce").iloc[0]
    if pd.notna(expected_raw) and float(expected_raw) != 0:
        delta_pct = (len(raw) - float(expected_raw)) / float(expected_raw) * 100.0
    else:
        delta_pct = math.nan

    preflight_status = "PASS_DRY_RUN_PREFLIGHT"
    if missing:
        preflight_status = "BLOCKED_MISSING_FEATURES"
    elif not conditions:
        preflight_status = "BLOCKED_CONDITIONS_NOT_PARSED"
    elif len(raw) == 0:
        preflight_status = "WATCH_ZERO_RAW_SIGNALS"
    elif pd.notna(delta_pct) and abs(delta_pct) > 25.0:
        preflight_status = "WATCH_EVENT_COUNT_DEVIATION_GT_25PCT"

    metrics = {
        "observer_design_rule_id": rule_id,
        "source_rule_id": source_rule_id,
        "preflight_status": preflight_status,
        "raw_signal_rows": int(len(raw)),
        "spaced_signal_rows": int(len(spaced)),
        "expected_raw_all_events": float(expected_raw) if pd.notna(expected_raw) else "",
        "raw_event_count_delta_pct": round(float(delta_pct), 4) if pd.notna(delta_pct) else "",
        "missing_required_features": ";".join(missing),
        "condition_parse_count": len(conditions),
        "event_spacing_hours": float(spacing_hours),
        "candidate_only": row.get("candidate_only", ""),
        "stage116_dxy_fallback_active": row.get("stage116_dxy_fallback_active", ""),
        "stage116_direct_dxy_valid": row.get("stage116_direct_dxy_valid", ""),
        "stage116_spdr_status": row.get("stage116_spdr_status", ""),
        "readiness_score": row.get("readiness_score", ""),
        "bucket": row.get("bucket", ""),
    }

    event_cols = [
        "_stage121_timestamp",
        "stage121_split",
        "utc_time",
        "time_utc",
        "timestamp",
        "date",
        "close",
        "forward_return_bps",
        "h120_forward_return_bps",
    ]
    feature_cols = [f for f in required_features if f in spaced.columns]
    keep_cols = []
    for c in event_cols + feature_cols:
        if c in spaced.columns and c not in keep_cols:
            keep_cols.append(c)
    events = spaced[keep_cols].copy() if keep_cols else spaced.head(0).copy()
    events.insert(0, "source_rule_id", source_rule_id)
    events.insert(0, "observer_design_rule_id", rule_id)
    if "_stage121_timestamp" in events.columns:
        events["_stage121_timestamp"] = events["_stage121_timestamp"].astype(str)
    return events, metrics, coverage_rows


def build_governance_rows(summary_status: str, metrics_rows: List[dict]) -> List[dict]:
    any_blocked = any(str(r.get("preflight_status", "")).startswith("BLOCKED") for r in metrics_rows)
    any_pass = any(r.get("preflight_status") == "PASS_DRY_RUN_PREFLIGHT" for r in metrics_rows)
    return [
        {"gate": "no_order_surface", "status": "PASS", "detail": "Stage121 is reports-only and does not touch broker/order surfaces."},
        {"gate": "no_mt5_write", "status": "PASS", "detail": "Stage121 does not write MT5/MQL5/Files or bridge files."},
        {"gate": "no_observer_update", "status": "PASS", "detail": "Stage121 does not modify active observer configuration."},
        {"gate": "feature_contract_checked", "status": "FAIL" if any_blocked else "PASS", "detail": "Required feature presence and condition parsing checked."},
        {"gate": "dry_run_signals_generated", "status": "PASS" if any_pass else "WATCH", "detail": "Dry-run signal events are report artifacts only."},
        {"gate": "next_stage_allowed", "status": "PASS" if summary_status == STATUS_OK else "BLOCKED", "detail": "Stage122 design-to-shadow-pack review can be considered only if PASS and manually accepted."},
    ]


def run(root: Path) -> dict:
    stage120_dir = root / "reports/stage120_observer_design_review"
    stage117_dir = root / "reports/stage117_segmented_macro_cot_dollar_discovery"
    report_dir = root / "reports/stage121_dry_run_observer_preflight"
    ensure_dir(report_dir)

    queue = load_stage120_preflight_queue(stage120_dir)
    dataset, dataset_source = find_joined_or_split_dataset(root, stage117_dir)
    dataset, time_col = coerce_timestamp(dataset) if not dataset.empty else (dataset, None)

    metrics_rows: List[dict] = []
    all_events: List[pd.DataFrame] = []
    coverage_out: List[dict] = []

    if queue.empty:
        status = STATUS_BLOCKED
        decision = DECISION_BLOCKED
    else:
        for _, row in queue.iterrows():
            events, metrics, cov = evaluate_rule(row, dataset)
            metrics_rows.append(metrics)
            if not events.empty:
                all_events.append(events)
            rid = metrics.get("observer_design_rule_id", "")
            for cr in cov:
                cr["observer_design_rule_id"] = rid
                coverage_out.append(cr)

        blocked = any(str(r.get("preflight_status", "")).startswith("BLOCKED") for r in metrics_rows)
        status = STATUS_BLOCKED if blocked else STATUS_OK
        decision = DECISION_BLOCKED if blocked else DECISION_OK

    events_df = pd.concat(all_events, ignore_index=True, sort=False) if all_events else pd.DataFrame()
    signal_events_path = report_dir / "stage121_dry_run_signal_events.csv"
    metrics_path = report_dir / "stage121_preflight_metrics.csv"
    coverage_path = report_dir / "stage121_feature_availability.csv"
    governance_path = report_dir / "stage121_governance_gate.csv"
    no_write_path = report_dir / "stage121_no_write_manifest.csv"
    selected_path = report_dir / "stage121_selected_for_stage122.csv"
    rejected_path = report_dir / "stage121_rejected_or_watch.csv"
    summary_path = report_dir / "stage121_dry_run_observer_preflight_summary.json"
    report_md_path = report_dir / "stage121_dry_run_observer_preflight_report.md"

    events_df.to_csv(signal_events_path, index=False)
    write_csv(metrics_path, metrics_rows)
    write_csv(coverage_path, coverage_out)
    governance_rows = build_governance_rows(status, metrics_rows)
    write_csv(governance_path, governance_rows)

    no_write_rows = [
        {"surface": "MT5/MQL5/Files", "write_status": "NO_WRITE", "path_or_scope": "all"},
        {"surface": "EA", "write_status": "NO_CHANGE", "path_or_scope": "all"},
        {"surface": "active_observer", "write_status": "NO_CHANGE", "path_or_scope": "all"},
        {"surface": "broker_order", "write_status": "NO_TOUCH", "path_or_scope": "all"},
        {"surface": "paper_live", "write_status": "NO_TOUCH", "path_or_scope": "all"},
    ]
    write_csv(no_write_path, no_write_rows)

    pass_rows = [r for r in metrics_rows if r.get("preflight_status") == "PASS_DRY_RUN_PREFLIGHT"]
    watch_rows = [r for r in metrics_rows if r.get("preflight_status") != "PASS_DRY_RUN_PREFLIGHT"]
    write_csv(selected_path, pass_rows)
    write_csv(rejected_path, watch_rows)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": "DRY_RUN_OBSERVER_PREFLIGHT_ONLY_NO_UPDATE",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage120_dir": str(stage120_dir),
        "stage117_dir": str(stage117_dir),
        "dataset_source": dataset_source,
        "dataset_rows": int(len(dataset)),
        "dataset_time_column": time_col,
        "queue_rows_seen": int(len(queue)),
        "preflight_rule_count": int(len(metrics_rows)),
        "pass_preflight_count": int(len(pass_rows)),
        "watch_or_block_count": int(len(watch_rows)),
        "dry_run_signal_event_rows": int(len(events_df)),
        "signal_events": str(signal_events_path),
        "preflight_metrics": str(metrics_path),
        "feature_availability": str(coverage_path),
        "governance_gate": str(governance_path),
        "no_write_manifest": str(no_write_path),
        "selected_for_stage122": str(selected_path),
        "rejected_or_watch": str(rejected_path),
        "summary_json": str(summary_path),
        "report_md": str(report_md_path),
        "next": [
            "If pass_preflight_count > 0, review Stage121 selected_for_stage122 manually.",
            "Stage122 may prepare a shadow-observer package only after manual approval; no active observer update yet.",
            "If any rule is watch/block, fix feature availability or rule contract before active observer consideration.",
        ],
    }
    write_json(summary_path, summary)

    md = f"""# {STAGE}

Generated UTC: {summary['generated_utc']}

Status: `{status}`

Decision: `{decision}`

## Interpretation

Stage121 performs a dry-run observer preflight from Stage120 design artifacts. It writes reports only and does not update active observer files, MT5, EA, broker, paper-live, or live surfaces.

## Inputs

- Stage120 directory: `{stage120_dir}`
- Stage117 data source: `{dataset_source}`
- Dataset rows: `{len(dataset)}`
- Queue rows: `{len(queue)}`

## Results

- Preflight rules: `{len(metrics_rows)}`
- Passed preflight: `{len(pass_rows)}`
- Watch/block: `{len(watch_rows)}`
- Dry-run signal event rows: `{len(events_df)}`

## Outputs

- `{signal_events_path}`
- `{metrics_path}`
- `{coverage_path}`
- `{governance_path}`
- `{no_write_path}`
- `{selected_path}`
- `{rejected_path}`

## Hard blocks

{chr(10).join([f"- `{x}`" for x in HARD_BLOCKS])}

## Next

Use Stage121 outputs to decide whether Stage122 should prepare a shadow-observer package. Stage122 must remain non-active unless manually approved later.
"""
    report_md_path.write_text(md, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage121 dry-run observer preflight.")
    parser.add_argument("--root", default=".", help="Repository root.")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    summary = run(root)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == STATUS_OK else 2


if __name__ == "__main__":
    raise SystemExit(main())
