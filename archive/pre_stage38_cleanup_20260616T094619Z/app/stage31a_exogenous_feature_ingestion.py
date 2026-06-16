#!/usr/bin/env python3
"""
Stage31A External/Macro/News Feature Ingestion for XAUUSD research.

Research/shadow only. No trading, no order generation.

Purpose:
- Consume Stage30A ML meta dataset.
- Look for manually supplied exogenous CSVs under data/exogenous.
- Normalize and backward-join daily/hourly exogenous features to candidate events.
- Export an enriched ML dataset for Stage31B.
- If exogenous files are missing, create templates and a readiness report.

No internet fetch is performed here. Data files are research inputs only.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path.cwd()
REPORT_DIR = ROOT / "data" / "reports" / "stage31a_exogenous_feature_ingestion"
DEFAULT_DATASET = ROOT / "data" / "reports" / "stage30a_candidate_pool_builder_ml_dataset" / "stage30a_ml_meta_dataset.csv"
EXOG_DIR = ROOT / "data" / "exogenous"

RESEARCH_GUARDRAILS = [
    "Research/shadow feature ingestion only.",
    "No EA change, no automatic trading, no paper/live/order authorization.",
    "Consumes Stage30A ML dataset and manually supplied exogenous CSVs only.",
    "No external internet fetch is performed by this stage.",
    "Existing trade artifacts remain research evidence only, not market-data fallback.",
    "All joined exogenous values use asof/backward joins only: no future values are allowed.",
]

# Expected exogenous input file names. Users may add any subset.
EXPECTED_SOURCES = {
    "dxy": {
        "filename": "dxy.csv",
        "description": "US Dollar Index or broad USD proxy. Columns: timestamp/date, close/value.",
    },
    "us10y": {
        "filename": "us10y.csv",
        "description": "US 10-year Treasury yield proxy. Columns: timestamp/date, close/value.",
    },
    "real_yield": {
        "filename": "real_yield.csv",
        "description": "US real yield / TIPS proxy. Columns: timestamp/date, close/value.",
    },
    "vix": {
        "filename": "vix.csv",
        "description": "VIX or risk-off proxy. Columns: timestamp/date, close/value.",
    },
    "spx": {
        "filename": "spx.csv",
        "description": "S&P 500 or equity-risk proxy. Columns: timestamp/date, close/value.",
    },
    "oil": {
        "filename": "oil.csv",
        "description": "WTI/Brent/oil proxy. Columns: timestamp/date, close/value.",
    },
    "calendar_events": {
        "filename": "calendar_events.csv",
        "description": "Macro/news event calendar. Columns: timestamp, event, importance(optional), currency(optional).",
    },
}

TIME_CANDIDATES = ["timestamp", "time", "datetime", "date", "Date", "Time", "Datetime"]
VALUE_CANDIDATES = ["close", "Close", "value", "Value", "price", "Price", "last", "Last", "yield", "Yield"]


def _now_utc_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def _to_utc_series(s: pd.Series) -> pd.Series:
    ts = pd.to_datetime(s, utc=True, errors="coerce")
    return ts


def _pick_col(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols_list = list(cols)
    lower_map = {c.lower(): c for c in cols_list}
    for cand in candidates:
        if cand in cols_list:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _safe_pf(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    pos = vals[vals > 0].sum()
    neg = -vals[vals < 0].sum()
    if neg <= 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def _metrics(df: pd.DataFrame, net_col: str = "net_x4") -> Dict[str, float]:
    """Return stable x4/x6 metrics even when optional columns are absent.

    Stage31A may be run before real exogenous sources are supplied. In that
    template/missing-data path, feature-quality rows can be sparse. Always
    returning the same metric keys keeps markdown/CSV generation crash-safe.
    """
    empty_metrics: Dict[str, float] = {
        "events": 0,
        "pf_x4": 0.0,
        "pf_x6": 0.0,
        "total_x4": 0.0,
        "total_x6": 0.0,
        "win_rate_x4": 0.0,
        "median_x4": 0.0,
    }
    if df.empty or net_col not in df.columns:
        return empty_metrics.copy()
    vals = pd.to_numeric(df[net_col], errors="coerce").dropna()
    if vals.empty:
        return empty_metrics.copy()
    pf4 = _safe_pf(vals)
    metrics: Dict[str, float] = {
        "events": int(len(vals)),
        "pf_x4": round(pf4, 6) if math.isfinite(pf4) else float("inf"),
        "pf_x6": 0.0,
        "total_x4": round(float(vals.sum()), 6),
        "total_x6": 0.0,
        "win_rate_x4": round(float((vals > 0).mean()), 6),
        "median_x4": round(float(vals.median()), 6),
    }
    if "net_x6" in df.columns:
        vals6 = pd.to_numeric(df["net_x6"], errors="coerce").dropna()
        if not vals6.empty:
            pf6 = _safe_pf(vals6)
            metrics["pf_x6"] = round(pf6, 6) if math.isfinite(pf6) else float("inf")
            metrics["total_x6"] = round(float(vals6.sum()), 6)
    return metrics


def ensure_dirs() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    EXOG_DIR.mkdir(parents=True, exist_ok=True)


def create_templates() -> List[Dict[str, str]]:
    created = []
    for key, meta in EXPECTED_SOURCES.items():
        path = EXOG_DIR / meta["filename"]
        if path.exists():
            continue
        if key == "calendar_events":
            tpl = pd.DataFrame(
                [
                    {
                        "timestamp": "2026-01-01T13:30:00Z",
                        "event": "example_cpi_or_fomc_or_nfp",
                        "importance": "high",
                        "currency": "USD",
                    }
                ]
            )
        else:
            tpl = pd.DataFrame(
                [
                    {"timestamp": "2026-01-01T00:00:00Z", "close": 100.0},
                    {"timestamp": "2026-01-02T00:00:00Z", "close": 100.5},
                ]
            )
        tpl.to_csv(path, index=False)
        created.append({"source": key, "path": str(path), "status": "template_created"})
    return created




def _is_numeric_template(df: pd.DataFrame, time_col: str, val_col: str) -> bool:
    """Detect the example files Stage31A creates itself.

    This prevents a first run with untouched templates from being reported as
    real exogenous data.
    """
    if len(df) != 2:
        return False
    times = [str(x) for x in df[time_col].tolist()]
    vals = pd.to_numeric(df[val_col], errors="coerce").tolist()
    return (
        times == ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]
        and len(vals) == 2
        and abs(float(vals[0]) - 100.0) < 1e-9
        and abs(float(vals[1]) - 100.5) < 1e-9
    )


def _is_calendar_template(df: pd.DataFrame, time_col: str) -> bool:
    if len(df) != 1 or "event" not in df.columns:
        return False
    return str(df[time_col].iloc[0]) == "2026-01-01T13:30:00Z" and str(df["event"].iloc[0]) == "example_cpi_or_fomc_or_nfp"


def load_base_dataset(path: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    info: Dict[str, object] = {"dataset_path": str(path), "loaded": False}
    if not path.exists():
        info["error"] = "dataset_not_found"
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        info["error"] = "dataset_empty_no_columns"
        info["loaded"] = False
        info["rows_raw"] = 0
        info["columns"] = []
        return pd.DataFrame(), info
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"dataset_read_error: {exc!r}"
        info["loaded"] = False
        return pd.DataFrame(), info
    if df.empty or len(df.columns) == 0:
        info.update({"loaded": False, "rows_raw": int(len(df)), "columns": list(df.columns), "error": "dataset_empty"})
        return pd.DataFrame(), info
    info.update({"loaded": True, "rows_raw": int(len(df)), "columns": list(df.columns)})
    time_col = _pick_col(
        df.columns,
        [
            "entry_ts_norm",
            "entry_time",
            "entry_ts",
            "signal_time",
            "opened_ts",
            "ts_utc",
            "time_utc",
            "timestamp_utc",
            "timestamp",
            "datetime",
            "date",
            "time",
        ],
    )
    if time_col is None:
        info["error"] = "no_entry_time_column"
        return pd.DataFrame(), info
    info["time_column_used"] = time_col
    df["entry_ts_norm"] = _to_utc_series(df[time_col])
    before = len(df)
    df = df.dropna(subset=["entry_ts_norm"]).copy()
    info["rows_after_time_parse"] = int(len(df))
    info["rows_dropped_bad_time"] = int(before - len(df))
    if "net_x4" in df.columns:
        df["net_x4"] = pd.to_numeric(df["net_x4"], errors="coerce")
    return df.sort_values("entry_ts_norm"), info


def load_numeric_exogenous(key: str, path: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    info: Dict[str, object] = {"source": key, "path": str(path), "exists": path.exists(), "loaded": False}
    if not path.exists():
        info["status"] = "missing"
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        info.update({"status": "read_error", "error": repr(exc)})
        return pd.DataFrame(), info
    info["rows_raw"] = int(len(df))
    time_col = _pick_col(df.columns, TIME_CANDIDATES)
    val_col = _pick_col(df.columns, VALUE_CANDIDATES)
    if time_col is None or val_col is None:
        info.update({"status": "missing_required_columns", "time_col": time_col, "value_col": val_col, "columns": list(df.columns)})
        return pd.DataFrame(), info
    if _is_numeric_template(df, time_col, val_col):
        info.update({"status": "template_present", "loaded": False, "time_col": time_col, "value_col": val_col, "rows_loaded": 0})
        return pd.DataFrame(), info
    out = pd.DataFrame({"timestamp": _to_utc_series(df[time_col]), f"{key}_value": pd.to_numeric(df[val_col], errors="coerce")})
    out = out.dropna(subset=["timestamp", f"{key}_value"]).sort_values("timestamp")
    out = out.drop_duplicates(subset=["timestamp"], keep="last")
    if out.empty:
        info.update({"status": "empty_after_parse", "time_col": time_col, "value_col": val_col})
        return out, info
    val = out[f"{key}_value"]
    out[f"{key}_ret_1"] = val.pct_change()
    out[f"{key}_ret_5"] = val.pct_change(5)
    out[f"{key}_chg_1"] = val.diff()
    out[f"{key}_chg_5"] = val.diff(5)
    roll = val.rolling(60, min_periods=20)
    out[f"{key}_z60"] = (val - roll.mean()) / roll.std(ddof=0).replace(0, np.nan)
    out[f"{key}_rank250"] = val.rolling(250, min_periods=50).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    info.update(
        {
            "loaded": True,
            "status": "loaded",
            "time_col": time_col,
            "value_col": val_col,
            "rows_loaded": int(len(out)),
            "span": f"{out['timestamp'].min()} → {out['timestamp'].max()}",
        }
    )
    return out, info


def load_calendar_events(path: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    info: Dict[str, object] = {"source": "calendar_events", "path": str(path), "exists": path.exists(), "loaded": False}
    if not path.exists():
        info["status"] = "missing"
        return pd.DataFrame(), info
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        info.update({"status": "read_error", "error": repr(exc)})
        return pd.DataFrame(), info
    time_col = _pick_col(df.columns, TIME_CANDIDATES)
    if time_col is None:
        info.update({"status": "missing_timestamp", "columns": list(df.columns)})
        return pd.DataFrame(), info
    if _is_calendar_template(df, time_col):
        info.update({"status": "template_present", "loaded": False, "rows_loaded": 0})
        return pd.DataFrame(), info
    out = df.copy()
    out["event_ts"] = _to_utc_series(out[time_col])
    out = out.dropna(subset=["event_ts"]).sort_values("event_ts")
    info.update({"loaded": not out.empty, "status": "loaded" if not out.empty else "empty_after_parse", "rows_loaded": int(len(out))})
    return out, info


def asof_join_numeric(base: pd.DataFrame, exog: pd.DataFrame, key: str) -> pd.DataFrame:
    if exog.empty:
        return base
    if base.empty or "entry_ts_norm" not in base.columns:
        # GitHub workflow can refresh FRED before a Stage30A dataset exists.
        # In that case Stage31A should produce a readiness report, not crash.
        return base
    b = base.sort_values("entry_ts_norm").copy()
    e = exog.sort_values("timestamp").copy()
    joined = pd.merge_asof(b, e, left_on="entry_ts_norm", right_on="timestamp", direction="backward")
    if "timestamp" in joined.columns:
        joined = joined.rename(columns={"timestamp": f"{key}_asof_ts"})
    joined[f"{key}_age_hours"] = (joined["entry_ts_norm"] - joined[f"{key}_asof_ts"]).dt.total_seconds() / 3600.0
    return joined


def add_calendar_features(base: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    out["macro_event_within_2h"] = 0
    out["macro_event_within_6h"] = 0
    out["macro_event_within_24h"] = 0
    if events.empty or out.empty or "entry_ts_norm" not in out.columns:
        return out
    ev = events["event_ts"].sort_values().to_numpy(dtype="datetime64[ns]")
    entries = out["entry_ts_norm"].to_numpy(dtype="datetime64[ns]")
    for hours, col in [(2, "macro_event_within_2h"), (6, "macro_event_within_6h"), (24, "macro_event_within_24h")]:
        # nearest event before or after, no outcome leakage: event timestamps are known schedule inputs.
        window = np.timedelta64(hours, "h")
        idx = np.searchsorted(ev, entries)
        flags = np.zeros(len(out), dtype=bool)
        prev_idx = idx - 1
        valid_prev = prev_idx >= 0
        flags[valid_prev] |= (entries[valid_prev] - ev[prev_idx[valid_prev]]) <= window
        valid_next = idx < len(ev)
        flags[valid_next] |= (ev[idx[valid_next]] - entries[valid_next]) <= window
        out[col] = flags.astype(int)
    return out


def feature_quality(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    if df.empty or "net_x4" not in df.columns:
        return pd.DataFrame(rows)
    base = _metrics(df)
    candidate_cols = [c for c in df.columns if any(c.endswith(suf) for suf in ["_value", "_ret_1", "_ret_5", "_chg_1", "_chg_5", "_z60", "_rank250", "_age_hours"])]
    candidate_cols += [c for c in ["macro_event_within_2h", "macro_event_within_6h", "macro_event_within_24h"] if c in df.columns]
    for col in candidate_cols:
        vals = pd.to_numeric(df[col], errors="coerce")
        coverage = float(vals.notna().mean()) if len(vals) else 0.0
        if coverage < 0.2:
            rows.append({"feature": col, "gate": "", "status": "low_coverage", "coverage": round(coverage, 4)})
            continue
        if set(vals.dropna().unique()).issubset({0, 1}):
            for val in [1, 0]:
                mask = vals == val
                sub = df[mask]
                if len(sub) < max(50, int(0.01 * len(df))):
                    continue
                m = _metrics(sub)
                rows.append({"feature": col, "gate": f"{col}=={val}", "status": "binary", "coverage": round(coverage, 4), **m})
            continue
        clean = vals.dropna()
        for q, side in [(0.2, "le"), (0.3, "le"), (0.7, "ge"), (0.8, "ge")]:
            thr = float(clean.quantile(q))
            mask = vals <= thr if side == "le" else vals >= thr
            sub = df[mask]
            if len(sub) < max(50, int(0.01 * len(df))):
                continue
            m = _metrics(sub)
            rows.append(
                {
                    "feature": col,
                    "gate": f"{col}_{side}_q{int(q*100)}",
                    "status": "numeric_quantile",
                    "coverage": round(coverage, 4),
                    "threshold": round(thr, 8),
                    **m,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Some rows are diagnostics such as low_coverage and intentionally do not
    # contain metrics. Add missing metric columns before scoring so the report
    # is robust in template/missing-data runs.
    for col in ["pf_x4", "pf_x6", "total_x4", "total_x6", "win_rate_x4", "median_x4", "events"]:
        if col not in out.columns:
            out[col] = 0.0
    out["rank_score"] = (
        pd.to_numeric(out["pf_x4"], errors="coerce").replace(np.inf, 10.0).fillna(0)
        + pd.to_numeric(out["pf_x6"], errors="coerce").replace(np.inf, 10.0).fillna(0)
        + (pd.to_numeric(out["total_x4"], errors="coerce").fillna(0) / 100.0)
    )
    return out.sort_values("rank_score", ascending=False)



def _df_to_markdown_safe(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Render a small dataframe as markdown without requiring optional tabulate."""
    if df is None or df.empty:
        return ""
    preview = df.head(max_rows).copy()
    try:
        return preview.to_markdown(index=False)
    except Exception:
        cols = [str(c) for c in preview.columns]
        rows = []
        rows.append("| " + " | ".join(cols) + " |")
        rows.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for _, row in preview.iterrows():
            vals = []
            for c in preview.columns:
                val = row.get(c, "")
                if pd.isna(val):
                    val = ""
                text = str(val).replace("|", "\\|").replace("\n", " ")
                vals.append(text)
            rows.append("| " + " | ".join(vals) + " |")
        return "\n".join(rows)

def write_markdown(report: Dict[str, object], source_manifest: pd.DataFrame, fq: pd.DataFrame) -> None:
    md = []
    md.append("# Stage31A External/Macro/News Feature Ingestion\n")
    md.append(f"Generated UTC: `{_now_utc_iso()}`\n")
    md.append("## Decision\n")
    md.append("```text\n" + str(report["decision"]) + "\n```\n")
    md.append("## Scope guardrails\n")
    for item in RESEARCH_GUARDRAILS:
        md.append(f"- {item}")
    md.append("")
    md.append("## Base dataset\n")
    md.append("```json\n" + json.dumps(report.get("dataset_info", {}), indent=2, ensure_ascii=False, default=str) + "\n```\n")
    md.append("## Counts\n")
    for k, v in report.get("counts", {}).items():
        md.append(f"- {k}: `{v}`")
    md.append("")
    md.append("## Source manifest\n")
    if source_manifest.empty:
        md.append("No source manifest rows.")
    else:
        md.append(_df_to_markdown_safe(source_manifest, max_rows=50))
    md.append("")
    md.append("## Feature quality sample\n")
    if fq.empty:
        md.append("No feature quality rows. Add exogenous CSVs to `data/exogenous/` and rerun Stage31A.")
    else:
        md.append(_df_to_markdown_safe(fq, max_rows=30))
    md.append("")
    md.append("## Interpretation\n")
    md.append("- Stage31A does not create a tradable strategy; it only builds an exogenous-feature dataset for Stage31B.")
    md.append("- Missing source files are not an error; templates are created under `data/exogenous/`.")
    md.append("- All numerical joins are backward/asof joins, so event rows do not receive future exogenous values.")
    md.append("- Calendar event proximity features are schedule-based proxies and still require careful validation before use.")
    md.append("")
    md.append("## Operational reminder\n")
    md.append("```bash\ncd ~/Desktop/xauusd-trader\npython3 -m app.stage31a_exogenous_feature_ingestion\n```\n")
    md.append("## Output files\n")
    for p in report.get("output_files", []):
        md.append(f"- `{p}`")
    (REPORT_DIR / "stage31a_exogenous_feature_ingestion.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    dataset_path = Path(os.environ.get("STAGE31A_DATASET", str(DEFAULT_DATASET)))
    template_rows = create_templates()
    base, dataset_info = load_base_dataset(dataset_path)

    source_rows: List[Dict[str, object]] = []
    if template_rows:
        source_rows.extend(template_rows)

    enriched = base.copy()
    numeric_loaded = 0
    for key, meta in EXPECTED_SOURCES.items():
        path = EXOG_DIR / meta["filename"]
        if key == "calendar_events":
            events, info = load_calendar_events(path)
            source_rows.append(info)
            enriched = add_calendar_features(enriched, events)
            continue
        exog, info = load_numeric_exogenous(key, path)
        source_rows.append(info)
        if not exog.empty:
            numeric_loaded += 1
            enriched = asof_join_numeric(enriched, exog, key)

    # Feature quality is only meaningful if base loaded.
    fq = feature_quality(enriched)
    source_manifest = pd.DataFrame(source_rows)

    enriched_path = REPORT_DIR / "stage31a_exogenous_ml_dataset.csv"
    source_path = REPORT_DIR / "stage31a_exogenous_source_manifest.csv"
    fq_path = REPORT_DIR / "stage31a_exogenous_feature_quality.csv"
    json_path = REPORT_DIR / "stage31a_exogenous_feature_ingestion.json"
    md_path = REPORT_DIR / "stage31a_exogenous_feature_ingestion.md"

    enriched.to_csv(enriched_path, index=False)
    source_manifest.to_csv(source_path, index=False)
    fq.to_csv(fq_path, index=False)

    non_template_loaded = [r for r in source_rows if r.get("status") == "loaded"]
    if not dataset_info.get("loaded"):
        decision = "STAGE31A_BASE_DATASET_MISSING_REVIEW_ONLY"
    elif len(non_template_loaded) == 0:
        decision = "STAGE31A_EXTERNAL_DATA_MISSING_TEMPLATES_CREATED_REVIEW_ONLY"
    else:
        decision = "STAGE31A_EXOGENOUS_FEATURE_DATASET_READY_FOR_STAGE31B_REVIEW_ONLY"

    report = {
        "decision": decision,
        "scope_guardrails": RESEARCH_GUARDRAILS,
        "dataset_info": dataset_info,
        "counts": {
            "base_rows": int(len(base)),
            "enriched_rows": int(len(enriched)),
            "expected_source_count": len(EXPECTED_SOURCES),
            "sources_loaded": len(non_template_loaded),
            "numeric_sources_loaded": numeric_loaded,
            "templates_created_this_run": len(template_rows),
            "feature_quality_rows": int(len(fq)),
            "output_feature_cols": int(len([c for c in enriched.columns if c not in base.columns])),
        },
        "output_files": [str(json_path), str(md_path), str(enriched_path), str(source_path), str(fq_path)],
    }
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(report, source_manifest, fq)


if __name__ == "__main__":
    main()
