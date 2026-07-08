#!/usr/bin/env python3
"""Stage161: Macro-aware classification for Stage159 technical candidate families.

Read-only classifier. It does not write execution KV, does not modify MT5, and
must not be used as a direct order-routing surface. It labels Stage159 candidates
against refreshed macro/fundamental context so demo remains frozen unless a
separate locked-family demo writer is intentionally created later.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

UTC = timezone.utc
DATE_CANDIDATES = ["date", "datetime", "timestamp", "utc_time", "time", "ds", "observation_date", "event_date", "release_date"]
EVENT_KEYWORDS = ["cpi", "fomc", "nfp", "payroll", "unemployment", "pce", "powell", "fed", "federal reserve", "treasury", "auction", "jobs"]


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: Optional[datetime]) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z") if dt else ""


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def safe_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}
    return {}


def read_csv_any(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, sep="\t")
        except Exception:
            return pd.DataFrame()


def find_date_col(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lower = {c.lower(): c for c in cols}
    for name in DATE_CANDIDATES:
        if name in lower:
            return lower[name]
    for c in cols:
        lc = c.lower()
        if "date" in lc or "time" in lc:
            return c
    return ""


def with_datetime(df: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    if df.empty:
        return df, ""
    c = find_date_col(df)
    if not c:
        return df, ""
    out = df.copy()
    out["__dt"] = pd.to_datetime(out[c], errors="coerce", utc=True)
    out = out[out["__dt"].notna()].sort_values("__dt")
    return out, c


def numeric_col_candidates(df: pd.DataFrame, patterns: List[str]) -> List[str]:
    out: List[str] = []
    for c in df.columns:
        lc = c.lower()
        if any(p in lc for p in patterns):
            s = pd.to_numeric(df[c], errors="coerce")
            if s.notna().sum() > 5:
                out.append(c)
    return out


def latest_delta(df: pd.DataFrame, patterns: List[str], lookback_rows: int = 20) -> Dict[str, Any]:
    if df.empty:
        return {"column": "", "latest": "", "delta": "", "direction": "UNKNOWN"}
    cols = numeric_col_candidates(df, patterns)
    if not cols:
        return {"column": "", "latest": "", "delta": "", "direction": "UNKNOWN"}
    c = cols[0]
    s = pd.to_numeric(df[c], errors="coerce").dropna()
    if len(s) < 2:
        return {"column": c, "latest": "", "delta": "", "direction": "UNKNOWN"}
    latest = float(s.iloc[-1])
    prev = float(s.iloc[max(0, len(s) - 1 - lookback_rows)])
    delta = latest - prev
    direction = "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"
    return {"column": c, "latest": round(latest, 6), "delta": round(delta, 6), "direction": direction}


def percentile_state(df: pd.DataFrame, patterns: List[str]) -> Dict[str, Any]:
    cols = numeric_col_candidates(df, patterns)
    if not cols:
        return {"column": "", "latest": "", "percentile": "", "state": "UNKNOWN"}
    c = cols[0]
    s = pd.to_numeric(df[c], errors="coerce").dropna()
    if len(s) < 20:
        return {"column": c, "latest": "", "percentile": "", "state": "UNKNOWN"}
    latest = float(s.iloc[-1])
    pct = float((s <= latest).mean())
    if pct >= 0.70:
        state = "HIGH"
    elif pct <= 0.30:
        state = "LOW"
    else:
        state = "MID"
    return {"column": c, "latest": round(latest, 6), "percentile": round(pct, 4), "state": state}


def macro_context(feature_dir: Path, stage160: Dict[str, Any], event_window_days: int = 1) -> Dict[str, Any]:
    dollar_path = feature_dir / "stage116_validated_dollar_pressure.csv"
    macro_path = feature_dir / "stage115_daily_macro_feature_panel.csv"
    fred_path = feature_dir / "stage115_fred_macro_daily_wide.csv"
    event_path = feature_dir / "stage115_unified_event_calendar_features.csv"
    dollar, _ = with_datetime(read_csv_any(dollar_path))
    macro, _ = with_datetime(read_csv_any(macro_path))
    fred, _ = with_datetime(read_csv_any(fred_path))
    events, _ = with_datetime(read_csv_any(event_path))
    base = dollar if not dollar.empty else macro if not macro.empty else fred
    latest_dt = None
    if not base.empty and "__dt" in base:
        latest_dt = base["__dt"].max().to_pydatetime().astimezone(UTC)
    generated = now_utc()

    dxy = latest_delta(pd.concat([dollar, macro, fred], ignore_index=True, sort=False), ["dxy", "dollar", "dtwex", "trade_weighted"])
    real_yield = latest_delta(pd.concat([dollar, macro, fred], ignore_index=True, sort=False), ["dfii10", "real_yield", "real yield"])
    us10y = latest_delta(pd.concat([dollar, macro, fred], ignore_index=True, sort=False), ["dgs10", "us10", "10y", "yield_10"])
    vix = percentile_state(pd.concat([macro, fred], ignore_index=True, sort=False), ["vix"])

    dxy_up = dxy.get("direction") == "UP"
    ry_up = real_yield.get("direction") == "UP"
    dxy_down = dxy.get("direction") == "DOWN"
    ry_down = real_yield.get("direction") == "DOWN"
    if dxy_up and ry_up:
        gold_macro_pressure = "USD_REAL_YIELD_HEADWIND_FOR_GOLD"
    elif dxy_down and ry_down:
        gold_macro_pressure = "USD_REAL_YIELD_TAILWIND_FOR_GOLD"
    elif dxy.get("direction") == "UNKNOWN" and real_yield.get("direction") == "UNKNOWN":
        gold_macro_pressure = "UNKNOWN"
    else:
        gold_macro_pressure = "MIXED"

    event_hits: List[Dict[str, Any]] = []
    if latest_dt and not events.empty and "__dt" in events:
        lo = pd.Timestamp(latest_dt - timedelta(days=event_window_days))
        hi = pd.Timestamp(latest_dt + timedelta(days=event_window_days))
        window = events[(events["__dt"] >= lo) & (events["__dt"] <= hi)]
        for _, row in window.head(50).iterrows():
            text = " ".join(str(v) for v in row.to_dict().values()).lower()
            if any(k in text for k in EVENT_KEYWORDS):
                event_hits.append({
                    "event_time_utc": iso(row["__dt"].to_pydatetime()),
                    "matched_keywords": ",".join(k for k in EVENT_KEYWORDS if k in text),
                    "raw_preview": text[:180].replace("\n", " "),
                })
    event_blackout = bool(event_hits)

    st_decision = str(stage160.get("decision", ""))
    if "BLOCKED" in st_decision:
        macro_data_status = "MACRO_DATA_BLOCKED"
    elif not latest_dt:
        macro_data_status = "MACRO_DATA_UNKNOWN"
    else:
        age_days = (generated - latest_dt).total_seconds() / 86400.0
        macro_data_status = "MACRO_DATA_FRESH" if age_days <= 7 else "MACRO_DATA_STALE"

    return {
        "latest_macro_time_utc": iso(latest_dt),
        "macro_data_status": macro_data_status,
        "gold_macro_pressure": gold_macro_pressure,
        "dxy_signal": dxy,
        "real_yield_signal": real_yield,
        "us10y_signal": us10y,
        "vix_signal": vix,
        "event_blackout_required": event_blackout,
        "event_hit_count": len(event_hits),
        "event_hits_preview": event_hits[:10],
    }


def family_key_from_row(row: Dict[str, Any]) -> str:
    for k in ["family_key", "selected_family_key", "family", "family_id"]:
        if k in row and str(row[k]).strip():
            return str(row[k]).strip()
    rid = str(row.get("rule_id") or row.get("selected_rule_id") or row.get("candidate_id") or "").strip()
    if not rid:
        return "UNKNOWN_FAMILY"
    # Remove thresholds but keep feature pair. D150C_M5_ret_3h_bps_GEQ35__trend_50_100_bps_GEQ35
    parts = []
    for part in rid.split("__"):
        part = re.sub(r"_(GEQ|LEQ|GT|LT|EQ)\d+(?:P\d+)?$", "", part)
        parts.append(part)
    return "__".join(parts)


def classify_rule(row: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    rid = str(row.get("rule_id") or row.get("selected_rule_id") or row.get("candidate_id") or row.get("family_key") or "")
    text = rid.lower()
    reasons: List[str] = []
    if ctx["macro_data_status"] != "MACRO_DATA_FRESH":
        return "MACRO_DATA_STALE_OR_INCOMPLETE_NO_DEMO_RELEASE", "BLOCK", [ctx["macro_data_status"]]
    if ctx.get("event_blackout_required"):
        return "EVENT_BLACKOUT_REQUIRED", "BLOCK", ["high_impact_event_near_current_macro_date"]
    pressure = ctx.get("gold_macro_pressure")
    is_momentum = any(x in text for x in ["trend", "ret_", "momentum", "breakout"])
    is_reversal = any(x in text for x in ["range", "reversal", "mean"])
    # Current execution surface is effectively long-only. Continuation/momentum should not fight dollar/yield headwind.
    if pressure == "USD_REAL_YIELD_HEADWIND_FOR_GOLD" and is_momentum:
        return "MACRO_CONFLICTED", "BLOCK", [pressure, "long_momentum_candidate"]
    if pressure == "USD_REAL_YIELD_TAILWIND_FOR_GOLD" and is_momentum:
        return "MACRO_SUPPORTED", "REVIEW", [pressure, "long_momentum_candidate"]
    if pressure == "MIXED":
        return "MACRO_MIXED_TECHNICAL_ONLY", "WARN", [pressure]
    if pressure == "UNKNOWN":
        return "MACRO_UNKNOWN_NO_DEMO_RELEASE", "BLOCK", [pressure]
    if is_reversal:
        return "REGIME_SPECIFIC_ONLY", "WARN", [pressure, "reversal_or_range_rule_needs_separate_regime_test"]
    return "MACRO_NEUTRAL_REVIEW_ONLY", "WARN", [str(pressure)]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage161 macro-aware candidate classifier")
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--feature-dir", default="data/fundamental_event_inbox/features")
    ap.add_argument("--stage160-summary", default="reports/stage160_macro_pipeline_readiness_audit/stage160_macro_pipeline_readiness_audit_summary.json")
    ap.add_argument("--stage159-shortlist", default="reports/stage159_locked_family_repair_discovery/stage159_locked_family_shortlist.csv")
    ap.add_argument("--stage159-family-summary", default="reports/stage159_locked_family_repair_discovery/stage159_family_repair_summary.csv")
    ap.add_argument("--event-window-days", type=int, default=1)
    ap.add_argument("--out", default="reports/stage161_macro_aware_candidate_classifier")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    feature_dir = (root / args.feature_dir).resolve() if not Path(args.feature_dir).is_absolute() else Path(args.feature_dir).expanduser().resolve()
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).expanduser().resolve()
    stage160_path = (root / args.stage160_summary).resolve() if not Path(args.stage160_summary).is_absolute() else Path(args.stage160_summary).expanduser().resolve()
    stage160 = safe_json(stage160_path)
    shortlist_path = (root / args.stage159_shortlist).resolve() if not Path(args.stage159_shortlist).is_absolute() else Path(args.stage159_shortlist).expanduser().resolve()
    family_path = (root / args.stage159_family_summary).resolve() if not Path(args.stage159_family_summary).is_absolute() else Path(args.stage159_family_summary).expanduser().resolve()
    shortlist = read_csv_any(shortlist_path)
    family_summary = read_csv_any(family_path)
    source_df = shortlist if not shortlist.empty else family_summary

    ctx = macro_context(feature_dir, stage160, args.event_window_days)
    rows: List[Dict[str, Any]] = []
    if not source_df.empty:
        for _, srow in source_df.iterrows():
            d = {str(k): srow[k] for k in source_df.columns}
            fkey = family_key_from_row(d)
            label, action, reasons = classify_rule(d, ctx)
            out = {
                "family_key": fkey,
                "rule_id": d.get("rule_id") or d.get("selected_rule_id") or d.get("candidate_id") or "",
                "macro_label": label,
                "macro_action": action,
                "macro_reasons": ";".join(reasons),
                "gold_macro_pressure": ctx.get("gold_macro_pressure"),
                "event_blackout_required": ctx.get("event_blackout_required"),
                "macro_data_status": ctx.get("macro_data_status"),
            }
            # Preserve useful score columns if present.
            for c in ["mean_bps", "hit_rate", "event_count", "total_bps", "closed_trade_count", "family_repair_decision", "decision", "rank", "score"]:
                if c in d:
                    out[c] = d[c]
            rows.append(out)

    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["macro_label"]] = counts.get(r["macro_label"], 0) + 1
    supported = counts.get("MACRO_SUPPORTED", 0)
    if ctx["macro_data_status"] != "MACRO_DATA_FRESH":
        decision = "STAGE161_MACRO_DATA_NOT_READY_KEEP_FREEZE"
        recommended = "KEEP_STAGE157_FREEZE_AND_REPAIR_MACRO_DATA"
        severity = "HIGH"
    elif not rows:
        decision = "STAGE161_NO_STAGE159_CANDIDATES_KEEP_FREEZE"
        recommended = "KEEP_STAGE157_FREEZE_AND_REPAIR_TECHNICAL_DISCOVERY"
        severity = "HIGH"
    elif ctx.get("event_blackout_required"):
        decision = "STAGE161_EVENT_BLACKOUT_ACTIVE_KEEP_FREEZE"
        recommended = "KEEP_STAGE157_FREEZE_UNTIL_EVENT_WINDOW_CLEARS"
        severity = "HIGH"
    elif supported > 0:
        decision = "STAGE161_MACRO_SUPPORTED_CANDIDATES_REVIEW_ONLY_NO_DEMO_RELEASE"
        recommended = "REVIEW_LOCKED_FAMILY_CANDIDATES_BEFORE_ANY_STAGE162_DEMO_WRITER"
        severity = "MEDIUM"
    else:
        decision = "STAGE161_NO_MACRO_SUPPORTED_CANDIDATES_KEEP_FREEZE"
        recommended = "KEEP_STAGE157_FREEZE_AND_REPAIR_DISCOVERY_OR_WAIT_FOR_REGIME_CHANGE"
        severity = "HIGH"

    # Family-level aggregation.
    fam_rows: List[Dict[str, Any]] = []
    if rows:
        tmp = pd.DataFrame(rows)
        for fkey, grp in tmp.groupby("family_key", dropna=False):
            label_counts = grp["macro_label"].value_counts().to_dict()
            # Best label priority.
            if label_counts.get("MACRO_SUPPORTED", 0) > 0:
                fam_label = "MACRO_SUPPORTED"
            elif label_counts.get("MACRO_CONFLICTED", 0) > 0:
                fam_label = "MACRO_CONFLICTED"
            elif label_counts.get("EVENT_BLACKOUT_REQUIRED", 0) > 0:
                fam_label = "EVENT_BLACKOUT_REQUIRED"
            else:
                fam_label = str(grp["macro_label"].iloc[0])
            fam_rows.append({
                "family_key": fkey,
                "candidate_count": int(len(grp)),
                "family_macro_label": fam_label,
                "label_counts_json": json.dumps(label_counts, ensure_ascii=False, sort_keys=True),
            })

    summary = {
        "stage": "Stage161_MACRO_AWARE_CANDIDATE_CLASSIFIER",
        "generated_utc": iso(now_utc()),
        "status": "STAGE161_COMPLETE_MACRO_AWARE_CLASSIFICATION_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended,
        "root": str(root),
        "feature_dir": str(feature_dir),
        "stage160_summary": str(stage160_path),
        "stage159_shortlist": str(shortlist_path),
        "stage159_family_summary": str(family_path),
        "candidate_row_count": len(rows),
        "family_row_count": len(fam_rows),
        "macro_label_counts": counts,
        "macro_context": ctx,
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "outputs": {
            "summary_json": str(out_dir / "stage161_macro_aware_candidate_classifier_summary.json"),
            "candidate_classification_csv": str(out_dir / "stage161_macro_candidate_classification.csv"),
            "family_classification_csv": str(out_dir / "stage161_macro_family_classification.csv"),
            "macro_context_json": str(out_dir / "stage161_macro_context_snapshot.json"),
        },
        "next": [
            "Keep Stage157 freeze active.",
            "Only consider Stage162 locked-family demo writer if a small number of macro-supported families survive manual review.",
            "If labels are macro-conflicted or event-blackout, do not trade the technical shortlist.",
        ],
    }
    write_csv(out_dir / "stage161_macro_candidate_classification.csv", rows)
    write_csv(out_dir / "stage161_macro_family_classification.csv", fam_rows)
    write_json(out_dir / "stage161_macro_context_snapshot.json", ctx)
    write_json(out_dir / "stage161_macro_aware_candidate_classifier_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
