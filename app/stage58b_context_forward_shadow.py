#!/usr/bin/env python3
"""Stage58B context-aware Stage51 true-forward shadow.

This script is a true-forward evidence collector only. It reads the broker-real
AMarkets multitf SQLite DB, Stage58A context-aware candidate shortlist, and
Stage57A context regime tables. On first normal run it initializes a forward
watermark and inserts no historical signals. Subsequent runs collect only new
signals after the watermark and later evaluate them after horizon maturation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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
    print(json.dumps({"stage": "Stage58B_CONTEXT_FORWARD_SHADOW_NO_PROMOTION", "status": "ERROR", "error": f"pandas import failed: {exc}"}), file=sys.stderr)
    raise

STAGE = "Stage58B_CONTEXT_AWARE_STAGE51_TRUE_FORWARD_SHADOW_NO_PROMOTION"
PASS_STATUS = "CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN"
DEFAULT_STATE_DB = "data/shadow/stage58b_context_forward_shadow.sqlite"


@dataclass
class Candidate:
    candidate_id: str
    base_candidate_id: str
    context_tag: str
    cw: int
    pct: float
    buffer_bps: float
    m30_sma: int
    horizon_m5_bars: int
    raw: Dict[str, Any]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_ts(x: Any) -> Optional[pd.Timestamp]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    try:
        ts = pd.to_datetime(x, utc=True)
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def iso_z(ts: Any) -> Optional[str]:
    t = norm_ts(ts)
    if t is None:
        return None
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_state_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            started_utc TEXT NOT NULL,
            ended_utc TEXT,
            mode TEXT NOT NULL,
            previous_watermark_utc TEXT,
            new_watermark_utc TEXT,
            generated_signals INTEGER DEFAULT 0,
            inserted_new_signals INTEGER DEFAULT 0,
            newly_evaluated_signals INTEGER DEFAULT 0,
            note TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            base_candidate_id TEXT,
            context_tag TEXT,
            signal_time_utc TEXT NOT NULL,
            entry_time_utc TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            horizon_m5_bars INTEGER NOT NULL,
            stress_cost_bps REAL NOT NULL,
            spread_cost_bps REAL,
            status TEXT NOT NULL,
            planned_exit_time_utc TEXT,
            exit_time_utc TEXT,
            exit_price REAL,
            gross_bps REAL,
            stress_bps REAL,
            created_utc TEXT NOT NULL,
            evaluated_utc TEXT,
            is_backfill INTEGER NOT NULL DEFAULT 0,
            source_run_id TEXT NOT NULL,
            params_json TEXT,
            context_json TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_signals_entry_time ON signals(entry_time_utc)")
    con.commit()
    return con


def kv_get(con: sqlite3.Connection, key: str) -> Optional[str]:
    row = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def kv_set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO kv(key,value,updated_utc) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_utc=excluded.updated_utc",
        (key, value, now_utc()),
    )


def reset_state(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM signals")
    con.execute("DELETE FROM runs")
    con.execute("DELETE FROM kv")
    con.commit()


def load_bars(db_path: Path, timeframes: Iterable[str]) -> Dict[str, pd.DataFrame]:
    if not db_path.exists():
        raise FileNotFoundError(f"Broker DB not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    out: Dict[str, pd.DataFrame] = {}
    for tf in timeframes:
        q = """
            SELECT time_utc, open, high, low, close, tick_volume, spread_cost_bps
            FROM amarkets_bars
            WHERE timeframe = ?
            ORDER BY time_utc
        """
        df = pd.read_sql_query(q, con, params=(tf,))
        if df.empty:
            raise ValueError(f"No rows for timeframe {tf} in broker DB")
        df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
        for c in ["open", "high", "low", "close", "tick_volume", "spread_cost_bps"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["time_utc", "open", "high", "low", "close"]).sort_values("time_utc").reset_index(drop=True)
        out[tf] = df
    con.close()
    return out


def load_context(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Context table not found: {path}")
    df = pd.read_csv(path)
    if "time_utc" not in df.columns:
        # tolerate first unnamed time column from accidental index export
        candidates = [c for c in df.columns if c.lower().strip() in {"timestamp", "datetime", "utc_time", "time"}]
        if candidates:
            df = df.rename(columns={candidates[0]: "time_utc"})
        else:
            raise ValueError(f"Context table missing time_utc: {path}")
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    return df.sort_values("time_utc").reset_index(drop=True)


def load_candidates(path: Path) -> List[Candidate]:
    if not path.exists():
        raise FileNotFoundError(f"Stage58A candidates file not found: {path}")
    df = pd.read_csv(path)
    status_col = "status"
    if status_col not in df.columns:
        raise ValueError("Stage58A candidates missing status column")
    passed = df[df[status_col].astype(str).eq(PASS_STATUS)].copy()
    if passed.empty:
        raise ValueError(f"No Stage58A pass candidates with status {PASS_STATUS}")
    out: List[Candidate] = []
    for _, r in passed.iterrows():
        raw = {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}
        out.append(
            Candidate(
                candidate_id=str(raw.get("candidate_id")),
                base_candidate_id=str(raw.get("base_candidate_id", "")),
                context_tag=str(raw.get("context_tag", raw.get("context_variant", raw.get("context", raw.get("context_filter", "")))) or ""),
                cw=int(float(raw.get("cw"))),
                pct=float(raw.get("pct")),
                buffer_bps=float(raw.get("buffer_bps")),
                m30_sma=int(float(raw.get("m30_sma"))),
                horizon_m5_bars=int(float(raw.get("horizon_m5_bars"))),
                raw=raw,
            )
        )
    return out


def load_costs(cost_model_path: Path) -> Tuple[float, float]:
    if not cost_model_path.exists():
        raise FileNotFoundError(f"Cost model not found: {cost_model_path}")
    data = read_json(cost_model_path)
    # tolerate nested and flat schemas from Stage48F
    stress = data.get("stress_cost_bps")
    extreme = data.get("extreme_cost_bps")
    if stress is None and isinstance(data.get("costs"), dict):
        stress = data["costs"].get("stress_cost_bps")
        extreme = data["costs"].get("extreme_cost_bps")
    if stress is None:
        stress = data.get("recommended_cost_bps", 2.982003733153722)
    if extreme is None:
        extreme = max(float(stress), float(data.get("recommended_cost_bps", stress)))
    return float(stress), float(extreme)


def candidate_context_filter(tag: str, m15_row: Optional[pd.Series], m5_row: Optional[pd.Series]) -> Tuple[bool, Dict[str, Any]]:
    tag = str(tag or "").upper()
    details: Dict[str, Any] = {"context_tag": tag}

    def has_spread_le75(row: Optional[pd.Series]) -> bool:
        if row is None:
            return False
        if "spread_regime" in row.index:
            val = str(row.get("spread_regime", "")).lower()
            return val in {"spread_le_50", "spread_le_75"}
        if "spread_cost_bps" in row.index:
            # fallback: threshold should match Stage57 quantile-ish bound; conservative.
            try:
                return float(row.get("spread_cost_bps")) <= 1.76
            except Exception:
                return False
        if "is_spread_le_75" in row.index:
            return bool(row.get("is_spread_le_75"))
        return False

    def has_range_gt50(row: Optional[pd.Series]) -> bool:
        if row is None:
            return False
        if "range_regime" in row.index:
            val = str(row.get("range_regime", "")).lower()
            return val in {"range_le_75", "range_le_90", "range_gt_90", "range_gt_50"}
        if "range_bps" in row.index:
            try:
                # fallback M15 median from Stage57A summary ~11 bps; use row-level median proxy not available.
                return float(row.get("range_bps")) > 11.0
            except Exception:
                return False
        if "is_range_gt_50" in row.index:
            return bool(row.get("is_range_gt_50"))
        return False

    if "SPREAD_LE75" in tag:
        ok = has_spread_le75(m5_row) or has_spread_le75(m15_row)
        details["spread_filter_pass"] = ok
        return ok, details
    if "RANGE_GT50" in tag:
        ok = has_range_gt50(m15_row)
        details["range_filter_pass"] = ok
        return ok, details
    # strict fallback: unknown context tag does not pass automatically.
    details["unknown_context_tag"] = True
    return False, details


def make_signal_id(candidate_id: str, entry_time_utc: str, direction: str) -> str:
    h = hashlib.sha1(f"{candidate_id}|{entry_time_utc}|{direction}".encode("utf-8")).hexdigest()[:20]
    return f"S58B_{h}"


def build_asof_series(df: pd.DataFrame, value_cols: List[str]) -> pd.DataFrame:
    return df[["time_utc"] + [c for c in value_cols if c in df.columns]].sort_values("time_utc").reset_index(drop=True)


def attach_m30_trend(m15: pd.DataFrame, m30: pd.DataFrame, sma_window: int) -> pd.DataFrame:
    m30x = m30[["time_utc", "close"]].copy()
    m30x[f"m30_sma_{sma_window}"] = m30x["close"].rolling(sma_window, min_periods=sma_window).mean()
    m30x = m30x.rename(columns={"close": "m30_close"})
    return pd.merge_asof(
        m15.sort_values("time_utc"),
        m30x.sort_values("time_utc"),
        on="time_utc",
        direction="backward",
    )


def compute_candidate_signals(
    cand: Candidate,
    m15: pd.DataFrame,
    m30: pd.DataFrame,
    m5: pd.DataFrame,
    m15_context: pd.DataFrame,
    m5_context: pd.DataFrame,
    stress_cost_bps: float,
    extreme_cost_bps: float,
    after_watermark: Optional[pd.Timestamp],
    allow_historical_backfill: bool,
) -> List[Dict[str, Any]]:
    x = m15[["time_utc", "open", "high", "low", "close", "spread_cost_bps"]].copy()
    x["range_bps"] = (x["high"] - x["low"]) / x["close"] * 10000.0
    x["prev_range_bps"] = x["range_bps"].shift(1)
    x["prev_high"] = x["high"].shift(1)
    x["prev_low"] = x["low"].shift(1)
    x["range_q"] = x["range_bps"].rolling(cand.cw, min_periods=cand.cw).quantile(cand.pct / 100.0).shift(1)
    x = attach_m30_trend(x, m30, cand.m30_sma)
    sma_col = f"m30_sma_{cand.m30_sma}"
    x["compressed_prior"] = x["prev_range_bps"] <= x["range_q"]
    x["up_break"] = x["close"] > x["prev_high"] * (1.0 + cand.buffer_bps / 10000.0)
    x["dn_break"] = x["close"] < x["prev_low"] * (1.0 - cand.buffer_bps / 10000.0)
    x["trend_up"] = x["m30_close"] > x[sma_col]
    x["trend_down"] = x["m30_close"] < x[sma_col]
    x["direction"] = None
    x.loc[x["compressed_prior"] & x["up_break"] & x["trend_up"], "direction"] = "LONG"
    x.loc[x["compressed_prior"] & x["dn_break"] & x["trend_down"], "direction"] = "SHORT"
    sig = x.dropna(subset=["direction"]).copy()
    if after_watermark is not None and not allow_historical_backfill:
        sig = sig[sig["time_utc"] > after_watermark]
    if sig.empty:
        return []

    # Only evaluate eligible signal bars with a later M5 entry available.
    m5x = m5[["time_utc", "close", "spread_cost_bps"]].copy().sort_values("time_utc").reset_index(drop=True)
    m5_times = list(m5x["time_utc"])
    # Build quick index maps.
    m15ctx = m15_context.set_index("time_utc", drop=False)
    m5ctx = m5_context.set_index("time_utc", drop=False)
    rows: List[Dict[str, Any]] = []
    for _, r in sig.iterrows():
        signal_time = r["time_utc"]
        pos = m5x["time_utc"].searchsorted(signal_time, side="right")
        if pos >= len(m5x):
            continue
        entry_row = m5x.iloc[int(pos)]
        entry_time = entry_row["time_utc"]
        spread_cost = None if pd.isna(entry_row.get("spread_cost_bps")) else float(entry_row.get("spread_cost_bps"))
        if spread_cost is not None and spread_cost > extreme_cost_bps:
            continue
        exit_pos = int(pos) + cand.horizon_m5_bars
        planned_exit_time = m5x.iloc[exit_pos]["time_utc"] if exit_pos < len(m5x) else None
        m15_row = m15ctx.loc[signal_time] if signal_time in m15ctx.index else None
        m5_row = m5ctx.loc[entry_time] if entry_time in m5ctx.index else None
        ok_context, context_details = candidate_context_filter(cand.context_tag or cand.candidate_id, m15_row, m5_row)
        if not ok_context:
            continue
        entry_iso = iso_z(entry_time)
        signal_iso = iso_z(signal_time)
        direction = str(r["direction"])
        rows.append({
            "signal_id": make_signal_id(cand.candidate_id, entry_iso, direction),
            "candidate_id": cand.candidate_id,
            "base_candidate_id": cand.base_candidate_id,
            "context_tag": cand.context_tag or cand.candidate_id,
            "signal_time_utc": signal_iso,
            "entry_time_utc": entry_iso,
            "direction": direction,
            "entry_price": float(entry_row["close"]),
            "horizon_m5_bars": cand.horizon_m5_bars,
            "stress_cost_bps": float(stress_cost_bps),
            "spread_cost_bps": spread_cost,
            "status": "PENDING",
            "planned_exit_time_utc": iso_z(planned_exit_time),
            "exit_time_utc": None,
            "exit_price": None,
            "gross_bps": None,
            "stress_bps": None,
            "created_utc": now_utc(),
            "evaluated_utc": None,
            "is_backfill": 1 if allow_historical_backfill else 0,
            "source_run_id": "",
            "params_json": json.dumps({
                "cw": cand.cw,
                "pct": cand.pct,
                "buffer_bps": cand.buffer_bps,
                "m30_sma": cand.m30_sma,
                "horizon_m5_bars": cand.horizon_m5_bars,
            }, sort_keys=True),
            "context_json": json.dumps(context_details, sort_keys=True),
        })
    return rows


def insert_signals(con: sqlite3.Connection, signals: List[Dict[str, Any]], run_id: str) -> int:
    inserted = 0
    cols = [
        "signal_id", "candidate_id", "base_candidate_id", "context_tag", "signal_time_utc", "entry_time_utc", "direction", "entry_price",
        "horizon_m5_bars", "stress_cost_bps", "spread_cost_bps", "status", "planned_exit_time_utc", "exit_time_utc", "exit_price",
        "gross_bps", "stress_bps", "created_utc", "evaluated_utc", "is_backfill", "source_run_id", "params_json", "context_json"
    ]
    for s in signals:
        s = dict(s)
        s["source_run_id"] = run_id
        values = [s.get(c) for c in cols]
        cur = con.execute(
            f"INSERT OR IGNORE INTO signals({','.join(cols)}) VALUES({','.join(['?']*len(cols))})",
            values,
        )
        inserted += int(cur.rowcount or 0)
    con.commit()
    return inserted


def evaluate_pending(con: sqlite3.Connection, m5: pd.DataFrame) -> int:
    pending = con.execute(
        "SELECT signal_id, entry_time_utc, direction, entry_price, planned_exit_time_utc, stress_cost_bps FROM signals WHERE status='PENDING'"
    ).fetchall()
    if not pending:
        return 0
    m5x = m5[["time_utc", "close"]].copy().sort_values("time_utc")
    m5x["time_iso"] = m5x["time_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    m5_by_iso = dict(zip(m5x["time_iso"], m5x["close"]))
    updated = 0
    for signal_id, entry_time, direction, entry_price, planned_exit_time, stress_cost_bps in pending:
        if planned_exit_time is None or planned_exit_time not in m5_by_iso:
            continue
        exit_price = float(m5_by_iso[planned_exit_time])
        if str(direction).upper() == "LONG":
            gross = (exit_price / float(entry_price) - 1.0) * 10000.0
        else:
            gross = (float(entry_price) / exit_price - 1.0) * 10000.0
        stress = gross - float(stress_cost_bps)
        con.execute(
            """
            UPDATE signals
            SET status='EVALUATED', exit_time_utc=?, exit_price=?, gross_bps=?, stress_bps=?, evaluated_utc=?
            WHERE signal_id=?
            """,
            (planned_exit_time, exit_price, gross, stress, now_utc(), signal_id),
        )
        updated += 1
    con.commit()
    return updated


def state_metrics(con: sqlite3.Connection) -> Dict[str, Any]:
    def one(q: str) -> Any:
        r = con.execute(q).fetchone()
        return r[0] if r else None
    total = int(one("SELECT COUNT(*) FROM signals") or 0)
    pending = int(one("SELECT COUNT(*) FROM signals WHERE status='PENDING'") or 0)
    evaluated = int(one("SELECT COUNT(*) FROM signals WHERE status='EVALUATED'") or 0)
    backfill = int(one("SELECT COUNT(*) FROM signals WHERE is_backfill=1") or 0)
    true_forward = int(one("SELECT COUNT(*) FROM signals WHERE is_backfill=0") or 0)
    mean = one("SELECT AVG(stress_bps) FROM signals WHERE status='EVALUATED' AND is_backfill=0")
    wr = one("SELECT AVG(CASE WHEN stress_bps>0 THEN 1.0 ELSE 0.0 END) FROM signals WHERE status='EVALUATED' AND is_backfill=0")
    first_entry = one("SELECT MIN(entry_time_utc) FROM signals WHERE is_backfill=0")
    last_entry = one("SELECT MAX(entry_time_utc) FROM signals WHERE is_backfill=0")
    return {
        "total_signals": total,
        "pending_signals": pending,
        "evaluated_signals": evaluated,
        "backfill_signals": backfill,
        "true_forward_signals": true_forward,
        "evaluated_mean_stress_bps": mean,
        "evaluated_win_rate": wr,
        "first_true_forward_entry_utc": first_entry,
        "last_true_forward_entry_utc": last_entry,
    }


def write_outputs(out_dir: Path, summary: Dict[str, Any], con: sqlite3.Connection) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "stage58b_context_forward_shadow_summary.json"
    report_path = out_dir / "stage58b_context_forward_shadow_report.md"
    signals_path = out_dir / "stage58b_context_forward_shadow_signals.csv"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=False)
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Stage58B Context-Aware Stage51 True Forward Shadow\n\n")
        for k in ["status", "mode", "decision", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
            f.write(f"- {k}: `{summary.get(k)}`\n")
        f.write("\n## This run\n\n")
        for k in ["previous_watermark_utc", "eligible_latest_m15_time_utc", "new_watermark_utc", "generated_signals_this_run", "inserted_new_signals", "newly_evaluated_signals"]:
            f.write(f"- {k}: `{summary.get(k)}`\n")
        f.write("\n## State\n\n")
        for k, v in summary.get("state", {}).items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Interpretation\n\n")
        f.write("This is a true-forward evidence collector for the context-aware Stage51 shortlist. It does not authorize promotion, EA, paper-live, live trading, or order submission.\n")
    rows = con.execute("SELECT * FROM signals ORDER BY entry_time_utc DESC LIMIT 5000").fetchall()
    cols = [d[0] for d in con.execute("SELECT * FROM signals LIMIT 0").description]
    with signals_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    ap.add_argument("--stage58a-candidates", default="reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv")
    ap.add_argument("--m15-context", default="reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv")
    ap.add_argument("--m5-context", default="reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv")
    ap.add_argument("--state-db", default=DEFAULT_STATE_DB)
    ap.add_argument("--out", default="reports/stage58_context_forward_shadow")
    ap.add_argument("--reset-forward-state", action="store_true")
    ap.add_argument("--allow-historical-backfill", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    db_path = (root / args.db).resolve() if not os.path.isabs(args.db) else Path(args.db)
    cost_model_path = (root / args.cost_model).resolve() if not os.path.isabs(args.cost_model) else Path(args.cost_model)
    cand_path = (root / args.stage58a_candidates).resolve() if not os.path.isabs(args.stage58a_candidates) else Path(args.stage58a_candidates)
    m15_context_path = (root / args.m15_context).resolve() if not os.path.isabs(args.m15_context) else Path(args.m15_context)
    m5_context_path = (root / args.m5_context).resolve() if not os.path.isabs(args.m5_context) else Path(args.m5_context)
    state_db_path = (root / args.state_db).resolve() if not os.path.isabs(args.state_db) else Path(args.state_db)
    out_dir = (root / args.out).resolve() if not os.path.isabs(args.out) else Path(args.out)

    run_id = f"stage58b_{hashlib.sha1(now_utc().encode()).hexdigest()[:12]}"
    started = now_utc()
    con = ensure_state_db(state_db_path)
    if args.reset_forward_state:
        reset_state(con)
    con.execute("INSERT OR REPLACE INTO runs(run_id,started_utc,mode,note) VALUES(?,?,?,?)", (run_id, started, "starting", None))
    con.commit()

    costs = load_costs(cost_model_path)
    stress_cost_bps, extreme_cost_bps = costs
    bars = load_bars(db_path, ["M15", "M30", "M5"])
    m15_context = load_context(m15_context_path)
    m5_context = load_context(m5_context_path)
    candidates = load_candidates(cand_path)

    m15 = bars["M15"]
    m5 = bars["M5"]
    eligible_m15 = m15[m15["time_utc"] < m5["time_utc"].max()]
    eligible_latest = eligible_m15["time_utc"].max() if not eligible_m15.empty else None
    eligible_latest_iso = iso_z(eligible_latest)
    previous_watermark = kv_get(con, "forward_watermark_m15_utc")

    if previous_watermark is None and not args.allow_historical_backfill:
        # First run must not create historical pseudo-forward evidence.
        if eligible_latest_iso:
            kv_set(con, "forward_watermark_m15_utc", eligible_latest_iso)
        metrics = state_metrics(con)
        summary = {
            "stage": STAGE,
            "status": "TRUE_FORWARD_CONTEXT_SHADOW_INITIALIZED_NO_BACKFILL_NO_PROMOTION",
            "promotion": "NO_GO",
            "EA": "NO_GO",
            "paper_live": "NO_GO",
            "live": "NO_GO",
            "decision": "INITIALIZED_FORWARD_WATERMARK_WAIT_FOR_NEW_BARS_NO_PROMOTION",
            "next_allowed_step": "UPDATE_AMARKETS_AFTER_MARKET_REOPEN_THEN_RUN_STAGE58B_STAGE53_STYLE_GATES_NO_PROMOTION",
            "mode": "initialize_watermark_no_backfill",
            "root": str(root),
            "db": str(db_path),
            "state_db": str(state_db_path),
            "candidates_loaded": len(candidates),
            "previous_watermark_utc": previous_watermark,
            "eligible_latest_m15_time_utc": eligible_latest_iso,
            "new_watermark_utc": eligible_latest_iso,
            "generated_signals_this_run": 0,
            "inserted_new_signals": 0,
            "newly_evaluated_signals": 0,
            "state": metrics,
            "generated_utc": now_utc(),
        }
        con.execute("UPDATE runs SET ended_utc=?, mode=?, previous_watermark_utc=?, new_watermark_utc=?, generated_signals=0, inserted_new_signals=0, newly_evaluated_signals=0, note=? WHERE run_id=?",
                    (now_utc(), "initialize_watermark_no_backfill", previous_watermark, eligible_latest_iso, "first normal run initializes watermark only", run_id))
        con.commit()
        write_outputs(out_dir, summary, con)
        print(json.dumps({"stage": STAGE, "status": summary["status"], "mode": summary["mode"], "state": metrics, "out": str(out_dir)}))
        return 0

    watermark_ts = norm_ts(previous_watermark) if previous_watermark else None
    generated: List[Dict[str, Any]] = []
    for cand in candidates:
        generated.extend(compute_candidate_signals(
            cand, bars["M15"], bars["M30"], bars["M5"], m15_context, m5_context,
            stress_cost_bps, extreme_cost_bps, watermark_ts, args.allow_historical_backfill,
        ))
    inserted = insert_signals(con, generated, run_id)
    evaluated = evaluate_pending(con, bars["M5"])

    new_watermark = previous_watermark
    if eligible_latest_iso and not args.allow_historical_backfill:
        new_watermark = eligible_latest_iso
        kv_set(con, "forward_watermark_m15_utc", new_watermark)
    elif args.allow_historical_backfill and eligible_latest_iso:
        kv_set(con, "historical_backfill_latest_m15_utc", eligible_latest_iso)

    metrics = state_metrics(con)
    mode = "historical_backfill" if args.allow_historical_backfill else "true_forward_update"
    status = "TRUE_FORWARD_CONTEXT_SHADOW_UPDATED_NO_PROMOTION" if not args.allow_historical_backfill else "HISTORICAL_BACKFILL_CONTEXT_SHADOW_UPDATED_NO_PROMOTION"
    summary = {
        "stage": STAGE,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "decision": "CONTINUE_CONTEXT_TRUE_FORWARD_SHADOW_UNTIL_MIN_EVIDENCE_NO_PROMOTION",
        "next_allowed_step": "CONTINUE_CONTEXT_TRUE_FORWARD_SHADOW_AND_RUN_STAGE58C_GATES_NO_PROMOTION",
        "mode": mode,
        "root": str(root),
        "db": str(db_path),
        "state_db": str(state_db_path),
        "stage58a_candidates": str(cand_path),
        "m15_context": str(m15_context_path),
        "m5_context": str(m5_context_path),
        "candidates_loaded": len(candidates),
        "costs": {"stress_cost_bps": stress_cost_bps, "extreme_cost_bps": extreme_cost_bps},
        "rows": {"M15": len(bars["M15"]), "M30": len(bars["M30"]), "M5": len(bars["M5"]), "M15_context": len(m15_context), "M5_context": len(m5_context)},
        "previous_watermark_utc": previous_watermark,
        "eligible_latest_m15_time_utc": eligible_latest_iso,
        "new_watermark_utc": new_watermark,
        "generated_signals_this_run": len(generated),
        "inserted_new_signals": inserted,
        "newly_evaluated_signals": evaluated,
        "state": metrics,
        "generated_utc": now_utc(),
    }
    con.execute("UPDATE runs SET ended_utc=?, mode=?, previous_watermark_utc=?, new_watermark_utc=?, generated_signals=?, inserted_new_signals=?, newly_evaluated_signals=?, note=? WHERE run_id=?",
                (now_utc(), mode, previous_watermark, new_watermark, len(generated), inserted, evaluated, None, run_id))
    con.commit()
    write_outputs(out_dir, summary, con)
    print(json.dumps({"stage": STAGE, "status": status, "mode": mode, "inserted_new_signals": inserted, "newly_evaluated_signals": evaluated, "state": metrics, "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
