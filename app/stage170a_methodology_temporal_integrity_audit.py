#!/usr/bin/env python3
"""
Stage170A Methodology, Temporal Integrity and Feature Adequacy Audit

Read-only audit stage for the XAUUSD/gold research program.
It does NOT produce trading candidates, MT5 signals, demo orders, or live orders.

Outputs:
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_methodology_audit_summary.json
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_decision.md
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_stage_decision_inventory.csv
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_temporal_alignment_audit.csv
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_feature_timing_ledger.csv
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_validation_risk_register.csv
  reports/stage170a_methodology_temporal_integrity_audit/stage170a_methodology_recommendations.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas is required for Stage170A audit: {exc}")

STAGE = "Stage170A_METHODOLOGY_TEMPORAL_INTEGRITY_AND_FEATURE_ADEQUACY_AUDIT"
OUT_DIR_NAME = "stage170a_methodology_temporal_integrity_audit"

ORDER_ROUTING_ALLOWED = False
DEMO_RELEASE_ALLOWED = False


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}
    return {}


def detect_separator(path: Path) -> str:
    sample = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            sample = f.readline()
    except Exception:
        return ","
    candidates = {"\t": sample.count("\t"), ",": sample.count(","), ";": sample.count(";"), "|": sample.count("|")}
    sep, count = max(candidates.items(), key=lambda kv: kv[1])
    return sep if count > 0 else ","


def read_csv_sample(path: Path, nrows: int = 5) -> Tuple[List[str], int, str, Optional[str]]:
    if not path.exists():
        return [], 0, "missing", "file_missing"
    sep = detect_separator(path)
    try:
        df = pd.read_csv(path, sep=sep, nrows=nrows)
        return [str(c) for c in df.columns], len(df), sep, None
    except Exception as exc:
        return [], 0, sep, str(exc)


def count_csv_rows_fast(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            # header excluded. This is fast enough for ~hundreds of MB.
            return max(sum(1 for _ in f) - 1, 0)
    except Exception:
        return None


def normalize_time_col_names(cols: Iterable[str]) -> Dict[str, str]:
    normalized = {}
    for c in cols:
        k = str(c).strip().lower().replace("<", "").replace(">", "")
        normalized[k] = str(c)
    return normalized


def read_time_bounds_csv(path: Path, time_col: Optional[str] = None, n_tail: int = 10) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return meta
    sep = detect_separator(path)
    meta["detected_separator"] = "tab" if sep == "\t" else sep
    try:
        cols = pd.read_csv(path, sep=sep, nrows=0).columns.tolist()
        meta["columns"] = [str(c) for c in cols]
        norm = normalize_time_col_names(cols)
        if time_col and time_col in cols:
            tc = time_col
            head = pd.read_csv(path, sep=sep, usecols=[tc], nrows=1)
            # Portable tail read for typical project sizes.
            full = pd.read_csv(path, sep=sep, usecols=[tc])
            ts = pd.to_datetime(full[tc], utc=True, errors="coerce")
            meta["min_time_utc"] = str(ts.min()) if ts.notna().any() else None
            meta["max_time_utc"] = str(ts.max()) if ts.notna().any() else None
            meta["row_count"] = int(len(full))
            meta["time_parse_na"] = int(ts.isna().sum())
            return meta
        if "time_utc" in norm:
            tc = norm["time_utc"]
            full = pd.read_csv(path, sep=sep, usecols=[tc])
            ts = pd.to_datetime(full[tc], utc=True, errors="coerce")
            meta["min_time_utc"] = str(ts.min()) if ts.notna().any() else None
            meta["max_time_utc"] = str(ts.max()) if ts.notna().any() else None
            meta["row_count"] = int(len(full))
            meta["time_parse_na"] = int(ts.isna().sum())
            return meta
        if "time_bucket_utc" in norm:
            tc = norm["time_bucket_utc"]
            full = pd.read_csv(path, sep=sep, usecols=[tc])
            ts = pd.to_datetime(full[tc], utc=True, errors="coerce")
            meta["min_time_utc"] = str(ts.min()) if ts.notna().any() else None
            meta["max_time_utc"] = str(ts.max()) if ts.notna().any() else None
            meta["row_count"] = int(len(full))
            meta["time_parse_na"] = int(ts.isna().sum())
            return meta
        if "date" in norm and "time" in norm:
            dc, tc = norm["date"], norm["time"]
            full = pd.read_csv(path, sep=sep, usecols=[dc, tc])
            ts = pd.to_datetime(full[dc].astype(str) + " " + full[tc].astype(str), utc=True, errors="coerce")
            meta["min_time_utc_raw"] = str(ts.min()) if ts.notna().any() else None
            meta["max_time_utc_raw"] = str(ts.max()) if ts.notna().any() else None
            meta["row_count"] = int(len(full))
            meta["time_parse_na"] = int(ts.isna().sum())
            meta["timezone_warning"] = "Broker split DATE/TIME may need broker-to-UTC shift; verify against existing stage metadata."
            return meta
        meta["time_detection_error"] = "no recognizable time column"
    except Exception as exc:
        meta["read_error"] = str(exc)
    return meta


def flatten_summary(path: Path, data: Dict[str, Any]) -> Dict[str, Any]:
    def get_nested(d: Dict[str, Any], keys: List[str], default=None):
        cur: Any = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    return {
        "file": str(path),
        "stage": data.get("stage") or infer_stage_from_path(path),
        "generated_utc": data.get("generated_utc"),
        "status": data.get("status"),
        "decision": data.get("decision"),
        "severity": data.get("severity"),
        "recommended_action": data.get("recommended_action"),
        "order_routing_allowed": data.get("order_routing_allowed"),
        "demo_release_allowed": data.get("demo_release_allowed"),
        "score_count": get_nested(data, ["evaluation_context", "score_count"]),
        "rule_spec_count": get_nested(data, ["evaluation_context", "rule_spec_count"]),
        "shortlist_count": get_nested(data, ["evaluation_context", "shortlist_count"]),
        "train_rows": get_nested(data, ["split_meta", "train_rows"]),
        "holdout_rows": get_nested(data, ["split_meta", "holdout_rows"]),
        "holdout_pct": get_nested(data, ["split_meta", "holdout_pct"]),
        "train_start_utc": get_nested(data, ["split_meta", "train_start_utc"]),
        "train_end_utc": get_nested(data, ["split_meta", "train_end_utc"]),
        "holdout_start_utc": get_nested(data, ["split_meta", "holdout_start_utc"]),
        "holdout_end_utc": get_nested(data, ["split_meta", "holdout_end_utc"]),
        "event_overlay_trainable": get_nested(data, ["event_panel_health", "event_overlay_trainable"]),
        "bars_path": data.get("bars_m5"),
        "event_panel_path": data.get("event_panel"),
    }


def infer_stage_from_path(path: Path) -> str:
    m = re.search(r"stage(\d+[a-zA-Z]?)", str(path).lower())
    return f"Stage{m.group(1)}" if m else "UNKNOWN"


def discover_summary_files(root: Path) -> List[Path]:
    reports = root / "reports"
    if not reports.exists():
        return []
    patterns = ["*summary.json", "*_summary.json", "*decision*.json", "*holdout_gate_summary.json"]
    paths: List[Path] = []
    for pat in patterns:
        paths.extend(reports.rglob(pat))
    # Deduplicate, keep stage-ish files only.
    out = []
    seen = set()
    for p in sorted(paths):
        if p in seen:
            continue
        seen.add(p)
        if "stage" in p.name.lower() or "stage" in str(p.parent).lower():
            out.append(p)
    return out


def build_feature_timing_ledger(args: argparse.Namespace, root: Path) -> List[Dict[str, Any]]:
    rows = [
        {
            "feature_group": "Broker OHLCV/spread",
            "source": str(Path(args.bars_m5).expanduser()) if args.bars_m5 else "AMarkets broker CSV",
            "intended_role": "technical price/volatility/liquidity features",
            "as_of_available_time": "bar close plus broker/export latency",
            "expected_effect_horizon": "5m to 24h depending on rule family",
            "known_risk": "timezone shift, tab/comma delimiter drift, duplicate bars, export refresh gaps, spread unit conversion",
            "required_audit": "verify UTC conversion, monotonic timestamps, duplicate rate, spread-point bps mapping, no future bars in features",
            "current_confidence": "MEDIUM_HIGH",
        },
        {
            "feature_group": "Scheduled macro releases / calendar",
            "source": "calendar_events / FRED/BLS/BEA/Treasury inputs if present",
            "intended_role": "event timing, blackout/volatility regime, surprise proxy when values are available",
            "as_of_available_time": "scheduled release time; actual values only after release publication",
            "expected_effect_horizon": "minutes to several sessions; varies by CPI/NFP/FOMC/Treasury/yields",
            "known_risk": "calendar date without exact release time creates lookahead/lag ambiguity; surprise requires vintage expectations or consensus",
            "required_audit": "build release-time ledger with timezone, actual/forecast/as-of timestamp, event-type-specific decay",
            "current_confidence": "MEDIUM",
        },
        {
            "feature_group": "Macro levels: DXY/yields/real yields/VIX/ETF",
            "source": "stage115 macro panel and exogenous files if present",
            "intended_role": "macro regime prior, not necessarily intraday trigger",
            "as_of_available_time": "daily close or provider publication timestamp; vintage handling needed for revised series",
            "expected_effect_horizon": "daily to weekly regime",
            "known_risk": "daily as-of join may leak same-day close into intraday decisions; revised data may be used as if known historically",
            "required_audit": "force previous-close availability for intraday; use vintage/realtime fields when available; document release lag",
            "current_confidence": "MEDIUM_LOW_UNTIL_VINTAGE_AUDIT",
        },
        {
            "feature_group": "COT positioning",
            "source": "CFTC/COT data",
            "intended_role": "slow positioning regime prior",
            "as_of_available_time": "Friday publication for prior Tuesday positions; not Tuesday close",
            "expected_effect_horizon": "weekly to multi-week",
            "known_risk": "using report date instead of publication timestamp creates lookahead; low-frequency regimes can be sample-starved",
            "required_audit": "join by publication timestamp + embargo; avoid intraday trigger use",
            "current_confidence": "MEDIUM_LOW_UNTIL_PUBLICATION_LAG_AUDIT",
        },
        {
            "feature_group": "GDELT/news shock panel",
            "source": str(Path(args.event_panel).expanduser()) if args.event_panel else "Stage166F/166E event panel",
            "intended_role": "current-event guard; alpha only if stronger labels pass event-study and holdout",
            "as_of_available_time": "article publication / API timestamp plus collection lag; GitHub artifact fetch time for historical backfill",
            "expected_effect_horizon": "hours to days, event-class dependent",
            "known_risk": "article-count intensity is not causal label; source coverage varies; historical backfill may reflect later article indexing; sparse counts need positive-distribution thresholds",
            "required_audit": "event-study by class, lag, decay; compare article time vs event time; supervised/manual labels for major shocks",
            "current_confidence": "LOW_AS_ALPHA_MEDIUM_AS_GUARD",
        },
        {
            "feature_group": "Manual/current event labels",
            "source": "manual_current_events.csv / news_raw browser downloads",
            "intended_role": "current regime guard and external expert-labeled event seed",
            "as_of_available_time": "manual entry time and source publication time; must be recorded separately",
            "expected_effect_horizon": "hours to days",
            "known_risk": "human hindsight bias if entered after price reaction; inconsistent severity/confidence scale",
            "required_audit": "log created_at_utc, source_published_utc, event_time_utc, labeler, confidence, and no-retrospective policy",
            "current_confidence": "MEDIUM_FOR_CURRENT_GUARD_LOW_FOR_HISTORICAL_BACKTEST_UNLESS_LOCKED",
        },
    ]
    return rows


def build_validation_risk_register(stage_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total_scores = 0
    max_score = 0
    for r in stage_rows:
        sc = r.get("score_count")
        if isinstance(sc, (int, float)):
            total_scores += int(sc)
            max_score = max(max_score, int(sc))
    rows = [
        {
            "risk_id": "R1",
            "risk_area": "As-of / lookahead leakage",
            "severity": "HIGH",
            "evidence": "Heterogeneous data sources include broker intraday bars, daily macro, COT, scheduled events, ETF/news; not all have proven availability timestamps.",
            "impact": "Can create false historical edge even when code is syntactically correct.",
            "required_control": "Feature timing ledger with availability_timestamp_utc; as-of join tests; same-day daily macro embargo for intraday rules unless explicitly available.",
            "blocking_before_demo": "YES",
        },
        {
            "risk_id": "R2",
            "risk_area": "Multiple testing / data-snooping",
            "severity": "HIGH",
            "evidence": f"Discovered summaries show at least {total_scores} scored variants across available stage summaries; Stage168 alone scanned 7500 rules when present.",
            "impact": "Best candidates can be luck from large search surface.",
            "required_control": "Track candidate family lineage; apply walk-forward, deflated Sharpe/probabilistic Sharpe or reality-check-style correction; keep final locked holdout untouched.",
            "blocking_before_demo": "YES_FOR_PROMOTION_NOT_FOR_READONLY_RESEARCH",
        },
        {
            "risk_id": "R3",
            "risk_area": "Label adequacy",
            "severity": "MEDIUM_HIGH",
            "evidence": "Many scans use fixed-horizon net bps; execution paths with stops, MFE/MAE and time-in-trade are not yet first-class labels.",
            "impact": "A rule can look weak/strong under fixed horizon but fail/pass under executable stop/take-profit path.",
            "required_control": "Add triple-barrier / MFE-MAE / path-based labels before execution replay; report turnover and dwell time.",
            "blocking_before_demo": "YES_FOR_EXECUTION_RELEASE",
        },
        {
            "risk_id": "R4",
            "risk_area": "Event/news feature semantics",
            "severity": "HIGH",
            "evidence": "GDELT-derived article-count features became trainable but failed 7500-rule reaction scan; Stage169 keeps them only as guard.",
            "impact": "News may still matter, but current representation is too crude for alpha discovery.",
            "required_control": "Event study by class and manually labeled major shocks; decouple event intensity, direction, surprise, and source reliability.",
            "blocking_before_demo": "NO_AS_GUARD_YES_AS_ALPHA",
        },
        {
            "risk_id": "R5",
            "risk_area": "Regime coverage and concentration",
            "severity": "MEDIUM_HIGH",
            "evidence": "Prior candidates often failed due to low train/holdout events or event-spike dependence.",
            "impact": "Low-frequency edges can be dominated by 2025/2026 or a few shock days.",
            "required_control": "Year/regime contribution report, single-day/month share gates, bull/bear/sideways/vol regimes.",
            "blocking_before_demo": "YES",
        },
        {
            "risk_id": "R6",
            "risk_area": "Cost/slippage realism",
            "severity": "MEDIUM_HIGH",
            "evidence": "Current stages use fixed cost plus spread proxy; actual MT5 execution/slippage/fill rejection risks are not fully replayed for candidates.",
            "impact": "Small bps edges may vanish; high-event windows can have unstable spread/slippage.",
            "required_control": "Broker spread distribution by session/news state; slippage stress; execution replay before any demo release.",
            "blocking_before_demo": "YES",
        },
        {
            "risk_id": "R7",
            "risk_area": "Validation design",
            "severity": "HIGH",
            "evidence": "Newest 20% holdout is used; purged/walk-forward validation has not been uniformly applied across all thesis families.",
            "impact": "One holdout can over/understate robustness; overlapping horizons leak information between train/test folds.",
            "required_control": "Purged/embargoed walk-forward with final untouched holdout and regime-stratified reporting.",
            "blocking_before_demo": "YES_FOR_NEW_ALPHA_PROMOTION",
        },
    ]
    return rows


def build_recommendations() -> List[Dict[str, Any]]:
    return [
        {
            "priority": 1,
            "recommendation": "Freeze new discovery until Stage170A audit artifacts are reviewed.",
            "reason": "The project has reached a methodological decision point; more scans risk repeating data-snooping loops.",
            "deliverable": "Stage170A summary, timing ledger, risk register, specialist review brief.",
        },
        {
            "priority": 2,
            "recommendation": "Create an explicit as-of data contract for every input table/file.",
            "reason": "Correct code does not guarantee historical availability correctness.",
            "deliverable": "data_asof_contract.csv with source, observed_time, available_time, effective_time, revision policy.",
        },
        {
            "priority": 3,
            "recommendation": "Run event-study diagnostics before any future news alpha scan.",
            "reason": "News article counts need empirical response curves by class before rule search.",
            "deliverable": "event_study_by_class_lag_decay.md/csv.",
        },
        {
            "priority": 4,
            "recommendation": "Replace simple fixed-horizon candidate evaluation with path-aware labels for promotion.",
            "reason": "Commercial execution depends on path, stops, spread and hold time, not just endpoint return.",
            "deliverable": "triple_barrier_or_mfe_mae_label_audit.csv.",
        },
        {
            "priority": 5,
            "recommendation": "Add purged walk-forward and multiple-testing correction before any demo candidate.",
            "reason": "Thousands of tested variants make raw shortlist metrics unreliable without correction.",
            "deliverable": "walk_forward_matrix.csv and data_snooping_adjustment_report.md.",
        },
        {
            "priority": 6,
            "recommendation": "Keep GDELT/news as current-event guard unless hand-labeled historical events are added.",
            "reason": "Stage168 failed alpha discovery but Stage169 provides usable context guard.",
            "deliverable": "current_event_guard_json consumed by future execution/research layers.",
        },
    ]


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    for r in rows[1:]:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_temporal_alignment_audit(args: argparse.Namespace, root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    targets = []
    if args.bars_m5:
        targets.append(("bars_m5", Path(args.bars_m5).expanduser()))
    if args.event_panel:
        targets.append(("event_panel", Path(args.event_panel).expanduser()))
    if args.stage168_summary:
        targets.append(("stage168_summary", Path(args.stage168_summary).expanduser()))
    if args.stage169_summary:
        targets.append(("stage169_summary", Path(args.stage169_summary).expanduser()))
    if args.macro_panel:
        targets.append(("macro_panel", Path(args.macro_panel).expanduser()))
    if args.event_inbox:
        inbox = Path(args.event_inbox).expanduser()
        if inbox.exists():
            for p in sorted(inbox.glob("*.csv"))[:50]:
                targets.append((f"event_inbox_csv:{p.name}", p))
    for label, path in targets:
        if path.suffix.lower() == ".json":
            data = safe_read_json(path)
            row = {"artifact": label, "path": str(path), "exists": path.exists(), "type": "json"}
            if data:
                row.update({
                    "stage": data.get("stage"),
                    "generated_utc": data.get("generated_utc"),
                    "decision": data.get("decision"),
                    "split_holdout_start_utc": (data.get("split_meta") or {}).get("holdout_start_utc"),
                    "split_train_end_utc": (data.get("split_meta") or {}).get("train_end_utc"),
                })
            rows.append(row)
        else:
            meta = read_time_bounds_csv(path)
            row = {"artifact": label, "type": "csv", **meta}
            rows.append(row)
    return rows


def build_decision_md(summary: Dict[str, Any], stage_rows: List[Dict[str, Any]], risks: List[Dict[str, Any]], recommendations: List[Dict[str, Any]]) -> str:
    generated = summary["generated_utc"]
    decision = summary["decision"]
    lines: List[str] = []
    lines.append("# Stage170A Methodology, Temporal Integrity and Feature Adequacy Audit")
    lines.append("")
    lines.append(f"Generated UTC: `{generated}`")
    lines.append("")
    lines.append(f"Decision: `{decision}`")
    lines.append(f"Recommended action: `{summary['recommended_action']}`")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("This is a read-only methodology audit. It does not create trading candidates, does not write MT5 execution signals, and does not authorize demo/live orders.")
    lines.append("")
    lines.append("## Current project verdict")
    lines.append("")
    lines.append("The GDELT/news branch is not deleted, but it should remain a current-event guard unless stronger hand-labeled historical event features are added and pass event-study plus robust validation. Existing Stage168/169 evidence does not justify using the news panel as a direct alpha.")
    lines.append("")
    lines.append("## Audit conclusion")
    lines.append("")
    lines.append("- Implementation discipline is improving: newest holdout, no demo/live release, fast-stop guards, and branch-kill decisions are present.")
    lines.append("- Methodological confidence is not high enough for new demo/live promotion until as-of timing, validation, multiple-testing and path-aware labeling controls are added.")
    lines.append("- The next productive work is not another broad scan; it is a formal data contract and validation redesign.")
    lines.append("")
    lines.append("## Key risks")
    lines.append("")
    for r in risks:
        lines.append(f"- `{r['risk_id']}` **{r['risk_area']}** — severity `{r['severity']}`; blocking: `{r['blocking_before_demo']}`. {r['required_control']}")
    lines.append("")
    lines.append("## Recent stage inventory")
    lines.append("")
    selected = [r for r in stage_rows if any(s in str(r.get("stage", "")).lower() or s in str(r.get("file", "")).lower() for s in ["166", "167", "168", "169"])]
    if not selected:
        selected = stage_rows[-10:]
    lines.append("| stage | decision | scores | shortlist | order_allowed | demo_allowed |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in selected[-20:]:
        lines.append(f"| {r.get('stage')} | {r.get('decision')} | {r.get('score_count')} | {r.get('shortlist_count')} | {r.get('order_routing_allowed')} | {r.get('demo_release_allowed')} |")
    lines.append("")
    lines.append("## Recommended next work")
    lines.append("")
    for rec in recommendations:
        lines.append(f"{rec['priority']}. **{rec['recommendation']}** {rec['reason']} Deliverable: `{rec['deliverable']}`.")
    lines.append("")
    lines.append("## Specialist questions")
    lines.append("")
    lines.append("1. Are the proposed as-of timestamps and publication-lag assumptions sufficient for broker M5 + daily macro + COT + ETF + GDELT/news integration?")
    lines.append("2. Should gold candidate labels move to triple-barrier/MFE-MAE before any further discovery, or is fixed-horizon acceptable for first-pass scanning?")
    lines.append("3. What multiple-testing correction is appropriate for thousands of deterministic rule variants in a commercial trading system: Deflated Sharpe, Reality Check, walk-forward selection, or another control?")
    lines.append("4. Should news/GDELT be retained only as guard, or should a hand-labeled event-study dataset be built for a second news-alpha attempt?")
    lines.append("5. What is the minimum validation matrix before a candidate can move to demo: regime-stratified walk-forward, final locked holdout, spread/slippage replay, and live-shadow sample count?")
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("Do not run Stage170 discovery until the as-of data contract and validation redesign are accepted. If the specialist approves, proceed to a Stage170B data-contract patch and Stage171 validation framework, not immediate execution replay.")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--bars-m5", default="~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv")
    ap.add_argument("--event-panel", default="~/Desktop/xauusd-trader/reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv")
    ap.add_argument("--stage168-summary", default="~/Desktop/xauusd-trader/reports/stage168_gdelt_reaction_rulespace_rebuild/stage168_gdelt_reaction_rulespace_summary.json")
    ap.add_argument("--stage169-summary", default="~/Desktop/xauusd-trader/reports/stage169_event_branch_kill_and_current_guard/stage169_event_branch_kill_and_current_guard_summary.json")
    ap.add_argument("--macro-panel", default="")
    ap.add_argument("--event-inbox", default="~/Downloads/xauusd_fundamental_event_inbox")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else root / "reports" / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    discovered = discover_summary_files(root)
    # Ensure key supplied summaries are included even outside report discovery.
    for p in [Path(args.stage168_summary).expanduser(), Path(args.stage169_summary).expanduser()]:
        if p.exists() and p not in discovered:
            discovered.append(p)

    stage_rows: List[Dict[str, Any]] = []
    for p in sorted(discovered):
        data = safe_read_json(p)
        if data:
            stage_rows.append(flatten_summary(p, data))

    feature_ledger = build_feature_timing_ledger(args, root)
    temporal_rows = build_temporal_alignment_audit(args, root)
    risks = build_validation_risk_register(stage_rows)
    recommendations = build_recommendations()

    # Determine status from known stage169/stage168 verdicts.
    stage168 = safe_read_json(Path(args.stage168_summary).expanduser())
    stage169 = safe_read_json(Path(args.stage169_summary).expanduser())
    stage168_decision = stage168.get("decision")
    stage169_decision = stage169.get("decision")
    if stage169_decision == "STAGE169_KILL_GDELT_REACTION_ALPHA_KEEP_CURRENT_EVENT_GUARD_ONLY":
        decision = "STAGE170A_METHOD_AUDIT_REQUIRED_BEFORE_NEW_DISCOVERY"
        recommended_action = "FREEZE_NEW_DISCOVERY; BUILD_ASOF_DATA_CONTRACT_AND_VALIDATION_REDESIGN"
        severity = "HIGH"
    else:
        decision = "STAGE170A_AUDIT_INCOMPLETE_MISSING_STAGE169_VERDICT"
        recommended_action = "COMPLETE_STAGE169_OR_PROVIDE_SUMMARY_BEFORE_NEW_DISCOVERY"
        severity = "HIGH"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": now_utc_iso(),
        "root": str(root),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
        "status": "STAGE170A_COMPLETE_READONLY_METHOD_AUDIT_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended_action,
        "inputs": {
            "bars_m5": str(Path(args.bars_m5).expanduser()) if args.bars_m5 else None,
            "event_panel": str(Path(args.event_panel).expanduser()) if args.event_panel else None,
            "stage168_summary": str(Path(args.stage168_summary).expanduser()) if args.stage168_summary else None,
            "stage169_summary": str(Path(args.stage169_summary).expanduser()) if args.stage169_summary else None,
            "macro_panel": str(Path(args.macro_panel).expanduser()) if args.macro_panel else None,
            "event_inbox": str(Path(args.event_inbox).expanduser()) if args.event_inbox else None,
        },
        "stage168_verdict": {
            "decision": stage168_decision,
            "score_count": (stage168.get("evaluation_context") or {}).get("score_count"),
            "shortlist_count": (stage168.get("evaluation_context") or {}).get("shortlist_count"),
            "event_overlay_trainable": (stage168.get("event_panel_health") or {}).get("event_overlay_trainable"),
        },
        "stage169_verdict": {
            "decision": stage169_decision,
            "current_guard": stage169.get("current_guard"),
            "event_meta": stage169.get("event_meta"),
        },
        "audit_counts": {
            "stage_summary_files_discovered": len(stage_rows),
            "feature_timing_ledger_rows": len(feature_ledger),
            "temporal_alignment_rows": len(temporal_rows),
            "risk_register_rows": len(risks),
            "recommendation_rows": len(recommendations),
        },
        "methodology_verdict": {
            "implementation_smoke_confidence": "MEDIUM_HIGH",
            "temporal_integrity_confidence": "MEDIUM_LOW_UNTIL_ASOF_CONTRACT",
            "news_alpha_confidence": "LOW_WITH_CURRENT_FEATURES",
            "news_guard_confidence": "MEDIUM",
            "validation_confidence": "MEDIUM_LOW_UNTIL_PURGED_WALK_FORWARD_AND_MULTIPLE_TESTING_CONTROL",
            "commercial_promotion_allowed": False,
            "new_discovery_allowed_before_audit_review": False,
        },
        "outputs": {},
        "next": [
            "Review Stage170A decision and risk register before running Stage170 discovery.",
            "Build an as-of data contract for every source and enforce it in loaders.",
            "Add purged walk-forward and multiple-testing adjustment before any candidate promotion.",
            "Keep GDELT/news as current-event guard unless stronger hand-labeled event features are added.",
        ],
    }

    paths = {
        "summary_json": out_dir / "stage170a_methodology_audit_summary.json",
        "decision_md": out_dir / "stage170a_decision.md",
        "stage_inventory_csv": out_dir / "stage170a_stage_decision_inventory.csv",
        "temporal_alignment_csv": out_dir / "stage170a_temporal_alignment_audit.csv",
        "feature_timing_ledger_csv": out_dir / "stage170a_feature_timing_ledger.csv",
        "validation_risk_register_csv": out_dir / "stage170a_validation_risk_register.csv",
        "methodology_recommendations_csv": out_dir / "stage170a_methodology_recommendations.csv",
    }
    summary["outputs"] = {k: str(v) for k, v in paths.items()}

    write_csv(paths["stage_inventory_csv"], stage_rows)
    write_csv(paths["temporal_alignment_csv"], temporal_rows)
    write_csv(paths["feature_timing_ledger_csv"], feature_ledger)
    write_csv(paths["validation_risk_register_csv"], risks)
    write_csv(paths["methodology_recommendations_csv"], recommendations)
    paths["decision_md"].write_text(build_decision_md(summary, stage_rows, risks, recommendations), encoding="utf-8")
    paths["summary_json"].write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "decision": decision,
        "recommended_action": recommended_action,
        "summary_json": str(paths["summary_json"]),
        "decision_md": str(paths["decision_md"]),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
