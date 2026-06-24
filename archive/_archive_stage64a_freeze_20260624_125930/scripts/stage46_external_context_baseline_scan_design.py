#!/usr/bin/env python3
"""Stage46 external-context baseline scan design.

This stage is a DESIGN/PRECHECK stage only. It reads the validated external-context
state from Stage45B3 and the local XAUUSD bars inventory, then writes a predefined
external-context baseline design contract for the next implementation stage.

It does not generate trading signals, does not scan candidates, and cannot promote
any archived Stage41/42/43 row.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


STAGE = "Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN"
READY_STAGE45B3_STATUS = "EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_READY_NO_PROMOTION"
READY_STAGE45B3_NEXT = "Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN"

P0_KEYS = ["dxy", "us10y_yield", "cme_gc_reference", "news_calendar"]

GATES = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

NOT_ALLOWED = [
    "candidate_rescue_from_stage41_42_43",
    "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
    "EA_paper_live_live_from_archived_rows",
    "ML_before_robust_cost_aware_baseline",
    "running_external_context_scan_before_stage46_design_contract_is_committed",
]


@dataclass
class FileProfile:
    key: str
    path: str
    exists: bool
    schema_ok: bool
    row_count: int = 0
    start: Optional[str] = None
    end: Optional[str] = None
    columns: Optional[List[str]] = None
    error: Optional[str] = None


@dataclass
class DesignRow:
    family_id: str
    design_role: str
    direction_scope: str
    required_inputs: str
    optional_inputs: str
    alignment_rule: str
    candidate_features: str
    parameter_grid: str
    mandatory_guards: str
    evaluation_contract: str
    implementation_status: str
    notes: str


def _read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        if not path.exists():
            return None, "missing"
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, repr(exc)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def profile_csv(repo_root: Path, rel_path: str, required_sets: Sequence[Sequence[str]]) -> FileProfile:
    path = repo_root / rel_path
    if not path.exists():
        return FileProfile(key=rel_path, path=rel_path, exists=False, schema_ok=False, error="missing")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return FileProfile(key=rel_path, path=rel_path, exists=True, schema_ok=False, error=repr(exc))

    cols = list(df.columns)
    lower_cols = {str(c).strip().lower(): c for c in cols}
    schema_ok = False
    for req in required_sets:
        if all(r.lower() in lower_cols for r in req):
            schema_ok = True
            break

    ts_col = None
    for c in ["timestamp", "date", "datetime", "time", "utc_time"]:
        if c in lower_cols:
            ts_col = lower_cols[c]
            break

    start = end = None
    if ts_col is not None:
        ts = _norm_ts(df[ts_col]).dropna()
        if len(ts):
            start = ts.min().isoformat()
            end = ts.max().isoformat()

    return FileProfile(
        key=rel_path,
        path=rel_path,
        exists=True,
        schema_ok=bool(schema_ok),
        row_count=int(len(df)),
        start=start,
        end=end,
        columns=cols,
        error=None,
    )


def load_bar_profile(repo_root: Path, db_path: str, table: str, source: str, symbol: str, timeframe: str) -> Dict[str, Any]:
    full = repo_root / db_path
    meta: Dict[str, Any] = {
        "db_path": str(full),
        "table": table,
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
        "exists": full.exists(),
        "loaded_rows": 0,
        "loaded_start": None,
        "loaded_end": None,
        "daily_count": 0,
        "error": None,
    }
    if not full.exists():
        meta["error"] = "db_missing"
        return meta
    try:
        con = sqlite3.connect(full)
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        meta["columns"] = cols
        if not cols:
            meta["error"] = "table_missing_or_no_columns"
            return meta
        ts_col = "utc_time" if "utc_time" in cols else None
        if ts_col is None:
            meta["error"] = "utc_time_column_missing"
            return meta
        where = []
        params: List[Any] = []
        for col, val in [("source", source), ("symbol", symbol), ("timeframe", timeframe)]:
            if col in cols and val:
                where.append(f"{col} = ?")
                params.append(val)
        sql = f"SELECT {ts_col} AS utc_time, open, high, low, close FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        df = pd.read_sql_query(sql, con, params=params)
        con.close()
        if df.empty:
            meta["error"] = "no_matching_rows"
            return meta
        df["utc_time"] = _norm_ts(df["utc_time"])
        df = df.dropna(subset=["utc_time"])
        meta["loaded_rows"] = int(len(df))
        meta["loaded_start"] = df["utc_time"].min().isoformat()
        meta["loaded_end"] = df["utc_time"].max().isoformat()
        meta["daily_count"] = int(df["utc_time"].dt.floor("D").nunique())
        return meta
    except Exception as exc:
        meta["error"] = repr(exc)
        return meta


def extract_stage45b3_readiness(stage45b3: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not stage45b3:
        return {
            "exists": False,
            "status": None,
            "next_allowed_step": None,
            "ready_for_stage46": False,
            "blockers": ["stage45b3_summary_missing_or_unreadable"],
        }
    status = stage45b3.get("decision", {}).get("status") or stage45b3.get("status")
    next_allowed = stage45b3.get("next_allowed_step") or stage45b3.get("decision", {}).get("recommended_next_stage")
    blockers = list(stage45b3.get("decision", {}).get("blockers", []))
    p0_value = None
    for row in stage45b3.get("precheck_matrix", []):
        if row.get("metric") == "required_external_context_schema_ready":
            p0_value = row.get("value")
            break
    ready = status == READY_STAGE45B3_STATUS and next_allowed == READY_STAGE45B3_NEXT and not blockers
    return {
        "exists": True,
        "status": status,
        "next_allowed_step": next_allowed,
        "ready_for_stage46": bool(ready),
        "blockers": blockers,
        "p0_schema_ready_keys_from_precheck": p0_value,
        "warnings": list(stage45b3.get("decision", {}).get("warnings", [])),
    }


def get_feature_contract(stage45b3: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if stage45b3 and isinstance(stage45b3.get("feature_contract"), list):
        return stage45b3["feature_contract"]
    return []


def design_rows() -> List[DesignRow]:
    evaluation = (
        "walk_forward_train_oos; min_events_guard; observed_costs; spread_bucket_guard; "
        "quarter_stability; bootstrap_stability; benchmark_residual_vs_simple_hold_or_drift; "
        "no_posthoc_bad_bucket_exclusion"
    )
    mandatory = (
        "NO_STAGE41_42_43_RESCUE; daily_context_lag1_only; "
        "news_blackout_predefined_windows_only; cme_reference_only_not_execution; "
        "cost_aware_evaluation; min_trade_count_by_segment"
    )
    return [
        DesignRow(
            family_id="EXTCTX_A_DXY_YIELD_TREND_FILTER",
            design_role="directional_context_filter",
            direction_scope="long_and_short_design_but_no_execution",
            required_inputs="data/external/dxy.csv;data/external/us10y_yield.csv;M15_XAUUSD_bars",
            optional_inputs="data/external/real_yield.csv",
            alignment_rule="daily_safe_lag_1d_forward_fill_only",
            candidate_features="dxy_ret_1d_lag1,dxy_slope_5d_lag1,us10y_delta_1d_lag1,us10y_slope_5d_lag1,real_yield_delta_1d_lag1_optional",
            parameter_grid="dxy_slope_5d_quantile={0.25,0.50,0.75}; yield_delta_1d_sign={falling,rising}; context_mode={confirm,avoid}; hold_bars={4,8,16}",
            mandatory_guards=mandatory,
            evaluation_contract=evaluation,
            implementation_status="DESIGNED_NOT_IMPLEMENTED",
            notes="Gold-supportive context is falling USD/yields; hostile context is rising USD/yields. No post-hoc filtering allowed.",
        ),
        DesignRow(
            family_id="EXTCTX_B_NEWS_BLACKOUT_GUARD",
            design_role="risk_filter_not_alpha_source",
            direction_scope="applies_to_all_future_baselines",
            required_inputs="data/external/news_blackout_windows.csv;M15_XAUUSD_bars",
            optional_inputs="data/external/news_calendar.csv",
            alignment_rule="utc_interval_overlap_predefined_windows_only",
            candidate_features="is_news_blackout,minutes_to_next_event,minutes_since_event,event_category",
            parameter_grid="blackout_mode={exclude,tag_only}; event_scope={scheduled_macro_only}; pre_post_windows=from_calendar_contract",
            mandatory_guards=mandatory,
            evaluation_contract=evaluation,
            implementation_status="DESIGNED_NOT_IMPLEMENTED",
            notes="Blackout is a guard/diagnostic layer. It must not become a post-hoc edge rescue filter.",
        ),
        DesignRow(
            family_id="EXTCTX_C_REFERENCE_FEED_SANITY",
            design_role="feed_sanity_and_marketwide_confirmation",
            direction_scope="confirmation_only",
            required_inputs="data/reference/cme_gc.csv;daily_MT5_XAUUSD_profile",
            optional_inputs="none",
            alignment_rule="daily_reference_overlap_only;source_must_remain_reference_only",
            candidate_features="gc_ret_1d_reference,mt5_vs_gc_return_sign_agreement,gc_close_diff_bps,gc_gap_reference",
            parameter_grid="confirm_mode={same_day_reference_sign,lagged_reference_sign}; disagreement_action={tag,exclude}; close_diff_bps_cap={p90,p95}",
            mandatory_guards=mandatory,
            evaluation_contract=evaluation,
            implementation_status="DESIGNED_NOT_IMPLEMENTED",
            notes="Yahoo GC=F is acceptable for reference-feed sanity only, not execution-grade settlement.",
        ),
        DesignRow(
            family_id="EXTCTX_D_COMPOSITE_CONTEXT_SCORE",
            design_role="predefined_composite_context_bucket",
            direction_scope="context_bucket_only_not_ml",
            required_inputs="dxy;us10y_yield;news_blackout_windows;cme_gc_reference",
            optional_inputs="real_yield",
            alignment_rule="all_features_lagged_or_interval_known_at_bar_open",
            candidate_features="macro_support_score,macro_hostile_score,reference_confirmation,news_blackout_flag",
            parameter_grid="score_components={dxy,yield,real_yield_optional,gc_reference}; threshold={-2,-1,0,1,2}; use_blackout={exclude,tag_only}",
            mandatory_guards=mandatory,
            evaluation_contract=evaluation,
            implementation_status="DESIGNED_NOT_IMPLEMENTED",
            notes="Composite score must be a transparent rule score, not ML. All weights fixed before test.",
        ),
    ]


def guardrail_rows() -> List[Dict[str, Any]]:
    return [
        {"guardrail": "no_archived_candidate_rescue", "rule": "Do not evaluate Stage41/42/43 rows with new filters", "severity": "hard"},
        {"guardrail": "daily_context_no_lookahead", "rule": "DXY/yields/real yield available only with lag1 daily forward-fill", "severity": "hard"},
        {"guardrail": "news_blackout_predefined", "rule": "Use pre-materialized UTC windows only; no optimizing event windows on outcomes", "severity": "hard"},
        {"guardrail": "reference_feed_not_execution", "rule": "GC=F/yfinance reference can tag market-wide agreement only; not settlement/execution", "severity": "hard"},
        {"guardrail": "cost_aware_first", "rule": "Observed spread/cost assumptions remain first-class in every implementation", "severity": "hard"},
        {"guardrail": "stability_before_promotion", "rule": "Quarter and bootstrap stability required before any promotion discussion", "severity": "hard"},
        {"guardrail": "no_ml", "rule": "No ML until robust cost-aware rule baselines survive", "severity": "hard"},
    ]


def readiness_rows(stage45b3_ready: Dict[str, Any], profiles: List[FileProfile], bar_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    rows.append({
        "area": "stage_chain",
        "check": "stage45b3_ready_for_stage46",
        "value": stage45b3_ready.get("ready_for_stage46"),
        "ok": bool(stage45b3_ready.get("ready_for_stage46")),
        "severity": "blocker",
        "note": f"status={stage45b3_ready.get('status')}; next={stage45b3_ready.get('next_allowed_step')}",
    })
    rows.append({
        "area": "bars",
        "check": "m15_xauusd_bars_loaded",
        "value": bar_meta.get("loaded_rows", 0),
        "ok": bool(bar_meta.get("loaded_rows", 0) > 1000 and not bar_meta.get("error")),
        "severity": "blocker",
        "note": f"start={bar_meta.get('loaded_start')}; end={bar_meta.get('loaded_end')}; error={bar_meta.get('error')}",
    })
    for p in profiles:
        rows.append({
            "area": "external_file",
            "check": p.path,
            "value": p.row_count,
            "ok": bool(p.exists and p.schema_ok and p.row_count > 0),
            "severity": "blocker" if p.path in ["data/external/dxy.csv", "data/external/us10y_yield.csv", "data/reference/cme_gc.csv", "data/external/news_calendar.csv", "data/external/news_blackout_windows.csv"] else "warning",
            "note": f"schema_ok={p.schema_ok}; start={p.start}; end={p.end}; error={p.error}",
        })
    return rows


def write_markdown(path: Path, summary: Dict[str, Any], design_df: pd.DataFrame, readiness_df: pd.DataFrame) -> None:
    lines: List[str] = []
    dec = summary["decision"]
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"promotion = {dec['promotion']}")
    lines.append(f"EA = {dec['EA']}")
    lines.append(f"paper_live = {dec['paper_live']}")
    lines.append(f"live = {dec['live']}")
    lines.append(f"status = {dec['status']}")
    lines.append(f"recommended_next_stage = {dec['recommended_next_stage']}")
    lines.append("```")
    lines.append("")
    lines.append("Stage46 is a design-contract stage only. It does not run a scan, create trading signals, shortlist candidates, or promote archived rows.")
    lines.append("")
    lines.append("## Readiness")
    lines.append("")
    lines.append(readiness_df.to_markdown(index=False))
    lines.append("")
    lines.append("## Designed baseline families")
    lines.append("")
    lines.append(design_df[["family_id", "design_role", "implementation_status", "notes"]].to_markdown(index=False))
    lines.append("")
    lines.append("## Required guardrails")
    lines.append("")
    for item in summary["guardrail_contract"]:
        lines.append(f"- `{item['guardrail']}`: {item['rule']} ({item['severity']})")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for item in dec["not_allowed"]:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("This design cannot be used to rescue Stage41/42/43 rows. The next step, if ready, is implementation of this predefined design in a fresh cost-aware baseline pass.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--db-path", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--table", default="bars")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--stage45b3-summary", default="reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json")
    ap.add_argument("--outdir", default="reports/stage46")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = (repo_root / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    stage45b3_path = repo_root / args.stage45b3_summary
    stage45b3, stage45b3_error = _read_json(stage45b3_path)
    stage45b3_ready = extract_stage45b3_readiness(stage45b3)
    if stage45b3_error:
        stage45b3_ready["error"] = stage45b3_error

    profiles = [
        profile_csv(repo_root, "data/external/dxy.csv", [["timestamp", "close"]]),
        profile_csv(repo_root, "data/external/us10y_yield.csv", [["timestamp", "yield"], ["timestamp", "close"]]),
        profile_csv(repo_root, "data/external/real_yield.csv", [["timestamp", "yield"], ["timestamp", "close"]]),
        profile_csv(repo_root, "data/reference/cme_gc.csv", [["timestamp", "open", "high", "low", "close"]]),
        profile_csv(repo_root, "data/external/news_calendar.csv", [["timestamp", "event"], ["timestamp", "name"]]),
        profile_csv(repo_root, "data/external/news_blackout_windows.csv", [["window_start", "window_end"], ["start", "end"], ["timestamp", "event"]]),
    ]

    bar_meta = load_bar_profile(repo_root, args.db_path, args.table, args.source, args.symbol, args.timeframe)
    readiness = readiness_rows(stage45b3_ready, profiles, bar_meta)
    readiness_df = pd.DataFrame(readiness)
    design = design_rows()
    design_df = pd.DataFrame([asdict(r) for r in design])
    guardrails = guardrail_rows()

    blockers: List[str] = []
    warnings: List[str] = []
    for row in readiness:
        if not row["ok"] and row["severity"] == "blocker":
            blockers.append(str(row["check"]))
        elif not row["ok"]:
            warnings.append(str(row["check"]))
    if stage45b3_ready.get("warnings"):
        warnings.extend([f"stage45b3_warning:{w}" for w in stage45b3_ready.get("warnings", [])])

    status = "EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN_READY_NO_PROMOTION" if not blockers else "EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN_BLOCKED_NO_PROMOTION"
    recommended_next_stage = "Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION" if not blockers else "Stage45B3_REPAIR_BEFORE_STAGE46"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "db_path": args.db_path,
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "stage45b3_summary": args.stage45b3_summary,
            "outdir": args.outdir,
        },
        "stage45b3_reference": stage45b3_ready,
        "bar_load_meta": bar_meta,
        "external_file_profiles": [asdict(p) for p in profiles],
        "readiness_matrix": readiness,
        "feature_contract_from_stage45b3": get_feature_contract(stage45b3),
        "baseline_design_matrix": [asdict(r) for r in design],
        "guardrail_contract": guardrails,
        "decision": {
            "status": status,
            **GATES,
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": recommended_next_stage,
            "rationale": [
                "Stage46 converts the external-context readiness into a predefined baseline design contract.",
                "This stage does not create signals, scan candidates, rescue archived rows, or authorize EA/paper/live.",
                "If ready, the next step is implementing this exact design in a fresh cost-aware baseline pass.",
            ],
            "not_allowed": NOT_ALLOWED,
        },
        **GATES,
        "next_allowed_step": recommended_next_stage,
        "outputs": {
            "summary_json": str(outdir / "stage46_external_context_baseline_scan_design_summary.json"),
            "markdown": str(outdir / "stage46_external_context_baseline_scan_design.md"),
            "readiness_matrix_csv": str(outdir / "stage46_readiness_matrix.csv"),
            "baseline_design_matrix_csv": str(outdir / "stage46_baseline_design_matrix.csv"),
            "guardrail_contract_csv": str(outdir / "stage46_guardrail_contract.csv"),
        },
    }

    readiness_df.to_csv(outdir / "stage46_readiness_matrix.csv", index=False)
    design_df.to_csv(outdir / "stage46_baseline_design_matrix.csv", index=False)
    pd.DataFrame(guardrails).to_csv(outdir / "stage46_guardrail_contract.csv", index=False)
    _write_json(outdir / "stage46_external_context_baseline_scan_design_summary.json", summary)
    write_markdown(outdir / "stage46_external_context_baseline_scan_design.md", summary, design_df, readiness_df)

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": status,
            "blockers": blockers,
            "warnings": warnings,
            "designed_families": [r.family_id for r in design],
            "next_allowed_step": recommended_next_stage,
            "summary_path": str(outdir / "stage46_external_context_baseline_scan_design_summary.json"),
            "markdown_path": str(outdir / "stage46_external_context_baseline_scan_design.md"),
        }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
