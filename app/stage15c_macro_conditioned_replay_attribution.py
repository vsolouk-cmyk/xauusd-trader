#!/usr/bin/env python3
"""
Stage 15C — Macro-Conditioned Exact Replay Attribution

Purpose:
- Add macro/fundamental context to the Stage 15B validated research candidate.
- Use macro/fundamental data only as attribution/regime context, not as a standalone signal.
- Determine whether available macro/event context improves or explains the validated sweep/reclaim behavior.

Candidate from Stage 15B:
- setup: prev_day_low_sweep_rejection
- side: LONG
- branch: sweep_depth_ge_q50
- regime: reclaim_lt_q50
- horizon: 60 minutes
- result source: stage15b_exact_replay_trades.csv

Hard rules:
- Research attribution only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TRADES = Path("data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_exact_replay_trades.csv")
DEFAULT_EVENTS = Path("data/config/stage10a_news_events.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage15c_macro_conditioned_replay_attribution")


@dataclass(frozen=True)
class ContextSpec:
    name: str
    description: str
    predicate: Callable[[pd.DataFrame], pd.Series]
    source: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> Optional[sqlite3.Connection]:
    if not db.exists():
        return None
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [str(r["name"]) for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [str(r["name"]) for r in rows]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def normalize_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def detect_date_col(cols: Sequence[str]) -> Optional[str]:
    normalized = {normalize_col(c): c for c in cols}
    candidates = [
        "date", "datetime", "timestamp", "time", "utc_time", "entry_time",
        "observation_date", "event_time_utc", "time_utc", "date_utc",
    ]
    for c in candidates:
        if c in normalized:
            return normalized[c]
    for c in cols:
        n = normalize_col(c)
        if "date" in n or "time" in n:
            return c
    return None


def detect_series_col(cols: Sequence[str]) -> Optional[str]:
    normalized = {normalize_col(c): c for c in cols}
    candidates = ["series_id", "series", "symbol", "ticker", "indicator", "feature", "metric", "name"]
    for c in candidates:
        if c in normalized:
            return normalized[c]
    return None


def numeric_value_cols(df: pd.DataFrame, exclude: Sequence[str]) -> List[str]:
    out = []
    ex = set(exclude)
    for c in df.columns:
        if c in ex:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().sum() >= max(5, int(len(df) * 0.10)):
            out.append(c)
    return out


def likely_macro_table(table: str) -> bool:
    t = normalize_col(table)
    keywords = ["macro", "fred", "economic", "calendar", "event", "gdelt", "news", "yield", "rate", "dxy", "usd"]
    if any(k in t for k in keywords):
        return True
    return False


def read_table_sample_or_all(conn: sqlite3.Connection, table: str, max_rows: int) -> pd.DataFrame:
    # Ordered full-ish read with a safety limit. Macro/event tables should be small enough.
    q = f"SELECT * FROM {quote_ident(table)} LIMIT {int(max_rows)}"
    return pd.read_sql_query(q, conn)


def table_to_long_macro(df: pd.DataFrame, table: str) -> Tuple[pd.DataFrame, Dict]:
    audit = {"table": table, "rows": int(len(df)), "status": "ignored", "reason": ""}
    if df.empty:
        audit["reason"] = "empty"
        return pd.DataFrame(), audit

    date_col = detect_date_col(df.columns)
    if date_col is None:
        audit["reason"] = "no_date_column"
        return pd.DataFrame(), audit

    df = df.copy()
    df["_date"] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    df = df.dropna(subset=["_date"])
    if df.empty:
        audit["reason"] = "date_parse_failed"
        return pd.DataFrame(), audit

    series_col = detect_series_col(df.columns)
    value_candidates = numeric_value_cols(df, exclude=[date_col] + ([series_col] if series_col else []))

    if not value_candidates:
        audit["reason"] = "no_numeric_value_columns"
        return pd.DataFrame(), audit

    if series_col and len(value_candidates) >= 1:
        # Long form: choose the densest numeric column as value.
        densities = []
        for c in value_candidates:
            densities.append((pd.to_numeric(df[c], errors="coerce").notna().sum(), c))
        value_col = sorted(densities, reverse=True)[0][1]
        out = pd.DataFrame({
            "dt": df["_date"],
            "series": df[series_col].astype(str).map(lambda x: f"{table}.{x}"),
            "value": pd.to_numeric(df[value_col], errors="coerce"),
            "source_table": table,
            "source_column": value_col,
        }).dropna(subset=["dt", "series", "value"])
        audit["status"] = "loaded_long"
        audit["reason"] = f"date_col={date_col};series_col={series_col};value_col={value_col};series={out['series'].nunique()}"
        return out, audit

    # Wide form: melt all numeric value columns.
    parts = []
    for c in value_candidates:
        tmp = pd.DataFrame({
            "dt": df["_date"],
            "series": f"{table}.{c}",
            "value": pd.to_numeric(df[c], errors="coerce"),
            "source_table": table,
            "source_column": c,
        }).dropna(subset=["dt", "value"])
        if not tmp.empty:
            parts.append(tmp)
    if not parts:
        audit["reason"] = "wide_melt_no_values"
        return pd.DataFrame(), audit

    out = pd.concat(parts, ignore_index=True)
    audit["status"] = "loaded_wide"
    audit["reason"] = f"date_col={date_col};value_cols={len(value_candidates)};series={out['series'].nunique()}"
    return out, audit


def discover_macro_long(db: Path, max_rows_per_table: int, include_all_tables: bool) -> Tuple[pd.DataFrame, pd.DataFrame]:
    conn = connect(db)
    if conn is None:
        return pd.DataFrame(), pd.DataFrame([{"table": str(db), "rows": 0, "status": "missing_db", "reason": "db_missing"}])

    audits = []
    parts = []
    try:
        tables = list_tables(conn)
        for table in tables:
            if normalize_col(table) in {"bars"}:
                continue
            if not include_all_tables and not likely_macro_table(table):
                continue
            try:
                df = read_table_sample_or_all(conn, table, max_rows_per_table)
                long, audit = table_to_long_macro(df, table)
                audits.append(audit)
                if not long.empty:
                    parts.append(long)
            except Exception as e:
                audits.append({"table": table, "rows": 0, "status": "error", "reason": str(e)[:240]})
    finally:
        conn.close()

    macro = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    audit_df = pd.DataFrame(audits)
    if not macro.empty:
        macro["dt"] = pd.to_datetime(macro["dt"], utc=True, errors="coerce")
        macro = macro.dropna(subset=["dt", "series", "value"]).sort_values(["series", "dt"])
        macro = macro.drop_duplicates(["series", "dt"], keep="last")
    return macro, audit_df


def classify_series(series_name: str) -> Dict:
    s = normalize_col(series_name)
    # Direction convention for gold support:
    # yields/usd down is gold-supportive; vix/risk-off up is gold-supportive.
    if any(k in s for k in ["dfii", "real_yield", "tips", "realrate"]):
        return {"class": "real_yield", "supportive_when": "down"}
    if any(k in s for k in ["dgs10", "us10", "10y", "ten_year", "treasury_10"]):
        return {"class": "nominal_yield_10y", "supportive_when": "down"}
    if any(k in s for k in ["dgs2", "us2", "2y", "two_year", "treasury_2"]):
        return {"class": "nominal_yield_2y", "supportive_when": "down"}
    if any(k in s for k in ["dxy", "dollar", "usd", "dtwex", "broad_dollar"]):
        return {"class": "usd", "supportive_when": "down"}
    if any(k in s for k in ["vix", "volatility", "risk"]):
        return {"class": "risk_off", "supportive_when": "up"}
    if any(k in s for k in ["cpi", "inflation", "pce"]):
        return {"class": "inflation", "supportive_when": "mixed"}
    if any(k in s for k in ["oil", "wti", "brent"]):
        return {"class": "oil", "supportive_when": "mixed"}
    if any(k in s for k in ["fed", "funds", "sofr", "rate"]):
        return {"class": "policy_rate", "supportive_when": "down"}
    return {"class": "other", "supportive_when": "unknown"}


def select_macro_series(macro: pd.DataFrame, max_series: int) -> List[str]:
    if macro.empty:
        return []
    rows = []
    for ser, g in macro.groupby("series"):
        meta = classify_series(ser)
        priority = {
            "real_yield": 1,
            "nominal_yield_10y": 2,
            "nominal_yield_2y": 3,
            "usd": 4,
            "policy_rate": 5,
            "risk_off": 6,
            "inflation": 7,
            "oil": 8,
            "other": 99,
        }.get(meta["class"], 99)
        rows.append({"series": ser, "count": len(g), "priority": priority})
    sel = pd.DataFrame(rows).sort_values(["priority", "count"], ascending=[True, False])
    return sel.head(max_series)["series"].tolist()


def enrich_trades_with_macro(trades: pd.DataFrame, macro: pd.DataFrame, max_series: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if macro.empty:
        return trades.copy(), pd.DataFrame()

    out = trades.sort_values("entry_dt").copy()
    series_list = select_macro_series(macro, max_series=max_series)
    audits = []

    for ser in series_list:
        g = macro[macro["series"] == ser].sort_values("dt").copy()
        if g.empty:
            continue
        g["value"] = pd.to_numeric(g["value"], errors="coerce")
        g = g.dropna(subset=["value"]).drop_duplicates("dt", keep="last")
        if len(g) < 5:
            continue
        g["chg_1"] = g["value"] - g["value"].shift(1)
        g["chg_5"] = g["value"] - g["value"].shift(5)
        g["chg_20"] = g["value"] - g["value"].shift(20)

        safe = safe_series_name(ser)
        feat = g[["dt", "value", "chg_1", "chg_5", "chg_20"]].rename(columns={
            "value": f"{safe}__value",
            "chg_1": f"{safe}__chg1",
            "chg_5": f"{safe}__chg5",
            "chg_20": f"{safe}__chg20",
        })

        out = pd.merge_asof(
            out.sort_values("entry_dt"),
            feat.sort_values("dt"),
            left_on="entry_dt",
            right_on="dt",
            direction="backward",
        ).drop(columns=["dt"])

        meta = classify_series(ser)
        audits.append({
            "series": ser,
            "safe_name": safe,
            "class": meta["class"],
            "supportive_when": meta["supportive_when"],
            "rows": int(len(g)),
            "first_dt": g["dt"].min().isoformat(),
            "last_dt": g["dt"].max().isoformat(),
        })

    # Build a conservative macro support score from known directional classes.
    score_cols = []
    for a in audits:
        chg_col = f"{a['safe_name']}__chg5"
        if chg_col not in out.columns:
            continue
        if a["supportive_when"] == "down":
            col = f"{a['safe_name']}__supportive5"
            out[col] = (pd.to_numeric(out[chg_col], errors="coerce") < 0).astype(float)
            out.loc[pd.to_numeric(out[chg_col], errors="coerce").isna(), col] = float("nan")
            score_cols.append(col)
        elif a["supportive_when"] == "up":
            col = f"{a['safe_name']}__supportive5"
            out[col] = (pd.to_numeric(out[chg_col], errors="coerce") > 0).astype(float)
            out.loc[pd.to_numeric(out[chg_col], errors="coerce").isna(), col] = float("nan")
            score_cols.append(col)

    if score_cols:
        out["macro_support_score"] = out[score_cols].sum(axis=1, min_count=1)
        out["macro_support_available"] = out[score_cols].notna().sum(axis=1)
        out["macro_supportive"] = (out["macro_support_score"] >= 1).astype(int)
        out["macro_hostile"] = (out["macro_support_score"] <= 0).astype(int)
    else:
        out["macro_support_score"] = float("nan")
        out["macro_support_available"] = 0
        out["macro_supportive"] = 0
        out["macro_hostile"] = 0

    return out, pd.DataFrame(audits)


def safe_series_name(name: str) -> str:
    s = normalize_col(name)
    if len(s) > 80:
        s = s[:80]
    return s


def normalize_trades(path: Path, cost_usd: float) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage15B replay CSV not found: {path}")
    x = pd.read_csv(path)
    if "entry_utc" not in x.columns:
        raise RuntimeError("Replay CSV must include entry_utc.")
    x["entry_dt"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")

    # Prefer exact replay net result if available.
    if "time_exit_net_x1" in x.columns:
        x["net_ret"] = pd.to_numeric(x["time_exit_net_x1"], errors="coerce")
    elif "time_exit_ret" in x.columns:
        x["net_ret"] = pd.to_numeric(x["time_exit_ret"], errors="coerce") - cost_usd
    elif "ret_usd" in x.columns:
        x["net_ret"] = pd.to_numeric(x["ret_usd"], errors="coerce") - cost_usd
    else:
        raise RuntimeError("Replay CSV must include time_exit_net_x1, time_exit_ret, or ret_usd.")

    x = x.dropna(subset=["entry_dt", "net_ret"]).sort_values("entry_dt").reset_index(drop=True)
    x["year"] = x["entry_dt"].dt.year
    x["quarter"] = x["entry_dt"].dt.to_period("Q").astype(str)
    return x


def load_event_calendar(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    date_col = detect_date_col(x.columns)
    if date_col is None:
        return pd.DataFrame()
    x["event_dt"] = pd.to_datetime(x[date_col], utc=True, errors="coerce")
    x = x.dropna(subset=["event_dt"]).sort_values("event_dt")
    if x.empty:
        return x

    # Basic class extraction.
    cls_col = None
    for c in ["event_class", "class", "category", "event", "title", "name"]:
        if c in x.columns:
            cls_col = c
            break
    x["event_class_norm"] = x[cls_col].astype(str).map(normalize_col) if cls_col else "event"
    return x


def enrich_trades_with_events(trades: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["event_prev_24h"] = 0
    out["event_next_24h"] = 0
    out["event_same_day"] = 0
    out["fomc_cpi_nfp_prev_24h"] = 0
    out["fomc_cpi_nfp_next_24h"] = 0
    if events.empty:
        return out

    ev_times = events["event_dt"].sort_values().reset_index(drop=True)
    important_mask = events["event_class_norm"].astype(str).str.contains("fomc|cpi|nfp|payroll|inflation|fed|rate", regex=True, na=False)
    imp_times = events[important_mask]["event_dt"].sort_values().reset_index(drop=True)

    for i, row in out.iterrows():
        t = row["entry_dt"]
        prev = ev_times[(ev_times >= t - pd.Timedelta(hours=24)) & (ev_times <= t)]
        nxt = ev_times[(ev_times > t) & (ev_times <= t + pd.Timedelta(hours=24))]
        same = ev_times[ev_times.dt.strftime("%Y-%m-%d") == t.strftime("%Y-%m-%d")]
        out.at[i, "event_prev_24h"] = int(len(prev) > 0)
        out.at[i, "event_next_24h"] = int(len(nxt) > 0)
        out.at[i, "event_same_day"] = int(len(same) > 0)

        if not imp_times.empty:
            iprev = imp_times[(imp_times >= t - pd.Timedelta(hours=24)) & (imp_times <= t)]
            inxt = imp_times[(imp_times > t) & (imp_times <= t + pd.Timedelta(hours=24))]
            out.at[i, "fomc_cpi_nfp_prev_24h"] = int(len(iprev) > 0)
            out.at[i, "fomc_cpi_nfp_next_24h"] = int(len(inxt) > 0)
    return out


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


def metrics(df: pd.DataFrame, ret_col: str = "net_ret") -> Dict:
    if df.empty:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[ret_col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    s = pd.Series(vals)
    by_year = x.groupby(x["entry_dt"].dt.year)[ret_col].sum()
    by_quarter = x.groupby(x["entry_dt"].dt.to_period("Q").astype(str))[ret_col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
        "pos_quarters": int((by_quarter > 0).sum()),
        "quarters": int(len(by_quarter)),
    }


def split_metrics(df: pd.DataFrame, ret_col: str = "net_ret", frac: float = 0.70) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {
        "train_frac": float(frac),
        "train": metrics(x.iloc[:cut], ret_col),
        "test": metrics(x.iloc[cut:], ret_col),
    }


def period_metrics(df: pd.DataFrame, ret_col: str, period: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    elif period == "month":
        x["period"] = x["entry_dt"].dt.to_period("M").astype(str)
    else:
        raise ValueError(period)
    rows = []
    for p, g in x.groupby("period"):
        row = {"period": p}
        row.update(metrics(g, ret_col))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("period") if rows else pd.DataFrame()


def build_context_specs(df: pd.DataFrame, macro_audit: pd.DataFrame, event_available: bool, min_events: int) -> List[ContextSpec]:
    specs: List[ContextSpec] = []

    if "macro_support_available" in df.columns and int(df["macro_support_available"].max()) > 0:
        specs += [
            ContextSpec("macro_supportive", "Known macro series directional score supportive for gold", lambda d: d["macro_supportive"].eq(1), "macro_score"),
            ContextSpec("macro_not_supportive", "Known macro series directional score not supportive for gold", lambda d: ~d["macro_supportive"].eq(1), "macro_score"),
        ]
        # Score thresholds if enough available.
        specs += [
            ContextSpec("macro_score_ge_2", "Macro support score >= 2", lambda d: d["macro_support_score"] >= 2, "macro_score"),
            ContextSpec("macro_score_eq_0", "Macro support score == 0", lambda d: d["macro_support_score"] == 0, "macro_score"),
        ]

    # Individual selected macro series direction contexts.
    if not macro_audit.empty:
        for _, a in macro_audit.iterrows():
            safe = str(a["safe_name"])
            cls = str(a["class"])
            chg5 = f"{safe}__chg5"
            if chg5 not in df.columns:
                continue
            # Only include known classes and a few best-supported individual directions.
            if cls not in {"real_yield", "nominal_yield_10y", "nominal_yield_2y", "usd", "policy_rate", "risk_off"}:
                continue
            if str(a["supportive_when"]) == "down":
                specs.append(ContextSpec(f"{safe}_chg5_down", f"{a['series']} 5-observation change < 0", lambda d, col=chg5: pd.to_numeric(d[col], errors="coerce") < 0, "macro_series"))
                specs.append(ContextSpec(f"{safe}_chg5_up", f"{a['series']} 5-observation change > 0", lambda d, col=chg5: pd.to_numeric(d[col], errors="coerce") > 0, "macro_series"))
            elif str(a["supportive_when"]) == "up":
                specs.append(ContextSpec(f"{safe}_chg5_up", f"{a['series']} 5-observation change > 0", lambda d, col=chg5: pd.to_numeric(d[col], errors="coerce") > 0, "macro_series"))
                specs.append(ContextSpec(f"{safe}_chg5_down", f"{a['series']} 5-observation change < 0", lambda d, col=chg5: pd.to_numeric(d[col], errors="coerce") < 0, "macro_series"))

    if event_available:
        specs += [
            ContextSpec("no_event_prev_24h", "No known event in previous 24h", lambda d: d["event_prev_24h"].eq(0), "events"),
            ContextSpec("event_prev_24h", "Known event in previous 24h", lambda d: d["event_prev_24h"].eq(1), "events"),
            ContextSpec("no_fomc_cpi_nfp_prev_24h", "No FOMC/CPI/NFP-like event in previous 24h", lambda d: d["fomc_cpi_nfp_prev_24h"].eq(0), "events"),
            ContextSpec("fomc_cpi_nfp_prev_24h", "FOMC/CPI/NFP-like event in previous 24h", lambda d: d["fomc_cpi_nfp_prev_24h"].eq(1), "events"),
            ContextSpec("no_event_next_24h", "No known event in next 24h", lambda d: d["event_next_24h"].eq(0), "events"),
        ]

    return specs


def evaluate_contexts(df: pd.DataFrame, specs: Sequence[ContextSpec], min_events: int) -> pd.DataFrame:
    base = metrics(df, "net_ret")
    rows = []
    for spec in specs:
        try:
            mask = spec.predicate(df).fillna(False)
        except Exception:
            continue
        sub = df[mask].copy()
        comp = df[~mask].copy()
        if len(sub) < max(8, min_events // 2):
            continue
        m = metrics(sub, "net_ret")
        c = metrics(comp, "net_ret")
        sp = split_metrics(sub, "net_ret", 0.70)
        candidate = (
            m["events"] >= min_events
            and m["total"] > 0
            and m["pf"] >= max(1.25, base["pf"])
            and m["median"] >= max(0.25, base["median"])
            and m["win_rate"] >= 0.55
            and sp["test"]["events"] >= max(8, int(min_events * 0.25))
            and sp["test"]["total"] > 0
            and sp["test"]["pf"] >= 1.05
        )
        rows.append({
            "context": spec.name,
            "source": spec.source,
            "description": spec.description,
            "selected_events": m["events"],
            "coverage": round(m["events"] / max(1, len(df)), 6),
            "net_total": m["total"],
            "net_avg": m["avg"],
            "net_median": m["median"],
            "net_wr": m["win_rate"],
            "net_pf": m["pf"],
            "net_dd": m["max_dd"],
            "pos_years": m["pos_years"],
            "years": m["years"],
            "pos_quarters": m["pos_quarters"],
            "quarters": m["quarters"],
            "test_events": sp["test"]["events"],
            "test_total": sp["test"]["total"],
            "test_median": sp["test"]["median"],
            "test_pf": sp["test"]["pf"],
            "complement_events": c["events"],
            "complement_total": c["total"],
            "complement_median": c["median"],
            "complement_pf": c["pf"],
            "delta_pf_vs_base": round(m["pf"] - base["pf"], 6),
            "delta_median_vs_base": round(m["median"] - base["median"], 6),
            "candidate_flag": bool(candidate),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["candidate_flag", "net_pf", "net_median", "test_pf", "selected_events"],
        ascending=[False, False, False, False, False],
    )


def decide(base: Dict, context_summary: pd.DataFrame, macro_loaded: bool, events_loaded: bool) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if not macro_loaded and not events_loaded:
        return "MACRO_EVENT_DATA_MISSING", ["No usable macro or event context data was found."]

    if context_summary.empty:
        return "INCONCLUSIVE_NO_CONTEXT_RESULTS", ["Context data exists but no context condition had enough matching trades."]

    cands = context_summary[context_summary["candidate_flag"] == True]
    if not cands.empty:
        top = cands.iloc[0].to_dict()
        reasons.append(f"Top context `{top['context']}` improved/preserved the validated candidate after cost.")
        reasons.append("This permits one focused robustness check for this macro-conditioned context only, not EA/paper/live.")
        return "MACRO_CONTEXT_CANDIDATE_FOUND", reasons

    top = context_summary.iloc[0].to_dict()
    if top["net_total"] > 0 and top["net_pf"] >= 1.10:
        reasons.append(f"Best context `{top['context']}` is positive but fails strict improvement thresholds.")
        reasons.append("Macro context is attribution-only at this stage.")
        return "MACRO_CONTEXT_WEAK_ATTRIBUTION_ONLY", reasons

    return "MACRO_CONTEXT_NO_IMPROVEMENT", ["No tested macro/event context improved the validated candidate."]


def run(
    db: Path,
    trades_path: Path,
    events_path: Path,
    out_dir: Path,
    cost_usd: float,
    min_events: int,
    max_series: int,
    max_rows_per_table: int,
    include_all_tables: bool,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    trades = normalize_trades(trades_path, cost_usd)
    base = metrics(trades, "net_ret")

    macro_long, table_audit = discover_macro_long(db, max_rows_per_table=max_rows_per_table, include_all_tables=include_all_tables)
    macro_loaded = not macro_long.empty

    enriched, macro_series_audit = enrich_trades_with_macro(trades, macro_long, max_series=max_series)
    events = load_event_calendar(events_path)
    events_loaded = not events.empty
    enriched = enrich_trades_with_events(enriched, events)

    specs = build_context_specs(enriched, macro_series_audit, event_available=events_loaded, min_events=min_events)
    context_summary = evaluate_contexts(enriched, specs, min_events=min_events)
    final_decision, reasons = decide(base, context_summary, macro_loaded=macro_loaded, events_loaded=events_loaded)

    year = period_metrics(enriched, "net_ret", "year")
    quarter = period_metrics(enriched, "net_ret", "quarter")

    enriched_csv = out_dir / "stage15c_trades_with_macro_context.csv"
    macro_long_csv = out_dir / "stage15c_macro_long_loaded.csv"
    table_audit_csv = out_dir / "stage15c_macro_table_audit.csv"
    macro_series_audit_csv = out_dir / "stage15c_macro_series_audit.csv"
    context_csv = out_dir / "stage15c_context_summary.csv"
    year_csv = out_dir / "stage15c_by_year.csv"
    quarter_csv = out_dir / "stage15c_by_quarter.csv"
    json_path = out_dir / "stage15c_macro_conditioned_replay_attribution.json"
    md_path = out_dir / "stage15c_macro_conditioned_replay_attribution.md"

    enriched.to_csv(enriched_csv, index=False)
    table_audit.to_csv(table_audit_csv, index=False)
    macro_series_audit.to_csv(macro_series_audit_csv, index=False)
    context_summary.to_csv(context_csv, index=False)
    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)
    if not macro_long.empty:
        macro_long.head(200000).to_csv(macro_long_csv, index=False)
    else:
        pd.DataFrame().to_csv(macro_long_csv, index=False)

    availability = {
        "db_exists": bool(db.exists()),
        "macro_long_rows": int(len(macro_long)),
        "macro_series_loaded": int(macro_long["series"].nunique()) if not macro_long.empty else 0,
        "macro_selected_series": int(len(macro_series_audit)),
        "events_path_exists": bool(events_path.exists()),
        "events_loaded": int(len(events)),
        "context_specs": int(len(specs)),
        "context_rows": int(len(context_summary)),
    }

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "trades_path": str(trades_path),
            "events_path": str(events_path),
            "cost_usd": float(cost_usd),
            "min_events": int(min_events),
            "max_series": int(max_series),
            "max_rows_per_table": int(max_rows_per_table),
            "include_all_tables": bool(include_all_tables),
        },
        "availability": availability,
        "baseline": base,
        "final_decision": final_decision,
        "reasons": reasons,
        "top_contexts": context_summary.head(15).to_dict(orient="records") if not context_summary.empty else [],
        "macro_series_audit": macro_series_audit.to_dict(orient="records") if not macro_series_audit.empty else [],
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
        "# Stage 15C Macro-Conditioned Exact Replay Attribution",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: macro/fundamental attribution only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate under attribution",
        "- setup: `prev_day_low_sweep_rejection`",
        "- side: `LONG`",
        "- branch: `sweep_depth_ge_q50`",
        "- regime: `reclaim_lt_q50`",
        "- replay source: `Stage 15B exact M1 time-exit`",
        f"- trades: `{len(trades)}`",
        f"- cost_usd: `{cost_usd}`",
        "",
        "## Data availability",
        f"- db_exists: `{availability['db_exists']}`",
        f"- macro_long_rows: `{availability['macro_long_rows']}`",
        f"- macro_series_loaded: `{availability['macro_series_loaded']}`",
        f"- macro_selected_series: `{availability['macro_selected_series']}`",
        f"- events_loaded: `{availability['events_loaded']}`",
        f"- context_specs: `{availability['context_specs']}`",
        f"- context_rows: `{availability['context_rows']}`",
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
        "## Baseline Stage 15B candidate",
        "| Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {base['events']} | {base['total']} | {base['avg']} | {base['median']} | {base['win_rate']} | {base['pf']} | {base['max_dd']} | {base['pos_years']}/{base['years']} | {base['pos_quarters']}/{base['quarters']} |",
        "",
        "## Top macro/event contexts",
        "| Rank | Context | Source | Events | Coverage | Total | Median | WR | PF | DD | Test total | Test PF | Candidate |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    if not context_summary.empty:
        for i, r in enumerate(context_summary.head(20).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | {r['context']} | {r['source']} | {r['selected_events']} | {r['coverage']} | "
                f"{r['net_total']} | {r['net_median']} | {r['net_wr']} | {r['net_pf']} | {r['net_dd']} | "
                f"{r['test_total']} | {r['test_pf']} | {r['candidate_flag']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | False |")

    lines += [
        "",
        "## Selected macro series",
        "| Series | Class | Supportive when | Rows | First | Last |",
        "|---|---|---|---:|---|---|",
    ]
    if not macro_series_audit.empty:
        for r in macro_series_audit.head(30).to_dict(orient="records"):
            lines.append(
                f"| {r['series']} | {r['class']} | {r['supportive_when']} | {r['rows']} | {r['first_dt']} | {r['last_dt']} |"
            )
    else:
        lines.append("| none | none | none | 0 | none | none |")

    lines += [
        "",
        "## Year distribution - baseline replay",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(
            f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- `MACRO_CONTEXT_CANDIDATE_FOUND` permits one focused robustness check for the top macro-conditioned context only.",
        "- `MACRO_CONTEXT_WEAK_ATTRIBUTION_ONLY` means macro helps explain but is not strong enough for system design.",
        "- `MACRO_CONTEXT_NO_IMPROVEMENT` means available macro/event context did not improve this candidate.",
        "- `MACRO_EVENT_DATA_MISSING` means data is not available in the current repo/local store.",
        "- Macro/fundamental context is not an independent signal here.",
        "- No EA/paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- enriched_csv: `{enriched_csv}`",
        f"- macro_long_csv: `{macro_long_csv}`",
        f"- table_audit_csv: `{table_audit_csv}`",
        f"- macro_series_audit_csv: `{macro_series_audit_csv}`",
        f"- context_csv: `{context_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 15C macro-conditioned replay attribution: DONE")
    print(f"final_decision={final_decision}")
    print(f"macro_series_loaded={availability['macro_series_loaded']} selected={availability['macro_selected_series']} events_loaded={availability['events_loaded']}")
    if not context_summary.empty:
        top = context_summary.iloc[0].to_dict()
        print(f"top_context={top['context']} source={top['source']} pf={top['net_pf']} median={top['net_median']} candidate={top['candidate_flag']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--trades", default=str(DEFAULT_TRADES))
    p.add_argument("--events", default=str(DEFAULT_EVENTS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--min-events", type=int, default=30)
    p.add_argument("--max-series", type=int, default=40)
    p.add_argument("--max-rows-per-table", type=int, default=200000)
    p.add_argument("--include-all-tables", action="store_true", help="Scan non-obvious SQLite tables too. Slower.")
    args = p.parse_args()
    return run(
        db=Path(args.db),
        trades_path=Path(args.trades),
        events_path=Path(args.events),
        out_dir=Path(args.out_dir),
        cost_usd=args.cost_usd,
        min_events=args.min_events,
        max_series=args.max_series,
        max_rows_per_table=args.max_rows_per_table,
        include_all_tables=bool(args.include_all_tables),
    )


if __name__ == "__main__":
    raise SystemExit(main())
