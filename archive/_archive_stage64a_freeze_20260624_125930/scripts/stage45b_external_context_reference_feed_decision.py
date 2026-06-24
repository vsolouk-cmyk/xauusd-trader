#!/usr/bin/env python3
"""
Stage45B external-context and reference-feed decision for the XAUUSD project.

This script is a decision/inventory audit only. It does not create signals,
shortlists, operational orders, or promotion decisions.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
NO_GO = "NO_GO"

DEFAULT_CONTEXT_SPECS = [
    {
        "key": "dxy",
        "label": "US Dollar Index / DXY proxy",
        "required_for": "macro_context",
        "paths": [
            "data/external/dxy.csv",
            "data/external/DXY.csv",
            "data/external/us_dollar_index.csv",
            "data/external/dxy_daily.csv",
        ],
        "required_columns_any": [["timestamp", "close"], ["date", "close"], ["time", "close"]],
        "notes": "At least daily DXY proxy aligned to UTC; preferably open/high/low/close if available.",
    },
    {
        "key": "us10y_yield",
        "label": "US 10-year Treasury yield",
        "required_for": "macro_context",
        "paths": [
            "data/external/us10y_yield.csv",
            "data/external/us10y.csv",
            "data/external/US10Y.csv",
            "data/external/treasury_10y.csv",
        ],
        "required_columns_any": [["timestamp", "close"], ["date", "close"], ["date", "yield"], ["timestamp", "yield"]],
        "notes": "Gold is materially sensitive to nominal and real yields; daily is acceptable for first context gate.",
    },
    {
        "key": "us02y_yield",
        "label": "US 2-year Treasury yield",
        "required_for": "macro_context_optional",
        "paths": [
            "data/external/us02y_yield.csv",
            "data/external/us2y.csv",
            "data/external/US02Y.csv",
            "data/external/treasury_2y.csv",
        ],
        "required_columns_any": [["timestamp", "close"], ["date", "close"], ["date", "yield"], ["timestamp", "yield"]],
        "notes": "Useful for rate-expectation regime and curve context; optional for first external-context pass.",
    },
    {
        "key": "real_yield",
        "label": "US real yield / TIPS proxy",
        "required_for": "macro_context_optional",
        "paths": [
            "data/external/real_yield.csv",
            "data/external/us10y_real_yield.csv",
            "data/external/tips_10y.csv",
        ],
        "required_columns_any": [["timestamp", "close"], ["date", "close"], ["date", "yield"], ["timestamp", "yield"]],
        "notes": "Strong gold context variable, but can be added after DXY + nominal yields.",
    },
    {
        "key": "cme_gc_reference",
        "label": "CME GC/MGC futures reference feed",
        "required_for": "reference_feed",
        "paths": [
            "data/external/cme_gc.csv",
            "data/external/gc_futures.csv",
            "data/external/GC.csv",
            "data/external/mgc_futures.csv",
            "data/reference/cme_gc.csv",
        ],
        "required_columns_any": [["timestamp", "open", "high", "low", "close"], ["date", "open", "high", "low", "close"]],
        "notes": "Needed to decide whether MT5 CFD feed behavior is broker-specific or market-wide.",
    },
    {
        "key": "news_calendar",
        "label": "High-impact macro news calendar",
        "required_for": "news_blackout_context",
        "paths": [
            "data/external/news_calendar.csv",
            "data/external/high_impact_news.csv",
            "data/external/macro_calendar.csv",
            "data/calendar/news_calendar.csv",
        ],
        "required_columns_any": [["timestamp", "event"], ["datetime", "event"], ["date", "event"], ["timestamp", "name"]],
        "notes": "Must support FOMC/CPI/NFP/US jobs/inflation/rate events and UTC timestamps for blackout tagging.",
    },
    {
        "key": "fomc_calendar",
        "label": "FOMC/rate decision calendar",
        "required_for": "news_blackout_optional",
        "paths": [
            "data/external/fomc_calendar.csv",
            "data/calendar/fomc_calendar.csv",
        ],
        "required_columns_any": [["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        "notes": "Optional if covered by a unified high-impact news calendar.",
    },
    {
        "key": "cpi_calendar",
        "label": "US CPI calendar",
        "required_for": "news_blackout_optional",
        "paths": [
            "data/external/cpi_calendar.csv",
            "data/calendar/cpi_calendar.csv",
        ],
        "required_columns_any": [["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        "notes": "Optional if covered by a unified high-impact news calendar.",
    },
    {
        "key": "nfp_calendar",
        "label": "US employment/NFP calendar",
        "required_for": "news_blackout_optional",
        "paths": [
            "data/external/nfp_calendar.csv",
            "data/calendar/nfp_calendar.csv",
        ],
        "required_columns_any": [["timestamp", "event"], ["datetime", "event"], ["date", "event"]],
        "notes": "Optional if covered by a unified high-impact news calendar.",
    },
]

DATE_COLUMN_CANDIDATES = [
    "timestamp",
    "datetime",
    "utc_time",
    "time",
    "date",
    "source_time",
    "event_time",
]


def _safe_load_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return None, f"missing: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"failed to parse {path}: {exc}"


def _parse_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Fast path for common ISO formats; preserve only the comparable ISO string.
    normalized = text.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            if fmt is None:
                dt = datetime.fromisoformat(normalized)
            else:
                dt = datetime.strptime(text[:10], fmt)
            return dt.isoformat()
        except Exception:
            continue
    return text[:32]


def _norm_col(name: str) -> str:
    return "".join(ch for ch in str(name).strip().lower() if ch.isalnum())


def _columns_satisfy(headers: Sequence[str], required_any: Sequence[Sequence[str]]) -> bool:
    norm_headers = {_norm_col(h) for h in headers}
    for required_set in required_any:
        if all(_norm_col(col) in norm_headers for col in required_set):
            return True
    return False


def _inspect_csv(path: Path, required_any: Sequence[Sequence[str]], max_rows_scan: int = 250000) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "exists": path.exists(),
        "path": str(path),
        "readable": False,
        "columns": [],
        "row_count_scanned": 0,
        "row_count_exact_up_to_scan_limit": None,
        "timestamp_column": None,
        "start": None,
        "end": None,
        "schema_ok": False,
        "error": None,
    }
    if not path.exists():
        return info
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            headers = list(reader.fieldnames or [])
            info["columns"] = headers
            info["schema_ok"] = _columns_satisfy(headers, required_any)
            norm_to_original = {_norm_col(h): h for h in headers}
            timestamp_col = None
            for cand in DATE_COLUMN_CANDIDATES:
                if _norm_col(cand) in norm_to_original:
                    timestamp_col = norm_to_original[_norm_col(cand)]
                    break
            info["timestamp_column"] = timestamp_col
            first_dt: Optional[str] = None
            last_dt: Optional[str] = None
            count = 0
            for row in reader:
                count += 1
                if timestamp_col:
                    parsed = _parse_datetime(row.get(timestamp_col))
                    if parsed:
                        if first_dt is None:
                            first_dt = parsed
                        last_dt = parsed
                if count >= max_rows_scan:
                    break
            info["row_count_scanned"] = count
            info["row_count_exact_up_to_scan_limit"] = count if count < max_rows_scan else f">={max_rows_scan}"
            info["start"] = first_dt
            info["end"] = last_dt
            info["readable"] = True
    except Exception as exc:
        info["error"] = str(exc)
    return info


def _find_first_existing(root: Path, paths: Sequence[str]) -> Optional[Path]:
    for rel in paths:
        p = root / rel
        if p.exists():
            return p
    return None


def _audit_external_inventory(root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    inventory: List[Dict[str, Any]] = []
    required_dataset_spec: List[Dict[str, Any]] = []
    for spec in DEFAULT_CONTEXT_SPECS:
        existing = _find_first_existing(root, spec["paths"])
        inspected = _inspect_csv(existing, spec["required_columns_any"]) if existing else None
        found = inspected is not None and bool(inspected.get("exists"))
        schema_ok = bool(inspected and inspected.get("schema_ok"))
        row = {
            "key": spec["key"],
            "label": spec["label"],
            "required_for": spec["required_for"],
            "found": found,
            "schema_ok": schema_ok,
            "selected_path": str(existing) if existing else None,
            "row_count_scanned": inspected.get("row_count_scanned") if inspected else 0,
            "timestamp_column": inspected.get("timestamp_column") if inspected else None,
            "start": inspected.get("start") if inspected else None,
            "end": inspected.get("end") if inspected else None,
            "columns": inspected.get("columns") if inspected else [],
            "error": inspected.get("error") if inspected else None,
            "candidate_paths": spec["paths"],
            "notes": spec["notes"],
        }
        inventory.append(row)
        required_dataset_spec.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "required_for": spec["required_for"],
                "acceptable_paths": " | ".join(spec["paths"]),
                "required_columns_any": " OR ".join(["+".join(cols) for cols in spec["required_columns_any"]]),
                "notes": spec["notes"],
            }
        )
    return inventory, required_dataset_spec


def _count_ok(inventory: Sequence[Dict[str, Any]], keys: Iterable[str]) -> int:
    keyset = set(keys)
    return sum(1 for row in inventory if row.get("key") in keyset and row.get("found") and row.get("schema_ok"))


def _get_row(inventory: Sequence[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    for row in inventory:
        if row.get("key") == key:
            return row
    return None


def _decide(stage45c: Optional[Dict[str, Any]], inventory: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    macro_core_keys = ["dxy", "us10y_yield"]
    reference_keys = ["cme_gc_reference"]
    news_keys = ["news_calendar", "fomc_calendar", "cpi_calendar", "nfp_calendar"]

    macro_core_ok = _count_ok(inventory, macro_core_keys)
    reference_ok = _count_ok(inventory, reference_keys)
    unified_news = _get_row(inventory, "news_calendar")
    news_ok = bool(unified_news and unified_news.get("found") and unified_news.get("schema_ok")) or _count_ok(inventory, news_keys[1:]) >= 2

    stage45c_recommended = None
    if stage45c:
        stage45c_recommended = (
            stage45c.get("decision", {}).get("recommended_next_stage")
            or stage45c.get("next_allowed_step")
        )

    rationale = [
        "Stage45C found that spread/cost realism alone is not decisive enough to restart candle-only scans.",
        "No Stage41/42/43 candidate is promoted; this branch is direction selection only.",
    ]

    if macro_core_ok < len(macro_core_keys) and reference_ok == 0 and not news_ok:
        status = "EXTERNAL_CONTEXT_DATA_MISSING"
        next_stage = "Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN"
        rationale.append("Core external context is absent or schema-invalid: DXY, US 10Y, reference futures, and/or news calendar must be added before external-context baselines.")
    elif macro_core_ok >= len(macro_core_keys) and reference_ok == 0:
        status = "MACRO_CONTEXT_PRESENT_REFERENCE_FEED_MISSING"
        next_stage = "Stage45B2_REFERENCE_FEED_ALIGNMENT_AUDIT"
        rationale.append("Macro context is present, but a CME GC/MGC or equivalent reference feed is still missing for CFD-vs-market separation.")
    elif macro_core_ok >= len(macro_core_keys) and reference_ok >= 1 and news_ok:
        status = "EXTERNAL_CONTEXT_READY_FOR_PREDEFINED_BASELINE_SCAN"
        next_stage = "Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN"
        rationale.append("Minimum macro, reference-feed, and news-blackout context are available with acceptable schemas.")
    else:
        status = "PARTIAL_EXTERNAL_CONTEXT_PRESENT"
        next_stage = "Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN"
        rationale.append("Some external files are present, but the minimum set is incomplete; fill the missing pieces before Stage46.")

    return {
        "status": status,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "stage45c_recommended_next_stage": stage45c_recommended,
        "macro_core_ok_count": macro_core_ok,
        "macro_core_required_count": len(macro_core_keys),
        "reference_feed_ok_count": reference_ok,
        "news_context_ok": news_ok,
        "recommended_next_stage": next_stage,
        "rationale": rationale,
        "not_allowed": [
            "candidate_rescue_from_stage41_42_43",
            "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
            "EA_paper_live_live_from_archived_rows",
            "ML_before_robust_cost_aware_baseline",
            "new_candle_only_blind_megascan_before_external_context_decision_is_satisfied",
        ],
    }


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            out = {}
            for key in fieldnames:
                value = row.get(key)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                out[key] = value
            writer.writerow(out)


def _markdown_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join([":--" for _ in columns]) + " |"
    body = []
    for row in rows:
        values = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            text = str(val if val is not None else "")
            text = text.replace("|", "\\|").replace("\n", " ")
            if len(text) > 120:
                text = text[:117] + "..."
            values.append(text)
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep] + body)


def _write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    inv_cols = [
        "key",
        "required_for",
        "found",
        "schema_ok",
        "selected_path",
        "row_count_scanned",
        "timestamp_column",
        "start",
        "end",
    ]
    spec_cols = ["key", "required_for", "acceptable_paths", "required_columns_any", "notes"]
    lines = [
        f"# {STAGE}",
        "",
        "## Decision",
        "",
        "```text",
        f"promotion = {summary['promotion']}",
        f"EA = {summary['EA']}",
        f"paper_live = {summary['paper_live']}",
        f"live = {summary['live']}",
        f"recommended_next_stage = {summary['decision']['recommended_next_stage']}",
        "```",
        "",
        "Stage45B is an external-context and reference-feed decision step only. It does not create trading signals, does not shortlist candidates, and cannot promote archived rows.",
        "",
        "## Stage45C reference",
        "",
        "```json",
        json.dumps(summary.get("stage45c_reference", {}), ensure_ascii=False, indent=2)[:5000],
        "```",
        "",
        "## External context inventory",
        "",
        _markdown_table(summary["external_context_inventory"], inv_cols),
        "",
        "## Required dataset specification",
        "",
        _markdown_table(summary["required_dataset_spec"], spec_cols),
        "",
        "## Decision rationale",
        "",
    ]
    for item in summary["decision"].get("rationale", []):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Not allowed",
        "",
    ])
    for item in summary["decision"].get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.extend([
        "",
        "## Anti-overfit note",
        "",
        "Do not use this step to rescue Stage41/42/43 rows. Stage45B can only determine whether the next valid branch is data acquisition, reference-feed alignment, or a pre-defined external-context baseline scan.",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--repo-root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--stage45c-summary", default="reports/stage45c/stage45c_feed_transaction_cost_realism_audit_summary.json")
    parser.add_argument("--outdir", default="reports/stage45b")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    outdir = root / args.outdir
    stage45c_path = root / args.stage45c_summary
    stage45c, stage45c_error = _safe_load_json(stage45c_path)

    inventory, required_dataset_spec = _audit_external_inventory(root)
    decision = _decide(stage45c, inventory)

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(root),
            "stage45c_summary_path": str(stage45c_path),
            "outdir": str(outdir),
        },
        "stage45c_reference": {
            "exists": stage45c is not None,
            "error": stage45c_error,
            "decision_status": stage45c.get("decision", {}).get("status") if stage45c else None,
            "recommended_next_stage": stage45c.get("decision", {}).get("recommended_next_stage") if stage45c else None,
            "next_allowed_step": stage45c.get("next_allowed_step") if stage45c else None,
            "promotion": stage45c.get("promotion") if stage45c else None,
            "EA": stage45c.get("EA") if stage45c else None,
            "paper_live": stage45c.get("paper_live") if stage45c else None,
            "live": stage45c.get("live") if stage45c else None,
        },
        "external_context_inventory": inventory,
        "required_dataset_spec": required_dataset_spec,
        "decision": decision,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": decision["recommended_next_stage"],
    }

    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / "stage45b_external_context_reference_feed_decision_summary.json"
    md_path = outdir / "stage45b_external_context_reference_feed_decision.md"
    inventory_csv_path = outdir / "stage45b_external_context_inventory.csv"
    spec_csv_path = outdir / "stage45b_required_dataset_spec.csv"

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, summary)
    _write_csv(
        inventory_csv_path,
        inventory,
        [
            "key",
            "label",
            "required_for",
            "found",
            "schema_ok",
            "selected_path",
            "row_count_scanned",
            "timestamp_column",
            "start",
            "end",
            "columns",
            "error",
            "candidate_paths",
            "notes",
        ],
    )
    _write_csv(
        spec_csv_path,
        required_dataset_spec,
        ["key", "label", "required_for", "acceptable_paths", "required_columns_any", "notes"],
    )

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": decision["status"],
            "recommended_next_stage": decision["recommended_next_stage"],
            "macro_core_ok_count": decision["macro_core_ok_count"],
            "reference_feed_ok_count": decision["reference_feed_ok_count"],
            "news_context_ok": decision["news_context_ok"],
            "promotion": NO_GO,
            "outputs": {
                "summary": str(summary_path),
                "markdown": str(md_path),
                "inventory_csv": str(inventory_csv_path),
                "required_dataset_spec_csv": str(spec_csv_path),
            },
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
