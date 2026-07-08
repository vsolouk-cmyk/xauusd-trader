#!/usr/bin/env python3
"""Stage158B trade attribution audit for XAUUSD demo execution.

Read-only audit. It does not write MT5 execution KV files and never sends orders.

Stage158B fixes the Stage158 M5 bar loader for AMarkets tab-separated exports and
adds MFE/MAE/theoretical-horizon attribution so we can distinguish rule failure
from execution/exit/router protocol problems.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage158B_TRADE_ATTRIBUTION_AUDIT_BAR_LOADER_FIX"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _parse_dt(value: Any) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\ufeff", "")
    try:
        ts = pd.to_datetime(s, utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.tz_convert("UTC").tz_localize(None)


def _parse_float(value: Any) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _family_key(rule_id: str) -> str:
    """Convert a rule_id into the coarser family key used by Stage145."""
    if not rule_id:
        return ""
    parts = str(rule_id).split("__")
    cleaned = []
    for part in parts:
        # remove terminal quantile operators: _GEQ65, _LEQ35, etc.
        cleaned.append(re.sub(r"_(GEQ|LEQ)\d+(?:P\d+)?$", "", part))
    return "__".join(cleaned)


def _detect_sep(first_line: str) -> str:
    if "\t" in first_line:
        return "\t"
    if ";" in first_line and first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def _looks_like_header(tokens: List[str]) -> bool:
    lowered = [t.strip().lower() for t in tokens]
    header_words = {"date", "time", "datetime", "utc_time", "time_utc", "open", "high", "low", "close", "volume", "spread"}
    return any(t in header_words for t in lowered)


def load_m5_bars(path: Path, timestamp_shift_hours: float = 0.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Load AMarkets M5 bars robustly.

    Supports:
    - tab-separated MetaTrader exports without header:
      YYYY.MM.DD<TAB>HH:MM:SS<TAB>open<TAB>high<TAB>low<TAB>close<TAB>tick_volume<TAB>volume<TAB>spread
    - headered CSV/TSV with common date/time/open/high/low/close names.
    """
    info: Dict[str, Any] = {"path": str(path), "exists": path.exists(), "bar_loader_version": "stage158b_robust_amarkets_tsv"}
    if not path.exists():
        info.update({"bar_count": 0, "load_error": "missing_file"})
        return pd.DataFrame(), info

    first_line = ""
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        first_line = f.readline().rstrip("\n")
    sep = _detect_sep(first_line)
    tokens = next(csv.reader([first_line], delimiter=sep)) if first_line else []
    has_header = _looks_like_header(tokens)
    info.update({"detected_separator": "tab" if sep == "\t" else sep, "detected_header": has_header})

    try:
        if has_header:
            raw = pd.read_csv(path, sep=sep, engine="python")
        else:
            raw = pd.read_csv(path, sep=sep, engine="python", header=None)
    except Exception as exc:
        info.update({"bar_count": 0, "load_error": f"read_csv_failed:{type(exc).__name__}:{exc}"})
        return pd.DataFrame(), info

    if raw.empty:
        info.update({"bar_count": 0, "load_error": "empty_file"})
        return pd.DataFrame(), info

    df = raw.copy()
    if not has_header:
        # AMarkets/MT5 common export: date time O H L C tick_volume volume spread
        names = ["date", "time", "open", "high", "low", "close", "tick_volume", "volume", "spread"]
        if df.shape[1] < 6:
            info.update({"bar_count": 0, "load_error": f"too_few_columns:{df.shape[1]}"})
            return pd.DataFrame(), info
        df = df.iloc[:, : min(df.shape[1], len(names))]
        df.columns = names[: df.shape[1]]
    else:
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        rename = {
            "time_utc": "utc_time",
            "datetime": "utc_time",
            "timestamp": "utc_time",
            "date_time": "utc_time",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Build raw timestamp.
    raw_ts: Optional[pd.Series] = None
    if "utc_time" in df.columns:
        raw_ts = pd.to_datetime(df["utc_time"], utc=True, errors="coerce").dt.tz_convert("UTC").dt.tz_localize(None)
    elif "date" in df.columns and "time" in df.columns:
        raw_ts = pd.to_datetime(df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(), utc=True, errors="coerce").dt.tz_convert("UTC").dt.tz_localize(None)
    elif "date" in df.columns:
        raw_ts = pd.to_datetime(df["date"], utc=True, errors="coerce").dt.tz_convert("UTC").dt.tz_localize(None)
    else:
        info.update({"bar_count": 0, "load_error": "no_timestamp_columns"})
        return pd.DataFrame(), info

    out = pd.DataFrame({"raw_time": raw_ts})
    out["utc_time"] = out["raw_time"] + pd.to_timedelta(float(timestamp_shift_hours), unit="h")
    for col in ["open", "high", "low", "close", "spread", "tick_volume", "volume"]:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            out[col] = float("nan")

    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"])
    out = out.sort_values("utc_time").drop_duplicates(subset=["utc_time"], keep="last").reset_index(drop=True)
    if out.empty:
        info.update({"bar_count": 0, "load_error": "no_parseable_bars"})
        return out, info

    info.update(
        {
            "bar_count": int(len(out)),
            "raw_first_time": out["raw_time"].iloc[0].isoformat() + "Z",
            "raw_last_time": out["raw_time"].iloc[-1].isoformat() + "Z",
            "normalized_first_time": out["utc_time"].iloc[0].isoformat() + "Z",
            "normalized_last_time": out["utc_time"].iloc[-1].isoformat() + "Z",
            "load_error": "",
        }
    )
    return out, info


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def score_lookup(score_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    if score_df.empty:
        return {}
    cols = {str(c).lower(): c for c in score_df.columns}
    rid_col = cols.get("rule_id") or cols.get("selected_rule_id") or cols.get("candidate_id")
    if rid_col is None:
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in score_df.iterrows():
        rid = str(row.get(rid_col, "")).strip()
        if rid:
            lookup[rid] = {str(k): row.get(k) for k in score_df.columns}
    return lookup


def _find_metric(row: Dict[str, Any], candidates: Iterable[str]) -> Any:
    lower = {str(k).lower(): k for k in row.keys()}
    for c in candidates:
        if c.lower() in lower:
            return row.get(lower[c.lower()])
    for k in row.keys():
        lk = str(k).lower()
        for c in candidates:
            if c.lower() in lk:
                return row.get(k)
    return ""


def compute_bar_window_metrics(
    bars: pd.DataFrame,
    entry_time: Optional[pd.Timestamp],
    exit_time: Optional[pd.Timestamp],
    entry_price: float,
    horizon_hours: float,
) -> Dict[str, Any]:
    if bars.empty or entry_time is None or not math.isfinite(entry_price) or entry_price <= 0:
        return {
            "bar_window_count": 0,
            "mfe_bps": "",
            "mae_bps": "",
            "theoretical_horizon_bps": "",
            "window_end_utc": "",
            "window_last_close": "",
        }
    horizon_end = entry_time + pd.to_timedelta(float(horizon_hours), unit="h")
    if exit_time is not None:
        window_end = min(exit_time, horizon_end)
    else:
        window_end = horizon_end
    win = bars[(bars["utc_time"] >= entry_time) & (bars["utc_time"] <= window_end)]
    if win.empty:
        return {
            "bar_window_count": 0,
            "mfe_bps": "",
            "mae_bps": "",
            "theoretical_horizon_bps": "",
            "window_end_utc": window_end.isoformat() + "Z",
            "window_last_close": "",
        }
    max_high = float(win["high"].max())
    min_low = float(win["low"].min())
    last_close = float(win["close"].iloc[-1])
    return {
        "bar_window_count": int(len(win)),
        "mfe_bps": round((max_high - entry_price) / entry_price * 10000.0, 4),
        "mae_bps": round((min_low - entry_price) / entry_price * 10000.0, 4),
        "theoretical_horizon_bps": round((last_close - entry_price) / entry_price * 10000.0, 4),
        "window_end_utc": window_end.isoformat() + "Z",
        "window_last_close": round(last_close, 5),
    }


def diagnose_trade(row: Dict[str, Any], same_feature_rule_count: int, max_signal_age_sec: int) -> str:
    outcome = str(row.get("outcome", "")).upper()
    actual_bps = _parse_float(row.get("bps_move"))
    signal_age_sec = _parse_float(row.get("entry_delay_sec"))
    mfe = _parse_float(row.get("mfe_bps"))
    theo = _parse_float(row.get("theoretical_horizon_bps"))
    bar_window_count = int(_parse_float(row.get("bar_window_count")) if str(row.get("bar_window_count", "")).strip() else 0)

    if math.isfinite(signal_age_sec) and signal_age_sec > max_signal_age_sec:
        return "STALE_CONTAMINATED"

    if same_feature_rule_count > 1:
        return "ROUTER_PROTOCOL_RISK_PROFIT" if actual_bps >= 0 else "ROUTER_PROTOCOL_FAIL"

    if outcome == "PROFIT" or actual_bps > 0:
        return "PROFIT_SMALL_N"

    if bar_window_count > 0:
        if math.isfinite(mfe) and mfe >= 15.0 and actual_bps < 0:
            return "EXIT_FAIL"
        if math.isfinite(theo) and theo > 0 and actual_bps < 0:
            return "EXECUTION_OR_EXIT_FAIL"
        if math.isfinite(theo) and theo <= 0 and actual_bps < 0:
            return "RULE_FAIL"

    return "SMALL_N_UNRESOLVED"


def build_attribution(args: argparse.Namespace) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root = Path(args.root)
    out_dir = Path(args.output_dir) if args.output_dir else root / "reports" / "stage158_trade_attribution_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    ledger = load_csv(Path(args.clean_ledger))
    score_df = load_csv(Path(args.score_csv))
    risk = load_json(Path(args.risk_summary))
    bars, bar_info = load_m5_bars(Path(args.bars_m5), float(args.timestamp_shift_hours))
    scores = score_lookup(score_df)

    rows: List[Dict[str, Any]] = []
    if not ledger.empty:
        # Restrict to closed trades if outcome column exists.
        if "outcome" in ledger.columns:
            ledger_iter = ledger[~ledger["outcome"].astype(str).str.upper().isin(["OPEN_OR_UNMATCHED", "", "NAN"])]
        else:
            ledger_iter = ledger
        feature_to_rules: Dict[str, set] = defaultdict(set)
        tmp_rows: List[Dict[str, Any]] = []
        for _, src in ledger_iter.iterrows():
            d = {str(k): src.get(k) for k in ledger_iter.columns}
            rule_id = str(d.get("rule_id", "") or "").strip()
            feature_date = _parse_dt(d.get("feature_date"))
            entry_time_raw = _parse_dt(d.get("entry_time"))
            exit_time_raw = _parse_dt(d.get("exit_time"))
            entry_time = entry_time_raw + pd.to_timedelta(float(args.entry_time_shift_hours), unit="h") if entry_time_raw is not None else None
            exit_time = exit_time_raw + pd.to_timedelta(float(args.entry_time_shift_hours), unit="h") if exit_time_raw is not None else None
            entry_price = _parse_float(d.get("entry_price"))
            if not math.isfinite(entry_price):
                entry_price = _parse_float(d.get("entry_price_from_trade_log"))
            family = _family_key(rule_id)
            feature_key = feature_date.isoformat() + "Z" if feature_date is not None else ""
            if feature_key and rule_id:
                feature_to_rules[feature_key].add(rule_id)
            entry_delay_sec = ""
            if feature_date is not None and entry_time is not None:
                entry_delay_sec = round((entry_time - feature_date).total_seconds(), 3)
            m = compute_bar_window_metrics(bars, entry_time, exit_time, entry_price, float(args.horizon_hours))
            score_row = scores.get(rule_id, {})
            out = {
                **d,
                "family_key": family,
                "feature_date_norm": feature_key,
                "entry_time_raw": entry_time_raw.isoformat() + "Z" if entry_time_raw is not None else "",
                "entry_time_adjusted": entry_time.isoformat() + "Z" if entry_time is not None else "",
                "exit_time_adjusted": exit_time.isoformat() + "Z" if exit_time is not None else "",
                "entry_delay_sec": entry_delay_sec,
                "entry_delay_min": round(float(entry_delay_sec) / 60.0, 3) if entry_delay_sec != "" else "",
                "score_validation_mean_bps": _find_metric(score_row, ["validation_mean_bps", "val_mean_bps"]),
                "score_validation_hit": _find_metric(score_row, ["validation_hit", "validation_hit_rate", "val_hit"]),
                "score_tail_mean_bps": _find_metric(score_row, ["tail_mean_bps", "recent_tail_mean_bps"]),
                "score_tail_hit": _find_metric(score_row, ["tail_hit", "tail_hit_rate"]),
                **m,
            }
            tmp_rows.append(out)

        for out in tmp_rows:
            same_count = len(feature_to_rules.get(str(out.get("feature_date_norm", "")), set()))
            out["same_feature_rule_count"] = same_count
            out["diagnosis"] = diagnose_trade(out, same_count, int(args.max_signal_age_sec))
            rows.append(out)

    trades = pd.DataFrame(rows)

    if trades.empty:
        diagnosis_summary = pd.DataFrame(columns=["diagnosis", "count"])
        family_summary = pd.DataFrame(columns=["family_key", "closed_trade_count", "profit_count", "loss_count", "win_rate", "total_net_profit", "mean_net_profit", "total_bps", "mean_bps"])
        cohort_summary = pd.DataFrame(columns=["cohort", "closed_trade_count", "profit_count", "loss_count", "win_rate", "total_bps", "mean_bps"])
    else:
        diagnosis_summary = trades["diagnosis"].value_counts().rename_axis("diagnosis").reset_index(name="count")
        trades["bps_numeric"] = pd.to_numeric(trades.get("bps_move"), errors="coerce")
        trades["net_profit_numeric"] = pd.to_numeric(trades.get("net_profit"), errors="coerce")
        trades["is_profit"] = trades["bps_numeric"] > 0
        trades["is_loss"] = trades["bps_numeric"] < 0
        fam = []
        for family, g in trades.groupby("family_key", dropna=False):
            fam.append({
                "family_key": family,
                "closed_trade_count": int(len(g)),
                "profit_count": int(g["is_profit"].sum()),
                "loss_count": int(g["is_loss"].sum()),
                "win_rate": round(float(g["is_profit"].mean()), 4) if len(g) else 0.0,
                "total_net_profit": round(float(g["net_profit_numeric"].sum(skipna=True)), 4),
                "mean_net_profit": round(float(g["net_profit_numeric"].mean(skipna=True)), 4),
                "total_bps": round(float(g["bps_numeric"].sum(skipna=True)), 4),
                "mean_bps": round(float(g["bps_numeric"].mean(skipna=True)), 4),
                "diagnosis_mix": ";".join(f"{k}:{v}" for k, v in Counter(g["diagnosis"]).items()),
            })
        family_summary = pd.DataFrame(fam).sort_values(["closed_trade_count", "total_bps"], ascending=[False, False])
        # Cohorts: stale contaminated vs post-fix non-stale; keep simple and deterministic.
        trades["cohort"] = trades["diagnosis"].apply(lambda x: "STALE_CONTAMINATED" if x == "STALE_CONTAMINATED" else "POST_STALE_FIX_OR_UNKNOWN")
        coh = []
        for cohort, g in trades.groupby("cohort", dropna=False):
            coh.append({
                "cohort": cohort,
                "closed_trade_count": int(len(g)),
                "profit_count": int(g["is_profit"].sum()),
                "loss_count": int(g["is_loss"].sum()),
                "win_rate": round(float(g["is_profit"].mean()), 4) if len(g) else 0.0,
                "total_bps": round(float(g["bps_numeric"].sum(skipna=True)), 4),
                "mean_bps": round(float(g["bps_numeric"].mean(skipna=True)), 4),
                "diagnosis_mix": ";".join(f"{k}:{v}" for k, v in Counter(g["diagnosis"]).items()),
            })
        cohort_summary = pd.DataFrame(coh)

    trade_csv = out_dir / "stage158_trade_attribution_audit_trades.csv"
    diagnosis_csv = out_dir / "stage158_diagnosis_summary.csv"
    family_csv = out_dir / "stage158_family_attribution_summary.csv"
    cohort_csv = out_dir / "stage158_cohort_attribution_summary.csv"
    summary_json = out_dir / "stage158_trade_attribution_audit_summary.json"

    trades.to_csv(trade_csv, index=False)
    diagnosis_summary.to_csv(diagnosis_csv, index=False)
    family_summary.to_csv(family_csv, index=False)
    cohort_summary.to_csv(cohort_csv, index=False)

    closed_count = int(len(trades))
    profit_count = int((pd.to_numeric(trades.get("bps_move", pd.Series(dtype=float)), errors="coerce") > 0).sum()) if not trades.empty else 0
    loss_count = int((pd.to_numeric(trades.get("bps_move", pd.Series(dtype=float)), errors="coerce") < 0).sum()) if not trades.empty else 0
    total_bps = float(pd.to_numeric(trades.get("bps_move", pd.Series(dtype=float)), errors="coerce").sum(skipna=True)) if not trades.empty else 0.0
    total_net = float(pd.to_numeric(trades.get("net_profit", pd.Series(dtype=float)), errors="coerce").sum(skipna=True)) if not trades.empty else 0.0
    diagnosis_counts = dict(zip(diagnosis_summary.get("diagnosis", []), diagnosis_summary.get("count", [])))

    # Decision is conservative: this audit does not unfreeze routing.
    if bar_info.get("bar_count", 0) == 0:
        decision = "STAGE158B_AUDIT_INCOMPLETE_BARS_NOT_LOADED_KEEP_FREEZE"
        recommended_action = "FIX_BAR_LOADER_OR_BARS_PATH_BEFORE_RULE_VS_EXECUTION_DECISION"
    elif diagnosis_counts.get("RULE_FAIL", 0) > max(diagnosis_counts.get("EXIT_FAIL", 0), diagnosis_counts.get("EXECUTION_OR_EXIT_FAIL", 0), diagnosis_counts.get("ROUTER_PROTOCOL_FAIL", 0)):
        decision = "STAGE158B_RULE_FAILURE_DOMINANT_REPAIR_DISCOVERY"
        recommended_action = "KEEP_ROUTING_FROZEN_AND_REBUILD_DISCOVERY_WITH_STRICTER_VALIDATION"
    elif diagnosis_counts.get("EXIT_FAIL", 0) + diagnosis_counts.get("EXECUTION_OR_EXIT_FAIL", 0) > 0:
        decision = "STAGE158B_EXECUTION_OR_EXIT_REPAIR_REQUIRED"
        recommended_action = "KEEP_ROUTING_FROZEN_AND_REPAIR_EXIT_EXECUTION_BEFORE_DISCARDING_RULES"
    elif diagnosis_counts.get("ROUTER_PROTOCOL_FAIL", 0) > 0:
        decision = "STAGE158B_ROUTER_PROTOCOL_REPAIR_REQUIRED"
        recommended_action = "KEEP_ROUTING_FROZEN_AND_REPLACE_ACTIVE_ROUTER_WITH_LOCKED_RULE_OR_LOCKED_FAMILY_PROTOCOL"
    else:
        decision = "STAGE158B_SMALL_N_OR_MIXED_ATTRIBUTION_KEEP_FREEZE"
        recommended_action = "KEEP_ROUTING_FROZEN_AND_USE_ATTRIBUTION_FOR_NEXT_REPAIR_STEP"

    summary = {
        "stage": STAGE,
        "generated_utc": _utcnow_iso(),
        "status": "STAGE158B_COMPLETE_ATTRIBUTION_AUDIT_READY",
        "decision": decision,
        "recommended_action": recommended_action,
        "severity": "HIGH" if "KEEP" in recommended_action or "REPAIR" in recommended_action else "MEDIUM",
        "root": str(root),
        "clean_ledger": str(args.clean_ledger),
        "score_csv": str(args.score_csv),
        "risk_summary": str(args.risk_summary),
        "bars_m5": str(args.bars_m5),
        "bar_loader": bar_info,
        "bar_count": int(bar_info.get("bar_count", 0) or 0),
        "closed_trade_count": closed_count,
        "profit_count": profit_count,
        "loss_count": loss_count,
        "win_rate": round(profit_count / closed_count, 4) if closed_count else 0.0,
        "total_net_profit": round(total_net, 4),
        "mean_net_profit": round(total_net / closed_count, 4) if closed_count else 0.0,
        "total_bps": round(total_bps, 4),
        "mean_bps": round(total_bps / closed_count, 4) if closed_count else 0.0,
        "stage145_gate_decision": risk.get("gate_decision", ""),
        "stage145_recommended_action": risk.get("recommended_action", ""),
        "diagnosis_counts": {str(k): int(v) for k, v in diagnosis_counts.items()},
        "cohort_summary_csv": str(cohort_csv),
        "family_summary_csv": str(family_csv),
        "diagnosis_summary_csv": str(diagnosis_csv),
        "trade_attribution_csv": str(trade_csv),
        "summary_json": str(summary_json),
        "next": [
            "Keep Stage157 freeze active while this attribution is reviewed.",
            "If RULE_FAIL dominates, rebuild discovery with stricter walk-forward/session/spread/event validation.",
            "If EXIT_FAIL or EXECUTION_OR_EXIT_FAIL appears, repair exit/MFE/MAE/timeout before discarding all rules.",
            "If ROUTER_PROTOCOL_FAIL appears, replace active-router demo with locked-rule or locked-family protocol.",
        ],
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary, trades, diagnosis_summary, family_summary, cohort_summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage158B read-only trade attribution audit")
    p.add_argument("--root", default=".")
    p.add_argument("--clean-ledger", required=True)
    p.add_argument("--score-csv", required=True)
    p.add_argument("--risk-summary", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--entry-time-shift-hours", type=float, default=-3.0)
    p.add_argument("--max-signal-age-sec", type=int, default=7200)
    p.add_argument("--horizon-hours", type=float, default=4.0)
    p.add_argument("--output-dir", default="")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    summary, *_ = build_attribution(args)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
