#!/usr/bin/env python3
"""
Stage45B1A_EXTERNAL_CONTEXT_IMPORT_VALIDATE

Normalize and validate externally acquired context CSV files for the XAUUSD project.
This script does not create signals, does not shortlist candidates, and never promotes
archived rows. It only prepares P0 external context datasets for a later alignment audit.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "pandas is required for Stage45B1A. Install project requirements before running. "
        f"Original import error: {exc}"
    )

STAGE = "Stage45B1A_EXTERNAL_CONTEXT_IMPORT_VALIDATE"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    priority: str
    output_path: str
    required_for: str
    canonical_columns: Tuple[str, ...]
    required_any: Tuple[Tuple[str, ...], ...]
    aliases: Dict[str, Tuple[str, ...]]
    min_rows: int
    notes: str


COMMON_TIMESTAMP_ALIASES = (
    "timestamp", "datetime", "date", "time", "utc_time", "ts", "time_utc", "datetime_utc",
)

SPECS: Dict[str, DatasetSpec] = {
    "dxy": DatasetSpec(
        key="dxy",
        label="US Dollar Index / DXY proxy",
        priority="P0_REQUIRED",
        output_path="data/external/dxy.csv",
        required_for="macro_context_core",
        canonical_columns=("timestamp", "open", "high", "low", "close", "volume", "source"),
        required_any=(("timestamp", "close"),),
        aliases={
            "timestamp": COMMON_TIMESTAMP_ALIASES,
            "open": ("open", "o"),
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c", "last", "price", "px_last", "value", "adj_close", "adjclose"),
            "volume": ("volume", "vol"),
            "source": ("source", "vendor"),
        },
        min_rows=100,
        notes="Daily DXY/USD-index proxy. Intraday is acceptable but not required.",
    ),
    "us10y_yield": DatasetSpec(
        key="us10y_yield",
        label="US 10-year Treasury yield",
        priority="P0_REQUIRED",
        output_path="data/external/us10y_yield.csv",
        required_for="macro_context_core",
        canonical_columns=("timestamp", "yield", "close", "source"),
        required_any=(("timestamp", "yield"), ("timestamp", "close")),
        aliases={
            "timestamp": COMMON_TIMESTAMP_ALIASES,
            "yield": ("yield", "rate", "value", "us10y", "us10y_yield", "dgs10", "close", "price", "last"),
            "close": ("close", "price", "last", "value", "yield", "rate", "dgs10"),
            "source": ("source", "vendor"),
        },
        min_rows=100,
        notes="Daily nominal 10Y yield. Keep percent-vs-decimal semantics documented in source.",
    ),
    "cme_gc_reference": DatasetSpec(
        key="cme_gc_reference",
        label="CME GC/MGC futures reference feed",
        priority="P0_REQUIRED",
        output_path="data/reference/cme_gc.csv",
        required_for="reference_feed_core",
        canonical_columns=("timestamp", "open", "high", "low", "close", "volume", "contract", "source"),
        required_any=(("timestamp", "open", "high", "low", "close"),),
        aliases={
            "timestamp": COMMON_TIMESTAMP_ALIASES,
            "open": ("open", "o"),
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c", "settle", "settlement", "last", "price", "px_last"),
            "volume": ("volume", "vol"),
            "contract": ("contract", "symbol", "ticker"),
            "source": ("source", "vendor"),
        },
        min_rows=100,
        notes="GC/MGC reference feed. If continuous futures are used, document roll method separately.",
    ),
    "news_calendar": DatasetSpec(
        key="news_calendar",
        label="High-impact macro news calendar",
        priority="P0_REQUIRED",
        output_path="data/external/news_calendar.csv",
        required_for="news_blackout_core",
        canonical_columns=("timestamp", "event", "currency", "impact", "category", "actual", "forecast", "previous", "source"),
        required_any=(("timestamp", "event"),),
        aliases={
            "timestamp": ("timestamp", "datetime", "date", "time", "event_time", "utc_time"),
            "event": ("event", "name", "indicator", "title", "release"),
            "currency": ("currency", "ccy", "country"),
            "impact": ("impact", "importance", "priority"),
            "category": ("category", "type"),
            "actual": ("actual",),
            "forecast": ("forecast", "consensus"),
            "previous": ("previous", "prior"),
            "source": ("source", "vendor"),
        },
        min_rows=10,
        notes="High-impact US macro calendar. UTC timestamp preferred; date-only is accepted but flagged.",
    ),
    "us02y_yield": DatasetSpec(
        key="us02y_yield",
        label="US 2-year Treasury yield",
        priority="P1_OPTIONAL",
        output_path="data/external/us02y_yield.csv",
        required_for="macro_context_optional",
        canonical_columns=("timestamp", "yield", "close", "source"),
        required_any=(("timestamp", "yield"), ("timestamp", "close")),
        aliases={
            "timestamp": COMMON_TIMESTAMP_ALIASES,
            "yield": ("yield", "rate", "value", "us2y", "us02y", "dgs2", "close", "price", "last"),
            "close": ("close", "price", "last", "value", "yield", "rate", "dgs2"),
            "source": ("source", "vendor"),
        },
        min_rows=100,
        notes="Optional rate-expectation/curve context.",
    ),
    "real_yield": DatasetSpec(
        key="real_yield",
        label="US real yield / TIPS proxy",
        priority="P1_OPTIONAL",
        output_path="data/external/real_yield.csv",
        required_for="macro_context_optional",
        canonical_columns=("timestamp", "yield", "close", "source"),
        required_any=(("timestamp", "yield"), ("timestamp", "close")),
        aliases={
            "timestamp": COMMON_TIMESTAMP_ALIASES,
            "yield": ("yield", "rate", "value", "real_yield", "tips", "dfii10", "close", "price", "last"),
            "close": ("close", "price", "last", "value", "yield", "rate", "dfii10"),
            "source": ("source", "vendor"),
        },
        min_rows=100,
        notes="Optional but strategically useful for gold context.",
    ),
}

P0_KEYS = ("dxy", "us10y_yield", "cme_gc_reference", "news_calendar")


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _find_col(columns: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    normalized_map = {_norm_col(c): c for c in columns}
    for alias in aliases:
        key = _norm_col(alias)
        if key in normalized_map:
            return normalized_map[key]
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
        cleaned = cleaned.replace({"": None, "nan": None, "None": None})
        return pd.to_numeric(cleaned, errors="coerce")
    return pd.to_numeric(series, errors="coerce")


def _profile_numeric(series: pd.Series) -> Optional[Dict[str, Any]]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return None
    qs = vals.quantile([0.1, 0.5, 0.9]).to_dict()
    return {
        "n": int(vals.shape[0]),
        "min": float(vals.min()),
        "p10": float(qs.get(0.1, math.nan)),
        "median": float(qs.get(0.5, math.nan)),
        "p90": float(qs.get(0.9, math.nan)),
        "max": float(vals.max()),
        "mean": float(vals.mean()),
    }


def _parse_timestamp(series: pd.Series) -> Tuple[pd.Series, Dict[str, Any]]:
    raw = series.astype(str).str.strip()
    # pandas will parse date-only strings as midnight. This is acceptable for daily context,
    # but the report flags how many raw values look date-only.
    date_only = raw.str.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{4}/\d{1,2}/\d{1,2}", na=False)
    parsed = pd.to_datetime(raw, errors="coerce", utc=True)
    meta = {
        "raw_count": int(raw.shape[0]),
        "parsed_count": int(parsed.notna().sum()),
        "date_only_like_count": int(date_only.sum()),
        "date_only_like_pct": float(date_only.mean() * 100.0) if raw.shape[0] else 0.0,
    }
    return parsed, meta


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in ("utf-8", "utf-8-sig", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as exc:  # try next encoding / dialect
            last_error = exc
    # Try semi-colon separated export.
    try:
        return pd.read_csv(path, sep=";")
    except Exception as exc:
        last_error = exc
    raise RuntimeError(f"Could not read CSV {path}: {last_error}")


def _normalize_df(spec: DatasetSpec, raw: pd.DataFrame, source_default: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    columns = list(raw.columns)
    output = pd.DataFrame()
    alias_used: Dict[str, Optional[str]] = {}
    timestamp_meta: Dict[str, Any] = {}

    for canonical in spec.canonical_columns:
        source_col = _find_col(columns, spec.aliases.get(canonical, (canonical,)))
        alias_used[canonical] = source_col
        if source_col is None:
            output[canonical] = pd.NA
        else:
            output[canonical] = raw[source_col]

    if "timestamp" in output.columns:
        parsed, timestamp_meta = _parse_timestamp(output["timestamp"])
        output["timestamp"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        output.loc[parsed.isna(), "timestamp"] = pd.NA

    for col in ("open", "high", "low", "close", "volume", "yield", "actual", "forecast", "previous"):
        if col in output.columns:
            output[col] = _to_numeric(output[col])

    if spec.key in ("us10y_yield", "us02y_yield", "real_yield"):
        if "yield" in output.columns and "close" in output.columns:
            if output["yield"].isna().all() and not output["close"].isna().all():
                output["yield"] = output["close"]
            if output["close"].isna().all() and not output["yield"].isna().all():
                output["close"] = output["yield"]

    if "source" in output.columns:
        output["source"] = output["source"].astype("object")
        output.loc[output["source"].isna() | (output["source"].astype(str).str.strip() == ""), "source"] = source_default

    if "event" in output.columns:
        output["event"] = output["event"].astype("object")

    # Drop completely empty rows after timestamp normalization.
    if "timestamp" in output.columns:
        output = output[output["timestamp"].notna()].copy()

    # Keep stable column order.
    output = output[list(spec.canonical_columns)]

    meta = {
        "input_columns": columns,
        "alias_used": alias_used,
        "timestamp_parse": timestamp_meta,
        "rows_after_timestamp_clean": int(len(output)),
    }
    return output, meta


def _validate_normalized(spec: DatasetSpec, df: pd.DataFrame) -> Dict[str, Any]:
    columns = list(df.columns)
    missing_sets = []
    required_ok = False
    for req_set in spec.required_any:
        missing = [c for c in req_set if c not in columns or df[c].notna().sum() == 0]
        missing_sets.append({"required_set": list(req_set), "missing_or_empty": missing})
        if not missing:
            required_ok = True

    row_count = int(len(df))
    timestamp_parsed = pd.to_datetime(df.get("timestamp", pd.Series(dtype=str)), errors="coerce", utc=True)
    valid_ts = int(timestamp_parsed.notna().sum())
    start = timestamp_parsed.min().isoformat() if valid_ts else None
    end = timestamp_parsed.max().isoformat() if valid_ts else None

    value_col = None
    for c in ("yield", "close", "event"):
        if c in df.columns and df[c].notna().sum() > 0:
            value_col = c
            break

    numeric_profiles: Dict[str, Any] = {}
    for c in ("open", "high", "low", "close", "yield", "volume"):
        if c in df.columns:
            prof = _profile_numeric(df[c])
            if prof:
                numeric_profiles[c] = prof

    if spec.key == "news_calendar":
        event_non_empty = int(df.get("event", pd.Series(dtype=object)).astype(str).str.strip().replace("<NA>", "").ne("").sum())
        value_ok = event_non_empty > 0
    else:
        value_ok = bool(numeric_profiles)

    schema_ok = required_ok and row_count >= spec.min_rows and valid_ts > 0 and value_ok
    return {
        "key": spec.key,
        "label": spec.label,
        "priority": spec.priority,
        "output_path": spec.output_path,
        "schema_ok": bool(schema_ok),
        "required_ok": bool(required_ok),
        "row_count": row_count,
        "min_rows": spec.min_rows,
        "valid_timestamp_count": valid_ts,
        "timestamp_column": "timestamp" if "timestamp" in columns else None,
        "value_column": value_col,
        "start": start,
        "end": end,
        "columns": columns,
        "required_set_checks": missing_sets,
        "numeric_profiles": numeric_profiles,
        "notes": spec.notes,
    }


def _write_csv(df: pd.DataFrame, path: Path, overwrite: bool) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return {"written": False, "path": str(path), "reason": "exists_and_overwrite_false"}
    if path.exists() and overwrite:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return {"written": True, "path": str(path), "reason": "created_or_overwritten"}


def _load_existing_or_import(
    spec: DatasetSpec,
    repo_root: Path,
    import_path: Optional[str],
    overwrite: bool,
    source_default: str,
) -> Dict[str, Any]:
    output_path = repo_root / spec.output_path
    result: Dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "priority": spec.priority,
        "import_path": import_path,
        "output_path": str(output_path),
        "import_attempted": bool(import_path),
        "import_result": None,
        "normalize_meta": None,
        "validation": None,
        "error": None,
    }

    try:
        if import_path:
            raw_path = Path(os.path.expanduser(import_path)).resolve()
            if not raw_path.exists():
                raise FileNotFoundError(f"Input file not found: {raw_path}")
            raw = _read_csv_flexible(raw_path)
            normalized, meta = _normalize_df(spec, raw, source_default=source_default)
            result["normalize_meta"] = meta
            result["import_result"] = _write_csv(normalized, output_path, overwrite=overwrite)
            df_to_validate = normalized
            if result["import_result"]["written"] is False and output_path.exists():
                df_to_validate = _read_csv_flexible(output_path)
        elif output_path.exists():
            df_to_validate = _read_csv_flexible(output_path)
        else:
            result["validation"] = {
                "key": spec.key,
                "label": spec.label,
                "priority": spec.priority,
                "output_path": str(output_path),
                "schema_ok": False,
                "required_ok": False,
                "row_count": 0,
                "min_rows": spec.min_rows,
                "valid_timestamp_count": 0,
                "timestamp_column": None,
                "value_column": None,
                "start": None,
                "end": None,
                "columns": [],
                "required_set_checks": [
                    {"required_set": list(req), "missing_or_empty": list(req)} for req in spec.required_any
                ],
                "numeric_profiles": {},
                "notes": spec.notes,
            }
            return result

        # If an existing user file has arbitrary columns, normalize in-memory for validation but do not write unless imported.
        if set(df_to_validate.columns) != set(spec.canonical_columns):
            normalized_existing, meta = _normalize_df(spec, df_to_validate, source_default=source_default)
            result["normalize_meta"] = result.get("normalize_meta") or meta
            df_to_validate = normalized_existing
        result["validation"] = _validate_normalized(spec, df_to_validate)
    except Exception as exc:
        result["error"] = str(exc)
        result["validation"] = {
            "key": spec.key,
            "label": spec.label,
            "priority": spec.priority,
            "output_path": str(output_path),
            "schema_ok": False,
            "required_ok": False,
            "row_count": 0,
            "min_rows": spec.min_rows,
            "valid_timestamp_count": 0,
            "timestamp_column": None,
            "value_column": None,
            "start": None,
            "end": None,
            "columns": [],
            "required_set_checks": [],
            "numeric_profiles": {},
            "notes": spec.notes,
        }
    return result


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = dict(data)
            data["exists"] = True
            data["path"] = str(path)
            return data
        return {"exists": True, "path": str(path), "error": "not_a_json_object"}
    except Exception as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}


def _write_inventory_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key", "label", "priority", "output_path", "import_attempted", "import_path",
        "schema_ok", "row_count", "start", "end", "value_column", "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            val = row.get("validation") or {}
            writer.writerow({
                "key": row.get("key"),
                "label": row.get("label"),
                "priority": row.get("priority"),
                "output_path": row.get("output_path"),
                "import_attempted": row.get("import_attempted"),
                "import_path": row.get("import_path"),
                "schema_ok": val.get("schema_ok"),
                "row_count": val.get("row_count"),
                "start": val.get("start"),
                "end": val.get("end"),
                "value_column": val.get("value_column"),
                "error": row.get("error"),
            })


def _write_written_files_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["key", "written", "path", "reason"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            res = row.get("import_result") or {}
            if res:
                writer.writerow({
                    "key": row.get("key"),
                    "written": res.get("written"),
                    "path": res.get("path"),
                    "reason": res.get("reason"),
                })


def _markdown(summary: Dict[str, Any]) -> str:
    decision = summary["decision"]
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    for k in ("promotion", "EA", "paper_live", "live", "recommended_next_stage"):
        lines.append(f"{k} = {decision.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45B1A only imports, normalizes, and validates external context files. It does not create signals, shortlist candidates, or promote archived rows.")
    lines.append("")
    lines.append("## P0 readiness")
    lines.append("")
    lines.append("| key | schema_ok | row_count | start | end | output_path |")
    lines.append("| :-- | :-- | --: | :-- | :-- | :-- |")
    for row in summary["inventory"]:
        if row.get("key") not in P0_KEYS:
            continue
        val = row.get("validation") or {}
        lines.append(
            f"| {row.get('key')} | {val.get('schema_ok')} | {val.get('row_count')} | "
            f"{val.get('start') or ''} | {val.get('end') or ''} | {row.get('output_path')} |"
        )
    lines.append("")
    lines.append("## Optional readiness")
    lines.append("")
    lines.append("| key | schema_ok | row_count | output_path |")
    lines.append("| :-- | :-- | --: | :-- |")
    for row in summary["inventory"]:
        if row.get("key") in P0_KEYS:
            continue
        val = row.get("validation") or {}
        lines.append(f"| {row.get('key')} | {val.get('schema_ok')} | {val.get('row_count')} | {row.get('output_path')} |")
    lines.append("")
    lines.append("## Imports performed")
    lines.append("")
    lines.append("| key | import_attempted | written | path | reason |")
    lines.append("| :-- | :-- | :-- | :-- | :-- |")
    for row in summary["inventory"]:
        res = row.get("import_result") or {}
        if row.get("import_attempted") or res:
            lines.append(
                f"| {row.get('key')} | {row.get('import_attempted')} | {res.get('written', '')} | "
                f"{res.get('path', '')} | {res.get('reason', '')} |"
            )
    if not any(r.get("import_attempted") for r in summary["inventory"]):
        lines.append("| none | False |  |  | validation-only run |")
    lines.append("")
    lines.append("## Decision rationale")
    lines.append("")
    for item in decision.get("rationale", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Next command pattern")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 scripts/stage45b1a_external_context_import_validate.py \\")
    lines.append("  --dxy ~/Downloads/xauusd_external_context/dxy.csv \\")
    lines.append("  --us10y ~/Downloads/xauusd_external_context/us10y_yield.csv \\")
    lines.append("  --cme-gc ~/Downloads/xauusd_external_context/cme_gc.csv \\")
    lines.append("  --news-calendar ~/Downloads/xauusd_external_context/news_calendar.csv \\")
    lines.append("  --overwrite --print-summary")
    lines.append("```")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for item in decision.get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use imported external data to rescue Stage41/42/43 rows post hoc. After P0 files validate, the only valid next step is a predefined alignment audit.")
    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".", help="Repository root. Default: current directory.")
    p.add_argument("--stage45b1-summary", default="reports/stage45b1/stage45b1_external_context_data_acquisition_plan_summary.json")
    p.add_argument("--outdir", default="reports/stage45b1a")
    p.add_argument("--source-default", default="manual_import")
    p.add_argument("--overwrite", action="store_true", help="Overwrite canonical output files if import paths are provided.")
    p.add_argument("--print-summary", action="store_true")
    p.add_argument("--dxy", default=None, help="Input CSV path for DXY/USD-index proxy.")
    p.add_argument("--us10y", default=None, help="Input CSV path for US 10Y yield.")
    p.add_argument("--cme-gc", default=None, help="Input CSV path for CME GC/MGC reference feed.")
    p.add_argument("--news-calendar", default=None, help="Input CSV path for high-impact macro calendar.")
    p.add_argument("--us02y", default=None, help="Optional input CSV path for US 2Y yield.")
    p.add_argument("--real-yield", default=None, help="Optional input CSV path for US real yield/TIPS proxy.")
    return p


def run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = (repo_root / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    imports = {
        "dxy": args.dxy,
        "us10y_yield": args.us10y,
        "cme_gc_reference": args.cme_gc,
        "news_calendar": args.news_calendar,
        "us02y_yield": args.us02y,
        "real_yield": args.real_yield,
    }

    inventory: List[Dict[str, Any]] = []
    for key in ("dxy", "us10y_yield", "cme_gc_reference", "news_calendar", "us02y_yield", "real_yield"):
        inventory.append(
            _load_existing_or_import(
                SPECS[key],
                repo_root=repo_root,
                import_path=imports.get(key),
                overwrite=bool(args.overwrite),
                source_default=args.source_default,
            )
        )

    p0_ok = [row["key"] for row in inventory if row["key"] in P0_KEYS and (row.get("validation") or {}).get("schema_ok")]
    p0_missing = [key for key in P0_KEYS if key not in p0_ok]
    optional_ok = [row["key"] for row in inventory if row["key"] not in P0_KEYS and (row.get("validation") or {}).get("schema_ok")]

    decision = {
        "status": "EXTERNAL_CONTEXT_P0_READY" if not p0_missing else "EXTERNAL_CONTEXT_P0_NOT_READY",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "p0_required_keys": list(P0_KEYS),
        "p0_schema_ok_keys": p0_ok,
        "p0_missing_or_invalid_keys": p0_missing,
        "optional_schema_ok_keys": optional_ok,
        "recommended_next_stage": "Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT" if not p0_missing else "Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION",
        "rationale": [
            "P0 external context files validate successfully; the next step is alignment auditing." if not p0_missing else "P0 external context files are still missing or schema-invalid; continue acquisition/import.",
            "This step only normalizes and validates external files; it does not authorize candle-only scans or candidate rescue.",
        ],
        "not_allowed": [
            "candidate_rescue_from_stage41_42_43",
            "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
            "EA_paper_live_live_from_archived_rows",
            "ML_before_robust_cost_aware_baseline",
            "new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned",
        ],
    }

    stage45b1_path = repo_root / args.stage45b1_summary
    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "stage45b1_summary_path": str(stage45b1_path),
            "outdir": str(outdir),
            "overwrite": bool(args.overwrite),
            "source_default": args.source_default,
        },
        "stage45b1_reference": _safe_read_json(stage45b1_path),
        "inventory": inventory,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": decision["recommended_next_stage"],
    }

    summary_path = outdir / "stage45b1a_external_context_import_validate_summary.json"
    md_path = outdir / "stage45b1a_external_context_import_validate.md"
    inventory_path = outdir / "stage45b1a_external_context_inventory.csv"
    written_path = outdir / "stage45b1a_normalized_files_written.csv"

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    md_path.write_text(_markdown(summary), encoding="utf-8")
    _write_inventory_csv(inventory, inventory_path)
    _write_written_files_csv(inventory, written_path)

    if args.print_summary:
        compact = {
            "stage": STAGE,
            "status": decision["status"],
            "p0_schema_ok_keys": decision["p0_schema_ok_keys"],
            "p0_missing_or_invalid_keys": decision["p0_missing_or_invalid_keys"],
            "next_allowed_step": decision["recommended_next_stage"],
            "summary_path": str(summary_path),
            "markdown_path": str(md_path),
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
