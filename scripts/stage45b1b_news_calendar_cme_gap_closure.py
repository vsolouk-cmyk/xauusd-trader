#!/usr/bin/env python3
"""
Stage45B1B_NEWS_CALENDAR_AND_CME_REFERENCE_GAP_CLOSURE

Local diagnostic/import helper for the two remaining P0 external-context gaps:
  1) high-impact macro news calendar
  2) CME GC/MGC futures reference feed

This script does NOT create signals, does NOT shortlist candidates, and does NOT promote
archived Stage41/42/43 rows. It only validates whether the remaining P0 inputs are
ready for a later predefined alignment audit.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage45B1B_NEWS_CALENDAR_AND_CME_REFERENCE_GAP_CLOSURE"
OUTDIR_DEFAULT = "reports/stage45b1b"

P0_FILES = {
    "dxy": Path("data/external/dxy.csv"),
    "us10y_yield": Path("data/external/us10y_yield.csv"),
    "real_yield_optional": Path("data/external/real_yield.csv"),
    "cme_gc_reference": Path("data/reference/cme_gc.csv"),
    "news_calendar": Path("data/external/news_calendar.csv"),
}

NEWS_CANDIDATE_PATHS = [
    Path("data/external/news_calendar.csv"),
    Path("data/external/high_impact_news.csv"),
    Path("data/external/macro_calendar.csv"),
    Path("data/calendar/news_calendar.csv"),
    Path("data/exogenous/calendar_events.csv"),
    Path("data/macro/events/stage10b_unified_news_events.csv"),
    Path("archive/pre_stage38_final_cleanup_20260616T095255Z/data/config/stage10a_news_events.csv"),
    Path("archive/pre_stage38_final_cleanup_20260616T095255Z/data/config/stage10a_news_events_manual.csv"),
]

CME_CANDIDATE_PATHS = [
    Path("data/reference/cme_gc.csv"),
    Path("data/external/cme_gc.csv"),
    Path("data/external/gc_futures.csv"),
    Path("data/external/GC.csv"),
    Path("data/external/mgc_futures.csv"),
    Path("data/reference/gc_futures.csv"),
    Path("data/reference/GC.csv"),
]

MACRO_KEYWORDS = [
    "cpi", "consumer price", "inflation", "pce", "core pce",
    "fomc", "fed rate", "rate decision", "federal funds", "fed chair", "powell",
    "nonfarm", "non-farm", "nfp", "payroll", "employment", "unemployment",
    "average hourly", "retail sales", "ism", "pmi", "gdp", "ppi",
]

CENTRAL_BANK_GOLD_ONLY_KEYWORDS = [
    "central_bank_gold_demand", "central bank gold", "world gold council", "央行", "黄金", "gold demand"
]


def _repo_path(repo_root: Path, p: Path) -> Path:
    return p if p.is_absolute() else repo_root / p


def _norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _read_csv_head(path: Path, n: Optional[int] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        if n is None:
            return pd.read_csv(path), None
        return pd.read_csv(path, nrows=n), None
    except Exception as e:  # pragma: no cover - error text included in report
        return None, f"{type(e).__name__}: {e}"


def _timestamp_profile(series: pd.Series) -> Dict[str, Any]:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    ok = parsed.dropna()
    return {
        "raw_count": int(len(series)),
        "valid_timestamp_count": int(ok.shape[0]),
        "start": ok.min().isoformat() if not ok.empty else None,
        "end": ok.max().isoformat() if not ok.empty else None,
    }


def _numeric_profile(series: pd.Series) -> Dict[str, Any]:
    x = pd.to_numeric(series, errors="coerce").dropna()
    if x.empty:
        return {"n": 0}
    return {
        "n": int(x.shape[0]),
        "min": float(x.min()),
        "p10": float(x.quantile(0.10)),
        "median": float(x.median()),
        "p90": float(x.quantile(0.90)),
        "max": float(x.max()),
        "mean": float(x.mean()),
    }


def _pick_col(cols_norm: Dict[str, str], aliases: Sequence[str]) -> Optional[str]:
    for a in aliases:
        key = _norm_col(a)
        if key in cols_norm:
            return cols_norm[key]
    return None


def validate_simple_series(repo_root: Path, key: str, path: Path, value_aliases: Sequence[str], min_rows: int = 100) -> Dict[str, Any]:
    full = _repo_path(repo_root, path)
    out: Dict[str, Any] = {
        "key": key,
        "path": str(path),
        "exists": full.exists(),
        "schema_ok": False,
        "required_ok": False,
        "row_count": 0,
        "timestamp_column": None,
        "value_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "numeric_profile": None,
        "error": None,
    }
    if not full.exists():
        return out
    df, err = _read_csv_head(full)
    if err or df is None:
        out["error"] = err
        return out
    out["row_count"] = int(df.shape[0])
    out["columns"] = [str(c) for c in df.columns]
    cols_norm = {_norm_col(c): str(c) for c in df.columns}
    ts_col = _pick_col(cols_norm, ["timestamp", "datetime", "date", "time", "utc_time", "event_time_utc"])
    value_col = _pick_col(cols_norm, value_aliases)
    out["timestamp_column"] = ts_col
    out["value_column"] = value_col
    if ts_col:
        prof = _timestamp_profile(df[ts_col])
        out.update({"start": prof["start"], "end": prof["end"], "valid_timestamp_count": prof["valid_timestamp_count"]})
    if value_col:
        out["numeric_profile"] = _numeric_profile(df[value_col])
    required_ok = bool(ts_col and value_col and out.get("valid_timestamp_count", 0) > 0 and out["row_count"] >= min_rows)
    out["required_ok"] = required_ok
    out["schema_ok"] = required_ok
    return out


def validate_cme_reference(repo_root: Path, path: Path = P0_FILES["cme_gc_reference"], min_rows: int = 100) -> Dict[str, Any]:
    full = _repo_path(repo_root, path)
    out: Dict[str, Any] = {
        "key": "cme_gc_reference",
        "path": str(path),
        "exists": full.exists(),
        "schema_ok": False,
        "required_ok": False,
        "row_count": 0,
        "timestamp_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "missing_required_columns": ["timestamp", "open", "high", "low", "close"],
        "numeric_profiles": {},
        "error": None,
    }
    if not full.exists():
        return out
    df, err = _read_csv_head(full)
    if err or df is None:
        out["error"] = err
        return out
    out["row_count"] = int(df.shape[0])
    out["columns"] = [str(c) for c in df.columns]
    cols_norm = {_norm_col(c): str(c) for c in df.columns}
    ts_col = _pick_col(cols_norm, ["timestamp", "datetime", "date", "time", "utc_time"])
    required = ["open", "high", "low", "close"]
    missing = []
    for col in required:
        actual = _pick_col(cols_norm, [col])
        if not actual:
            missing.append(col)
        else:
            out["numeric_profiles"][col] = _numeric_profile(df[actual])
    if not ts_col:
        missing.insert(0, "timestamp")
    else:
        prof = _timestamp_profile(df[ts_col])
        out.update({"timestamp_column": ts_col, "start": prof["start"], "end": prof["end"], "valid_timestamp_count": prof["valid_timestamp_count"]})
    out["missing_required_columns"] = missing
    required_ok = bool(not missing and out.get("valid_timestamp_count", 0) > 0 and out["row_count"] >= min_rows)
    out["required_ok"] = required_ok
    out["schema_ok"] = required_ok
    return out


def classify_news_calendar(repo_root: Path, path: Path, min_rows: int = 10) -> Dict[str, Any]:
    full = _repo_path(repo_root, path)
    out: Dict[str, Any] = {
        "key": "news_calendar_candidate",
        "path": str(path),
        "exists": full.exists(),
        "schema_ok": False,
        "blackout_ready": False,
        "row_count": 0,
        "timestamp_column": None,
        "event_column": None,
        "currency_column": None,
        "impact_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "macro_keyword_hits": 0,
        "central_bank_gold_only_hits": 0,
        "usd_or_unknown_rows": 0,
        "decision_reason": "missing",
        "error": None,
    }
    if not full.exists():
        return out
    df, err = _read_csv_head(full)
    if err or df is None:
        out["error"] = err
        out["decision_reason"] = "read_error"
        return out
    out["row_count"] = int(df.shape[0])
    out["columns"] = [str(c) for c in df.columns]
    cols_norm = {_norm_col(c): str(c) for c in df.columns}
    ts_col = _pick_col(cols_norm, ["timestamp", "datetime", "date", "event_time_utc", "time", "utc_time"])
    event_col = _pick_col(cols_norm, ["event", "name", "title", "event_name"])
    currency_col = _pick_col(cols_norm, ["currency", "ccy"])
    impact_col = _pick_col(cols_norm, ["impact", "importance", "initial_importance"])
    out.update({"timestamp_column": ts_col, "event_column": event_col, "currency_column": currency_col, "impact_column": impact_col})
    if ts_col:
        prof = _timestamp_profile(df[ts_col])
        out.update({"start": prof["start"], "end": prof["end"], "valid_timestamp_count": prof["valid_timestamp_count"]})
    if not ts_col or not event_col:
        out["decision_reason"] = "missing_timestamp_or_event_column"
        return out
    text = df[event_col].astype(str).str.lower()
    extra_cols = []
    for maybe in ["event_class", "event_channel", "manual_tags", "notes", "category"]:
        c = _pick_col(cols_norm, [maybe])
        if c:
            extra_cols.append(c)
    if extra_cols:
        combined = text.copy()
        for c in extra_cols:
            combined = combined + " " + df[c].astype(str).str.lower()
    else:
        combined = text
    macro_mask = combined.apply(lambda s: any(k in s for k in MACRO_KEYWORDS))
    gold_only_mask = combined.apply(lambda s: any(k.lower() in s for k in CENTRAL_BANK_GOLD_ONLY_KEYWORDS))
    out["macro_keyword_hits"] = int(macro_mask.sum())
    out["central_bank_gold_only_hits"] = int(gold_only_mask.sum())
    if currency_col:
        ccy = df[currency_col].astype(str).str.upper().str.strip()
        out["usd_or_unknown_rows"] = int((ccy.isin(["USD", "US", "USA", ""]) | ccy.isna()).sum())
    else:
        out["usd_or_unknown_rows"] = int(df.shape[0])

    # Schema is OK if timestamp/event exist and enough rows. Blackout-ready is stricter:
    # must include plausible US macro event content, not merely gold news candidates.
    schema_ok = bool(out.get("valid_timestamp_count", 0) > 0 and df.shape[0] >= min_rows)
    out["schema_ok"] = schema_ok

    if not schema_ok:
        out["decision_reason"] = "too_few_rows_or_invalid_timestamps"
    elif out["macro_keyword_hits"] >= max(5, min(20, math.ceil(df.shape[0] * 0.10))):
        out["blackout_ready"] = True
        out["decision_reason"] = "macro_blackout_candidate_ready"
    elif out["macro_keyword_hits"] > 0 and df.shape[0] >= min_rows:
        out["decision_reason"] = "partial_macro_hits_needs_manual_review"
    elif out["central_bank_gold_only_hits"] > 0:
        out["decision_reason"] = "gold_news_not_high_impact_macro_blackout_calendar"
    else:
        out["decision_reason"] = "no_macro_blackout_keywords_detected"
    return out


def scan_candidate_paths(repo_root: Path) -> Dict[str, Any]:
    news = [classify_news_calendar(repo_root, p) for p in NEWS_CANDIDATE_PATHS]
    cme = [validate_cme_reference(repo_root, p) for p in CME_CANDIDATE_PATHS]
    return {"news_candidates": news, "cme_candidates": cme}


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def build_summary(repo_root: Path, outdir: Path, print_summary: bool = False) -> Dict[str, Any]:
    outdir_abs = _repo_path(repo_root, outdir)
    outdir_abs.mkdir(parents=True, exist_ok=True)

    validations = {
        "dxy": validate_simple_series(repo_root, "dxy", P0_FILES["dxy"], ["close", "value"], min_rows=100),
        "us10y_yield": validate_simple_series(repo_root, "us10y_yield", P0_FILES["us10y_yield"], ["yield", "close", "value"], min_rows=100),
        "real_yield_optional": validate_simple_series(repo_root, "real_yield_optional", P0_FILES["real_yield_optional"], ["yield", "close", "value"], min_rows=100),
        "cme_gc_reference": validate_cme_reference(repo_root, P0_FILES["cme_gc_reference"], min_rows=100),
        "news_calendar": classify_news_calendar(repo_root, P0_FILES["news_calendar"], min_rows=10),
    }
    candidates = scan_candidate_paths(repo_root)

    p0_schema_ok = []
    if validations["dxy"].get("schema_ok"):
        p0_schema_ok.append("dxy")
    if validations["us10y_yield"].get("schema_ok"):
        p0_schema_ok.append("us10y_yield")
    if validations["cme_gc_reference"].get("schema_ok"):
        p0_schema_ok.append("cme_gc_reference")
    if validations["news_calendar"].get("blackout_ready"):
        p0_schema_ok.append("news_calendar")
    p0_required = ["dxy", "us10y_yield", "cme_gc_reference", "news_calendar"]
    missing = [k for k in p0_required if k not in p0_schema_ok]

    cme_candidate_ready = [c for c in candidates["cme_candidates"] if c.get("schema_ok")]
    news_candidate_ready = [n for n in candidates["news_candidates"] if n.get("blackout_ready")]
    partial_news_candidates = [n for n in candidates["news_candidates"] if n.get("schema_ok") and not n.get("blackout_ready")]

    if not missing:
        rec = "Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT"
        status = "EXTERNAL_CONTEXT_P0_READY_FOR_ALIGNMENT_AUDIT"
    else:
        rec = "Stage45B1B_CONTINUE_NEWS_CALENDAR_AND_CME_REFERENCE_ACQUISITION"
        status = "EXTERNAL_CONTEXT_P0_STILL_MISSING_NEWS_OR_CME"

    acquisition_tasks = []
    if "cme_gc_reference" in missing:
        acquisition_tasks.append({
            "key": "cme_gc_reference",
            "priority": "P0_REQUIRED",
            "status": "missing_or_schema_invalid",
            "canonical_path": "data/reference/cme_gc.csv",
            "required_columns": "timestamp,open,high,low,close[,volume,contract,source]",
            "minimum_rows": 100,
            "acceptable_reference_level": "daily minimum; intraday preferred; continuous roll method must be documented",
            "next_action": "recover prior GC/MGC file from archive/git or acquire a clean GC/MGC continuous futures reference feed",
        })
    if "news_calendar" in missing:
        acquisition_tasks.append({
            "key": "news_calendar",
            "priority": "P0_REQUIRED",
            "status": "missing_or_not_macro_blackout_ready",
            "canonical_path": "data/external/news_calendar.csv",
            "required_columns": "timestamp,event,currency,impact,category,actual,forecast,previous,source",
            "minimum_rows": 10,
            "acceptable_reference_level": "high-impact US macro events with real timestamps; date-only is weak and must be tagged",
            "next_action": "build/import CPI/FOMC/NFP/PCE/jobs/rate-event calendar; do not use generic GDELT gold news as blackout calendar",
        })

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "outdir": str(outdir),
        },
        "validations": validations,
        "candidate_scan": candidates,
        "decision": {
            "status": status,
            "promotion": "NO_GO",
            "EA": "NO_GO",
            "paper_live": "NO_GO",
            "live": "NO_GO",
            "p0_required_keys": p0_required,
            "p0_schema_ok_keys": p0_schema_ok,
            "p0_missing_or_invalid_keys": missing,
            "cme_candidate_ready_count": len(cme_candidate_ready),
            "news_blackout_ready_candidate_count": len(news_candidate_ready),
            "partial_news_candidate_count": len(partial_news_candidates),
            "recommended_next_stage": rec,
            "rationale": [
                "DXY and US10Y can be treated as macro-core ready only if canonical files validate.",
                "News must be a high-impact macro blackout calendar, not generic gold news or a one-row example file.",
                "CME GC/MGC reference remains required before external-context alignment can begin.",
                "This step does not authorize candidate rescue, candle-only scans, EA, paper-live, or live trading.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned",
            ],
        },
        "acquisition_tasks": acquisition_tasks,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": rec,
    }

    summary_path = outdir_abs / "stage45b1b_news_calendar_cme_gap_closure_summary.json"
    md_path = outdir_abs / "stage45b1b_news_calendar_cme_gap_closure.md"
    news_csv = outdir_abs / "stage45b1b_news_candidate_inventory.csv"
    cme_csv = outdir_abs / "stage45b1b_cme_candidate_inventory.csv"
    tasks_csv = outdir_abs / "stage45b1b_acquisition_tasks.csv"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, summary)
    write_csv(news_csv, candidates["news_candidates"])
    write_csv(cme_csv, candidates["cme_candidates"])
    write_csv(tasks_csv, acquisition_tasks)

    if print_summary:
        compact = {
            "stage": STAGE,
            "p0_schema_ok_keys": p0_schema_ok,
            "p0_missing_or_invalid_keys": missing,
            "recommended_next_stage": rec,
            "outputs": [str(summary_path), str(md_path), str(news_csv), str(cme_csv), str(tasks_csv)],
        }
        print(json.dumps(compact, indent=2, ensure_ascii=False))
    return summary


def _md_bool(x: Any) -> str:
    return "True" if bool(x) else "False"


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    d = summary["decision"]
    vals = summary["validations"]
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append(f"recommended_next_stage = {d['recommended_next_stage']}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45B1B is a gap-closure diagnostic for the remaining P0 external-context inputs. It does not create signals, shortlist candidates, or promote archived rows.")
    lines.append("")
    lines.append("## P0 readiness")
    lines.append("")
    lines.append("| key | schema_ok | row_count | start | end | path |")
    lines.append("| :-- | :-- | --: | :-- | :-- | :-- |")
    for key in ["dxy", "us10y_yield", "cme_gc_reference", "news_calendar"]:
        v = vals[key]
        schema_ok = v.get("schema_ok") if key != "news_calendar" else v.get("blackout_ready")
        lines.append(f"| {key} | {_md_bool(schema_ok)} | {v.get('row_count', 0)} | {v.get('start') or ''} | {v.get('end') or ''} | {v.get('path') or ''} |")
    lines.append("")
    lines.append("## Optional readiness")
    lines.append("")
    lines.append("| key | schema_ok | row_count | path |")
    lines.append("| :-- | :-- | --: | :-- |")
    for key in ["real_yield_optional"]:
        v = vals[key]
        lines.append(f"| {key} | {_md_bool(v.get('schema_ok'))} | {v.get('row_count', 0)} | {v.get('path') or ''} |")
    lines.append("")
    lines.append("## Candidate scan summary")
    lines.append("")
    lines.append(f"- CME schema-ready candidate count: `{d['cme_candidate_ready_count']}`")
    lines.append(f"- News blackout-ready candidate count: `{d['news_blackout_ready_candidate_count']}`")
    lines.append(f"- Partial/schema-only news candidate count: `{d['partial_news_candidate_count']}`")
    lines.append("")
    lines.append("## Acquisition tasks")
    lines.append("")
    if summary["acquisition_tasks"]:
        lines.append("| key | canonical_path | required_columns | next_action |")
        lines.append("| :-- | :-- | :-- | :-- |")
        for t in summary["acquisition_tasks"]:
            lines.append(f"| {t['key']} | {t['canonical_path']} | {t['required_columns']} | {t['next_action']} |")
    else:
        lines.append("No remaining P0 acquisition tasks. Proceed to Stage45B2 alignment audit.")
    lines.append("")
    lines.append("## Rationale")
    lines.append("")
    for r in d["rationale"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for item in d["not_allowed"]:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use this step to rescue Stage41/42/43 rows. After P0 validates, the next valid step is a predefined alignment audit, not a candidate rescue pass.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--repo-root", default=".", help="Repository root. Default: current directory.")
    ap.add_argument("--outdir", default=OUTDIR_DEFAULT, help="Output directory relative to repo root.")
    ap.add_argument("--print-summary", action="store_true", help="Print compact JSON summary.")
    args = ap.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    build_summary(repo_root=repo_root, outdir=Path(args.outdir), print_summary=args.print_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
