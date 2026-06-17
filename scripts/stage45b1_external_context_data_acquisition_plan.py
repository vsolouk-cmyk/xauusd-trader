#!/usr/bin/env python3
"""
Stage45B1 external-context data acquisition plan for XAUUSD research.

This script is a planning/validation step only. It does not download data,
create trading signals, rescue archived candidates, or authorize any
operational layer.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN"

DEFAULT_STAGE45B_SUMMARY = Path("reports/stage45b/stage45b_external_context_reference_feed_decision_summary.json")
DEFAULT_OUTDIR = Path("reports/stage45b1")
DEFAULT_TEMPLATE_DIR = Path("data/external/templates")

NO_GO_DECISION = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    required_for: str
    priority: str
    acceptable_paths: List[str]
    required_column_sets: List[List[str]]
    preferred_columns: List[str]
    minimum_granularity: str
    alignment_notes: str
    use_in_next_stage: str
    acquisition_notes: str


DEFAULT_SPECS: List[DatasetSpec] = [
    DatasetSpec(
        key="dxy",
        label="US Dollar Index / DXY proxy",
        required_for="macro_context_core",
        priority="P0_REQUIRED",
        acceptable_paths=[
            "data/external/dxy.csv",
            "data/external/DXY.csv",
            "data/external/us_dollar_index.csv",
            "data/external/dxy_daily.csv",
        ],
        required_column_sets=[["timestamp", "close"], ["date", "close"], ["time", "close"]],
        preferred_columns=["timestamp", "open", "high", "low", "close", "volume", "source"],
        minimum_granularity="daily",
        alignment_notes="Normalize to UTC date/session; forward-fill daily context into intraday XAUUSD bars only after the close/time is known.",
        use_in_next_stage="Dollar regime, DXY slope, DXY momentum, dollar-risk filter.",
        acquisition_notes="Use any reliable historical DXY or broad USD-index proxy export. Keep raw source unchanged and document source/vendor in a source column or README.",
    ),
    DatasetSpec(
        key="us10y_yield",
        label="US 10-year Treasury yield",
        required_for="macro_context_core",
        priority="P0_REQUIRED",
        acceptable_paths=[
            "data/external/us10y_yield.csv",
            "data/external/us10y.csv",
            "data/external/US10Y.csv",
            "data/external/treasury_10y.csv",
        ],
        required_column_sets=[["timestamp", "yield"], ["date", "yield"], ["timestamp", "close"], ["date", "close"]],
        preferred_columns=["timestamp", "yield", "close", "source"],
        minimum_granularity="daily",
        alignment_notes="Normalize percent yield consistently. If file uses close, map it to yield_value during later normalization.",
        use_in_next_stage="Nominal-yield regime, yield slope, yield shock filter.",
        acquisition_notes="Use a consistent daily 10Y yield series. Do not mix percent and decimal formats without documenting conversion.",
    ),
    DatasetSpec(
        key="cme_gc_reference",
        label="CME GC/MGC futures reference feed",
        required_for="reference_feed_core",
        priority="P0_REQUIRED",
        acceptable_paths=[
            "data/external/cme_gc.csv",
            "data/external/gc_futures.csv",
            "data/external/GC.csv",
            "data/external/mgc_futures.csv",
            "data/reference/cme_gc.csv",
        ],
        required_column_sets=[["timestamp", "open", "high", "low", "close"], ["date", "open", "high", "low", "close"]],
        preferred_columns=["timestamp", "open", "high", "low", "close", "volume", "contract", "source"],
        minimum_granularity="daily; intraday preferred if available",
        alignment_notes="If continuous futures are used, document roll method. Use only as reference/context until feed alignment is audited.",
        use_in_next_stage="Broker CFD vs market-wide direction check, gap/reference validation, futures trend context.",
        acquisition_notes="Use a clean continuous GC/MGC reference feed if available. Avoid mixing contracts without a documented continuous-series method.",
    ),
    DatasetSpec(
        key="news_calendar",
        label="High-impact macro news calendar",
        required_for="news_blackout_core",
        priority="P0_REQUIRED",
        acceptable_paths=[
            "data/external/news_calendar.csv",
            "data/external/high_impact_news.csv",
            "data/external/macro_calendar.csv",
            "data/calendar/news_calendar.csv",
        ],
        required_column_sets=[["timestamp", "event"], ["datetime", "event"], ["date", "event"], ["timestamp", "name"]],
        preferred_columns=["timestamp", "event", "currency", "impact", "category", "actual", "forecast", "previous", "source"],
        minimum_granularity="event timestamp; UTC or timezone column required",
        alignment_notes="Convert to UTC. Later blackout windows must be pre-defined, e.g. -2h/+2h or event-type-specific windows.",
        use_in_next_stage="News blackout, event-risk regime, no-trade windows around CPI/FOMC/NFP/jobs/inflation/rate events.",
        acquisition_notes="Calendar must include high-impact US macro events and timestamps. If only date is available, mark time confidence as low.",
    ),
    DatasetSpec(
        key="us02y_yield",
        label="US 2-year Treasury yield",
        required_for="macro_context_optional",
        priority="P1_OPTIONAL",
        acceptable_paths=[
            "data/external/us02y_yield.csv",
            "data/external/us2y.csv",
            "data/external/US02Y.csv",
            "data/external/treasury_2y.csv",
        ],
        required_column_sets=[["timestamp", "yield"], ["date", "yield"], ["timestamp", "close"], ["date", "close"]],
        preferred_columns=["timestamp", "yield", "close", "source"],
        minimum_granularity="daily",
        alignment_notes="Use together with 10Y to build curve and rate-expectation context.",
        use_in_next_stage="Rate-expectation and curve regime.",
        acquisition_notes="Optional for first pass; valuable if easily available alongside 10Y.",
    ),
    DatasetSpec(
        key="real_yield",
        label="US real yield / TIPS proxy",
        required_for="macro_context_optional",
        priority="P1_OPTIONAL",
        acceptable_paths=[
            "data/external/real_yield.csv",
            "data/external/us10y_real_yield.csv",
            "data/external/tips_10y.csv",
        ],
        required_column_sets=[["timestamp", "yield"], ["date", "yield"], ["timestamp", "close"], ["date", "close"]],
        preferred_columns=["timestamp", "yield", "close", "source"],
        minimum_granularity="daily",
        alignment_notes="If added, keep nominal-vs-real-yield semantics explicit.",
        use_in_next_stage="Real-yield pressure context for gold.",
        acquisition_notes="Optional but strategically useful; can be added after DXY and 10Y.",
    ),
    DatasetSpec(
        key="fomc_calendar",
        label="FOMC/rate decision calendar",
        required_for="news_blackout_optional",
        priority="P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL",
        acceptable_paths=["data/external/fomc_calendar.csv", "data/calendar/fomc_calendar.csv"],
        required_column_sets=[["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        preferred_columns=["timestamp", "event", "impact", "source"],
        minimum_granularity="event timestamp preferred; date acceptable with low time confidence",
        alignment_notes="Optional if unified news calendar already covers FOMC/rate events.",
        use_in_next_stage="FOMC blackout and rate-decision event regime.",
        acquisition_notes="Optional supporting calendar.",
    ),
    DatasetSpec(
        key="cpi_calendar",
        label="US CPI calendar",
        required_for="news_blackout_optional",
        priority="P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL",
        acceptable_paths=["data/external/cpi_calendar.csv", "data/calendar/cpi_calendar.csv"],
        required_column_sets=[["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        preferred_columns=["timestamp", "event", "impact", "source"],
        minimum_granularity="event timestamp preferred; date acceptable with low time confidence",
        alignment_notes="Optional if unified news calendar already covers CPI/inflation events.",
        use_in_next_stage="CPI/inflation blackout and event regime.",
        acquisition_notes="Optional supporting calendar.",
    ),
    DatasetSpec(
        key="nfp_calendar",
        label="US employment/NFP calendar",
        required_for="news_blackout_optional",
        priority="P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL",
        acceptable_paths=["data/external/nfp_calendar.csv", "data/calendar/nfp_calendar.csv"],
        required_column_sets=[["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        preferred_columns=["timestamp", "event", "impact", "source"],
        minimum_granularity="event timestamp preferred; date acceptable with low time confidence",
        alignment_notes="Optional if unified news calendar already covers employment/NFP events.",
        use_in_next_stage="NFP/jobs blackout and event regime.",
        acquisition_notes="Optional supporting calendar.",
    ),
]


def _norm_col(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(str(x).strip())
    except Exception:
        return None


def _try_parse_dt(value: str) -> Optional[str]:
    s = str(value).strip()
    if not s:
        return None
    # Keep only date part if simple date; support common ISO-ish exports.
    for candidate in (s, s.replace("Z", "+00:00"), s.split(" ")[0]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt.isoformat()
        except Exception:
            pass
    return s  # Keep raw as fallback for start/end reporting.


def _read_stage45b_summary(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "error": "missing"}
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        obj.setdefault("exists", True)
        obj.setdefault("path", str(path))
        return obj
    except Exception as exc:
        return {"exists": False, "path": str(path), "error": str(exc)}


def _validate_csv(path: Path, spec: DatasetSpec) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "schema_ok": False,
        "row_count": 0,
        "columns": [],
        "normalized_columns": [],
        "matched_required_column_set": None,
        "timestamp_column": None,
        "value_column": None,
        "start": None,
        "end": None,
        "numeric_value_profile": None,
        "error": None,
    }
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                result["error"] = "no_header"
                return result
            columns = list(reader.fieldnames)
            norm_cols = [_norm_col(c) for c in columns]
            result["columns"] = columns
            result["normalized_columns"] = norm_cols
            norm_to_original = {_norm_col(c): c for c in columns}
            for req_set in spec.required_column_sets:
                normalized_req = [_norm_col(c) for c in req_set]
                if all(c in norm_cols for c in normalized_req):
                    result["schema_ok"] = True
                    result["matched_required_column_set"] = req_set
                    break
            timestamp_candidates = ["timestamp", "datetime", "time", "date", "utc_time"]
            value_candidates = ["close", "yield", "value", "price"]
            ts_col = next((norm_to_original[c] for c in timestamp_candidates if c in norm_to_original), None)
            val_col = next((norm_to_original[c] for c in value_candidates if c in norm_to_original), None)
            result["timestamp_column"] = ts_col
            result["value_column"] = val_col
            row_count = 0
            first_ts: Optional[str] = None
            last_ts: Optional[str] = None
            values: List[float] = []
            for row in reader:
                row_count += 1
                if ts_col:
                    parsed = _try_parse_dt(row.get(ts_col, ""))
                    if parsed:
                        if first_ts is None:
                            first_ts = parsed
                        last_ts = parsed
                if val_col:
                    fv = _safe_float(row.get(val_col))
                    if fv is not None:
                        values.append(fv)
            result["row_count"] = row_count
            result["start"] = first_ts
            result["end"] = last_ts
            if values:
                values_sorted = sorted(values)
                def q(p: float) -> float:
                    idx = int(round((len(values_sorted) - 1) * p))
                    return values_sorted[max(0, min(idx, len(values_sorted) - 1))]
                result["numeric_value_profile"] = {
                    "n": len(values_sorted),
                    "min": values_sorted[0],
                    "p10": q(0.10),
                    "median": q(0.50),
                    "p90": q(0.90),
                    "max": values_sorted[-1],
                }
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _inventory_specs(repo_root: Path, specs: Sequence[DatasetSpec]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for spec in specs:
        path_results = []
        selected = None
        for p in spec.acceptable_paths:
            check = _validate_csv(repo_root / p, spec)
            path_results.append(check)
            if check["exists"] and check["schema_ok"] and selected is None:
                selected = check
        rows.append({
            "key": spec.key,
            "label": spec.label,
            "priority": spec.priority,
            "required_for": spec.required_for,
            "found": selected is not None,
            "schema_ok": bool(selected and selected.get("schema_ok")),
            "selected_path": selected.get("path") if selected else None,
            "row_count": selected.get("row_count") if selected else 0,
            "timestamp_column": selected.get("timestamp_column") if selected else None,
            "value_column": selected.get("value_column") if selected else None,
            "start": selected.get("start") if selected else None,
            "end": selected.get("end") if selected else None,
            "matched_required_column_set": selected.get("matched_required_column_set") if selected else None,
            "acceptable_paths": spec.acceptable_paths,
            "required_column_sets": spec.required_column_sets,
            "minimum_granularity": spec.minimum_granularity,
            "alignment_notes": spec.alignment_notes,
            "use_in_next_stage": spec.use_in_next_stage,
            "acquisition_notes": spec.acquisition_notes,
            "path_checks": path_results,
        })
    return rows


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _template_rows_for_spec(spec: DatasetSpec) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = spec.preferred_columns
    if spec.key in {"dxy", "cme_gc_reference"}:
        sample = {c: "" for c in cols}
        sample.update({"timestamp": "2022-05-02T00:00:00Z", "open": "", "high": "", "low": "", "close": "", "source": ""})
    elif "yield" in spec.key or spec.key == "real_yield":
        sample = {c: "" for c in cols}
        sample.update({"timestamp": "2022-05-02", "yield": "", "close": "", "source": ""})
    else:
        sample = {c: "" for c in cols}
        sample.update({"timestamp": "2022-05-02T12:30:00Z", "event": "", "currency": "USD", "impact": "high", "source": ""})
    # Preserve column order and remove keys not in cols.
    return cols, [{c: sample.get(c, "") for c in cols}]


def _write_templates(repo_root: Path, template_dir: Path, specs: Sequence[DatasetSpec]) -> List[Dict[str, Any]]:
    template_root = repo_root / template_dir
    template_root.mkdir(parents=True, exist_ok=True)
    written = []
    for spec in specs:
        cols, rows = _template_rows_for_spec(spec)
        out = template_root / f"{spec.key}_template.csv"
        _write_csv(out, rows, cols)
        written.append({"key": spec.key, "template_path": str(out), "columns": cols})
    readme = template_root / "README.md"
    readme.write_text(
        "# External context CSV templates\n\n"
        "These are schema templates only. Do not treat them as data. "
        "Populate real external context files under `data/external/` or `data/reference/` using the accepted paths in the Stage45B1 report.\n",
        encoding="utf-8",
    )
    written.append({"key": "README", "template_path": str(readme), "columns": []})
    return written


def _make_decision(inventory: Sequence[Dict[str, Any]], stage45b: Dict[str, Any]) -> Dict[str, Any]:
    by_key = {r["key"]: r for r in inventory}
    macro_core_ok = bool(by_key.get("dxy", {}).get("schema_ok")) and bool(by_key.get("us10y_yield", {}).get("schema_ok"))
    reference_ok = bool(by_key.get("cme_gc_reference", {}).get("schema_ok"))
    news_ok = bool(by_key.get("news_calendar", {}).get("schema_ok"))
    p0_keys = [r["key"] for r in inventory if r.get("priority") == "P0_REQUIRED"]
    p0_ok = [k for k in p0_keys if by_key.get(k, {}).get("schema_ok")]
    missing_p0 = [k for k in p0_keys if k not in p0_ok]

    if macro_core_ok and reference_ok and news_ok:
        status = "P0_EXTERNAL_CONTEXT_READY_FOR_ALIGNMENT_AUDIT"
        next_stage = "Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT"
        rationale = [
            "Core macro context, reference feed, and news calendar files are present and schema-valid.",
            "Next step is alignment audit before any external-context baseline scan.",
        ]
    elif macro_core_ok and (reference_ok or news_ok):
        status = "PARTIAL_EXTERNAL_CONTEXT_AVAILABLE_CONTINUE_ACQUISITION"
        next_stage = "Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION"
        rationale = [
            "Some core context is present, but the full P0 set is not complete.",
            "Do not run external-context baselines until DXY, US10Y, CME/reference feed, and high-impact news calendar are all available or explicitly waived in a documented decision.",
        ]
    else:
        status = "EXTERNAL_CONTEXT_DATA_NOT_READY"
        next_stage = "Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION"
        rationale = [
            "Stage45B found external context missing; Stage45B1 confirms the acquisition checklist is not yet satisfied.",
            "New candle-only blind scans remain blocked until external context is acquired and aligned.",
        ]

    return {
        "status": status,
        **NO_GO_DECISION,
        "macro_core_ok": macro_core_ok,
        "reference_feed_ok": reference_ok,
        "news_context_ok": news_ok,
        "p0_required_keys": p0_keys,
        "p0_schema_ok_keys": p0_ok,
        "p0_missing_or_invalid_keys": missing_p0,
        "stage45b_reference_next_allowed_step": stage45b.get("next_allowed_step") or stage45b.get("decision", {}).get("recommended_next_stage"),
        "recommended_next_stage": next_stage,
        "rationale": rationale,
        "not_allowed": [
            "candidate_rescue_from_stage41_42_43",
            "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
            "EA_paper_live_live_from_archived_rows",
            "ML_before_robust_cost_aware_baseline",
            "new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned",
        ],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    inv = summary["external_context_acquisition_inventory"]
    decision = summary["decision"]
    lines: List[str] = []
    lines.append(f"# {STAGE}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    lines.append(f"promotion = {summary['promotion']}")
    lines.append(f"EA = {summary['EA']}")
    lines.append(f"paper_live = {summary['paper_live']}")
    lines.append(f"live = {summary['live']}")
    lines.append(f"recommended_next_stage = {decision['recommended_next_stage']}")
    lines.append("```\n")
    lines.append("Stage45B1 is a data acquisition and schema-readiness plan only. It does not create trading signals, does not shortlist candidates, and cannot promote archived rows.\n")

    lines.append("## Stage45B reference\n")
    ref = summary.get("stage45b_reference", {})
    lines.append("```json")
    lines.append(json.dumps({
        "exists": ref.get("exists", False),
        "stage": ref.get("stage"),
        "next_allowed_step": ref.get("next_allowed_step"),
        "promotion": ref.get("promotion"),
        "EA": ref.get("EA"),
        "paper_live": ref.get("paper_live"),
        "live": ref.get("live"),
    }, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append("## P0 required datasets\n")
    lines.append("| key | found | schema_ok | selected_path | required_for | accepted first path | required columns |")
    lines.append("| :-- | :-- | :-- | :-- | :-- | :-- | :-- |")
    for r in inv:
        if r["priority"] != "P0_REQUIRED":
            continue
        req = " OR ".join(["+".join(x) for x in r["required_column_sets"]])
        first_path = r["acceptable_paths"][0] if r["acceptable_paths"] else ""
        lines.append(f"| {r['key']} | {r['found']} | {r['schema_ok']} | {r.get('selected_path') or ''} | {r['required_for']} | {first_path} | {req} |")
    lines.append("")

    lines.append("## Optional datasets\n")
    lines.append("| key | priority | found | schema_ok | use |")
    lines.append("| :-- | :-- | :-- | :-- | :-- |")
    for r in inv:
        if r["priority"] == "P0_REQUIRED":
            continue
        lines.append(f"| {r['key']} | {r['priority']} | {r['found']} | {r['schema_ok']} | {r['use_in_next_stage']} |")
    lines.append("")

    lines.append("## Minimal acquisition target\n")
    lines.append("```text")
    lines.append("P0_REQUIRED:")
    lines.append("1. data/external/dxy.csv")
    lines.append("2. data/external/us10y_yield.csv")
    lines.append("3. data/external/cme_gc.csv or data/reference/cme_gc.csv")
    lines.append("4. data/external/news_calendar.csv")
    lines.append("```\n")

    lines.append("## Generated templates\n")
    lines.append("| key | template_path | columns |")
    lines.append("| :-- | :-- | :-- |")
    for t in summary.get("templates_written", []):
        lines.append(f"| {t['key']} | {t['template_path']} | {', '.join(t.get('columns') or [])} |")
    lines.append("")

    lines.append("## Decision rationale\n")
    for item in decision.get("rationale", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Not allowed\n")
    for item in decision.get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.append("")

    lines.append("## Anti-overfit note\n")
    lines.append("Do not use this step to rescue Stage41/42/43 rows. Stage45B1 can only define, validate, and track external context data acquisition before any alignment audit or new external-context baseline scan.\n")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    stage45b_path = Path(args.stage45b_summary).expanduser()
    if not stage45b_path.is_absolute():
        stage45b_path = repo_root / stage45b_path
    outdir = Path(args.outdir).expanduser()
    if not outdir.is_absolute():
        outdir = repo_root / outdir
    template_dir = Path(args.template_dir)

    stage45b = _read_stage45b_summary(stage45b_path)
    inventory = _inventory_specs(repo_root, DEFAULT_SPECS)
    templates = _write_templates(repo_root, template_dir, DEFAULT_SPECS)
    decision = _make_decision(inventory, stage45b)

    summary = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "stage45b_summary_path": str(stage45b_path),
            "outdir": str(outdir),
            "template_dir": str(repo_root / template_dir),
        },
        "stage45b_reference": stage45b,
        "external_context_acquisition_inventory": inventory,
        "templates_written": templates,
        "decision": decision,
        **NO_GO_DECISION,
        "next_allowed_step": decision["recommended_next_stage"],
    }

    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / "stage45b1_external_context_data_acquisition_plan_summary.json"
    md_path = outdir / "stage45b1_external_context_data_acquisition_plan.md"
    checklist_path = outdir / "stage45b1_required_dataset_checklist.csv"
    templates_path = outdir / "stage45b1_templates_written.csv"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_markdown(summary), encoding="utf-8")

    checklist_rows = []
    for r in inventory:
        checklist_rows.append({
            "key": r["key"],
            "priority": r["priority"],
            "required_for": r["required_for"],
            "found": r["found"],
            "schema_ok": r["schema_ok"],
            "selected_path": r.get("selected_path") or "",
            "first_acceptable_path": r["acceptable_paths"][0] if r["acceptable_paths"] else "",
            "required_column_sets": " OR ".join(["+".join(x) for x in r["required_column_sets"]]),
            "minimum_granularity": r["minimum_granularity"],
            "acquisition_notes": r["acquisition_notes"],
        })
    _write_csv(checklist_path, checklist_rows, [
        "key", "priority", "required_for", "found", "schema_ok", "selected_path",
        "first_acceptable_path", "required_column_sets", "minimum_granularity", "acquisition_notes",
    ])
    _write_csv(templates_path, templates, ["key", "template_path", "columns"])

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "decision": decision,
            "outputs": {
                "summary": str(summary_path),
                "markdown": str(md_path),
                "checklist": str(checklist_path),
                "templates_written": str(templates_path),
            },
            **NO_GO_DECISION,
        }, indent=2, ensure_ascii=False))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".", help="Repository root. Default: current directory.")
    p.add_argument("--stage45b-summary", default=str(DEFAULT_STAGE45B_SUMMARY), help="Stage45B summary JSON path.")
    p.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output report directory.")
    p.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR), help="Template directory relative to repo root.")
    p.add_argument("--print-summary", action="store_true", help="Print compact summary JSON to stdout.")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
