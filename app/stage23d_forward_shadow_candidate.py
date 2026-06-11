"""
Stage 23D — narrow forward-shadow candidate tracker for the validated Stage23B signal.

Research/shadow-only module. It does NOT modify Stage18A, does NOT authorize paper/live,
and does NOT create orders.

Purpose:
- Track the de-duplicated Stage23B/Stage23C london_oneway_continuation candidate in forward-shadow mode.
- Detect open forward signals after AMarkets CSV refresh.
- Resolve outcomes only from observed M1 candles using conservative SL-first logic.
- Maintain a local ledger so future runs can distinguish genuine forward outcomes from late backfills.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage23d_forward_shadow_candidate
    cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from app.stage23b_continuation_no_trade_discovery import (
        Candidate,
        ROUNDTRIP_COST_USD,
        events_london_oneway_continuation,
        load_market_data,
        merge_atr,
        profit_factor,
    )
except Exception as exc:  # pragma: no cover - user-facing guard
    raise RuntimeError(
        "Stage23D depends on app.stage23b_continuation_no_trade_discovery. "
        "Apply/run Stage23B before Stage23D. Original import error: " + str(exc)
    )


STAGE_NAME = "stage23d_forward_shadow_candidate"
REPORT_DIR = Path("data/reports") / STAGE_NAME
LEDGER_PATH = REPORT_DIR / "stage23d_forward_shadow_ledger.csv"
REPORT_MD = REPORT_DIR / "stage23d_forward_shadow_candidate.md"
REPORT_JSON = REPORT_DIR / "stage23d_forward_shadow_candidate.json"
RECENT_EVENTS_CSV = REPORT_DIR / "stage23d_recent_events.csv"

LOOKBACK_HOURS = int(os.getenv("STAGE23D_LOOKBACK_HOURS", "336"))  # 14 days
MAX_RECENT_ROWS_REPORT = int(os.getenv("STAGE23D_MAX_RECENT_ROWS_REPORT", "25"))

# De-duplicated primary candidate selected from Stage23C:
# S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65
# The pb0.3 variant had identical events and is intentionally not tracked here.
PRIMARY_CANDIDATE = Candidate(
    "london_oneway_continuation",
    "S23D_PRIMARY_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65",
    {
        "london_move_atr_min": 0.9,
        "eff_min": 0.60,
        "pullback_atr_max": 0.10,
        "ny_confirm_atr_min": 0.15,
        "entry_hour": 13,
        "horizon_min": 180,
        "tp_atr": 0.60,
        "sl_atr": 0.65,
    },
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _finite_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_for_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        if math.isinf(val):
            return "inf"
        if math.isnan(val):
            return None
        return val
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def _signal_id(candidate: Candidate, signal_time: Any, direction: str) -> str:
    ts = str(pd.Timestamp(signal_time))
    return f"{candidate.name}|{ts}|{str(direction).lower()}"


def _read_ledger() -> pd.DataFrame:
    if not LEDGER_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(LEDGER_PATH)
        if "signal_id" not in df.columns:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def _write_ledger(df: pd.DataFrame) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if df.empty:
        df.to_csv(LEDGER_PATH, index=False)
        return
    sort_cols = [c for c in ["signal_time", "candidate", "direction"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    df.to_csv(LEDGER_PATH, index=False)


def _resolve_event_forward(candles: pd.DataFrame, event: pd.Series, candidate: Candidate, data_latest: pd.Timestamp) -> Dict[str, Any]:
    """Resolve one candidate event using only currently available M1 candles.

    Conservative rule: if both TP and SL are possible inside the same M1 bar, SL is assumed first
    because intrabar sequence is unknown.
    """
    c = candles.sort_values("time").reset_index(drop=True).copy()
    times = pd.to_datetime(c["time"]).to_numpy(dtype="datetime64[ns]")
    opens = c["open"].to_numpy(dtype=float)
    highs = c["high"].to_numpy(dtype=float)
    lows = c["low"].to_numpy(dtype=float)
    closes = c["close"].to_numpy(dtype=float)

    params = candidate.params
    signal_time = pd.Timestamp(event["signal_time"])
    direction = str(event["direction"]).lower()
    atr = _safe_float(event.get("atr", np.nan), default=np.nan)
    sid = _signal_id(candidate, signal_time, direction)

    base: Dict[str, Any] = {
        "signal_id": sid,
        "candidate": candidate.name,
        "family": candidate.family,
        "signal_time": str(signal_time),
        "direction": direction,
        "atr": round(float(atr), 6) if np.isfinite(atr) else None,
        "status": "UNRESOLVED_NO_ENTRY",
        "entry_time": None,
        "entry": None,
        "tp": None,
        "sl": None,
        "exit_time": None,
        "exit": None,
        "exit_reason": None,
        "gross": None,
        "net_x1": None,
        "net_x4": None,
        "floating_gross": None,
        "floating_net_x1": None,
        "horizon_deadline": None,
        "is_open": False,
        "is_resolved": False,
        "is_late_backfill_if_first_seen_now": False,
    }

    if not np.isfinite(atr) or atr <= 0 or direction not in {"long", "short"}:
        base["status"] = "INVALID_EVENT"
        return base

    signal_time64 = np.datetime64(signal_time.to_datetime64(), "ns")
    entry_idx = int(np.searchsorted(times, signal_time64, side="right"))
    if entry_idx >= len(times):
        base["status"] = "UNRESOLVED_WAITING_FOR_NEXT_M1_BAR"
        base["is_open"] = True
        return base

    entry_time64 = times[entry_idx]
    entry = float(opens[entry_idx])
    horizon_delta = np.timedelta64(int(params["horizon_min"]), "m")
    cutoff = entry_time64 + horizon_delta
    tp_atr = float(params["tp_atr"])
    sl_atr = float(params["sl_atr"])

    if direction == "long":
        tp = entry + tp_atr * atr
        sl = entry - sl_atr * atr
    else:
        tp = entry - tp_atr * atr
        sl = entry + sl_atr * atr

    base.update(
        {
            "entry_time": str(pd.Timestamp(entry_time64)),
            "entry": round(entry, 5),
            "tp": round(tp, 5),
            "sl": round(sl, 5),
            "horizon_deadline": str(pd.Timestamp(cutoff)),
        }
    )

    full_end_idx = int(np.searchsorted(times, cutoff, side="right"))
    available_end_idx = min(full_end_idx, len(times))
    if available_end_idx <= entry_idx:
        base["status"] = "UNRESOLVED_NO_AVAILABLE_M1_AFTER_ENTRY"
        base["is_open"] = True
        return base

    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    for j in range(entry_idx, available_end_idx):
        hi = float(highs[j])
        lo = float(lows[j])
        if direction == "long":
            if lo <= sl:
                exit_idx = j
                exit_price = sl
                exit_reason = "sl_conservative"
                break
            if hi >= tp:
                exit_idx = j
                exit_price = tp
                exit_reason = "tp"
                break
        else:
            if hi >= sl:
                exit_idx = j
                exit_price = sl
                exit_reason = "sl_conservative"
                break
            if lo <= tp:
                exit_idx = j
                exit_price = tp
                exit_reason = "tp"
                break

    if exit_idx is not None and exit_price is not None:
        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        base.update(
            {
                "status": "RESOLVED_TP_SL",
                "exit_time": str(pd.Timestamp(times[exit_idx])),
                "exit": round(float(exit_price), 5),
                "exit_reason": exit_reason,
                "gross": round(float(gross), 5),
                "net_x1": round(float(gross - ROUNDTRIP_COST_USD), 5),
                "net_x4": round(float(gross - 4.0 * ROUNDTRIP_COST_USD), 5),
                "is_open": False,
                "is_resolved": True,
                "is_late_backfill_if_first_seen_now": pd.Timestamp(times[exit_idx]) <= data_latest,
            }
        )
        return base

    # No TP/SL hit. If the full horizon has elapsed in available data, close at horizon bar.
    if full_end_idx <= len(times) and data_latest >= pd.Timestamp(cutoff):
        hidx = max(entry_idx, full_end_idx - 1)
        exit_price = float(closes[hidx])
        gross = (exit_price - entry) if direction == "long" else (entry - exit_price)
        base.update(
            {
                "status": "RESOLVED_HORIZON_CLOSE",
                "exit_time": str(pd.Timestamp(times[hidx])),
                "exit": round(float(exit_price), 5),
                "exit_reason": "horizon_close",
                "gross": round(float(gross), 5),
                "net_x1": round(float(gross - ROUNDTRIP_COST_USD), 5),
                "net_x4": round(float(gross - 4.0 * ROUNDTRIP_COST_USD), 5),
                "is_open": False,
                "is_resolved": True,
                "is_late_backfill_if_first_seen_now": pd.Timestamp(times[hidx]) <= data_latest,
            }
        )
        return base

    # Horizon still open; mark floating PnL using the latest available candle inside the horizon window.
    current_idx = max(entry_idx, available_end_idx - 1)
    current_close = float(closes[current_idx])
    floating = (current_close - entry) if direction == "long" else (entry - current_close)
    base.update(
        {
            "status": "OPEN_FORWARD_UNRESOLVED",
            "exit_time": None,
            "exit": None,
            "exit_reason": "open_unresolved",
            "floating_gross": round(float(floating), 5),
            "floating_net_x1": round(float(floating - ROUNDTRIP_COST_USD), 5),
            "is_open": True,
            "is_resolved": False,
            "is_late_backfill_if_first_seen_now": False,
        }
    )
    return base


def _merge_with_ledger(new_records: List[Dict[str, Any]], ledger: pd.DataFrame, data_latest: pd.Timestamp) -> tuple[pd.DataFrame, Dict[str, Any]]:
    now_utc = _utc_now_iso()
    old_by_id: Dict[str, Dict[str, Any]] = {}
    if not ledger.empty:
        for _, row in ledger.iterrows():
            old_by_id[str(row["signal_id"])] = row.to_dict()

    merged_updates: List[Dict[str, Any]] = []
    new_signal_count = 0
    new_forward_open_count = 0
    new_late_backfill_count = 0
    newly_resolved_forward_count = 0

    for rec in new_records:
        sid = str(rec["signal_id"])
        old = old_by_id.get(sid)
        is_new = old is None
        if is_new:
            rec["first_seen_utc"] = now_utc
            rec["first_seen_data_time"] = str(data_latest)
            if bool(rec.get("is_open")):
                rec["first_seen_class"] = "FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME"
                new_forward_open_count += 1
            elif bool(rec.get("is_resolved")):
                rec["first_seen_class"] = "LATE_DETECTED_ALREADY_RESOLVED"
                new_late_backfill_count += 1
            else:
                rec["first_seen_class"] = "UNRESOLVED_FIRST_SEEN"
            rec["previous_status"] = None
            new_signal_count += 1
        else:
            rec["first_seen_utc"] = old.get("first_seen_utc")
            rec["first_seen_data_time"] = old.get("first_seen_data_time")
            rec["first_seen_class"] = old.get("first_seen_class")
            rec["previous_status"] = old.get("status")
            prior_open = str(old.get("status", "")).startswith("OPEN") or bool(old.get("is_open") in [True, "True", "true", 1, "1"])
            if prior_open and bool(rec.get("is_resolved")):
                newly_resolved_forward_count += 1

        # Forward-valid outcome means it was first seen before or at its eventual exit time.
        rec["forward_valid_outcome"] = False
        if bool(rec.get("is_open")):
            rec["forward_valid_outcome"] = True
        elif bool(rec.get("is_resolved")) and rec.get("exit_time") and rec.get("first_seen_data_time"):
            try:
                first_seen_data = pd.Timestamp(rec["first_seen_data_time"])
                exit_time = pd.Timestamp(rec["exit_time"])
                rec["forward_valid_outcome"] = first_seen_data <= exit_time
            except Exception:
                rec["forward_valid_outcome"] = False

        rec["last_seen_utc"] = now_utc
        rec["last_seen_data_time"] = str(data_latest)
        merged_updates.append(rec)

    update_df = pd.DataFrame(merged_updates)
    if ledger.empty:
        final = update_df
    else:
        untouched = ledger[~ledger["signal_id"].astype(str).isin(set(update_df["signal_id"].astype(str)))] if not update_df.empty else ledger
        final = pd.concat([untouched, update_df], ignore_index=True, sort=False)

    counters = {
        "new_signal_count": int(new_signal_count),
        "new_forward_open_count": int(new_forward_open_count),
        "new_late_backfill_count": int(new_late_backfill_count),
        "newly_resolved_forward_count": int(newly_resolved_forward_count),
    }
    return final, counters


def _metric_summary(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "total_x1": 0.0, "win_rate_x1": 0.0}
    r = df[df["is_resolved"].astype(str).isin(["True", "true", "1"]) | (df["is_resolved"] == True)].copy()
    if r.empty or "net_x1" not in r.columns:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "total_x1": 0.0, "win_rate_x1": 0.0}
    n1 = pd.to_numeric(r["net_x1"], errors="coerce").dropna()
    n4 = pd.to_numeric(r["net_x4"], errors="coerce").dropna() if "net_x4" in r.columns else pd.Series(dtype=float)
    return {
        "events": int(len(n1)),
        "pf_x1": round(float(profit_factor(n1)), 4) if len(n1) else 0.0,
        "pf_x4": round(float(profit_factor(n4)), 4) if len(n4) else 0.0,
        "total_x1": round(float(n1.sum()), 4) if len(n1) else 0.0,
        "win_rate_x1": round(float((n1 > 0).mean()), 4) if len(n1) else 0.0,
    }


def _status_decision(counters: Dict[str, Any], open_count: int) -> str:
    if open_count > 0:
        return "STAGE23D_FORWARD_SIGNAL_OPEN_RESEARCH_ONLY"
    if counters.get("newly_resolved_forward_count", 0) > 0:
        return "STAGE23D_FORWARD_OUTCOME_AVAILABLE_RESEARCH_ONLY"
    if counters.get("new_late_backfill_count", 0) > 0:
        return "STAGE23D_LATE_DETECTED_REVIEW_CADENCE_RESEARCH_ONLY"
    return "STAGE23D_NO_ACTIVE_FORWARD_SIGNAL_RESEARCH_ONLY"


def _markdown_table(df: pd.DataFrame, cols: List[str], limit: int) -> str:
    if df.empty:
        return "No rows."
    show = df.copy()
    for c in cols:
        if c not in show.columns:
            show[c] = None
    show = show[cols].head(limit)

    def fmt(v: Any) -> str:
        if isinstance(v, (list, tuple, set)):
            return ", ".join(str(x) for x in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False, sort_keys=True)
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
        if isinstance(v, float):
            if math.isinf(v):
                return "inf"
            return f"{v:.4f}".rstrip("0").rstrip(".")
        return str(v).replace("|", "/")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def render_markdown(report: Dict[str, Any], recent_df: pd.DataFrame, ledger_df: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Stage23D Forward-Shadow Candidate Tracker")
    lines.append("")
    lines.append(f"Generated UTC: {report['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(str(report["decision"]))
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow only.")
    lines.append("- Stage18A v2 remains the active operational forward-shadow runner.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Stage23D tracks one de-duplicated Stage23B/Stage23C candidate separately; it does not add it to Stage18A.")
    lines.append("")
    lines.append("## Tracked candidate")
    lines.append("")
    lines.append(f"- Candidate: `{PRIMARY_CANDIDATE.name}`")
    lines.append("- Family: `london_oneway_continuation`")
    lines.append("- Parameters:")
    lines.append("```json")
    lines.append(json.dumps(PRIMARY_CANDIDATE.params, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- M1 rows: {report['data']['m1_rows']} | span: {report['data']['m1_start']} → {report['data']['m1_end']}")
    lines.append(f"- H1 rows: {report['data']['h1_rows']} | span: {report['data']['h1_start']} → {report['data']['h1_end']}")
    lines.append(f"- M15 rows: {report['data']['m15_rows']} | span: {report['data']['m15_start']} → {report['data']['m15_end']}")
    lines.append(f"- Lookback hours: {report['settings']['lookback_hours']}")
    lines.append(f"- Roundtrip cost x1: {ROUNDTRIP_COST_USD}")
    lines.append("")
    lines.append("## Run counters")
    lines.append("")
    for key, val in report["counters"].items():
        lines.append(f"- {key}: {val}")
    lines.append(f"- open_signal_count_now: {report['open_signal_count_now']}")
    lines.append(f"- resolved_signal_count_in_ledger: {report['resolved_signal_count_in_ledger']}")
    lines.append(f"- forward_valid_resolved_count: {report['forward_valid_resolved_count']}")
    lines.append("")
    lines.append("## Forward-valid resolved metric snapshot")
    lines.append("")
    lines.append("These metrics include only outcomes whose first recorded observation happened before or at exit time.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report["forward_valid_metrics"], indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Recent tracked events")
    lines.append("")
    recent_cols = [
        "status",
        "first_seen_class",
        "forward_valid_outcome",
        "signal_time",
        "direction",
        "entry_time",
        "exit_time",
        "exit_reason",
        "net_x1",
        "floating_net_x1",
    ]
    if not recent_df.empty:
        recent_sorted = recent_df.copy()
        recent_sorted["_signal_dt"] = pd.to_datetime(recent_sorted["signal_time"], errors="coerce")
        recent_sorted = recent_sorted.sort_values("_signal_dt", ascending=False).drop(columns=["_signal_dt"])
    else:
        recent_sorted = recent_df
    lines.append(_markdown_table(recent_sorted, recent_cols, MAX_RECENT_ROWS_REPORT))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- An open signal here is still research/shadow-only; it is not an order instruction.")
    lines.append("- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after its outcome was already knowable from the CSV; do not count it as forward proof.")
    lines.append("- `FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME` is the useful state for collecting forward-shadow evidence.")
    lines.append("- Keep Stage18A v2 running separately after each AMarkets CSV refresh.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `{REPORT_JSON}`")
    lines.append(f"- `{REPORT_MD}`")
    lines.append(f"- `{LEDGER_PATH}`")
    lines.append(f"- `{RECENT_EVENTS_CSV}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_utc = _utc_now_iso()

    m1, h1, m15, meta = load_market_data()
    m15_atr = merge_atr(m15, h1)
    data_latest = pd.Timestamp(m1["time"].max())
    lookback_start = data_latest - pd.Timedelta(hours=LOOKBACK_HOURS)

    events = events_london_oneway_continuation(m15_atr, PRIMARY_CANDIDATE.params)
    if events.empty:
        recent_events = events
    else:
        events["signal_time_dt"] = pd.to_datetime(events["signal_time"], errors="coerce")
        recent_events = events[events["signal_time_dt"] >= lookback_start].copy()

    new_records: List[Dict[str, Any]] = []
    for _, ev in recent_events.sort_values("signal_time").iterrows() if not recent_events.empty else []:
        new_records.append(_resolve_event_forward(m1, ev, PRIMARY_CANDIDATE, data_latest))

    ledger = _read_ledger()
    final_ledger, counters = _merge_with_ledger(new_records, ledger, data_latest)
    _write_ledger(final_ledger)

    # Recent events file is the current-window snapshot, not the full ledger.
    recent_df = pd.DataFrame(new_records)
    recent_df.to_csv(RECENT_EVENTS_CSV, index=False)

    if not final_ledger.empty:
        is_open = final_ledger.get("is_open", pd.Series(dtype=object)).astype(str).isin(["True", "true", "1"])
        is_resolved = final_ledger.get("is_resolved", pd.Series(dtype=object)).astype(str).isin(["True", "true", "1"])
        forward_valid = final_ledger.get("forward_valid_outcome", pd.Series(dtype=object)).astype(str).isin(["True", "true", "1"])
        open_count = int(is_open.sum())
        resolved_count = int(is_resolved.sum())
        forward_valid_resolved = final_ledger[is_resolved & forward_valid].copy()
    else:
        open_count = 0
        resolved_count = 0
        forward_valid_resolved = pd.DataFrame()

    decision = _status_decision(counters, open_count)
    report: Dict[str, Any] = {
        "generated_utc": generated_utc,
        "decision": decision,
        "scope": {
            "research_shadow_only": True,
            "stage18a_unchanged": True,
            "no_ea_change": True,
            "no_automatic_trading": True,
            "no_paper_live_order_authorization": True,
        },
        "candidate": {"name": PRIMARY_CANDIDATE.name, "family": PRIMARY_CANDIDATE.family, "params": PRIMARY_CANDIDATE.params},
        "data": {
            "m1_rows": int(len(m1)),
            "m1_start": str(pd.Timestamp(m1["time"].min())),
            "m1_end": str(pd.Timestamp(m1["time"].max())),
            "h1_rows": int(len(h1)),
            "h1_start": str(pd.Timestamp(h1["time"].min())),
            "h1_end": str(pd.Timestamp(h1["time"].max())),
            "m15_rows": int(len(m15)),
            "m15_start": str(pd.Timestamp(m15["time"].min())),
            "m15_end": str(pd.Timestamp(m15["time"].max())),
            "data_load_meta": meta,
        },
        "settings": {"lookback_hours": LOOKBACK_HOURS, "max_recent_rows_report": MAX_RECENT_ROWS_REPORT},
        "counters": {
            **counters,
            "recent_events_found_in_lookback": int(len(recent_events)) if recent_events is not None else 0,
            "ledger_total_rows": int(len(final_ledger)),
        },
        "open_signal_count_now": open_count,
        "resolved_signal_count_in_ledger": resolved_count,
        "forward_valid_resolved_count": int(len(forward_valid_resolved)),
        "forward_valid_metrics": _metric_summary(forward_valid_resolved),
        "output_files": {
            "report_json": str(REPORT_JSON),
            "report_md": str(REPORT_MD),
            "ledger_csv": str(LEDGER_PATH),
            "recent_events_csv": str(RECENT_EVENTS_CSV),
        },
    }

    REPORT_JSON.write_text(json.dumps(_finite_for_json(report), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report, recent_df, final_ledger), encoding="utf-8")

    print(json.dumps({"stage": STAGE_NAME, "decision": decision, "report_md": str(REPORT_MD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
