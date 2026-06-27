#!/usr/bin/env python3
"""
Stage104 Event-Surprise Dataset Readiness Builder.

Focused, no-order event-surprise frontier stage. It inventories local event
calendar/export files, normalizes rows with event time + actual + consensus,
computes lag-safe same-event surprise z-scores, and decides whether the event
surprise frontier is ready for Stage105 thesis discovery.

It never changes MT5/EA files, never connects to a broker, and never authorizes
orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

STAGE = "Stage104_EVENT_SURPRISE_DATASET_READINESS"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_MT5_OR_EA_CHANGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE104",
    "NO_THRESHOLD_TUNING_FROM_STAGE104_DATA_BUILDER",
]

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}

DATE_COLS = [
    "event_time_utc", "release_time_utc", "datetime_utc", "timestamp_utc",
    "datetime", "timestamp", "date_time", "date", "event_date", "release_date",
]
TIME_COLS = ["time", "event_time", "release_time", "time_utc"]
EVENT_COLS = ["event_type", "event", "event_name", "name", "title", "indicator", "calendar_event"]
ACTUAL_COLS = ["actual", "actual_value", "release_actual", "value", "latest"]
CONSENSUS_COLS = ["consensus", "forecast", "estimate", "expected", "survey", "consensus_value"]
PREVIOUS_COLS = ["previous", "prior", "prev", "previous_value"]
COUNTRY_COLS = ["country", "region", "economy"]
CURRENCY_COLS = ["currency", "ccy"]
IMPACT_COLS = ["impact", "importance", "priority", "volatility"]

EVENT_TYPE_ALIASES = {
    "CPI": ["cpi", "consumer price", "inflation rate", "core cpi"],
    "PCE": ["pce", "personal consumption", "core pce"],
    "NFP": ["nonfarm", "non-farm", "nfp", "payroll", "employment change"],
    "FOMC": ["fomc", "fed interest", "federal funds", "rate decision", "fed rate", "federal reserve"],
    "ISM": ["ism", "pmi", "purchasing managers"],
    "RetailSales": ["retail sales"],
    "JoblessClaims": ["jobless", "unemployment claims", "initial claims"],
    "GDP": ["gdp", "gross domestic product"],
    "PPI": ["ppi", "producer price"],
    "JOLTS": ["jolts", "job openings"],
    "UnemploymentRate": ["unemployment rate"],
    "ConsumerConfidence": ["consumer confidence", "michigan sentiment", "consumer sentiment"],
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand_path(root: Path, value: str) -> Path:
    value = os.path.expanduser(os.path.expandvars(str(value)))
    p = Path(value)
    return p if p.is_absolute() else root / p


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_col(c: Any) -> str:
    s = str(c).strip().lower()
    s = s.replace("<", "").replace(">", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def sniff_sep(path: Path) -> str:
    sample = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
    if sample.count("\t") > sample.count(",") and sample.count("\t") > sample.count(";"):
        return "\t"
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def read_table(path: Path, max_rows: Optional[int] = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, nrows=max_rows)
    else:
        sep = sniff_sep(path)
        try:
            df = pd.read_csv(path, sep=sep, nrows=max_rows, engine="python")
        except Exception:
            df = pd.read_csv(path, sep=None, nrows=max_rows, engine="python")
    df.columns = [normalize_col(c) for c in df.columns]
    return df


def first_present(cols: Iterable[str], candidates: Sequence[str]) -> Optional[str]:
    colset = set(cols)
    for c in candidates:
        nc = normalize_col(c)
        if nc in colset:
            return nc
    return None


def parse_numeric_one(x: Any) -> float:
    if pd.isna(x):
        return math.nan
    text = str(x).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-", "--"}:
        return math.nan
    lower = text.lower()
    for token in ["prelim", "final", "revised", "adv", "flash", "sa", "mom", "yoy"]:
        lower = lower.replace(token, " ")
    neg = False
    if lower.startswith("(") and lower.endswith(")"):
        neg = True
        lower = lower[1:-1]
    lower = lower.replace(",", "").replace("%", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", lower)
    if not m:
        return math.nan
    val = float(m.group(0))
    suffix = lower[m.end():].strip()[:1]
    if suffix == "k":
        val *= 1_000.0
    elif suffix == "m":
        val *= 1_000_000.0
    elif suffix == "b":
        val *= 1_000_000_000.0
    return -val if neg else val


def parse_numeric_series(s: pd.Series) -> pd.Series:
    return s.map(parse_numeric_one).astype(float)


def parse_event_datetime(df: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[pd.Series, str, str]:
    tz_name = str(cfg.get("assume_naive_timezone", "UTC"))
    source_note = ""
    # Prefer explicit datetime/timestamp columns.
    for c in DATE_COLS:
        nc = normalize_col(c)
        if nc not in df.columns:
            continue
        # If it is a pure date column and separate time exists, handle later.
        if nc in {"date", "event_date", "release_date"}:
            continue
        dt = pd.to_datetime(df[nc], errors="coerce", utc=True)
        if dt.notna().sum() > 0:
            return dt, nc, "explicit_or_utc_datetime"

    date_col = first_present(df.columns, ["date", "event_date", "release_date", "date_utc"])
    time_col = first_present(df.columns, TIME_COLS)
    if date_col and time_col:
        raw = df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip()
        dt_naive = pd.to_datetime(raw, errors="coerce")
        if dt_naive.notna().sum() > 0:
            # Localize naive values under explicit configured assumption, then convert to UTC.
            try:
                zone = ZoneInfo(tz_name)
                dt = dt_naive.dt.tz_localize(zone, nonexistent="shift_forward", ambiguous="NaT").dt.tz_convert("UTC")
                source_note = f"date_time_localized_as_{tz_name}"
            except Exception:
                dt = pd.to_datetime(raw, errors="coerce", utc=True)
                source_note = "date_time_forced_utc_due_timezone_error"
            return dt, f"{date_col}+{time_col}", source_note

    if date_col:
        dt = pd.to_datetime(df[date_col], errors="coerce", utc=True)
        if dt.notna().sum() > 0:
            return dt, date_col, "date_only_utc_midnight"

    empty = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    return empty, "", "missing_datetime"


def standardize_event_type(x: Any) -> str:
    text = str(x).strip().lower()
    for event_type, needles in EVENT_TYPE_ALIASES.items():
        if any(n in text for n in needles):
            return event_type
    cleaned = re.sub(r"\s+", " ", str(x).strip())
    return cleaned[:64] if cleaned else "UNKNOWN"


def is_us_row(country: Any, currency: Any) -> bool:
    text = f"{country} {currency}".strip().lower()
    if not text:
        return True
    return any(tok in text for tok in ["us", "usa", "united states", "usd", "america"])


def impact_rank(x: Any) -> int:
    text = str(x).lower().strip()
    if any(t in text for t in ["high", "3", "red", "important", "strong"]):
        return 3
    if any(t in text for t in ["medium", "2", "orange", "moderate"]):
        return 2
    if any(t in text for t in ["low", "1", "yellow", "weak"]):
        return 1
    return 0


def rolling_z_asof_by_type(df: pd.DataFrame, value_col: str, window: int, min_periods: int) -> pd.Series:
    out = pd.Series(math.nan, index=df.index, dtype=float)
    for _, idx in df.groupby("event_type", sort=False).groups.items():
        idx_list = list(idx)
        s = df.loc[idx_list, value_col].reset_index(drop=True)
        prior_mean = s.shift(1).rolling(window=window, min_periods=min_periods).mean()
        prior_std = s.shift(1).rolling(window=window, min_periods=min_periods).std(ddof=0).replace(0, math.nan)
        z = (s - prior_mean) / prior_std
        out.loc[idx_list] = z.values
    return out


def discover_files(root: Path, cfg: Dict[str, Any]) -> List[Path]:
    paths = cfg.get("event_search_paths", [])
    patterns = cfg.get("event_patterns", ["*.csv", "*.tsv", "*.txt", "*.xlsx", "*.xls"])
    ignore_parts = [str(x).lower() for x in cfg.get("ignore_path_fragments", [])]
    seen = set()
    out: List[Path] = []
    for base_raw in paths:
        base = expand_path(root, base_raw)
        if not base.exists():
            continue
        for pat in patterns:
            for p in base.glob(pat):
                if not p.is_file() or p.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                low = str(p).lower()
                if any(part in low for part in ignore_parts):
                    continue
                key = str(p.resolve())
                if key not in seen:
                    seen.add(key)
                    out.append(p)
    return sorted(out, key=lambda p: str(p).lower())


def normalize_event_file(path: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "read_ok": False,
        "ready_schema": False,
        "rows": 0,
        "normalized_rows": 0,
        "accepted_rows": 0,
        "issue": None,
    }
    try:
        df = read_table(path)
        meta["read_ok"] = True
        meta["rows"] = int(len(df))
        meta["columns"] = list(df.columns)
        meta["sha256"] = sha256_file(path)
    except Exception as e:
        meta["issue"] = f"read_error:{type(e).__name__}:{e}"
        return pd.DataFrame(), meta

    event_col = first_present(df.columns, EVENT_COLS)
    actual_col = first_present(df.columns, ACTUAL_COLS)
    consensus_col = first_present(df.columns, CONSENSUS_COLS)
    previous_col = first_present(df.columns, PREVIOUS_COLS)
    country_col = first_present(df.columns, COUNTRY_COLS)
    currency_col = first_present(df.columns, CURRENCY_COLS)
    impact_col = first_present(df.columns, IMPACT_COLS)
    event_time, event_time_source, tz_note = parse_event_datetime(df, cfg)
    meta["mapped_event_col"] = event_col
    meta["mapped_actual_col"] = actual_col
    meta["mapped_consensus_col"] = consensus_col
    meta["mapped_event_time_source"] = event_time_source
    meta["timezone_note"] = tz_note

    if not (event_col and actual_col and consensus_col) or event_time.notna().sum() == 0:
        meta["issue"] = (
            f"missing_required_columns event={event_col} actual={actual_col} "
            f"consensus={consensus_col} datetime_ok={int(event_time.notna().sum())}"
        )
        return pd.DataFrame(), meta

    out = pd.DataFrame()
    out["event_time_utc"] = event_time
    out["available_after_utc"] = event_time
    out["event_date_utc"] = out["event_time_utc"].dt.normalize()
    out["event_type"] = df[event_col].map(standardize_event_type)
    out["event_name_raw"] = df[event_col].astype(str)
    out["country"] = df[country_col].astype(str) if country_col else "US"
    out["currency"] = df[currency_col].astype(str) if currency_col else "USD"
    out["impact"] = df[impact_col].astype(str) if impact_col else "UNKNOWN"
    out["impact_rank"] = out["impact"].map(impact_rank).astype(int)
    out["actual"] = parse_numeric_series(df[actual_col])
    out["consensus"] = parse_numeric_series(df[consensus_col])
    out["previous"] = parse_numeric_series(df[previous_col]) if previous_col else math.nan
    out["surprise"] = out["actual"] - out["consensus"]
    out["surprise_pct_consensus"] = out["surprise"] / out["consensus"].replace(0, math.nan).abs()
    out["is_us_event"] = [is_us_row(c, u) for c, u in zip(out["country"], out["currency"])]
    accepted_types = set(cfg.get("accepted_event_types", []))
    out["accepted_event_type"] = out["event_type"].isin(accepted_types) if accepted_types else True
    min_impact = int(cfg.get("min_impact_rank", 0))
    out["accepted_event"] = out["is_us_event"] & out["accepted_event_type"] & (out["impact_rank"] >= min_impact)
    out["source_file"] = str(path)
    out = out.dropna(subset=["event_time_utc", "actual", "consensus", "surprise"])
    out = out.sort_values("event_time_utc").reset_index(drop=True)
    if len(out):
        out["surprise_z_asof"] = rolling_z_asof_by_type(
            out,
            "surprise",
            int(cfg.get("event_z_window", 60)),
            int(cfg.get("event_z_min_periods", 12)),
        )
        out["abs_surprise_z_asof"] = out["surprise_z_asof"].abs()
        out["surprise_direction"] = out["surprise"].map(lambda v: "positive" if v > 0 else ("negative" if v < 0 else "zero"))
    else:
        out["surprise_z_asof"] = []
        out["abs_surprise_z_asof"] = []
        out["surprise_direction"] = []

    meta["normalized_rows"] = int(len(out))
    meta["accepted_rows"] = int(out["accepted_event"].sum()) if len(out) else 0
    meta["ready_schema"] = bool(len(out) > 0)
    meta["min_time_utc"] = str(out["event_time_utc"].min()) if len(out) else None
    meta["max_time_utc"] = str(out["event_time_utc"].max()) if len(out) else None
    meta["zscore_non_null"] = int(out["surprise_z_asof"].notna().sum()) if len(out) else 0
    return out, meta


def write_template(root: Path, cfg: Dict[str, Any]) -> str:
    template_dir = expand_path(root, cfg.get("template_dir", "data/frontier_templates"))
    template_dir.mkdir(parents=True, exist_ok=True)
    p = template_dir / "stage104_event_surprise_raw_template.csv"
    if not p.exists():
        pd.DataFrame(columns=[
            "event_time_utc", "date", "time", "country", "currency", "impact", "event",
            "actual", "consensus", "previous",
        ]).to_csv(p, index=False)
    return str(p)


def build_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage104 Event-Surprise Dataset Readiness",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Event dataset",
        f"- event_file_count: `{summary['event_file_count']}`",
        f"- ready_file_count: `{summary['ready_file_count']}`",
        f"- normalized_rows: `{summary['normalized_rows']}`",
        f"- accepted_rows: `{summary['accepted_rows']}`",
        f"- zscore_non_null: `{summary['zscore_non_null']}`",
        f"- min_event_time_utc: `{summary['min_event_time_utc']}`",
        f"- max_event_time_utc: `{summary['max_event_time_utc']}`",
        "",
        "## Selected next stage",
        f"- `{summary['selected_next_stage']}`",
        "",
        "## Issues",
    ]
    if summary.get("issues"):
        lines.extend([f"- `{x}`" for x in summary["issues"]])
    else:
        lines.append("- none")
    lines += ["", "## Outputs"]
    for k, v in summary["outputs"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Hard blocks"]
    lines.extend([f"- `{x}`" for x in summary["hard_blocks"]])
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = read_json(expand_path(root, args.config))
    out_dir = expand_path(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    template_path = write_template(root, cfg)

    files = discover_files(root, cfg)
    frames: List[pd.DataFrame] = []
    inventory: List[Dict[str, Any]] = []
    for p in files:
        norm, meta = normalize_event_file(p, cfg)
        inventory.append(meta)
        if meta.get("ready_schema") and len(norm):
            frames.append(norm)

    output_dir = expand_path(root, cfg.get("output_data_dir", "data/external_frontiers"))
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / "event_surprise_normalized.csv"

    if frames:
        all_events = pd.concat(frames, ignore_index=True).sort_values("event_time_utc")
        all_events = all_events.drop_duplicates(
            subset=["event_time_utc", "event_type", "actual", "consensus"], keep="last"
        ).reset_index(drop=True)
        # Recompute z-scores across the consolidated dataset to avoid per-file fragmentation.
        all_events["surprise_z_asof"] = rolling_z_asof_by_type(
            all_events,
            "surprise",
            int(cfg.get("event_z_window", 60)),
            int(cfg.get("event_z_min_periods", 12)),
        )
        all_events["abs_surprise_z_asof"] = all_events["surprise_z_asof"].abs()
    else:
        all_events = pd.DataFrame(columns=[
            "event_time_utc", "available_after_utc", "event_date_utc", "event_type",
            "event_name_raw", "country", "currency", "impact", "impact_rank", "actual",
            "consensus", "previous", "surprise", "surprise_pct_consensus", "is_us_event",
            "accepted_event_type", "accepted_event", "source_file", "surprise_z_asof",
            "abs_surprise_z_asof", "surprise_direction",
        ])

    all_events.to_csv(normalized_path, index=False)
    inventory_path = out_dir / "stage104_event_file_inventory.csv"
    pd.DataFrame(inventory).to_csv(inventory_path, index=False)

    accepted = all_events[all_events.get("accepted_event", False) == True] if len(all_events) else all_events
    min_rows = int(cfg.get("min_event_rows", 300))
    min_accepted = int(cfg.get("min_accepted_rows", 200))
    min_z = int(cfg.get("min_zscore_non_null", 100))
    z_non_null = int(all_events["surprise_z_asof"].notna().sum()) if "surprise_z_asof" in all_events.columns else 0
    accepted_rows = int(all_events["accepted_event"].sum()) if "accepted_event" in all_events.columns else 0
    ready = len(all_events) >= min_rows and accepted_rows >= min_accepted and z_non_null >= min_z

    issues: List[str] = []
    if not files:
        issues.append("NO_EVENT_FILES_FOUND")
    if len(all_events) < min_rows:
        issues.append(f"NORMALIZED_ROWS_TOO_LOW:{len(all_events)}<{min_rows}")
    if accepted_rows < min_accepted:
        issues.append(f"ACCEPTED_ROWS_TOO_LOW:{accepted_rows}<{min_accepted}")
    if z_non_null < min_z:
        issues.append(f"ZSCORE_NON_NULL_TOO_LOW:{z_non_null}<{min_z}")

    event_type_counts_path = out_dir / "stage104_event_type_counts.csv"
    if len(all_events):
        counts = all_events.groupby("event_type", dropna=False).agg(
            rows=("event_type", "size"),
            accepted_rows=("accepted_event", "sum"),
            zscore_non_null=("surprise_z_asof", lambda s: int(s.notna().sum())),
            min_time=("event_time_utc", "min"),
            max_time=("event_time_utc", "max"),
        ).reset_index().sort_values(["accepted_rows", "rows"], ascending=False)
    else:
        counts = pd.DataFrame(columns=["event_type", "rows", "accepted_rows", "zscore_non_null", "min_time", "max_time"])
    counts.to_csv(event_type_counts_path, index=False)

    requirements_path = out_dir / "stage104_event_data_requirements.csv"
    pd.DataFrame([
        {
            "required_group": "datetime",
            "accepted_columns": "event_time_utc OR date+time",
            "note": f"Naive date+time localized as {cfg.get('assume_naive_timezone', 'UTC')} before UTC conversion.",
        },
        {"required_group": "event", "accepted_columns": ",".join(EVENT_COLS), "note": "Mapped to event_type."},
        {"required_group": "actual", "accepted_columns": ",".join(ACTUAL_COLS), "note": "Numeric parser supports %, K/M/B."},
        {"required_group": "consensus", "accepted_columns": ",".join(CONSENSUS_COLS), "note": "Required for surprise."},
        {"required_group": "optional", "accepted_columns": "previous,country,currency,impact", "note": "Used for filtering and context."},
    ]).to_csv(requirements_path, index=False)

    if ready:
        decision = "STAGE104_EVENT_SURPRISE_DATASET_READY_FOR_STAGE105_THESIS_DISCOVERY_NO_ORDER"
        classification = "S104_EVENT_SURPRISE_DATASET_READY"
        disposition = "EVENT_SURPRISE_READY_FOR_THESIS_DISCOVERY"
        selected_next_stage = "Stage105_EVENT_SURPRISE_THESIS_DISCOVERY"
    else:
        decision = "STAGE104_EVENT_SURPRISE_DATASET_NOT_READY_NO_ORDER"
        classification = "S104_EVENT_SURPRISE_DATASET_NOT_READY"
        disposition = "SUPPLY_OR_FIX_EVENT_SURPRISE_DATA_BEFORE_THESIS_DISCOVERY"
        selected_next_stage = "DATA_SUPPLY_OR_SCHEMA_FIX_REQUIRED"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(expand_path(root, args.config)),
        "generated_utc": utc_now_iso(),
        "status": "STAGE104_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Build a lag-safe event-surprise dataset before event-thesis discovery. No order, broker, MT5, EA, paper-live, or live change.",
        "event_file_count": len(files),
        "ready_file_count": int(sum(1 for x in inventory if x.get("ready_schema"))),
        "normalized_rows": int(len(all_events)),
        "accepted_rows": accepted_rows,
        "zscore_non_null": z_non_null,
        "min_event_time_utc": str(all_events["event_time_utc"].min()) if len(all_events) else None,
        "max_event_time_utc": str(all_events["event_time_utc"].max()) if len(all_events) else None,
        "accepted_event_types": cfg.get("accepted_event_types", []),
        "constraints": {
            "min_event_rows": min_rows,
            "min_accepted_rows": min_accepted,
            "min_zscore_non_null": min_z,
            "min_impact_rank": int(cfg.get("min_impact_rank", 0)),
        },
        "selected_next_stage": selected_next_stage,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage104_event_surprise_dataset_readiness_summary.json"),
            "report_md": str(out_dir / "stage104_event_surprise_dataset_readiness_report.md"),
            "normalized_event_csv": str(normalized_path),
            "event_file_inventory_csv": str(inventory_path),
            "event_type_counts_csv": str(event_type_counts_path),
            "data_requirements_csv": str(requirements_path),
            "raw_template_csv": template_path,
        },
    }
    write_json(out_dir / "stage104_event_surprise_dataset_readiness_summary.json", summary)
    (out_dir / "stage104_event_surprise_dataset_readiness_report.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "decision": decision, "normalized_rows": len(all_events), "issues": issues}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
