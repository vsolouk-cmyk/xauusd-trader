#!/usr/bin/env python3
"""
Stage57A context source precheck and derived regime table.

Purpose:
- Inventory context sources available for the XAUUSD broker-real pipeline.
- Derive session/spread/volatility context regimes from the AMarkets broker DB.
- Inspect optional local COT and reference-price/basis artifacts without using them as labels.
- Produce reports only. No promotion, EA, paper-live, live trading, or order submission.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    pd = None
    PANDAS_IMPORT_ERROR = str(exc)
else:
    PANDAS_IMPORT_ERROR = None

STAGE = "Stage57A_CONTEXT_SOURCE_PRECHECK_AND_DERIVED_REGIME_TABLE_NO_PROMOTION"
STATUS = "CONTEXT_SOURCE_PRECHECK_COMPLETE_NO_PROMOTION"
NO_GO = "NO_GO"

REQUIRED_DB_COLUMNS = {
    "time_utc",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "spread_cost_bps",
    "spread_points",
}

DEFAULT_CONTEXT_MANIFEST = {
    "stage": STAGE,
    "primary_timeframe": "M15",
    "derived_timeframes": ["M15", "M5"],
    "session_utc_windows": [
        {"label": "asia", "start_hour": 0, "end_hour": 6},
        {"label": "london", "start_hour": 7, "end_hour": 12},
        {"label": "london_ny_overlap", "start_hour": 13, "end_hour": 16},
        {"label": "new_york", "start_hour": 17, "end_hour": 21},
        {"label": "late_us", "start_hour": 22, "end_hour": 23},
    ],
    "spread_regime_quantiles": [0.50, 0.75, 0.90, 0.95, 0.99],
    "volatility_regime_quantiles": [0.25, 0.50, 0.75, 0.90],
    "ret_regime_quantiles": [0.25, 0.50, 0.75, 0.90],
    "cot_candidate_paths": [
        "data/cot/cftc",
        "data/cot/cftc/artifacts",
        "data/cot/gold_cot.csv",
    ],
    "reference_candidate_paths": [
        "data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_20260619T051819Z.csv",
        "data/normalized",
    ],
    "external_needed_paths": {
        "news_blackout_calendar": [
            "data/context/news_blackout_calendar.csv",
            "data/calendar/economic_calendar.csv",
            "data/macro/economic_calendar.csv",
        ],
        "usd_rate_proxy": [
            "data/context/dxy.csv",
            "data/context/us10y.csv",
            "data/context/us02y.csv",
            "data/macro/dxy.csv",
            "data/macro/us10y.csv",
        ],
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def jdump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_manifest(path: Optional[Path]) -> Dict[str, Any]:
    manifest = dict(DEFAULT_CONTEXT_MANIFEST)
    if path and path.exists():
        user_manifest = read_json(path)
        for k, v in user_manifest.items():
            manifest[k] = v
    return manifest


def rel_or_abs(root: Path, p: str) -> Path:
    pp = Path(p).expanduser()
    if pp.is_absolute():
        return pp
    return root / pp


def find_existing(root: Path, candidates: Iterable[str]) -> List[str]:
    out: List[str] = []
    for c in candidates:
        p = rel_or_abs(root, c)
        if p.exists():
            out.append(str(p))
    return out


def connect_sqlite(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def get_table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def db_meta(con: sqlite3.Connection) -> Dict[str, Any]:
    if not table_exists(con, "amarkets_bars"):
        return {"schema_ok": False, "error": "missing amarkets_bars table", "columns": [], "timeframes": {}}
    cols = get_table_columns(con, "amarkets_bars")
    missing = sorted(REQUIRED_DB_COLUMNS - set(cols))
    tf_meta: Dict[str, Any] = {}
    try:
        for row in con.execute(
            """
            SELECT timeframe, COUNT(*) AS rows, MIN(time_utc) AS start_utc, MAX(time_utc) AS end_utc
            FROM amarkets_bars
            GROUP BY timeframe
            ORDER BY timeframe
            """
        ):
            tf_meta[str(row["timeframe"])] = {
                "rows": int(row["rows"] or 0),
                "start_utc": row["start_utc"],
                "end_utc": row["end_utc"],
            }
    except Exception as exc:
        return {"schema_ok": False, "error": str(exc), "columns": cols, "timeframes": tf_meta}
    return {
        "schema_ok": not missing,
        "missing_required_columns": missing,
        "columns": cols,
        "timeframes": tf_meta,
    }


def label_session(hour: int, windows: List[Dict[str, Any]]) -> str:
    for w in windows:
        start = int(w["start_hour"])
        end = int(w["end_hour"])
        if start <= end:
            if start <= hour <= end:
                return str(w["label"])
        else:
            if hour >= start or hour <= end:
                return str(w["label"])
    return "unknown"


def classify_quantile(value: float, qvals: Dict[str, float], prefix: str) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return f"{prefix}_unknown"
    keys = sorted(qvals.keys(), key=lambda x: float(x[1:]) if x.startswith("q") else 999.0)
    for k in keys:
        try:
            q = float(k[1:]) / 100.0
        except Exception:
            continue
        if value <= float(qvals[k]):
            return f"{prefix}_le_{int(q*100):02d}"
    return f"{prefix}_gt_{int(float(keys[-1][1:])) if keys else 99}"


def quantile_dict(series: "pd.Series", quantiles: List[float]) -> Dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {}
    return {f"q{int(q * 100):02d}": float(s.quantile(q)) for q in quantiles}


def load_bars(con: sqlite3.Connection, timeframe: str) -> "pd.DataFrame":
    if pd is None:
        raise RuntimeError(f"pandas is required for Stage57A but could not be imported: {PANDAS_IMPORT_ERROR}")
    sql = """
    SELECT time_utc, open, high, low, close, tick_volume, spread_points, spread_cost_bps
    FROM amarkets_bars
    WHERE timeframe = ?
    ORDER BY time_utc
    """
    df = pd.read_sql_query(sql, con, params=(timeframe,))
    if df.empty:
        return df
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "tick_volume", "spread_points", "spread_cost_bps"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"]).reset_index(drop=True)
    return df


def derive_context_table(
    df: "pd.DataFrame",
    timeframe: str,
    manifest: Dict[str, Any],
) -> Tuple["pd.DataFrame", Dict[str, Any]]:
    if df.empty:
        return df, {"rows": 0, "error": "no rows"}

    windows = manifest.get("session_utc_windows", DEFAULT_CONTEXT_MANIFEST["session_utc_windows"])
    spread_qs = manifest.get("spread_regime_quantiles", DEFAULT_CONTEXT_MANIFEST["spread_regime_quantiles"])
    vol_qs = manifest.get("volatility_regime_quantiles", DEFAULT_CONTEXT_MANIFEST["volatility_regime_quantiles"])
    ret_qs = manifest.get("ret_regime_quantiles", DEFAULT_CONTEXT_MANIFEST["ret_regime_quantiles"])

    out = pd.DataFrame()
    out["time_utc"] = df["time_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["timeframe"] = timeframe
    out["weekday"] = df["time_utc"].dt.weekday.astype(int)
    out["hour_utc"] = df["time_utc"].dt.hour.astype(int)
    out["session"] = out["hour_utc"].apply(lambda h: label_session(int(h), windows))

    close = df["close"].replace(0, pd.NA).astype(float)
    out["range_bps"] = ((df["high"] - df["low"]) / close * 10000.0).astype(float)
    out["abs_return_bps"] = (close.pct_change().abs() * 10000.0).astype(float)
    out["signed_return_bps"] = (close.pct_change() * 10000.0).astype(float)
    out["spread_points"] = df.get("spread_points")
    out["spread_cost_bps"] = df.get("spread_cost_bps")
    out["tick_volume"] = df.get("tick_volume")

    spread_q = quantile_dict(out["spread_cost_bps"], spread_qs)
    vol_q = quantile_dict(out["range_bps"], vol_qs)
    ret_q = quantile_dict(out["abs_return_bps"], ret_qs)

    out["spread_regime"] = out["spread_cost_bps"].apply(lambda x: classify_quantile(float(x) if pd.notna(x) else math.nan, spread_q, "spread"))
    out["range_regime"] = out["range_bps"].apply(lambda x: classify_quantile(float(x) if pd.notna(x) else math.nan, vol_q, "range"))
    out["abs_return_regime"] = out["abs_return_bps"].apply(lambda x: classify_quantile(float(x) if pd.notna(x) else math.nan, ret_q, "absret"))

    # Simple flags that are useful as exclusion labels, not predictive labels.
    p95_spread = spread_q.get("q95")
    p90_range = vol_q.get("q90")
    out["is_spread_p95_or_worse"] = False if p95_spread is None else out["spread_cost_bps"] >= p95_spread
    out["is_range_p90_or_higher"] = False if p90_range is None else out["range_bps"] >= p90_range
    out["is_rollover_like_hour"] = out["hour_utc"].isin([21, 22, 23])

    session_counts = out["session"].value_counts(dropna=False).to_dict()
    spread_regime_counts = out["spread_regime"].value_counts(dropna=False).to_dict()
    range_regime_counts = out["range_regime"].value_counts(dropna=False).to_dict()

    meta = {
        "rows": int(len(out)),
        "timeframe": timeframe,
        "start_utc": str(out["time_utc"].iloc[0]),
        "end_utc": str(out["time_utc"].iloc[-1]),
        "quantiles": {
            "spread_cost_bps": spread_q,
            "range_bps": vol_q,
            "abs_return_bps": ret_q,
        },
        "session_counts": {str(k): int(v) for k, v in session_counts.items()},
        "spread_regime_counts": {str(k): int(v) for k, v in spread_regime_counts.items()},
        "range_regime_counts": {str(k): int(v) for k, v in range_regime_counts.items()},
        "p95_spread_flag_rows": int(out["is_spread_p95_or_worse"].sum()),
        "p90_range_flag_rows": int(out["is_range_p90_or_higher"].sum()),
        "rollover_like_rows": int(out["is_rollover_like_hour"].sum()),
    }
    return out, meta


def inspect_context_sources(root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    external_needed = manifest.get("external_needed_paths", DEFAULT_CONTEXT_MANIFEST["external_needed_paths"])
    news_found = find_existing(root, external_needed.get("news_blackout_calendar", []))
    usd_found = find_existing(root, external_needed.get("usd_rate_proxy", []))
    cot_found = find_existing(root, manifest.get("cot_candidate_paths", DEFAULT_CONTEXT_MANIFEST["cot_candidate_paths"]))
    reference_found = find_existing(root, manifest.get("reference_candidate_paths", DEFAULT_CONTEXT_MANIFEST["reference_candidate_paths"]))

    return {
        "CTX_SESSION_AND_SPREAD_REGIME": {
            "priority": 1,
            "available_now": True,
            "status": "AVAILABLE_DERIVED_FROM_BROKER_DB",
            "found_paths": [],
            "use_in_stage57a": True,
        },
        "CTX_NEWS_BLACKOUT_CALENDAR": {
            "priority": 2,
            "available_now": bool(news_found),
            "status": "AVAILABLE_EXTERNAL_CSV" if news_found else "NEEDS_MANUAL_OR_EXTERNAL_CSV",
            "found_paths": news_found,
            "use_in_stage57a": False,
        },
        "CTX_USD_RATE_PROXY": {
            "priority": 3,
            "available_now": bool(usd_found),
            "status": "AVAILABLE_EXTERNAL_CSV" if usd_found else "NEEDS_EXTERNAL_CSV_OR_EXISTING_PROXY",
            "found_paths": usd_found,
            "use_in_stage57a": False,
        },
        "CTX_COT_WEEKLY_POSITIONING": {
            "priority": 4,
            "available_now": bool(cot_found),
            "status": "LOCAL_PATH_FOUND_SCHEMA_NOT_ASSUMED" if cot_found else "NOT_FOUND_OPTIONAL",
            "found_paths": cot_found,
            "use_in_stage57a": bool(cot_found),
        },
        "CTX_REFERENCE_PRICE_BASIS": {
            "priority": 5,
            "available_now": bool(reference_found),
            "status": "LOCAL_REFERENCE_PATH_FOUND_OPTIONAL" if reference_found else "NOT_FOUND_OPTIONAL",
            "found_paths": reference_found,
            "use_in_stage57a": bool(reference_found),
        },
    }


def write_checks_csv(checks: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["check", "passed", "severity", "observed", "expected"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in checks:
            w.writerow({k: json.dumps(row.get(k), ensure_ascii=False) if isinstance(row.get(k), (dict, list)) else row.get(k) for k in fields})


def make_report(summary: Dict[str, Any]) -> str:
    m15 = summary.get("derived_context", {}).get("M15", {})
    m5 = summary.get("derived_context", {}).get("M5", {})
    inv = summary.get("context_inventory", {})
    failed = summary.get("failed_checks", [])
    lines: List[str] = []
    lines.append("# Stage57A Context Source Precheck and Derived Regime Table")
    lines.append("")
    for key in ["status", "decision", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Context inventory")
    for cid, obj in sorted(inv.items(), key=lambda kv: kv[1].get("priority", 99)):
        lines.append(f"- `{cid}` priority=`{obj.get('priority')}` available_now=`{obj.get('available_now')}` status=`{obj.get('status')}`")
        if obj.get("found_paths"):
            for p in obj.get("found_paths", []):
                lines.append(f"  - `{p}`")
    lines.append("")
    lines.append("## Derived regime tables")
    for tf, meta in [("M15", m15), ("M5", m5)]:
        if meta:
            lines.append(f"- {tf}: rows=`{meta.get('rows')}` start=`{meta.get('start_utc')}` end=`{meta.get('end_utc')}` output=`{summary.get('outputs', {}).get(tf)}`")
            q = meta.get("quantiles", {})
            lines.append(f"  - spread_cost_bps_quantiles: `{q.get('spread_cost_bps')}`")
            lines.append(f"  - range_bps_quantiles: `{q.get('range_bps')}`")
    lines.append("")
    lines.append("## Checks")
    if failed:
        lines.append("Failed checks:")
        for c in failed:
            lines.append(f"- `{c}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Interpretation")
    lines.append(
        "Stage57A is a context-precheck and regime-table generation step only. It does not scan a trading thesis, does not use context as a forward label, and does not authorize promotion, EA, paper-live, live trading, or order submission."
    )
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage57A context source precheck and derived regime table")
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--context-manifest", default="configs/stage57_context_source_manifest.json")
    ap.add_argument("--config", default="configs/stage57a_context_source_precheck.json")
    ap.add_argument("--out", default="reports/stage57_context_precheck")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    db_path = rel_or_abs(root, args.db)
    manifest_path = rel_or_abs(root, args.context_manifest)
    config_path = rel_or_abs(root, args.config)
    out_dir = rel_or_abs(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path if manifest_path.exists() else None)
    if config_path.exists():
        cfg = read_json(config_path)
        for k, v in cfg.items():
            manifest[k] = v

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    context_inventory = inspect_context_sources(root, manifest)

    db_info: Dict[str, Any]
    derived_meta: Dict[str, Any] = {}
    outputs: Dict[str, str] = {}
    schema_ok = False
    try:
        con = connect_sqlite(db_path)
        db_info = db_meta(con)
        schema_ok = bool(db_info.get("schema_ok"))
        checks.append({"check": "broker_db_schema_ok", "passed": schema_ok, "severity": "HIGH", "observed": db_info.get("missing_required_columns"), "expected": "amarkets_bars has required context columns"})
        if not schema_ok:
            failed_checks.append("broker_db_schema_ok")
        if pd is None:
            checks.append({"check": "pandas_available", "passed": False, "severity": "HIGH", "observed": PANDAS_IMPORT_ERROR, "expected": "pandas import succeeds"})
            failed_checks.append("pandas_available")
        else:
            checks.append({"check": "pandas_available", "passed": True, "severity": "HIGH", "observed": None, "expected": "pandas import succeeds"})

        if schema_ok and pd is not None:
            for tf in manifest.get("derived_timeframes", ["M15", "M5"]):
                df = load_bars(con, str(tf))
                present = not df.empty
                checks.append({"check": f"db_{tf}_present", "passed": present, "severity": "HIGH" if tf == manifest.get("primary_timeframe", "M15") else "MEDIUM", "observed": len(df), "expected": f"{tf} bars exist"})
                if not present and tf == manifest.get("primary_timeframe", "M15"):
                    failed_checks.append(f"db_{tf}_present")
                    continue
                ctx, meta = derive_context_table(df, str(tf), manifest)
                output_path = out_dir / f"stage57a_{str(tf).lower()}_context_regime_table.csv"
                ctx.to_csv(output_path, index=False)
                outputs[str(tf)] = str(output_path)
                derived_meta[str(tf)] = meta
                checks.append({"check": f"derived_{tf}_context_rows", "passed": int(meta.get("rows", 0)) > 0, "severity": "HIGH" if tf == manifest.get("primary_timeframe", "M15") else "MEDIUM", "observed": meta.get("rows"), "expected": "derived context table has rows"})
                if int(meta.get("rows", 0)) <= 0 and tf == manifest.get("primary_timeframe", "M15"):
                    failed_checks.append(f"derived_{tf}_context_rows")
        con.close()
    except Exception as exc:
        db_info = {"schema_ok": False, "error": str(exc), "path": str(db_path)}
        checks.append({"check": "broker_db_readable", "passed": False, "severity": "HIGH", "observed": str(exc), "expected": "SQLite DB readable"})
        failed_checks.append("broker_db_readable")

    # External context checks are informative; not blockers for Stage57A.
    for cid, obj in context_inventory.items():
        required_now = cid == "CTX_SESSION_AND_SPREAD_REGIME"
        passed = bool(obj.get("available_now")) if required_now else True
        checks.append({
            "check": f"context_{cid}_availability",
            "passed": passed,
            "severity": "HIGH" if required_now else "LOW",
            "observed": {"available_now": obj.get("available_now"), "status": obj.get("status"), "found_paths": obj.get("found_paths")},
            "expected": "available now" if required_now else "optional or can be added later",
        })
        if not passed:
            failed_checks.append(f"context_{cid}_availability")

    decision = "CONTEXT_TABLE_READY_FOR_STAGE58_DESIGN_NO_PROMOTION" if not failed_checks else "CONTEXT_PRECHECK_BLOCKED_FIX_HIGH_SEVERITY_NO_PROMOTION"
    next_step = "STAGE58_CONTEXT_AWARE_THESIS_DESIGN_NO_PROMOTION_AND_CONTINUE_STAGE52_FORWARD_SHADOW" if not failed_checks else "FIX_STAGE57A_CONTEXT_PRECHECK_BLOCKERS_NO_PROMOTION"

    summary = {
        "stage": STAGE,
        "status": STATUS,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "db": str(db_path),
        "out": str(out_dir),
        "context_manifest": str(manifest_path) if manifest_path.exists() else None,
        "config": str(config_path) if config_path.exists() else None,
        "db_info": db_info,
        "context_inventory": context_inventory,
        "derived_context": derived_meta,
        "outputs": outputs,
        "checks": checks,
        "failed_checks": failed_checks,
        "generated_utc": utc_now_iso(),
    }

    summary_path = out_dir / "stage57a_context_source_precheck_summary.json"
    report_path = out_dir / "stage57a_context_source_precheck_report.md"
    checks_path = out_dir / "stage57a_context_source_precheck_checks.csv"
    jdump(summary, summary_path)
    report_path.write_text(make_report(summary), encoding="utf-8")
    write_checks_csv(checks, checks_path)

    print(json.dumps({
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "failed_checks": failed_checks,
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0 if not any(c for c in failed_checks if c) else 0


if __name__ == "__main__":
    raise SystemExit(main())
