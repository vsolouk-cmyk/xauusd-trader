#!/usr/bin/env python3
"""
Stage 16B — Shadow Signal Outcome Ledger

Purpose:
- Convert Stage 16A research-only shadow signals into an outcome ledger.
- Label historical/recent shadow signals using M1 exact path.
- Keep true-forward evidence separate from retrospective scan evidence.

Important:
- Stage 16A scans a recent window, so signals inside that window are recent-history
  shadow records, not forward-proof records.
- True-forward evaluation starts only after the monitor is scheduled and signals are
  logged before their exits happen.

Hard rules:
- Research outcome ledger only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_SIGNALS = Path("data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_shadow_signals.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage16b_shadow_signal_outcome_ledger")


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def now_iso() -> str:
    return now_utc().replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("No AMarkets MT5 M1 bars found in local store.")
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time").set_index("utc_time")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_signals(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage16A signal CSV not found: {path}")
    x = pd.read_csv(path)
    if x.empty:
        return x
    required = ["event_utc", "next_bar_theoretical_entry_utc", "time_exit_target_utc"]
    missing = [c for c in required if c not in x.columns]
    if missing:
        raise RuntimeError(f"Signal CSV missing required columns: {missing}")
    for c in required:
        x[c] = pd.to_datetime(x[c], utc=True, errors="coerce")
    x = x.dropna(subset=required).sort_values("event_utc").reset_index(drop=True)
    return x


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


def metrics(df: pd.DataFrame, col: str = "net_ret_x1") -> Dict:
    if df.empty or col not in df.columns:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_days": 0, "days": 0,
        }
    x = df.sort_values("entry_utc").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_days": 0, "days": 0,
        }
    s = pd.Series(vals)
    by_day = x.groupby(x["entry_utc"].dt.strftime("%Y-%m-%d"))[col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_days": int((by_day > 0).sum()),
        "days": int(len(by_day)),
    }


def get_m15_entry_price(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    # Entry is the next theoretical M15 bar timestamp produced by Stage16A.
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def outcome_one(m1: pd.DataFrame, m15: pd.DataFrame, row: pd.Series, cost_usd: float) -> Dict:
    event_dt = pd.to_datetime(row["event_utc"], utc=True)
    entry_dt = pd.to_datetime(row["next_bar_theoretical_entry_utc"], utc=True)
    exit_dt = pd.to_datetime(row["time_exit_target_utc"], utc=True)
    latest_bar = m1.index.max()

    base = {
        "event_utc": event_dt,
        "entry_utc": entry_dt,
        "exit_target_utc": exit_dt,
        "research_side": str(row.get("research_side", "LONG")),
        "sweep_depth": float(row.get("sweep_depth", float("nan"))),
        "reclaim_above_pdl": float(row.get("reclaim_above_pdl", float("nan"))),
        "real_yield_10y": float(row.get("real_yield_10y", float("nan"))),
        "real_yield_10y_chg5": float(row.get("real_yield_10y_chg5", float("nan"))),
        "authorization": "RESEARCH_SHADOW_ONLY_NO_ORDER",
    }

    if latest_bar < entry_dt:
        base.update({
            "status": "pending_entry",
            "entry_price": float("nan"),
            "entry_price_source": "not_reached",
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_ret_x1": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "minutes_observed": 0,
        })
        return base

    entry_price, entry_source = get_m15_entry_price(m15, entry_dt)
    if pd.isna(entry_price):
        base.update({
            "status": "entry_after_available_data",
            "entry_price": float("nan"),
            "entry_price_source": entry_source,
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_ret_x1": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "minutes_observed": 0,
        })
        return base

    path = m1[(m1.index > entry_dt) & (m1.index <= min(exit_dt, latest_bar))].copy()
    if path.empty:
        base.update({
            "status": "open_no_m1_path_yet" if latest_bar < exit_dt else "missing_m1_path",
            "entry_price": entry_price,
            "entry_price_source": entry_source,
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_ret_x1": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "minutes_observed": 0,
        })
        return base

    if latest_bar < exit_dt:
        exit_price = float(path.iloc[-1]["close"])
        status = "open_shadow"
    else:
        exit_price = float(path.iloc[-1]["close"])
        status = "closed_time_exit"

    gross = exit_price - entry_price
    mfe = float(path["high"].max()) - entry_price
    mae = entry_price - float(path["low"].min())

    base.update({
        "status": status,
        "entry_price": round(entry_price, 6),
        "entry_price_source": entry_source,
        "exit_price": round(exit_price, 6),
        "gross_ret": round(gross, 6),
        "net_ret_x1": round(gross - cost_usd, 6),
        "mfe": round(mfe, 6),
        "mae": round(mae, 6),
        "minutes_observed": int(round((path.index.max() - entry_dt) / pd.Timedelta(minutes=1))),
    })
    return base


def label_outcomes(signals: pd.DataFrame, m1: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    m15 = resample_ohlc(m1, "15min")
    rows = [outcome_one(m1, m15, row, cost_usd) for _, row in signals.iterrows()]
    out = pd.DataFrame(rows)
    for c in ["event_utc", "entry_utc", "exit_target_utc"]:
        out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
    return out.sort_values("entry_utc").reset_index(drop=True)


def split_recent_forward(outcomes: pd.DataFrame, generated_utc: pd.Timestamp) -> Dict:
    """
    Anything whose signal/event timestamp is before this report generation is retrospective
    from the standpoint of this report. True forward requires signal creation before exit.
    """
    if outcomes.empty:
        return {
            "retrospective_closed": pd.DataFrame(),
            "true_forward_like_open_or_future": pd.DataFrame(),
        }

    retrospective = outcomes[outcomes["event_utc"] < generated_utc].copy()
    future_or_open = outcomes[outcomes["event_utc"] >= generated_utc].copy()
    return {
        "retrospective_closed": retrospective[retrospective["status"].eq("closed_time_exit")].copy(),
        "true_forward_like_open_or_future": future_or_open.copy(),
    }


def decide(closed: pd.DataFrame, open_or_future: pd.DataFrame) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    m = metrics(closed, "net_ret_x1")
    if m["events"] == 0:
        return "NO_CLOSED_SHADOW_OUTCOMES", ["No closed Stage16A shadow signals were available for outcome labeling."]
    if m["events"] < 10:
        reasons.append("Closed sample is below 10; only observational, not validation.")
        if m["total"] > 0:
            return "TOO_FEW_POSITIVE_RECENT_SHADOW_OUTCOMES", reasons
        return "TOO_FEW_NEGATIVE_RECENT_SHADOW_OUTCOMES", reasons

    if m["total"] > 0 and m["pf"] >= 1.25 and m["median"] > 0:
        reasons.append("Recent-history shadow outcomes are positive, but they are retrospective scans, not true-forward evidence.")
        reasons.append("Next step is scheduled true-forward shadow collection only.")
        return "RECENT_HISTORY_SHADOW_POSITIVE_NOT_FORWARD_PROOF", reasons

    reasons.append("Recent-history shadow outcomes do not preserve the validated edge.")
    return "RECENT_HISTORY_SHADOW_WEAK_OR_NEGATIVE", reasons


def run(db: Path, signals_path: Path, out_dir: Path, cost_usd: float) -> int:
    generated = now_utc().replace(microsecond=0)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    signals = load_signals(signals_path)
    outcomes = label_outcomes(signals, m1, cost_usd)
    split = split_recent_forward(outcomes, generated)

    closed = split["retrospective_closed"]
    open_or_future = split["true_forward_like_open_or_future"]
    closed_m = metrics(closed, "net_ret_x1")
    final_decision, reasons = decide(closed, open_or_future)

    outcomes_csv = out_dir / "stage16b_shadow_outcome_ledger.csv"
    closed_csv = out_dir / "stage16b_closed_recent_history_outcomes.csv"
    json_path = out_dir / "stage16b_shadow_signal_outcome_ledger.json"
    md_path = out_dir / "stage16b_shadow_signal_outcome_ledger.md"

    outcomes.to_csv(outcomes_csv, index=False)
    closed.to_csv(closed_csv, index=False)

    latest_closed = closed.tail(1).to_dict(orient="records") if not closed.empty else []
    status_counts = outcomes["status"].value_counts().to_dict() if not outcomes.empty and "status" in outcomes.columns else {}

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated.isoformat(),
        "inputs": {
            "db": str(db),
            "signals_path": str(signals_path),
            "cost_usd": float(cost_usd),
        },
        "data": {
            "m1_rows": int(len(m1)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
            "signals": int(len(signals)),
            "outcomes": int(len(outcomes)),
            "status_counts": status_counts,
        },
        "retrospective_recent_history_metrics": closed_m,
        "final_decision": final_decision,
        "reasons": reasons,
        "latest_closed": latest_closed,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 16B Shadow Signal Outcome Ledger",
        "",
        f"Generated UTC: `{generated.isoformat()}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research outcome ledger only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- signals_path: `{signals_path}`",
        f"- cost_usd: `{cost_usd}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        f"- signals_loaded: `{len(signals)}`",
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
        "## Status counts",
    ]
    if status_counts:
        for k, v in status_counts.items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Closed recent-history shadow outcomes",
        "| Events | Total | Avg | Median | WR | PF | DD | Pos days |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {closed_m['events']} | {closed_m['total']} | {closed_m['avg']} | {closed_m['median']} | {closed_m['win_rate']} | {closed_m['pf']} | {closed_m['max_dd']} | {closed_m['pos_days']}/{closed_m['days']} |",
        "",
        "## Latest closed shadow outcome",
    ]

    if latest_closed:
        last = latest_closed[0]
        for k in [
            "event_utc", "entry_utc", "exit_target_utc", "entry_price", "exit_price",
            "gross_ret", "net_ret_x1", "mfe", "mae", "sweep_depth",
            "reclaim_above_pdl", "real_yield_10y_chg5", "status",
        ]:
            lines.append(f"- {k}: `{last.get(k)}`")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Evidence classification",
        "- Outcomes in this report are recent-history shadow outcomes because Stage 16A scanned an existing window.",
        "- They are useful for sanity-checking the monitor implementation.",
        "- They are not true-forward proof.",
        "- True-forward evidence begins only after the monitor is scheduled and future signals are logged before outcome is known.",
        "",
        "## Output files",
        f"- outcomes_csv: `{outcomes_csv}`",
        f"- closed_csv: `{closed_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 16B shadow signal outcome ledger: DONE")
    print(f"final_decision={final_decision}")
    print(f"signals={len(signals)} closed={closed_m['events']} total={closed_m['total']} pf={closed_m['pf']} median={closed_m['median']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--signals", default=str(DEFAULT_SIGNALS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    args = p.parse_args()
    return run(
        db=Path(args.db),
        signals_path=Path(args.signals),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
    )


if __name__ == "__main__":
    raise SystemExit(main())
