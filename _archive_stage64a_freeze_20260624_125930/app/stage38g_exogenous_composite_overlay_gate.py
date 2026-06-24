#!/usr/bin/env python3
"""
Stage38G: Composite exogenous overlay gate for XAUUSD research.

Read-only diagnostic. It combines already-loaded GLD ETF-flow context, macro/risk context,
and optional COT context to test pre-declared event-clock policies.

No orders. No alerts. No paper/live. No strategy promotion.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_DB = "data/local/xauusd_local_store.sqlite"
DEFAULT_GLD_TABLE = "stage38f_spdr_gld_h1_joined"
DEFAULT_MACRO_TABLE = "stage38e_macro_risk_h1_joined"
DEFAULT_COT_TABLE = "cot_gold_h1_features_joined"
DEFAULT_REPORTS_DIR = "data/reports/stage38g_exogenous_composite_overlay_gate"
DEFAULT_HORIZONS = "24,72,120"

EVENTS_TABLE = "stage38g_exogenous_composite_gate_events"
SUMMARY_TABLE = "stage38g_exogenous_composite_gate_summary"
AUDIT_TABLE = "stage38g_exogenous_composite_gate_audit"


@dataclass(frozen=True)
class Policy:
    name: str
    role: str
    description: str
    predicate: Callable[[Dict[str, Any]], bool]


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1", (table,)
    ).fetchone()
    return row is not None


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    if not table_exists(con, table):
        return []
    return [r[1] for r in con.execute(f"pragma table_info({qident(table)})").fetchall()]


def find_col(cols: Sequence[str], candidates: Sequence[str], contains: Sequence[str] = ()) -> Optional[str]:
    lower_map = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    for c in cols:
        lc = c.lower()
        if all(x.lower() in lc for x in contains):
            return c
    return None


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            if fmt is None:
                dt = datetime.fromisoformat(s)
            else:
                dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def parse_date(value: Any) -> Optional[str]:
    dt = parse_dt(value)
    if dt:
        return dt.date().isoformat()
    if value is None:
        return None
    s = str(value).strip()
    if len(s) >= 10:
        return s[:10]
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        x = float(s)
        if math.isfinite(x):
            return x
    except Exception:
        return None
    return None


def mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def median(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    m = n // 2
    if n % 2:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


def sample_std(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mu = mean(xs)
    if mu is None:
        return None
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def t_stat(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    sd = sample_std(xs)
    if not sd or sd == 0:
        return None
    mu = mean(xs)
    if mu is None:
        return None
    return mu / (sd / math.sqrt(n))


def max_drawdown(cumulative_values: Sequence[float]) -> float:
    peak = 0.0
    max_dd = 0.0
    for v in cumulative_values:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def recreate_tables(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    for t in (EVENTS_TABLE, SUMMARY_TABLE, AUDIT_TABLE):
        cur.execute(f"drop table if exists {qident(t)}")

    cur.execute(
        f"""
        create table {qident(EVENTS_TABLE)} (
            horizon_bars integer not null,
            policy_name text not null,
            policy_role text not null,
            event_index integer not null,
            bar_ts_utc text not null,
            observation_date text,
            close_price real,
            future_close_price real,
            baseline_return_bps real,
            policy_trade integer not null,
            event_clock_return_bps real,
            gld_flow_state text,
            gld_flow_20d_bucket text,
            gld_flow_5d_bucket text,
            gld_flow_1d_bucket text,
            gld_holding_z_bucket text,
            macro_gold_pressure text,
            macro_risk_state text,
            macro_bias text,
            real_yield_5d_bucket text,
            dollar_5d_bucket text,
            vix_5d_bucket text,
            cot_state text,
            primary key (horizon_bars, policy_name, event_index)
        )
        """
    )

    cur.execute(
        f"""
        create table {qident(SUMMARY_TABLE)} (
            horizon_bars integer not null,
            policy_name text not null,
            policy_role text not null,
            source_event_count integer,
            trade_count integer,
            skipped_count integer,
            trade_mean_bps real,
            trade_median_bps real,
            trade_win_rate real,
            trade_t_stat real,
            event_clock_mean_bps real,
            baseline_event_clock_mean_bps real,
            uplift_vs_baseline_event_clock_mean_bps real,
            event_clock_max_drawdown_bps real,
            baseline_max_drawdown_bps real,
            dd_delta_vs_baseline_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month_share real,
            worst_loo_event_clock_mean_bps real,
            worst_loo_excluded_year text,
            decision text,
            note text,
            primary key (horizon_bars, policy_name)
        )
        """
    )

    cur.execute(
        f"""
        create table {qident(AUDIT_TABLE)} (
            audit_id integer primary key autoincrement,
            created_at_utc text not null,
            status text not null,
            decision text not null,
            gld_table text,
            macro_table text,
            cot_table text,
            gld_rows_loaded integer,
            event_count integer,
            events_written integer,
            summary_rows_written integer,
            pass_count integer,
            watch_count integer,
            no_promotion_count integer,
            warning_count integer,
            note_count integer,
            notes_json text
        )
        """
    )
    con.commit()


def load_table_by_ts(
    con: sqlite3.Connection,
    table: str,
    ts_col: str,
    wanted_cols: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    cols = [ts_col] + [c for c in wanted_cols if c and c != ts_col]
    cols = list(dict.fromkeys(cols))
    if not table_exists(con, table):
        return {}
    sql = f"select {', '.join(qident(c) for c in cols)} from {qident(table)}"
    out: Dict[str, Dict[str, Any]] = {}
    for row in con.execute(sql):
        d = dict(zip(cols, row))
        ts = str(d.get(ts_col))
        out[ts] = d
    return out


def build_feature_context(con: sqlite3.Connection, gld_table: str, macro_table: str, cot_table: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not table_exists(con, gld_table):
        raise RuntimeError(f"Missing required GLD joined table: {gld_table}")

    gld_cols = table_columns(con, gld_table)
    ts_col = find_col(gld_cols, ["bar_ts_utc", "ts_utc", "timestamp_utc", "time_utc", "utc_time"], contains=("ts",))
    close_col = find_col(
        gld_cols,
        ["close", "close_price", "mid_close", "bid_close", "ask_close", "c"],
        contains=("close",),
    )
    obs_col = find_col(gld_cols, ["gld_observation_date", "observation_date", "date"], contains=("observation", "date"))
    if not ts_col or not close_col:
        raise RuntimeError(f"Could not detect timestamp/close columns in {gld_table}. cols={gld_cols}")

    gld_feature_cols = [
        c
        for c in [
            obs_col,
            find_col(gld_cols, ["gld_flow_state"]),
            find_col(gld_cols, ["gld_flow_20d_bucket"]),
            find_col(gld_cols, ["gld_flow_5d_bucket"]),
            find_col(gld_cols, ["gld_flow_1d_bucket"]),
            find_col(gld_cols, ["gld_holding_z_bucket"]),
        ]
        if c
    ]

    select_cols = list(dict.fromkeys([ts_col, close_col] + gld_feature_cols))
    sql = f"select {', '.join(qident(c) for c in select_cols)} from {qident(gld_table)} order by {qident(ts_col)}"
    rows: List[Dict[str, Any]] = []
    for row in con.execute(sql):
        d = dict(zip(select_cols, row))
        ts = str(d.get(ts_col))
        close = to_float(d.get(close_col))
        dt = parse_dt(ts)
        if not dt or close is None:
            continue
        rows.append(
            {
                "bar_ts_utc": ts,
                "bar_dt": dt,
                "close": close,
                "observation_date": parse_date(d.get(obs_col)) if obs_col else dt.date().isoformat(),
                "gld_flow_state": d.get(find_col(gld_cols, ["gld_flow_state"]) or "") if find_col(gld_cols, ["gld_flow_state"]) else None,
                "gld_flow_20d_bucket": d.get(find_col(gld_cols, ["gld_flow_20d_bucket"]) or "") if find_col(gld_cols, ["gld_flow_20d_bucket"]) else None,
                "gld_flow_5d_bucket": d.get(find_col(gld_cols, ["gld_flow_5d_bucket"]) or "") if find_col(gld_cols, ["gld_flow_5d_bucket"]) else None,
                "gld_flow_1d_bucket": d.get(find_col(gld_cols, ["gld_flow_1d_bucket"]) or "") if find_col(gld_cols, ["gld_flow_1d_bucket"]) else None,
                "gld_holding_z_bucket": d.get(find_col(gld_cols, ["gld_holding_z_bucket"]) or "") if find_col(gld_cols, ["gld_holding_z_bucket"]) else None,
            }
        )

    # Macro context keyed by exact H1 timestamp.
    macro_meta = {"table_exists": table_exists(con, macro_table), "columns": []}
    if table_exists(con, macro_table):
        macro_cols = table_columns(con, macro_table)
        macro_meta["columns"] = macro_cols
        macro_ts = find_col(macro_cols, ["bar_ts_utc", "ts_utc", "timestamp_utc", "time_utc", "utc_time"], contains=("ts",))
        if macro_ts:
            macro_wanted = [
                find_col(macro_cols, ["macro_gold_pressure"]),
                find_col(macro_cols, ["macro_risk_state"]),
                find_col(macro_cols, ["macro_bias"]),
                find_col(macro_cols, ["real_yield_5d_bucket"]),
                find_col(macro_cols, ["dollar_5d_bucket"]),
                find_col(macro_cols, ["vix_5d_bucket"]),
            ]
            macro_by_ts = load_table_by_ts(con, macro_table, macro_ts, [c for c in macro_wanted if c])
            for r in rows:
                m = macro_by_ts.get(r["bar_ts_utc"], {})
                for key in ["macro_gold_pressure", "macro_risk_state", "macro_bias", "real_yield_5d_bucket", "dollar_5d_bucket", "vix_5d_bucket"]:
                    col = find_col(macro_cols, [key])
                    r[key] = m.get(col) if col else None
        else:
            for r in rows:
                for key in ["macro_gold_pressure", "macro_risk_state", "macro_bias", "real_yield_5d_bucket", "dollar_5d_bucket", "vix_5d_bucket"]:
                    r[key] = None
    else:
        for r in rows:
            for key in ["macro_gold_pressure", "macro_risk_state", "macro_bias", "real_yield_5d_bucket", "dollar_5d_bucket", "vix_5d_bucket"]:
                r[key] = None

    # Optional COT context keyed by exact H1 timestamp.
    cot_meta = {"table_exists": table_exists(con, cot_table), "columns": []}
    if table_exists(con, cot_table):
        cot_cols = table_columns(con, cot_table)
        cot_meta["columns"] = cot_cols
        cot_ts = find_col(cot_cols, ["bar_ts_utc", "ts_utc", "timestamp_utc", "time_utc", "utc_time"], contains=("ts",))
        cot_state_col = find_col(
            cot_cols,
            ["mm_crowding_state", "managed_money_crowding_state", "cot_mm_crowding_state", "crowding_state", "mm_state"],
            contains=("state",),
        )
        if cot_ts and cot_state_col:
            cot_by_ts = load_table_by_ts(con, cot_table, cot_ts, [cot_state_col])
            for r in rows:
                r["cot_state"] = cot_by_ts.get(r["bar_ts_utc"], {}).get(cot_state_col)
        else:
            for r in rows:
                r["cot_state"] = None
    else:
        for r in rows:
            r["cot_state"] = None

    meta = {
        "gld_columns": gld_cols,
        "timestamp_column": ts_col,
        "close_column": close_col,
        "observation_column": obs_col,
        "macro": macro_meta,
        "cot": cot_meta,
    }
    return rows, meta


def first_event_indices(rows: List[Dict[str, Any]]) -> List[int]:
    first: Dict[str, int] = {}
    for idx, r in enumerate(rows):
        od = r.get("observation_date") or r["bar_dt"].date().isoformat()
        if od not in first:
            first[od] = idx
    return [first[k] for k in sorted(first.keys())]


def sval(x: Any) -> str:
    if x is None:
        return ""
    return str(x)


def is_gld_flow20_outflow(e: Dict[str, Any]) -> bool:
    return sval(e.get("gld_flow_20d_bucket")) == "FLOW_20D_OUTFLOW"


def is_gld_etf_outflow(e: Dict[str, Any]) -> bool:
    return sval(e.get("gld_flow_state")) == "ETF_OUTFLOW"


def is_gld_supportive(e: Dict[str, Any]) -> bool:
    return sval(e.get("gld_flow_state")) in {"ETF_STRONG_OUTFLOW", "ETF_STRONG_INFLOW"} or sval(e.get("gld_flow_20d_bucket")) in {
        "FLOW_20D_STRONG_OUTFLOW",
        "FLOW_20D_STRONG_INFLOW",
    } or sval(e.get("gld_flow_5d_bucket")) == "FLOW_5D_INFLOW"


def is_macro_hostile(e: Dict[str, Any]) -> bool:
    return sval(e.get("macro_gold_pressure")) == "REAL_YIELD_FLAT+USD_DOWN" or sval(e.get("macro_risk_state")) == "RISK_ELEVATED"


def is_macro_supportive(e: Dict[str, Any]) -> bool:
    return sval(e.get("macro_gold_pressure")) in {"REAL_YIELD_DOWN+USD_FLAT", "REAL_YIELD_DOWN+USD_DOWN"} or sval(e.get("vix_5d_bucket")) == "VIX_5D_UP"


def is_cot_hostile(e: Dict[str, Any]) -> bool:
    s = sval(e.get("cot_state"))
    return s in {"MM_SHORT_CROWDED", "MM_EXTREME_LONG"}


def build_policies() -> List[Policy]:
    return [
        Policy("BASELINE_ALWAYS_LONG", "baseline", "Reference: take every event.", lambda e: True),
        Policy("BLOCK_GLD_FLOW20_OUTFLOW", "avoid_long_overlay", "Skip FLOW_20D_OUTFLOW.", lambda e: not is_gld_flow20_outflow(e)),
        Policy(
            "BLOCK_GLD_ETF_OR_FLOW20_OUTFLOW",
            "avoid_long_overlay",
            "Skip ETF_OUTFLOW or FLOW_20D_OUTFLOW.",
            lambda e: not (is_gld_etf_outflow(e) or is_gld_flow20_outflow(e)),
        ),
        Policy(
            "BLOCK_MACRO_HOSTILE",
            "avoid_long_overlay",
            "Skip macro-hostile contexts.",
            lambda e: not is_macro_hostile(e),
        ),
        Policy(
            "BLOCK_GLD_OR_MACRO_HOSTILE",
            "avoid_long_overlay",
            "Skip GLD outflow and macro-hostile contexts.",
            lambda e: not (is_gld_etf_outflow(e) or is_gld_flow20_outflow(e) or is_macro_hostile(e)),
        ),
        Policy(
            "BLOCK_ANY_EXOGENOUS_HOSTILE",
            "avoid_long_overlay",
            "Skip GLD hostile, macro hostile, and optional COT hostile states.",
            lambda e: not (is_gld_etf_outflow(e) or is_gld_flow20_outflow(e) or is_macro_hostile(e) or is_cot_hostile(e)),
        ),
        Policy(
            "LONG_ONLY_GLD_SUPPORTIVE",
            "supportive_long_context",
            "Trade only in pre-declared supportive GLD states.",
            lambda e: is_gld_supportive(e),
        ),
        Policy(
            "LONG_ONLY_GLD_SUPPORTIVE_AND_MACRO_NOT_HOSTILE",
            "supportive_long_context",
            "Trade only in supportive GLD states with no macro hostility.",
            lambda e: is_gld_supportive(e) and not is_macro_hostile(e),
        ),
        Policy(
            "LONG_ONLY_GLD_SUPPORTIVE_AND_MACRO_SUPPORTIVE",
            "supportive_long_context",
            "Trade only when GLD and macro contexts are both supportive.",
            lambda e: is_gld_supportive(e) and is_macro_supportive(e),
        ),
        Policy(
            "LONG_ONLY_GLD_SUPPORTIVE_AND_COT_NOT_HOSTILE",
            "supportive_long_context",
            "Trade only when GLD is supportive and optional COT state is not hostile.",
            lambda e: is_gld_supportive(e) and not is_cot_hostile(e),
        ),
    ]


def year_of_event(e: Dict[str, Any]) -> str:
    od = e.get("observation_date")
    if od:
        return str(od)[:4]
    return e["bar_dt"].date().isoformat()[:4]


def month_of_event(e: Dict[str, Any]) -> str:
    od = e.get("observation_date")
    if od and len(str(od)) >= 7:
        return str(od)[:7]
    return e["bar_dt"].date().isoformat()[:7]


def compute_summary(
    horizon: int,
    policy: Policy,
    policy_events: List[Dict[str, Any]],
    baseline_returns: List[float],
    baseline_dd: float,
) -> Dict[str, Any]:
    event_clock = [float(e["event_clock_return_bps"]) for e in policy_events]
    trade_returns = [float(e["baseline_return_bps"]) for e in policy_events if int(e["policy_trade"]) == 1]
    source_n = len(policy_events)
    trade_n = len(trade_returns)
    skipped_n = source_n - trade_n

    trade_mean = mean(trade_returns)
    trade_median = median(trade_returns)
    trade_wr = mean([1.0 if x > 0 else 0.0 for x in trade_returns]) if trade_returns else None
    trade_t = t_stat(trade_returns)
    event_mean = mean(event_clock) or 0.0
    baseline_mean = mean(baseline_returns) or 0.0
    uplift = event_mean - baseline_mean
    cum = []
    running = 0.0
    for x in event_clock:
        running += x
        cum.append(running)
    dd = max_drawdown(cum)

    by_year: Dict[str, List[float]] = defaultdict(list)
    by_month: Dict[str, List[float]] = defaultdict(list)
    for e in policy_events:
        y = year_of_event(e)
        m = month_of_event(e)
        by_year[y].append(float(e["event_clock_return_bps"]))
        by_month[m].append(float(e["event_clock_return_bps"]))

    y_means = {y: mean(v) or 0.0 for y, v in by_year.items()}
    m_means = {m: mean(v) or 0.0 for m, v in by_month.items()}
    pos_years = [y for y, v in y_means.items() if v > 0]
    neg_years = [y for y, v in y_means.items() if v <= 0]
    pos_months = [m for m, v in m_means.items() if v > 0]
    neg_months = [m for m, v in m_means.items() if v <= 0]

    total_pos_y = sum(sum(v) for y, v in by_year.items() if (mean(v) or 0.0) > 0)
    max_pos_y_share = None
    if total_pos_y > 0:
        max_pos_y_share = max(sum(v) for y, v in by_year.items() if (mean(v) or 0.0) > 0) / total_pos_y

    total_pos_m = sum(sum(v) for m, v in by_month.items() if (mean(v) or 0.0) > 0)
    max_pos_m_share = None
    if total_pos_m > 0:
        max_pos_m_share = max(sum(v) for m, v in by_month.items() if (mean(v) or 0.0) > 0) / total_pos_m

    worst_loo = None
    worst_loo_year = None
    for y in sorted(by_year.keys()):
        xs = [float(e["event_clock_return_bps"]) for e in policy_events if year_of_event(e) != y]
        if not xs:
            continue
        mu = mean(xs) or 0.0
        if worst_loo is None or mu < worst_loo:
            worst_loo = mu
            worst_loo_year = y

    notes: List[str] = []
    if policy.name != "BASELINE_ALWAYS_LONG":
        if trade_n < 150:
            notes.append("LOW_TRADE_COUNT_LT_150")
        if uplift < 5:
            notes.append("LOW_EVENT_CLOCK_UPLIFT_LT_5BPS")
        elif uplift < 8:
            notes.append("MARGINAL_EVENT_CLOCK_UPLIFT_LT_8BPS")
        if len(pos_years) < 4:
            notes.append("LOW_POSITIVE_YEAR_COUNT_LT_4")
        if max_pos_y_share is not None and max_pos_y_share > 0.55:
            notes.append("YEAR_CONCENTRATED_GT_55PCT")
        if worst_loo is not None and worst_loo <= 0:
            notes.append("WORST_LOO_NON_POSITIVE")
        if dd - baseline_dd > 0:
            notes.append("DRAWDOWN_WORSE_THAN_BASELINE")

    if policy.name == "BASELINE_ALWAYS_LONG":
        decision = "BASELINE_REFERENCE"
    elif (
        uplift >= 8.0
        and trade_n >= 150
        and len(pos_years) >= 4
        and (max_pos_y_share is None or max_pos_y_share <= 0.55)
        and (worst_loo is not None and worst_loo > 0)
        and dd <= baseline_dd
    ):
        decision = "PASS_COMPOSITE_OVERLAY_RESEARCH_GATE"
    elif uplift > 0 or (trade_mean is not None and trade_mean > baseline_mean and trade_n >= 60):
        decision = "WATCH_COMPOSITE_OVERLAY_GATE"
    else:
        decision = "NO_PROMOTION"

    return {
        "horizon_bars": horizon,
        "policy_name": policy.name,
        "policy_role": policy.role,
        "source_event_count": source_n,
        "trade_count": trade_n,
        "skipped_count": skipped_n,
        "trade_mean_bps": trade_mean,
        "trade_median_bps": trade_median,
        "trade_win_rate": trade_wr,
        "trade_t_stat": trade_t,
        "event_clock_mean_bps": event_mean,
        "baseline_event_clock_mean_bps": baseline_mean,
        "uplift_vs_baseline_event_clock_mean_bps": uplift,
        "event_clock_max_drawdown_bps": dd,
        "baseline_max_drawdown_bps": baseline_dd,
        "dd_delta_vs_baseline_bps": dd - baseline_dd,
        "positive_year_count": len(pos_years),
        "negative_year_count": len(neg_years),
        "max_positive_year_share": max_pos_y_share,
        "positive_month_count": len(pos_months),
        "negative_month_count": len(neg_months),
        "max_positive_month_share": max_pos_m_share,
        "worst_loo_event_clock_mean_bps": worst_loo,
        "worst_loo_excluded_year": worst_loo_year,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
    }


def insert_summary(con: sqlite3.Connection, s: Dict[str, Any]) -> None:
    cols = list(s.keys())
    con.execute(
        f"insert into {qident(SUMMARY_TABLE)} ({', '.join(qident(c) for c in cols)}) values ({', '.join('?' for _ in cols)})",
        [s[c] for c in cols],
    )


def insert_event(con: sqlite3.Connection, e: Dict[str, Any]) -> None:
    cols = [
        "horizon_bars",
        "policy_name",
        "policy_role",
        "event_index",
        "bar_ts_utc",
        "observation_date",
        "close_price",
        "future_close_price",
        "baseline_return_bps",
        "policy_trade",
        "event_clock_return_bps",
        "gld_flow_state",
        "gld_flow_20d_bucket",
        "gld_flow_5d_bucket",
        "gld_flow_1d_bucket",
        "gld_holding_z_bucket",
        "macro_gold_pressure",
        "macro_risk_state",
        "macro_bias",
        "real_yield_5d_bucket",
        "dollar_5d_bucket",
        "vix_5d_bucket",
        "cot_state",
    ]
    con.execute(
        f"insert into {qident(EVENTS_TABLE)} ({', '.join(qident(c) for c in cols)}) values ({', '.join('?' for _ in cols)})",
        [e.get(c) for c in cols],
    )


def run(args: argparse.Namespace) -> Dict[str, Any]:
    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(args.db)
    recreate_tables(con)

    notes: List[str] = []
    rows, meta = build_feature_context(con, args.gld_table, args.macro_table, args.cot_table)
    if not rows:
        raise RuntimeError("No usable GLD H1 joined rows loaded.")
    if not meta.get("macro", {}).get("table_exists"):
        notes.append("MACRO_TABLE_MISSING_COMPOSITE_RUNS_GLD_ONLY_PLUS_MACRO_POLICIES_FLAT")
    if not meta.get("cot", {}).get("table_exists"):
        notes.append("COT_TABLE_MISSING_COT_POLICY_REDUCES_TO_GLD_SUPPORTIVE")

    event_indices_all = first_event_indices(rows)
    policies = build_policies()

    events_written = 0
    summaries: List[Dict[str, Any]] = []

    for horizon in horizons:
        valid_event_indices = [idx for idx in event_indices_all if idx + horizon < len(rows)]
        base_events: List[Dict[str, Any]] = []
        for event_no, idx in enumerate(valid_event_indices):
            r = dict(rows[idx])
            future = rows[idx + horizon]
            ret = (float(future["close"]) / float(r["close"]) - 1.0) * 10000.0
            r.update(
                {
                    "event_index": event_no,
                    "future_close": future["close"],
                    "baseline_return_bps": ret,
                    "horizon_bars": horizon,
                }
            )
            base_events.append(r)

        baseline_returns = [float(e["baseline_return_bps"]) for e in base_events]
        running = 0.0
        baseline_cum: List[float] = []
        for x in baseline_returns:
            running += x
            baseline_cum.append(running)
        baseline_dd = max_drawdown(baseline_cum)

        for policy in policies:
            policy_events: List[Dict[str, Any]] = []
            for e in base_events:
                do_trade = bool(policy.predicate(e))
                out = {
                    "horizon_bars": horizon,
                    "policy_name": policy.name,
                    "policy_role": policy.role,
                    "event_index": e["event_index"],
                    "bar_ts_utc": e["bar_ts_utc"],
                    "observation_date": e.get("observation_date"),
                    "close_price": e["close"],
                    "future_close_price": e["future_close"],
                    "baseline_return_bps": e["baseline_return_bps"],
                    "policy_trade": 1 if do_trade else 0,
                    "event_clock_return_bps": e["baseline_return_bps"] if do_trade else 0.0,
                    "gld_flow_state": e.get("gld_flow_state"),
                    "gld_flow_20d_bucket": e.get("gld_flow_20d_bucket"),
                    "gld_flow_5d_bucket": e.get("gld_flow_5d_bucket"),
                    "gld_flow_1d_bucket": e.get("gld_flow_1d_bucket"),
                    "gld_holding_z_bucket": e.get("gld_holding_z_bucket"),
                    "macro_gold_pressure": e.get("macro_gold_pressure"),
                    "macro_risk_state": e.get("macro_risk_state"),
                    "macro_bias": e.get("macro_bias"),
                    "real_yield_5d_bucket": e.get("real_yield_5d_bucket"),
                    "dollar_5d_bucket": e.get("dollar_5d_bucket"),
                    "vix_5d_bucket": e.get("vix_5d_bucket"),
                    "cot_state": e.get("cot_state"),
                }
                insert_event(con, out)
                events_written += 1
                policy_events.append(out)
            summary = compute_summary(horizon, policy, policy_events, baseline_returns, baseline_dd)
            insert_summary(con, summary)
            summaries.append(summary)

    pass_count = sum(1 for s in summaries if s["decision"] == "PASS_COMPOSITE_OVERLAY_RESEARCH_GATE")
    watch_count = sum(1 for s in summaries if s["decision"] == "WATCH_COMPOSITE_OVERLAY_GATE")
    no_promotion_count = sum(1 for s in summaries if s["decision"] == "NO_PROMOTION")
    if pass_count:
        decision = "REVIEW_COMPOSITE_EXOGENOUS_PASS_CANDIDATES_READ_ONLY"
    elif watch_count:
        decision = "COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION"
    else:
        decision = "COMPOSITE_EXOGENOUS_GATE_NO_PROMOTION_ARCHIVE_OR_PIVOT"

    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS",
        "decision": decision,
        "gld_table": args.gld_table,
        "macro_table": args.macro_table,
        "cot_table": args.cot_table,
        "gld_rows_loaded": len(rows),
        "event_count": len(event_indices_all),
        "events_written": events_written,
        "summary_rows_written": len(summaries),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_promotion_count,
        "warning_count": 0,
        "note_count": len(notes),
        "notes_json": json.dumps(notes, ensure_ascii=False),
    }
    con.execute(
        f"""
        insert into {qident(AUDIT_TABLE)}
        (created_at_utc, status, decision, gld_table, macro_table, cot_table,
         gld_rows_loaded, event_count, events_written, summary_rows_written,
         pass_count, watch_count, no_promotion_count, warning_count, note_count, notes_json)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            audit["created_at_utc"],
            audit["status"],
            audit["decision"],
            audit["gld_table"],
            audit["macro_table"],
            audit["cot_table"],
            audit["gld_rows_loaded"],
            audit["event_count"],
            audit["events_written"],
            audit["summary_rows_written"],
            audit["pass_count"],
            audit["watch_count"],
            audit["no_promotion_count"],
            audit["warning_count"],
            audit["note_count"],
            audit["notes_json"],
        ],
    )
    con.commit()

    result = {"audit": audit, "summaries": summaries, "meta": meta}
    json_path = reports_dir / "stage38g_exogenous_composite_overlay_gate.json"
    md_path = reports_dir / "stage38g_exogenous_composite_overlay_gate.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    top = sorted(
        summaries,
        key=lambda s: (
            0 if s["decision"] == "PASS_COMPOSITE_OVERLAY_RESEARCH_GATE" else 1 if s["decision"] == "WATCH_COMPOSITE_OVERLAY_GATE" else 2,
            -(s.get("uplift_vs_baseline_event_clock_mean_bps") or -999999),
        ),
    )
    lines = [
        "# Stage38G Exogenous Composite Overlay Gate",
        "",
        "## Audit",
        "",
        "```text",
        json.dumps(audit, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Top summaries",
        "",
        "| horizon | policy | decision | trades | uplift bps | event mean bps | DD delta bps | note |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for s in top[:40]:
        lines.append(
            f"| {s['horizon_bars']} | {s['policy_name']} | {s['decision']} | {s['trade_count']} | "
            f"{(s.get('uplift_vs_baseline_event_clock_mean_bps') or 0):.2f} | "
            f"{(s.get('event_clock_mean_bps') or 0):.2f} | "
            f"{(s.get('dd_delta_vs_baseline_bps') or 0):.2f} | {s.get('note') or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    con.close()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--gld-table", default=DEFAULT_GLD_TABLE)
    ap.add_argument("--macro-table", default=DEFAULT_MACRO_TABLE)
    ap.add_argument("--cot-table", default=DEFAULT_COT_TABLE)
    ap.add_argument("--horizons", default=DEFAULT_HORIZONS)
    ap.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    args = ap.parse_args()
    result = run(args)
    audit = result["audit"]
    print(
        "audit:",
        (
            audit["status"],
            audit["decision"],
            audit["gld_rows_loaded"],
            audit["event_count"],
            audit["events_written"],
            audit["summary_rows_written"],
            audit["pass_count"],
            audit["watch_count"],
            audit["no_promotion_count"],
            audit["warning_count"],
            audit["note_count"],
        ),
    )


if __name__ == "__main__":
    main()
