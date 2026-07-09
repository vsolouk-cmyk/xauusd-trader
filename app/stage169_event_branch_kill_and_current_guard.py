#!/usr/bin/env python3
"""
Stage169 Event Branch Kill + Current Guard Export - Loader Speed Hotfix

Purpose:
- Read Stage168 GDELT reaction rulespace results.
- If the broad event-alpha rulespace produced no commercial shortlist, explicitly kill the
  GDELT-alpha branch to avoid waiting/research loops.
- Preserve the event panel only as a current-event risk/regime guard, not as an alpha signal.

Safety:
- Read-only with respect to execution.
- Does not write MT5 signal files.
- order_routing_allowed = False
- demo_release_allowed = False
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage169_EVENT_BRANCH_KILL_AND_CURRENT_EVENT_GUARD"
ORDER_ROUTING_ALLOWED = False
DEMO_RELEASE_ALLOWED = False

EVENT_COLUMNS = [
    "event_count",
    "gold_long_pressure",
    "gold_short_pressure",
    "shock_abs",
    "geopolitical_escalation_score",
    "deescalation_score",
    "macro_policy_hawkish_score",
    "macro_policy_dovish_score",
    "inflation_energy_shock_score",
    "market_stress_score",
    "central_bank_gold_score",
    "net_gold_event_pressure",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def _detect_delimiter_from_header(path: Path) -> str | None:
    """Fast delimiter detection for AMarkets/MT5 and normalized CSV files."""
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        header = f.readline()
    candidates = ["\t", ",", ";", "|"]
    scores = {sep: header.count(sep) for sep in candidates}
    best_sep, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_sep if best_score > 0 else None


def read_csv_auto(path: Path, *, nrows: int | None = None, usecols: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    sep = _detect_delimiter_from_header(path)
    kwargs: Dict[str, Any] = {"nrows": nrows}
    if usecols is not None:
        kwargs["usecols"] = usecols
    if sep is None:
        return pd.read_csv(path, **kwargs)
    return pd.read_csv(path, sep=sep, **kwargs)


def inspect_bars_file_fast(path: Path) -> Dict[str, Any]:
    """Read only the header/first rows. Stage169 guard does not need the full M5 file."""
    if not path.exists():
        raise FileNotFoundError(f"bars file not found: {path}")
    sep = _detect_delimiter_from_header(path)
    sample = read_csv_auto(path, nrows=5)
    return {
        "source_path": str(path),
        "detected_separator": "tab" if sep == "\t" else (sep or "default_csv"),
        "raw_columns": list(sample.columns),
        "sample_rows_read": int(len(sample)),
        "note": "FAST_INSPECT_ONLY_STAGE169_GUARD_DOES_NOT_NEED_FULL_BAR_LOAD",
    }


def load_bars_m5(path: Path) -> pd.DataFrame:
    """Fallback only. Robustly load M5 timestamps when Stage168 split metadata is unavailable."""
    if not path.exists():
        raise FileNotFoundError(f"bars file not found: {path}")
    header = read_csv_auto(path, nrows=0)
    cols = {str(c).lower().strip(): c for c in header.columns}
    usecols: list[str]
    mode: str
    if "time_utc" in cols:
        usecols = [cols["time_utc"]]
        mode = "time_utc"
    elif "utc_time" in cols:
        usecols = [cols["utc_time"]]
        mode = "utc_time"
    elif "<date>" in cols and "<time>" in cols:
        usecols = [cols["<date>"], cols["<time>"]]
        mode = "mt5_split_date_time"
    else:
        raise ValueError(f"Cannot identify time columns in bars after delimiter detection: {list(header.columns)}")

    df = read_csv_auto(path, usecols=usecols)
    lcols = {str(c).lower().strip(): c for c in df.columns}
    if mode == "time_utc":
        t = pd.to_datetime(df[lcols["time_utc"]], utc=True, errors="coerce")
    elif mode == "utc_time":
        t = pd.to_datetime(df[lcols["utc_time"]], utc=True, errors="coerce")
    else:
        raw = df[lcols["<date>"]].astype(str).str.strip() + " " + df[lcols["<time>"]].astype(str).str.strip()
        # AMarkets/MT5 export observed in this project is server time UTC+3; normalize by -3h.
        t = pd.to_datetime(raw, errors="coerce") - pd.Timedelta(hours=3)
        t = t.dt.tz_localize("UTC")
    out = pd.DataFrame({"time_utc": t}).dropna().sort_values("time_utc").reset_index(drop=True)
    return out


def load_event_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"event panel not found: {path}")
    df = pd.read_csv(path)
    if "time_utc" in df.columns:
        tcol = "time_utc"
    elif "time_bucket_utc" in df.columns:
        tcol = "time_bucket_utc"
    else:
        raise ValueError("event panel must contain time_utc or time_bucket_utc")
    df["time_utc"] = pd.to_datetime(df[tcol], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc"]).sort_values("time_utc").reset_index(drop=True)
    for col in EVENT_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "event_shock_regime" not in df.columns:
        df["event_shock_regime"] = "NONE"
    return df


def positive_quantiles(s: pd.Series, qs: Tuple[float, ...]) -> Dict[str, float]:
    x = pd.to_numeric(s, errors="coerce").fillna(0.0)
    x = x[x > 0]
    out: Dict[str, float] = {}
    for q in qs:
        key = f"q{int(q * 100)}"
        out[key] = float(x.quantile(q)) if len(x) else 0.0
    out["positive_count"] = int(len(x))
    return out


def infer_split_time(stage168_summary: Dict[str, Any], bars_path: Path, holdout_pct: float) -> tuple[pd.Timestamp, Dict[str, Any]]:
    """Prefer Stage168 split metadata. Loading all M5 bars is a slow fallback only."""
    split_meta = stage168_summary.get("split_meta") or {}
    for key in ("holdout_start_utc", "split_time_utc"):
        if split_meta.get(key):
            return pd.to_datetime(split_meta[key], utc=True), {
                "split_source": f"stage168_summary.split_meta.{key}",
                "bars_loaded_for_split": False,
                "bars_fast_meta": inspect_bars_file_fast(bars_path),
            }

    bars = load_bars_m5(bars_path)
    idx = int(len(bars) * (1.0 - holdout_pct))
    idx = max(0, min(idx, len(bars) - 1))
    return pd.to_datetime(bars.loc[idx, "time_utc"], utc=True), {
        "split_source": "fallback_bars_m5_holdout_pct",
        "bars_loaded_for_split": True,
        "bars_rows_loaded": int(len(bars)),
        "bars_min_time_utc": str(bars["time_utc"].min()) if len(bars) else None,
        "bars_max_time_utc": str(bars["time_utc"].max()) if len(bars) else None,
    }


def classify_guard(recent: pd.DataFrame, thresholds: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    shock_q90 = thresholds["shock_abs"].get("q90", 0.0)
    shock_q95 = thresholds["shock_abs"].get("q95", 0.0)
    long_q90 = thresholds["gold_long_pressure"].get("q90", 0.0)
    short_q90 = thresholds["gold_short_pressure"].get("q90", 0.0)

    recent_max_shock = float(recent["shock_abs"].max()) if len(recent) else 0.0
    recent_sum_long = float(recent["gold_long_pressure"].sum()) if len(recent) else 0.0
    recent_sum_short = float(recent["gold_short_pressure"].sum()) if len(recent) else 0.0
    recent_max_long = float(recent["gold_long_pressure"].max()) if len(recent) else 0.0
    recent_max_short = float(recent["gold_short_pressure"].max()) if len(recent) else 0.0
    nonzero_hours = int((recent["shock_abs"] > 0).sum()) if len(recent) else 0

    if recent_sum_long > recent_sum_short * 1.25 and recent_sum_long > 0:
        bias = "LONG_SAFE_HAVEN_OR_DOVISH_BIAS"
    elif recent_sum_short > recent_sum_long * 1.25 and recent_sum_short > 0:
        bias = "SHORT_DEESCALATION_OR_HAWKISH_BIAS"
    elif recent_sum_long > 0 or recent_sum_short > 0:
        bias = "MIXED_EVENT_PRESSURE"
    else:
        bias = "NO_CURRENT_EVENT_PRESSURE"

    high = (shock_q95 > 0 and recent_max_shock >= shock_q95) or (long_q90 > 0 and recent_max_long >= long_q90) or (short_q90 > 0 and recent_max_short >= short_q90)
    medium = (shock_q90 > 0 and recent_max_shock >= shock_q90) or nonzero_hours >= 6

    if high:
        guard_state = "EVENT_GUARD_HIGH"
        action = "GUARD_ONLY_BLOCK_PROMOTION_AND_REQUIRE_MANUAL_REVIEW_FOR_NEW_ORDER_ENABLEMENT"
    elif medium:
        guard_state = "EVENT_GUARD_MEDIUM"
        action = "GUARD_ONLY_REDUCE_RISK_OR_REQUIRE_CONFIRMATION; DO_NOT_USE_AS_ALPHA"
    elif nonzero_hours > 0:
        guard_state = "EVENT_GUARD_LOW"
        action = "GUARD_ONLY_LOG_CONTEXT; DO_NOT_USE_AS_ALPHA"
    else:
        guard_state = "EVENT_GUARD_NEUTRAL"
        action = "NO_EVENT_GUARD_RESTRICTION_FROM_PANEL"

    return {
        "guard_state": guard_state,
        "directional_bias": bias,
        "recommended_guard_action": action,
        "recent_nonzero_event_hours": nonzero_hours,
        "recent_max_shock_abs": recent_max_shock,
        "recent_sum_gold_long_pressure": recent_sum_long,
        "recent_sum_gold_short_pressure": recent_sum_short,
        "recent_max_gold_long_pressure": recent_max_long,
        "recent_max_gold_short_pressure": recent_max_short,
    }


def write_decision_md(path: Path, summary: Dict[str, Any], top_recent: pd.DataFrame) -> None:
    guard = summary["current_guard"]
    stage168 = summary["stage168_verdict"]
    lines: List[str] = []
    lines.append("# Stage169 Event Branch Kill + Current Event Guard")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append(f"Decision: `{summary['decision']}`")
    lines.append(f"Recommended action: `{summary['recommended_action']}`")
    lines.append("")
    lines.append("## Branch verdict")
    lines.append("")
    lines.append(f"Stage168 decision: `{stage168.get('decision')}`")
    lines.append(f"Rules scanned: `{stage168.get('score_count')}`")
    lines.append(f"Commercial shortlist: `{stage168.get('shortlist_count')}`")
    lines.append("")
    lines.append("The current GDELT reaction alpha branch is killed as an execution/discovery path. Do not wait for more samples.")
    lines.append("")
    lines.append("## Current guard")
    lines.append("")
    lines.append(f"Guard state: `{guard['guard_state']}`")
    lines.append(f"Directional bias: `{guard['directional_bias']}`")
    lines.append(f"Guard action: `{guard['recommended_guard_action']}`")
    lines.append(f"Recent nonzero event hours: `{guard['recent_nonzero_event_hours']}`")
    lines.append("")
    lines.append("## Top recent event hours")
    lines.append("")
    if top_recent.empty:
        lines.append("No recent event pressure in the configured window.")
    else:
        view = top_recent[["time_utc", "shock_abs", "gold_long_pressure", "gold_short_pressure", "event_shock_regime"]].copy()
        lines.append(view.to_markdown(index=False))
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("Use the GDELT/news panel as a guard and context input only. Return commercial discovery to broader non-news alpha paths unless stronger hand-labeled event data is added.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage169 event alpha branch kill and current-event guard export")
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument("--bars-m5", required=True)
    ap.add_argument("--event-panel", required=True)
    ap.add_argument("--stage168-summary", default=None)
    ap.add_argument("--holdout-pct", type=float, default=0.20)
    ap.add_argument("--recent-hours", type=int, default=72)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "reports" / "stage169_event_branch_kill_and_current_guard"
    out_dir.mkdir(parents=True, exist_ok=True)

    stage168_summary_path = Path(args.stage168_summary).expanduser().resolve() if args.stage168_summary else root / "reports" / "stage168_gdelt_reaction_rulespace_rebuild" / "stage168_gdelt_reaction_rulespace_summary.json"
    stage168 = read_json(stage168_summary_path)

    bars_path = Path(args.bars_m5).expanduser()
    # Stage169 is a current guard/export stage: normally it should not load the full M5 history.
    # Stage168 already contains the locked split metadata. Only fallback to full bars if that metadata is missing.
    split_time, bars_fast_meta = infer_split_time(stage168, bars_path, args.holdout_pct)
    event = load_event_panel(Path(args.event_panel).expanduser())

    train_event = event[event["time_utc"] < split_time].copy()
    holdout_event = event[event["time_utc"] >= split_time].copy()

    thresholds = {
        "shock_abs": positive_quantiles(train_event["shock_abs"], (0.8, 0.9, 0.95)),
        "gold_long_pressure": positive_quantiles(train_event["gold_long_pressure"], (0.8, 0.9, 0.95)),
        "gold_short_pressure": positive_quantiles(train_event["gold_short_pressure"], (0.8, 0.9, 0.95)),
    }

    latest_time = event["time_utc"].max() if len(event) else pd.NaT
    window_start = latest_time - pd.Timedelta(hours=args.recent_hours) if pd.notna(latest_time) else pd.Timestamp.utcnow()
    recent = event[event["time_utc"] >= window_start].copy() if len(event) else event.copy()
    guard = classify_guard(recent, thresholds)

    score_count = int((stage168.get("evaluation_context") or {}).get("score_count") or stage168.get("score_count") or 0)
    shortlist_count = int((stage168.get("evaluation_context") or {}).get("shortlist_count") or stage168.get("shortlist_count") or 0)
    event_trainable = bool((stage168.get("event_panel_health") or {}).get("event_overlay_trainable", False))
    stage168_decision = stage168.get("decision", "UNKNOWN")

    if score_count > 0 and shortlist_count == 0 and event_trainable:
        decision = "STAGE169_KILL_GDELT_REACTION_ALPHA_KEEP_CURRENT_EVENT_GUARD_ONLY"
        recommended = "DO_NOT_WAIT; DO_NOT_RUN_EXECUTION_REPLAY; USE_EVENT_PANEL_ONLY_AS_CURRENT_REGIME_GUARD"
        severity = "HIGH"
    elif shortlist_count > 0:
        decision = "STAGE169_STAGE168_SHORTLIST_PRESENT_REQUIRES_EXECUTION_REPLAY_NOT_BRANCH_KILL"
        recommended = "RUN_EXECUTION_REPLAY_BEFORE_ANY_DEMO_RELEASE"
        severity = "WARN"
    else:
        decision = "STAGE169_INCONCLUSIVE_REVIEW_STAGE168_INPUTS"
        recommended = "REVIEW_STAGE168_OUTPUTS_AND_EVENT_PANEL_HEALTH"
        severity = "WARN"

    top_recent = recent.sort_values(["shock_abs", "gold_long_pressure", "gold_short_pressure"], ascending=False).head(20).copy()
    guard_csv = out_dir / "stage169_current_event_guard_recent_hours.csv"
    top_recent.to_csv(guard_csv, index=False)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
        "status": "STAGE169B_COMPLETE_EVENT_BRANCH_DECISION_READY_FAST_LOADER",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended,
        "bars_m5": str(Path(args.bars_m5).expanduser()),
        "bars_fast_meta": bars_fast_meta,
        "event_panel": str(Path(args.event_panel).expanduser()),
        "stage168_summary": str(stage168_summary_path),
        "stage168_verdict": {
            "decision": stage168_decision,
            "score_count": score_count,
            "shortlist_count": shortlist_count,
            "event_overlay_trainable": event_trainable,
        },
        "split_time_utc": str(split_time),
        "event_meta": {
            "panel_rows": int(len(event)),
            "train_event_rows": int(len(train_event)),
            "holdout_event_rows": int(len(holdout_event)),
            "train_nonzero_shock_hours": int((train_event["shock_abs"] > 0).sum()),
            "holdout_nonzero_shock_hours": int((holdout_event["shock_abs"] > 0).sum()),
            "min_time_utc": str(event["time_utc"].min()) if len(event) else None,
            "max_time_utc": str(event["time_utc"].max()) if len(event) else None,
        },
        "guard_thresholds_positive_train": thresholds,
        "current_guard": guard,
        "recent_window": {
            "recent_hours": args.recent_hours,
            "window_start_utc": str(window_start),
            "latest_event_panel_time_utc": str(latest_time),
        },
        "outputs": {
            "summary_json": str(out_dir / "stage169_event_branch_kill_and_current_guard_summary.json"),
            "guard_json": str(out_dir / "stage169_current_event_guard.json"),
            "guard_recent_hours_csv": str(guard_csv),
            "decision_md": str(out_dir / "stage169_decision.md"),
        },
        "next": [
            "Do not run Stage169 execution replay when Stage168 shortlist_count is zero.",
            "Use event/news/GDELT only as a current regime guard unless stronger labeled historical event features are added.",
            "Return commercial discovery to broader non-news alpha paths or create a stronger supervised event-label dataset.",
        ],
    }

    write_json(out_dir / "stage169_event_branch_kill_and_current_guard_summary.json", summary)
    write_json(out_dir / "stage169_current_event_guard.json", {
        "generated_utc": summary["generated_utc"],
        "decision": decision,
        "current_guard": guard,
        "thresholds": thresholds,
        "recent_window": summary["recent_window"],
        "execution_safety": {
            "order_routing_allowed": ORDER_ROUTING_ALLOWED,
            "demo_release_allowed": DEMO_RELEASE_ALLOWED,
            "note": "Guard only. No alpha authorization and no MT5 signal writing.",
        },
    })
    write_decision_md(out_dir / "stage169_decision.md", summary, top_recent)

    print(json.dumps({
        "stage": STAGE,
        "decision": decision,
        "guard_state": guard["guard_state"],
        "directional_bias": guard["directional_bias"],
        "shortlist_count": shortlist_count,
        "outputs": summary["outputs"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
