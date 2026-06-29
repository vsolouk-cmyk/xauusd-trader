#!/usr/bin/env python3
"""
Stage123 static replay for the shadow observer package.

Reports-only stage:
- Does not update active observer files.
- Does not write observer bridge files.
- Does not write MT5/MQL5/Files.
- Does not touch EA, broker, paper/live/order surfaces.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


STAGE = "Stage123_STATIC_REPLAY_SHADOW_OBSERVER_PACKAGE"
STATUS_OK = "STAGE123_COMPLETE_STATIC_REPLAY_READY_NO_UPDATE"
STATUS_BLOCKED = "STAGE123_BLOCKED_STATIC_REPLAY_INPUTS_MISSING_NO_UPDATE"
DECISION_OK = "STAGE123_STAGE124_SHADOW_TELEMETRY_QUEUE_READY_NO_UPDATE"
DECISION_BLOCKED = "STAGE123_STATIC_REPLAY_BLOCKED_NO_OBSERVER_UPDATE"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE123",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE123",
    "NO_OBSERVER_BRIDGE_WRITE",
    "NO_MT5_MQL5_FILES_WRITE",
    "NO_ACTIVE_OBSERVER_FILE_WRITE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

BLOCKED_OUTPUT_TOKENS = [
    "active_observer",
    "observer_bridge",
    "MQL5/Files",
    "paper_order",
    "live_order",
]

TIME_COL_CANDIDATES = [
    "_stage121_timestamp",
    "utc_time",
    "time_utc",
    "timestamp",
    "datetime",
    "date_time",
    "bar_time",
    "time",
    "date",
]

RETURN_COL_CANDIDATES = [
    "fwd_ret_bps_h120",
    "forward_return_bps",
    "h120_forward_return_bps",
    "fwd_return_bps_h120",
    "ret_bps_h120",
]

SPLIT_COL_CANDIDATES = [
    "stage117_split",
    "stage121_split",
    "split",
    "sample_split",
    "segment",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Optional[List[str]] = None) -> None:
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
        writer = csv.DictWriter(f, fieldnames=fieldnames or ["empty"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def boolish(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass"}


def falseish(value: object) -> bool:
    return str(value).strip().lower() in {"0", "false", "no", "n", ""}


def first_existing_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    lowered = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lowered:
            return lowered[c.lower()]
    return None


def detect_split_col(df: pd.DataFrame) -> Optional[str]:
    direct = first_existing_col(df, SPLIT_COL_CANDIDATES)
    if direct:
        return direct
    for c in df.columns:
        lc = c.lower()
        if "split" in lc or "segment" in lc:
            return c
    return None


def coerce_event_time(df: pd.DataFrame) -> Tuple[pd.DataFrame, Optional[str]]:
    out = df.copy()
    time_col = first_existing_col(out, TIME_COL_CANDIDATES)
    if not time_col:
        return out, None
    out["_stage123_timestamp"] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    return out, time_col


def numeric_series(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
    if not col or col not in df.columns:
        return pd.Series([math.nan] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def safe_float(value: object, default: float = math.nan) -> float:
    try:
        v = float(value)
        return v
    except Exception:
        return default


def load_stage123_queue(stage122_dir: Path) -> pd.DataFrame:
    path = stage122_dir / "stage122_stage123_static_replay_queue.csv"
    q = read_csv_if_exists(path)
    if q.empty:
        return q
    if "stage122_decision" in q.columns:
        q = q[q["stage122_decision"].astype(str).str.contains("STAGE123_STATIC_REPLAY_QUEUE", na=False)].copy()
    if "stage123_task" in q.columns:
        q = q[q["stage123_task"].astype(str).str.contains("STATIC_REPLAY", na=False)].copy()
    return q


def validate_queue_row(row: pd.Series) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    allowed_scope = str(row.get("allowed_output_scope", "reports_only"))
    blocked_outputs = str(row.get("blocked_outputs", ""))
    if allowed_scope != "reports_only":
        reasons.append(f"allowed_output_scope_not_reports_only:{allowed_scope}")
    if not falseish(row.get("active_update_allowed", "False")):
        reasons.append("active_update_allowed_not_false")
    if not boolish(row.get("report_only_shadow_package", "True")):
        reasons.append("report_only_shadow_package_not_true")
    for token in BLOCKED_OUTPUT_TOKENS:
        if token not in blocked_outputs:
            reasons.append(f"blocked_output_token_missing:{token}")
    return (len(reasons) == 0, reasons)


def filter_events_for_row(events: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    out = events.copy()
    source_rule_id = str(row.get("source_rule_id", ""))
    observer_rule_id = str(row.get("observer_design_rule_id", ""))
    shadow_rule_id = str(row.get("shadow_observer_rule_id", ""))

    masks = []
    if "source_rule_id" in out.columns and source_rule_id:
        masks.append(out["source_rule_id"].astype(str) == source_rule_id)
    if "observer_design_rule_id" in out.columns and observer_rule_id:
        masks.append(out["observer_design_rule_id"].astype(str) == observer_rule_id)
    if "shadow_observer_rule_id" in out.columns and shadow_rule_id:
        masks.append(out["shadow_observer_rule_id"].astype(str) == shadow_rule_id)
    if masks:
        mask = masks[0]
        for m in masks[1:]:
            mask = mask | m
        out = out[mask].copy()
    return out


def spacing_stats(events: pd.DataFrame, min_spacing_hours: float) -> Tuple[float, bool]:
    if "_stage123_timestamp" not in events.columns or len(events) < 2:
        return math.nan, True
    ts = events["_stage123_timestamp"].dropna().sort_values()
    if len(ts) < 2:
        return math.nan, True
    diffs = ts.diff().dropna().dt.total_seconds() / 3600.0
    min_gap = float(diffs.min()) if not diffs.empty else math.nan
    return min_gap, bool(math.isnan(min_gap) or min_gap + 1e-9 >= min_spacing_hours)


def year_distribution(events: pd.DataFrame, rule_id: str) -> List[dict]:
    if "_stage123_timestamp" not in events.columns or events.empty:
        return []
    years = events["_stage123_timestamp"].dropna().dt.year
    counts = years.value_counts().sort_index()
    total = int(counts.sum()) if not counts.empty else 0
    return [
        {
            "shadow_observer_rule_id": rule_id,
            "year": int(year),
            "event_count": int(count),
            "event_share": round(float(count) / total, 6) if total else 0.0,
        }
        for year, count in counts.items()
    ]


def month_distribution(events: pd.DataFrame, rule_id: str) -> List[dict]:
    if "_stage123_timestamp" not in events.columns or events.empty:
        return []
    months = events["_stage123_timestamp"].dropna().dt.strftime("%Y-%m")
    counts = months.value_counts().sort_index()
    return [
        {"shadow_observer_rule_id": rule_id, "month": str(month), "event_count": int(count)}
        for month, count in counts.items()
    ]


def max_year_concentration(events: pd.DataFrame) -> float:
    if "_stage123_timestamp" not in events.columns or events.empty:
        return math.nan
    years = events["_stage123_timestamp"].dropna().dt.year
    if years.empty:
        return math.nan
    vc = years.value_counts()
    return float(vc.max()) / float(vc.sum()) if vc.sum() else math.nan


def metric_row(events: pd.DataFrame, label: str, return_col: Optional[str]) -> dict:
    ret = numeric_series(events, return_col).dropna()
    row = {
        "split_or_segment": label,
        "event_count": int(len(events)),
        "return_col": return_col or "",
        "return_count": int(len(ret)),
        "mean_bps": round(float(ret.mean()), 6) if not ret.empty else "",
        "median_bps": round(float(ret.median()), 6) if not ret.empty else "",
        "hit_rate": round(float((ret > 0).mean()), 6) if not ret.empty else "",
        "cost10_mean_bps": round(float((ret - 10.0).mean()), 6) if not ret.empty else "",
        "cost10_hit_rate": round(float(((ret - 10.0) > 0).mean()), 6) if not ret.empty else "",
        "min_bps": round(float(ret.min()), 6) if not ret.empty else "",
        "max_bps": round(float(ret.max()), 6) if not ret.empty else "",
    }
    return row


def replay_one(row: pd.Series, events_all: pd.DataFrame) -> Tuple[List[dict], List[dict], List[dict], List[dict], dict, pd.DataFrame]:
    shadow_rule_id = str(row.get("shadow_observer_rule_id", row.get("observer_design_rule_id", "UNKNOWN_SHADOW_RULE")))
    source_rule_id = str(row.get("source_rule_id", ""))
    observer_design_rule_id = str(row.get("observer_design_rule_id", ""))
    valid_contract, contract_reasons = validate_queue_row(row)
    min_spacing = safe_float(row.get("min_spacing_hours", row.get("event_spacing_hours", 120)), 120.0)

    events = filter_events_for_row(events_all, row)
    events, time_col = coerce_event_time(events) if not events.empty else (events, None)
    if "_stage123_timestamp" in events.columns:
        events = events.sort_values("_stage123_timestamp").copy()

    return_col = first_existing_col(events, RETURN_COL_CANDIDATES) if not events.empty else None
    split_col = detect_split_col(events) if not events.empty else None
    min_gap, spacing_pass = spacing_stats(events, min_spacing)
    max_year_share = max_year_concentration(events)

    status = "PASS_STATIC_REPLAY"
    reasons: List[str] = []
    if not valid_contract:
        status = "BLOCKED_SHADOW_CONTRACT"
        reasons.extend(contract_reasons)
    elif events.empty:
        status = "BLOCKED_NO_DRY_RUN_EVENTS"
        reasons.append("no_matching_stage121_dry_run_signal_events")
    elif not spacing_pass:
        status = "BLOCKED_EVENT_SPACING_LT_MIN"
        reasons.append(f"min_gap_hours={min_gap};required={min_spacing}")
    elif not time_col:
        status = "WATCH_TIME_COLUMN_NOT_DETECTED"
        reasons.append("time_column_not_detected")
    elif not return_col:
        status = "WATCH_RETURN_COLUMN_NOT_DETECTED"
        reasons.append("forward_return_column_not_detected")
    elif not math.isnan(max_year_share) and max_year_share > 0.60:
        status = "WATCH_YEAR_CONCENTRATION_GT_60PCT"
        reasons.append(f"max_year_concentration={max_year_share:.4f}")

    base = {
        "shadow_observer_rule_id": shadow_rule_id,
        "observer_design_rule_id": observer_design_rule_id,
        "source_rule_id": source_rule_id,
        "static_replay_status": status,
        "status_reasons": ";".join(reasons),
        "bucket": row.get("bucket", ""),
        "readiness_score": row.get("readiness_score", ""),
        "candidate_only": row.get("candidate_only", ""),
        "stage116_spdr_status": row.get("stage116_spdr_status", ""),
        "stage116_dxy_fallback_active": row.get("stage116_dxy_fallback_active", ""),
        "active_update_allowed": row.get("active_update_allowed", ""),
        "allowed_output_scope": row.get("allowed_output_scope", ""),
        "min_spacing_hours_required": min_spacing,
        "time_column": time_col or "",
        "return_column": return_col or "",
        "split_column": split_col or "",
        "matching_event_rows": int(len(events)),
        "min_observed_spacing_hours": round(float(min_gap), 6) if not math.isnan(min_gap) else "",
        "event_spacing_pass": spacing_pass,
        "max_year_concentration": round(float(max_year_share), 6) if not math.isnan(max_year_share) else "",
    }

    metrics: List[dict] = []
    if events.empty:
        metrics.append({**base, **metric_row(events, "ALL", return_col)})
    else:
        metrics.append({**base, **metric_row(events, "ALL", return_col)})
        if split_col and split_col in events.columns:
            for split_value, g in events.groupby(split_col, dropna=False):
                metrics.append({**base, **metric_row(g, str(split_value), return_col)})

    ydist = year_distribution(events, shadow_rule_id)
    mdist = month_distribution(events, shadow_rule_id)

    snapshot = events.tail(10).copy()
    if not snapshot.empty:
        snapshot.insert(0, "shadow_observer_rule_id", shadow_rule_id)
        if "_stage123_timestamp" in snapshot.columns:
            snapshot["_stage123_timestamp"] = snapshot["_stage123_timestamp"].astype(str)
    return metrics, ydist, mdist, [base], base, snapshot


def build_governance_rows(status: str, metrics_rows: List[dict]) -> List[dict]:
    any_pass = any(r.get("static_replay_status") == "PASS_STATIC_REPLAY" for r in metrics_rows)
    any_block = any(str(r.get("static_replay_status", "")).startswith("BLOCKED") for r in metrics_rows)
    all_report_only = all(str(r.get("allowed_output_scope", "")) == "reports_only" for r in metrics_rows) if metrics_rows else False
    all_active_false = all(falseish(r.get("active_update_allowed", "False")) for r in metrics_rows) if metrics_rows else False
    return [
        {"gate": "reports_only_scope", "status": "PASS" if all_report_only else "FAIL", "detail": "Stage123 outputs are restricted to reports."},
        {"gate": "active_update_blocked", "status": "PASS" if all_active_false else "FAIL", "detail": "No active observer update is permitted."},
        {"gate": "no_mt5_mql5_write", "status": "PASS", "detail": "Stage123 does not write MT5/MQL5/Files or bridge files."},
        {"gate": "static_replay_executed", "status": "PASS" if any_pass else "WATCH", "detail": "At least one shadow package replay passed."},
        {"gate": "blocked_status_absent", "status": "FAIL" if any_block else "PASS", "detail": "Blocked replays must not move forward."},
        {"gate": "next_stage_allowed", "status": "PASS" if status == STATUS_OK and any_pass else "BLOCKED", "detail": "Stage124 may only be a report-only shadow telemetry review."},
    ]


def build_no_write_manifest(report_dir: Path) -> List[dict]:
    return [
        {"surface": "active_observer", "path": "app/configs/active observer outputs", "write_allowed": False, "stage123_action": "NO_WRITE"},
        {"surface": "observer_bridge", "path": "bridge/observer outputs", "write_allowed": False, "stage123_action": "NO_WRITE"},
        {"surface": "MT5_MQL5_Files", "path": "MQL5/Files", "write_allowed": False, "stage123_action": "NO_WRITE"},
        {"surface": "EA", "path": "MQL5/Experts or EA source", "write_allowed": False, "stage123_action": "NO_WRITE"},
        {"surface": "paper_live_or_live_order", "path": "broker/order surfaces", "write_allowed": False, "stage123_action": "NO_WRITE"},
        {"surface": "stage123_reports", "path": str(report_dir), "write_allowed": True, "stage123_action": "REPORTS_ONLY"},
    ]


def run(root: Path) -> dict:
    stage122_dir = root / "reports/stage122_shadow_observer_package_review"
    stage121_dir = root / "reports/stage121_dry_run_observer_preflight"
    report_dir = root / "reports/stage123_static_replay_shadow_observer_package"
    ensure_dir(report_dir)

    queue = load_stage123_queue(stage122_dir)
    events_all = read_csv_if_exists(stage121_dir / "stage121_dry_run_signal_events.csv")
    stage122_summary = read_json_if_exists(stage122_dir / "stage122_shadow_observer_package_review_summary.json")
    stage121_summary = read_json_if_exists(stage121_dir / "stage121_dry_run_observer_preflight_summary.json")

    metrics_rows: List[dict] = []
    year_rows: List[dict] = []
    month_rows: List[dict] = []
    status_rows: List[dict] = []
    snapshots: List[pd.DataFrame] = []

    for _, row in queue.iterrows():
        metrics, ydist, mdist, status_base_rows, _base, snapshot = replay_one(row, events_all)
        metrics_rows.extend(metrics)
        year_rows.extend(ydist)
        month_rows.extend(mdist)
        status_rows.extend(status_base_rows)
        if not snapshot.empty:
            snapshots.append(snapshot)

    pass_rows = [r for r in status_rows if r.get("static_replay_status") == "PASS_STATIC_REPLAY"]
    block_rows = [r for r in status_rows if str(r.get("static_replay_status", "")).startswith("BLOCKED")]
    watch_rows = [r for r in status_rows if str(r.get("static_replay_status", "")).startswith("WATCH")]

    status = STATUS_OK if pass_rows and not block_rows else STATUS_BLOCKED
    decision = DECISION_OK if status == STATUS_OK else DECISION_BLOCKED

    replay_events_path = report_dir / "stage123_static_replay_events.csv"
    replay_metrics_path = report_dir / "stage123_static_replay_metrics.csv"
    year_distribution_path = report_dir / "stage123_year_distribution.csv"
    month_distribution_path = report_dir / "stage123_month_distribution.csv"
    latest_snapshot_path = report_dir / "stage123_latest_signal_snapshot.csv"
    governance_path = report_dir / "stage123_governance_gate.csv"
    no_write_path = report_dir / "stage123_no_write_manifest.csv"
    selected_path = report_dir / "stage123_selected_for_stage124.csv"
    watch_or_block_path = report_dir / "stage123_watch_or_block.csv"
    summary_path = report_dir / "stage123_static_replay_shadow_observer_package_summary.json"
    report_md_path = report_dir / "stage123_static_replay_shadow_observer_package_report.md"

    events_copy = events_all.copy()
    if not events_copy.empty:
        events_copy, _ = coerce_event_time(events_copy)
        if "_stage123_timestamp" in events_copy.columns:
            events_copy["_stage123_timestamp"] = events_copy["_stage123_timestamp"].astype(str)
    events_copy.to_csv(replay_events_path, index=False)
    write_csv(replay_metrics_path, metrics_rows)
    write_csv(year_distribution_path, year_rows)
    write_csv(month_distribution_path, month_rows)
    snapshot_df = pd.concat(snapshots, ignore_index=True, sort=False) if snapshots else pd.DataFrame()
    snapshot_df.to_csv(latest_snapshot_path, index=False)
    governance_rows = build_governance_rows(status, metrics_rows)
    write_csv(governance_path, governance_rows)
    write_csv(no_write_path, build_no_write_manifest(report_dir))

    selected_rows = []
    for r in pass_rows:
        selected_rows.append({
            **r,
            "stage124_task": "SHADOW_TELEMETRY_PACKAGE_REVIEW_ONLY",
            "stage124_allowed_output_scope": "reports_only",
            "activation_allowed_from_stage123": False,
        })
    write_csv(selected_path, selected_rows)
    write_csv(watch_or_block_path, watch_rows + block_rows)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": "STATIC_REPLAY_SHADOW_OBSERVER_PACKAGE_ONLY_NO_UPDATE",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage122_dir": str(stage122_dir),
        "stage121_dir": str(stage121_dir),
        "stage122_status": stage122_summary.get("status", ""),
        "stage122_decision": stage122_summary.get("decision", ""),
        "stage122_candidate_count": stage122_summary.get("stage123_static_replay_candidate_count", ""),
        "stage121_status": stage121_summary.get("status", ""),
        "stage121_dry_run_signal_event_rows": stage121_summary.get("dry_run_signal_event_rows", ""),
        "queue_rows_seen": int(len(queue)),
        "stage121_signal_rows_seen": int(len(events_all)),
        "static_replay_rule_count": int(len(status_rows)),
        "pass_static_replay_count": int(len(pass_rows)),
        "watch_static_replay_count": int(len(watch_rows)),
        "blocked_static_replay_count": int(len(block_rows)),
        "stage124_shadow_telemetry_candidate_count": int(len(selected_rows)),
        "replay_events": str(replay_events_path),
        "replay_metrics": str(replay_metrics_path),
        "year_distribution": str(year_distribution_path),
        "month_distribution": str(month_distribution_path),
        "latest_signal_snapshot": str(latest_snapshot_path),
        "governance_gate": str(governance_path),
        "no_write_manifest": str(no_write_path),
        "selected_for_stage124": str(selected_path),
        "watch_or_block": str(watch_or_block_path),
        "summary_json": str(summary_path),
        "report_md": str(report_md_path),
        "next": [
            "If stage124_shadow_telemetry_candidate_count > 0, create Stage124 report-only shadow telemetry package review.",
            "Do not update active observer, observer bridge, MT5, EA, paper-order, or live-order files from Stage123.",
            "Candidate-only SPDR-based rules remain shadow-only until telemetry and governance checks pass.",
        ],
    }
    write_json(summary_path, summary)

    report_md = f"""# {STAGE}

Generated UTC: {summary['generated_utc']}

Status: `{status}`

Decision: `{decision}`

## Interpretation

Stage123 performs a static replay of the Stage122 shadow-observer package using Stage121 dry-run signal events. It remains report-only and does not update active observer, observer bridge, MT5, EA, paper-order, or live-order surfaces.

## Key counts

- Queue rows seen: `{summary['queue_rows_seen']}`
- Stage121 signal rows seen: `{summary['stage121_signal_rows_seen']}`
- Pass static replay count: `{summary['pass_static_replay_count']}`
- Watch count: `{summary['watch_static_replay_count']}`
- Blocked count: `{summary['blocked_static_replay_count']}`
- Stage124 shadow telemetry candidate count: `{summary['stage124_shadow_telemetry_candidate_count']}`

## Governance

All outputs are confined to:

```text
{report_dir}
```

No active observer, observer bridge, MQL5/Files, EA, paper/live/order file is written.
"""
    report_md_path.write_text(report_md, encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage123 static replay shadow-observer package review")
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()
    summary = run(Path(args.root).expanduser().resolve())
    print(f"{summary['stage']} | status={summary['status']} | decision={summary['decision']} | pass={summary['pass_static_replay_count']} | selected_stage124={summary['stage124_shadow_telemetry_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
