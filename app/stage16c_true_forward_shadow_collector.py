#!/usr/bin/env python3
"""
Stage 16C — True-Forward Shadow Collector

Purpose:
- Start a persistent true-forward shadow journal for the Stage 16A/16B research setup.
- Avoid contaminating forward evidence with historical scans.
- Log only signals that occur after collector_start_utc.
- Mark any signal discovered after its exit time as NOT_FORWARD_LATE_DETECTED.
- Resolve outcomes only after exit_target_utc is reached.

Research setup:
- prev_day_low_sweep_rejection
- LONG research direction
- sweep_depth >= 1.62
- reclaim_above_prev_day_low < 1.55
- real_yield_10y_chg5 > 0
- entry = next M15 open
- exit = 60 minutes after theoretical entry
- cost = 0.35 USD

Hard rules:
- True-forward shadow collection only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage16c_true_forward_shadow_collector")


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def normalize_col(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(r)


def load_bars(conn: sqlite3.Connection, tf: str) -> pd.DataFrame:
    if not table_exists(conn, "bars"):
        raise RuntimeError("Missing table: bars")
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe=?
        ORDER BY utc_time
        """,
        (tf,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time").set_index("utc_time")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_m1_m15(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    m1 = load_bars(conn, "1m")
    if len(m1) > 1000:
        return m1, resample_ohlc(m1, "15min"), "m1_to_m15"
    m5 = load_bars(conn, "5m")
    if len(m5) > 1000:
        return pd.DataFrame(), resample_ohlc(m5, "15min"), "m5_to_m15_no_m1_outcome"
    m15 = load_bars(conn, "15m")
    if len(m15) > 500:
        return pd.DataFrame(), m15, "m15_no_m1_outcome"
    h1 = load_bars(conn, "1h")
    if len(h1) > 500:
        return pd.DataFrame(), h1, "h1_fallback_no_m1_outcome"
    raise RuntimeError("No usable bars found.")


def detect_date_col(cols: Sequence[str]) -> Optional[str]:
    nmap = {normalize_col(c): c for c in cols}
    for p in ["date", "dt", "datetime", "timestamp", "utc_time", "_date"]:
        if p in nmap:
            return nmap[p]
    for c in cols:
        n = normalize_col(c)
        if "date" in n or "time" in n:
            return c
    return None


def detect_real_yield_col(cols: Sequence[str]) -> Optional[str]:
    nmap = {normalize_col(c): c for c in cols}
    for p in ["real_yield_10y", "dfii10", "real_yield"]:
        if p in nmap:
            return nmap[p]
    for c in cols:
        n = normalize_col(c)
        if "real" in n and "yield" in n and "10" in n and not n.startswith("d_"):
            return c
    for c in cols:
        if "dfii10" in normalize_col(c):
            return c
    return None


def load_macro_real_yield(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, Dict]:
    audit = {
        "macro_source": None,
        "date_col": None,
        "real_yield_col": None,
        "rows": 0,
        "status": "missing",
        "reason": "",
    }

    if table_exists(conn, "macro_daily_regime"):
        df = pd.read_sql_query("SELECT * FROM macro_daily_regime ORDER BY 1", conn)
        date_col = detect_date_col(df.columns)
        ry_col = detect_real_yield_col(df.columns)
        if date_col and ry_col:
            out = pd.DataFrame({
                "dt": pd.to_datetime(df[date_col], utc=True, errors="coerce"),
                "real_yield_10y": pd.to_numeric(df[ry_col], errors="coerce"),
            }).dropna()
            if len(out) >= 10:
                out = out.sort_values("dt").drop_duplicates("dt", keep="last")
                out["real_yield_10y_chg5"] = out["real_yield_10y"] - out["real_yield_10y"].shift(5)
                out = out.dropna(subset=["real_yield_10y_chg5"])
                audit.update({
                    "macro_source": "macro_daily_regime",
                    "date_col": date_col,
                    "real_yield_col": ry_col,
                    "rows": int(len(out)),
                    "status": "loaded",
                    "reason": "preferred_daily_regime",
                })
                return out, audit

    audit["reason"] = "No usable macro_daily_regime.real_yield_10y found."
    return pd.DataFrame(), audit


def previous_day_levels(m15: pd.DataFrame) -> pd.DataFrame:
    daily = resample_ohlc(m15, "1D")
    rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        rows.append({"day": day, "pdh": float(prev["high"]), "pdl": float(prev["low"])})
    return pd.DataFrame(rows)


def attach_macro(events: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    x = events.sort_values("event_utc").copy()
    if macro.empty:
        x["real_yield_10y"] = float("nan")
        x["real_yield_10y_chg5"] = float("nan")
        x["macro_real_yield_up"] = False
        return x
    out = pd.merge_asof(
        x,
        macro.sort_values("dt"),
        left_on="event_utc",
        right_on="dt",
        direction="backward",
    )
    out["macro_real_yield_up"] = pd.to_numeric(out["real_yield_10y_chg5"], errors="coerce") > 0
    return out


def detect_setup_candidates(
    m15: pd.DataFrame,
    macro: pd.DataFrame,
    scan_days: int,
    sweep_depth_min: float,
    reclaim_max: float,
    buffer_usd: float,
) -> pd.DataFrame:
    x = m15.copy()
    if x.empty:
        return pd.DataFrame()
    if scan_days > 0:
        cutoff = x.index.max() - pd.Timedelta(days=scan_days)
        x = x[x.index >= cutoff].copy()

    levels = previous_day_levels(m15)
    if levels.empty or x.empty:
        return pd.DataFrame()

    x["day"] = x.index.strftime("%Y-%m-%d")
    x = x.reset_index()
    if "utc_time" in x.columns:
        x = x.rename(columns={"utc_time": "event_utc"})
    else:
        x = x.rename(columns={x.columns[0]: "event_utc"})

    x = x.merge(levels, on="day", how="left").dropna(subset=["pdl"])
    x["sweep_depth"] = x["pdl"] - x["low"]
    x["reclaim_above_pdl"] = x["close"] - x["pdl"]
    x["tech_condition"] = (
        (x["low"] < x["pdl"] - buffer_usd)
        & (x["close"] > x["pdl"])
        & (x["sweep_depth"] >= sweep_depth_min)
        & (x["reclaim_above_pdl"] >= 0)
        & (x["reclaim_above_pdl"] < reclaim_max)
    )
    x = x[x["tech_condition"]].copy()
    if x.empty:
        return x
    x = attach_macro(x, macro)
    x["stage16c_signal_condition"] = x["tech_condition"] & x["macro_real_yield_up"]
    x = x[x["stage16c_signal_condition"]].copy()
    if x.empty:
        return x

    x["event_utc"] = pd.to_datetime(x["event_utc"], utc=True, errors="coerce")
    x["entry_utc"] = x["event_utc"] + pd.Timedelta(minutes=15)
    x["exit_target_utc"] = x["entry_utc"] + pd.Timedelta(minutes=60)
    x["signal_id"] = x["event_utc"].dt.strftime("%Y%m%dT%H%M%SZ") + "_stage16c_macro_pressure_reversal_long"
    x["research_side"] = "LONG"
    x["authorization"] = "RESEARCH_TRUE_FORWARD_SHADOW_ONLY_NO_ORDER"
    return x.sort_values("event_utc")


def load_or_create_state(state_path: Path, collector_start_utc: Optional[str]) -> Dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))

    start = pd.to_datetime(collector_start_utc, utc=True) if collector_start_utc else now_utc()
    state = {
        "created_utc": now_iso(),
        "collector_start_utc": start.isoformat(),
        "tool_version": TOOL_VERSION,
        "purpose": "true_forward_shadow_start_boundary",
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return state


def load_journal(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for c in ["event_utc", "entry_utc", "exit_target_utc", "detected_utc", "resolved_utc"]:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], utc=True, errors="coerce")
    return x


def append_new_signals(
    journal: pd.DataFrame,
    candidates: pd.DataFrame,
    collector_start_utc: pd.Timestamp,
    detected_utc: pd.Timestamp,
    latest_bar_utc: pd.Timestamp,
) -> Tuple[pd.DataFrame, int, int]:
    existing_ids = set(journal["signal_id"].astype(str)) if not journal.empty and "signal_id" in journal.columns else set()
    new_rows = []
    skipped_before_start = 0

    for _, r in candidates.iterrows():
        event_utc = pd.to_datetime(r["event_utc"], utc=True)
        if event_utc <= collector_start_utc:
            skipped_before_start += 1
            continue
        sid = str(r["signal_id"])
        if sid in existing_ids:
            continue

        entry_utc = pd.to_datetime(r["entry_utc"], utc=True)
        exit_target_utc = pd.to_datetime(r["exit_target_utc"], utc=True)

        if detected_utc > exit_target_utc:
            status = "not_forward_late_detected"
            forward_valid = False
        elif latest_bar_utc >= exit_target_utc:
            status = "not_forward_exit_already_available"
            forward_valid = False
        else:
            status = "pending_entry" if latest_bar_utc < entry_utc else "open_shadow"
            forward_valid = True

        new_rows.append({
            "signal_id": sid,
            "detected_utc": detected_utc,
            "event_utc": event_utc,
            "entry_utc": entry_utc,
            "exit_target_utc": exit_target_utc,
            "research_side": "LONG",
            "forward_valid": bool(forward_valid),
            "status": status,
            "sweep_depth": float(r.get("sweep_depth", float("nan"))),
            "reclaim_above_pdl": float(r.get("reclaim_above_pdl", float("nan"))),
            "pdl": float(r.get("pdl", float("nan"))),
            "event_close": float(r.get("close", float("nan"))),
            "real_yield_10y": float(r.get("real_yield_10y", float("nan"))),
            "real_yield_10y_chg5": float(r.get("real_yield_10y_chg5", float("nan"))),
            "entry_price": float("nan"),
            "entry_price_source": "",
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_ret_x1": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "resolved_utc": pd.NaT,
            "authorization": "RESEARCH_TRUE_FORWARD_SHADOW_ONLY_NO_ORDER",
        })

    if new_rows:
        add = pd.DataFrame(new_rows)
        journal = pd.concat([journal, add], ignore_index=True) if not journal.empty else add

    return journal, len(new_rows), skipped_before_start


def get_entry_price(m15: pd.DataFrame, entry_utc: pd.Timestamp) -> Tuple[float, str]:
    if entry_utc in m15.index:
        return float(m15.loc[entry_utc]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_utc)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_data"


def resolve_journal(journal: pd.DataFrame, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float, resolved_utc: pd.Timestamp) -> Tuple[pd.DataFrame, int]:
    if journal.empty:
        return journal, 0

    latest_m1 = m1.index.max() if not m1.empty else pd.NaT
    resolved_count = 0
    out = journal.copy()

    for idx, row in out.iterrows():
        status = str(row.get("status", ""))
        if status in {"closed_time_exit", "not_forward_late_detected", "not_forward_exit_already_available"}:
            continue

        entry_utc = pd.to_datetime(row["entry_utc"], utc=True)
        exit_target_utc = pd.to_datetime(row["exit_target_utc"], utc=True)

        if pd.isna(latest_m1) or latest_m1 < entry_utc:
            out.at[idx, "status"] = "pending_entry"
            continue

        entry_price = row.get("entry_price", float("nan"))
        if pd.isna(pd.to_numeric(entry_price, errors="coerce")):
            ep, src = get_entry_price(m15, entry_utc)
            out.at[idx, "entry_price"] = ep
            out.at[idx, "entry_price_source"] = src
            entry_price = ep

        if pd.isna(entry_price):
            out.at[idx, "status"] = "entry_price_unavailable"
            continue

        if latest_m1 < exit_target_utc:
            out.at[idx, "status"] = "open_shadow"
            path = m1[(m1.index > entry_utc) & (m1.index <= latest_m1)]
        else:
            path = m1[(m1.index > entry_utc) & (m1.index <= exit_target_utc)]

        if path.empty:
            out.at[idx, "status"] = "open_no_path_yet" if latest_m1 < exit_target_utc else "missing_m1_path"
            continue

        exit_price = float(path.iloc[-1]["close"])
        gross = exit_price - float(entry_price)
        mfe = float(path["high"].max()) - float(entry_price)
        mae = float(entry_price) - float(path["low"].min())

        out.at[idx, "exit_price"] = round(exit_price, 6)
        out.at[idx, "gross_ret"] = round(gross, 6)
        out.at[idx, "net_ret_x1"] = round(gross - cost_usd, 6)
        out.at[idx, "mfe"] = round(mfe, 6)
        out.at[idx, "mae"] = round(mae, 6)

        if latest_m1 >= exit_target_utc:
            out.at[idx, "status"] = "closed_time_exit"
            out.at[idx, "resolved_utc"] = resolved_utc
            resolved_count += 1
        else:
            out.at[idx, "status"] = "open_shadow"

    return out, resolved_count


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, ret_col: str = "net_ret_x1") -> Dict:
    if df.empty or ret_col not in df.columns:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0}
    x = df.sort_values("entry_utc").copy()
    vals = pd.to_numeric(x[ret_col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0}
    s = pd.Series(vals)
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
    }


def save_journal(journal: pd.DataFrame, path: Path) -> None:
    if journal.empty:
        journal.to_csv(path, index=False)
        return
    out = journal.sort_values(["event_utc", "signal_id"]).copy()
    out.to_csv(path, index=False)


def decide(journal: pd.DataFrame) -> Tuple[str, List[str]]:
    if journal.empty:
        return "TRUE_FORWARD_STARTED_NO_SIGNALS_YET", ["Collector state exists; no post-start signal has been logged yet."]

    valid = journal[journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy()
    closed = valid[valid["status"].eq("closed_time_exit")].copy()
    open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])].copy()

    if len(closed) == 0 and len(open_) == 0:
        return "NO_VALID_TRUE_FORWARD_SIGNALS_YET", ["Signals found so far were historical or late-detected; none count as true-forward."]

    if len(closed) < 10:
        return "TRUE_FORWARD_COLLECTION_ACTIVE_INSUFFICIENT_CLOSED", [f"Closed true-forward outcomes={len(closed)}; need more observations before judgment."]

    m = metrics(closed, "net_ret_x1")
    if m["total"] > 0 and m["pf"] >= 1.25 and m["median"] > 0:
        return "TRUE_FORWARD_SHADOW_POSITIVE_EARLY", ["Closed true-forward outcomes are positive, but sample must grow before paper/demo consideration."]

    return "TRUE_FORWARD_SHADOW_WEAK_OR_NEGATIVE", ["Closed true-forward outcomes are weak/negative; do not escalate."]


def run(
    db: Path,
    out_dir: Path,
    scan_days: int,
    sweep_depth_min: float,
    reclaim_max: float,
    buffer_usd: float,
    cost_usd: float,
    collector_start_utc: Optional[str],
) -> int:
    generated = now_utc()
    out_dir.mkdir(parents=True, exist_ok=True)

    state_path = out_dir / "stage16c_collector_state.json"
    journal_path = out_dir / "stage16c_true_forward_shadow_journal.csv"
    report_json = out_dir / "stage16c_true_forward_shadow_collector.json"
    report_md = out_dir / "stage16c_true_forward_shadow_collector.md"
    candidates_csv = out_dir / "stage16c_scan_candidates.csv"

    state = load_or_create_state(state_path, collector_start_utc)
    collector_start = pd.to_datetime(state["collector_start_utc"], utc=True)

    conn = connect(db)
    try:
        m1, m15, intraday_source = load_m1_m15(conn)
        macro, macro_audit = load_macro_real_yield(conn)
    finally:
        conn.close()

    latest_bar = m15.index.max() if not m15.empty else pd.NaT
    candidates = detect_setup_candidates(
        m15=m15,
        macro=macro,
        scan_days=scan_days,
        sweep_depth_min=sweep_depth_min,
        reclaim_max=reclaim_max,
        buffer_usd=buffer_usd,
    )
    candidates.to_csv(candidates_csv, index=False)

    journal = load_journal(journal_path)
    journal, new_count, skipped_before_start = append_new_signals(
        journal=journal,
        candidates=candidates,
        collector_start_utc=collector_start,
        detected_utc=generated,
        latest_bar_utc=latest_bar,
    )
    journal, resolved_count = resolve_journal(journal, m1, m15, cost_usd, generated)
    save_journal(journal, journal_path)

    valid = journal[journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy() if not journal.empty else pd.DataFrame()
    closed_valid = valid[valid["status"].eq("closed_time_exit")].copy() if not valid.empty else pd.DataFrame()
    open_valid = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])].copy() if not valid.empty else pd.DataFrame()
    late_or_invalid = journal[~journal["forward_valid"].astype(str).str.lower().isin(["true", "1"])].copy() if not journal.empty else pd.DataFrame()
    closed_m = metrics(closed_valid, "net_ret_x1")
    final_decision, reasons = decide(journal)

    status_counts = journal["status"].value_counts().to_dict() if not journal.empty and "status" in journal.columns else {}

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated.isoformat(),
        "collector_start_utc": collector_start.isoformat(),
        "inputs": {
            "db": str(db),
            "scan_days": int(scan_days),
            "sweep_depth_min": float(sweep_depth_min),
            "reclaim_max": float(reclaim_max),
            "buffer_usd": float(buffer_usd),
            "cost_usd": float(cost_usd),
        },
        "source": {
            "intraday_source": intraday_source,
            "m15_rows": int(len(m15)),
            "m15_latest_bar": latest_bar.isoformat() if pd.notna(latest_bar) else None,
            "m1_rows": int(len(m1)) if not m1.empty else 0,
            "macro_audit": macro_audit,
        },
        "counts": {
            "scan_candidates": int(len(candidates)),
            "new_logged_this_run": int(new_count),
            "skipped_before_collector_start": int(skipped_before_start),
            "resolved_this_run": int(resolved_count),
            "journal_rows": int(len(journal)),
            "valid_forward_rows": int(len(valid)),
            "closed_valid_forward_rows": int(len(closed_valid)),
            "open_valid_forward_rows": int(len(open_valid)),
            "late_or_invalid_rows": int(len(late_or_invalid)),
            "status_counts": status_counts,
        },
        "closed_valid_forward_metrics": closed_m,
        "final_decision": final_decision,
        "reasons": reasons,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    report_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 16C True-Forward Shadow Collector",
        "",
        f"Generated UTC: `{generated.isoformat()}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: true-forward shadow collection only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Collector boundary",
        f"- collector_start_utc: `{collector_start.isoformat()}`",
        f"- latest_m15_bar_utc: `{latest_bar.isoformat() if pd.notna(latest_bar) else None}`",
        "",
        "## Research setup",
        "- setup: `prev_day_low_sweep_rejection`",
        "- side: `LONG` research direction",
        "- sweep_depth_min: `{}`".format(sweep_depth_min),
        "- reclaim_max: `{}`".format(reclaim_max),
        "- macro context: `real_yield_10y_chg5_up`",
        "- entry: `next M15 open`",
        "- exit: `60 minutes after entry`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Counts",
        f"- scan_candidates: `{len(candidates)}`",
        f"- new_logged_this_run: `{new_count}`",
        f"- skipped_before_collector_start: `{skipped_before_start}`",
        f"- resolved_this_run: `{resolved_count}`",
        f"- journal_rows: `{len(journal)}`",
        f"- valid_forward_rows: `{len(valid)}`",
        f"- closed_valid_forward_rows: `{len(closed_valid)}`",
        f"- open_valid_forward_rows: `{len(open_valid)}`",
        f"- late_or_invalid_rows: `{len(late_or_invalid)}`",
        "",
        "## Status counts",
    ]
    if status_counts:
        for k, v in status_counts.items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Closed valid true-forward outcomes",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {closed_m['events']} | {closed_m['total']} | {closed_m['avg']} | {closed_m['median']} | {closed_m['win_rate']} | {closed_m['pf']} | {closed_m['max_dd']} |",
        "",
        "## Evidence rule",
        "- Signals with `event_utc <= collector_start_utc` are not true-forward.",
        "- Signals detected after their `exit_target_utc` are marked invalid for forward proof.",
        "- Closed true-forward outcomes are judged only after the journal records them before outcome is known.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- state_json: `{state_path}`",
        f"- journal_csv: `{journal_path}`",
        f"- candidates_csv: `{candidates_csv}`",
        f"- json: `{report_json}`",
        f"- md: `{report_md}`",
    ]
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 16C true-forward shadow collector: DONE")
    print(f"final_decision={final_decision}")
    print(f"collector_start_utc={collector_start.isoformat()}")
    print(f"new_logged_this_run={new_count} resolved_this_run={resolved_count} valid_forward_rows={len(valid)} closed_valid={len(closed_valid)}")
    print(f"Report: {report_md}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--scan-days", type=int, default=10)
    p.add_argument("--sweep-depth-min", type=float, default=1.62)
    p.add_argument("--reclaim-max", type=float, default=1.55)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--collector-start-utc", default=None, help="Only for controlled initialization. Default: now on first run.")
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        scan_days=int(args.scan_days),
        sweep_depth_min=float(args.sweep_depth_min),
        reclaim_max=float(args.reclaim_max),
        buffer_usd=float(args.buffer_usd),
        cost_usd=float(args.cost_usd),
        collector_start_utc=args.collector_start_utc,
    )


if __name__ == "__main__":
    raise SystemExit(main())
