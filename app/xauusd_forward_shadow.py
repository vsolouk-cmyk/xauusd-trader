from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yaml

from app.xauusd_candidate_eval import finalize_df
from app.xauusd_sqlite_store import connect as connect_market_db
from app.xauusd_sqlite_store import read_interval


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_shadow_db(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def ensure_shadow_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_trades (
            id TEXT PRIMARY KEY,
            candidate_family TEXT NOT NULL,
            candidate_variant TEXT NOT NULL,
            source_name TEXT NOT NULL,
            interval TEXT NOT NULL,
            entry_time_utc TEXT NOT NULL,
            planned_exit_time_utc TEXT NOT NULL,
            exit_time_utc TEXT,
            direction INTEGER NOT NULL,
            direction_label TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            raw_usd REAL,
            cost_usd REAL NOT NULL,
            net_usd REAL,
            status TEXT NOT NULL,
            reason TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_shadow_status ON shadow_trades(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_shadow_entry_time ON shadow_trades(entry_time_utc)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_shadow_exit_time ON shadow_trades(exit_time_utc)")
    con.commit()


def get_meta(con: sqlite3.Connection, key: str) -> Optional[str]:
    row = con.execute("SELECT value FROM shadow_metadata WHERE key=?", (key,)).fetchone()
    return None if row is None else str(row[0])


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        """
        INSERT INTO shadow_metadata(key, value, updated_at_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at_utc=excluded.updated_at_utc
        """,
        (key, value, utc_now_iso()),
    )
    con.commit()


def load_market_df(db_path: str, interval: str) -> pd.DataFrame:
    con = connect_market_db(db_path)
    try:
        df = read_interval(con, interval)
    finally:
        con.close()
    if df.empty:
        raise FileNotFoundError(f"No market rows found for interval={interval!r} in {db_path}")
    return finalize_df(df)


def prepare_candidate_columns(df: pd.DataFrame, candidate: Dict[str, Any]) -> pd.DataFrame:
    work = df.copy()
    sma_window = int(candidate.get("sma_window", 10))
    work["candidate_sma"] = work["close"].rolling(sma_window).mean()
    work["candidate_diff"] = work["close"] - work["candidate_sma"]
    return work


def candidate_signal_at(df: pd.DataFrame, idx: int, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    horizon_bars = int(candidate.get("horizon_bars", 12))
    min_distance = float(candidate.get("min_distance_usd", 10.0))

    if idx < 0 or idx >= len(df):
        return None

    sma = df.loc[idx, "candidate_sma"]
    if pd.isna(sma):
        return None

    close = float(df.loc[idx, "close"])
    diff = float(df.loc[idx, "candidate_diff"])

    if abs(diff) < min_distance:
        return None

    direction = 1 if diff > 0 else -1

    if idx >= 1:
        step = df.loc[idx, "time_utc"] - df.loc[idx - 1, "time_utc"]
    else:
        step = pd.Timedelta(hours=1)

    planned_exit_time = df.loc[idx, "time_utc"] + step * horizon_bars

    return {
        "entry_idx": int(idx),
        "entry_time_utc": df.loc[idx, "time_utc"].isoformat(),
        "planned_exit_time_utc": planned_exit_time.isoformat(),
        "direction": int(direction),
        "direction_label": "long" if direction > 0 else "short",
        "entry_price": close,
        "sma": float(sma),
        "diff": float(diff),
        "reason": f"close_sma_diff_{diff:.4f}",
    }


def open_trades(con: sqlite3.Connection) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return list(con.execute("SELECT * FROM shadow_trades WHERE status='open' ORDER BY entry_time_utc ASC"))


def closed_trades_df(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM shadow_trades WHERE status='closed' ORDER BY entry_time_utc ASC", con)


def trade_exists(con: sqlite3.Connection, trade_id: str) -> bool:
    row = con.execute("SELECT 1 FROM shadow_trades WHERE id=?", (trade_id,)).fetchone()
    return row is not None


def latest_trade_event_time(con: sqlite3.Connection) -> Optional[pd.Timestamp]:
    row = con.execute(
        """
        SELECT MAX(event_time) FROM (
            SELECT MAX(entry_time_utc) AS event_time FROM shadow_trades
            UNION ALL
            SELECT MAX(exit_time_utc) AS event_time FROM shadow_trades WHERE exit_time_utc IS NOT NULL
        )
        """
    ).fetchone()
    if not row or not row[0]:
        return None
    return pd.to_datetime(row[0], utc=True)


def latest_closed_exit_time(con: sqlite3.Connection) -> Optional[pd.Timestamp]:
    row = con.execute("SELECT MAX(exit_time_utc) FROM shadow_trades WHERE status='closed'").fetchone()
    if not row or not row[0]:
        return None
    return pd.to_datetime(row[0], utc=True)


def interval_delta(interval: str, bars: int) -> pd.Timedelta:
    if interval == "1h":
        return pd.Timedelta(hours=int(bars))
    if interval == "15min":
        return pd.Timedelta(minutes=15 * int(bars))
    if interval == "5min":
        return pd.Timedelta(minutes=5 * int(bars))
    if interval == "1min":
        return pd.Timedelta(minutes=int(bars))
    return pd.Timedelta(hours=int(bars))


def should_respect_cooldown(con: sqlite3.Connection, entry_time: pd.Timestamp, interval: str, cooldown_bars: int) -> bool:
    last_exit = latest_closed_exit_time(con)
    if last_exit is None:
        return False
    return entry_time <= last_exit + interval_delta(interval, cooldown_bars)


def close_due_trades_until(
    con: sqlite3.Connection,
    market_df: pd.DataFrame,
    current_time: pd.Timestamp,
    cost_usd: float,
) -> list[Dict[str, Any]]:
    due_closed = []
    available_market = market_df[market_df["time_utc"] <= current_time].copy()
    if available_market.empty:
        return due_closed

    for row in open_trades(con):
        planned = pd.to_datetime(row["planned_exit_time_utc"], utc=True)
        if planned > current_time:
            continue

        available = available_market[available_market["time_utc"] >= planned]
        if available.empty:
            continue

        exit_bar = available.iloc[0]
        exit_time = exit_bar["time_utc"].isoformat()
        exit_price = float(exit_bar["close"])
        direction = int(row["direction"])
        entry_price = float(row["entry_price"])
        raw = direction * (exit_price - entry_price)
        net = raw - float(cost_usd)

        con.execute(
            """
            UPDATE shadow_trades
            SET status='closed',
                exit_time_utc=?,
                exit_price=?,
                raw_usd=?,
                net_usd=?,
                updated_at_utc=?
            WHERE id=?
            """,
            (exit_time, exit_price, raw, net, utc_now_iso(), row["id"]),
        )

        due_closed.append(
            {
                "id": row["id"],
                "entry_time_utc": row["entry_time_utc"],
                "exit_time_utc": exit_time,
                "direction_label": row["direction_label"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "raw_usd": raw,
                "net_usd": net,
            }
        )

    con.commit()
    return due_closed


def maybe_open_signal(
    con: sqlite3.Connection,
    signal: Optional[Dict[str, Any]],
    cfg: Dict[str, Any],
    cost_usd: float,
) -> Optional[Dict[str, Any]]:
    if signal is None:
        return None

    shadow_cfg = cfg.get("shadow", {}) or {}
    candidate = cfg.get("candidate", {}) or {}

    if not bool(shadow_cfg.get("allow_new_entries", True)):
        return None

    max_open = int(shadow_cfg.get("max_open_trades", 1))
    if len(open_trades(con)) >= max_open:
        return None

    interval = str(candidate.get("interval", "1h"))
    cooldown = int(candidate.get("cooldown_bars", 1))
    entry_ts = pd.to_datetime(signal["entry_time_utc"], utc=True)
    if should_respect_cooldown(con, entry_ts, interval, cooldown):
        return None

    source_name = str(shadow_cfg.get("source_name", "primary"))
    family = str(candidate.get("family", "sma_trend_1h"))
    variant = str(candidate.get("variant", "sma10_h12_dist10_cool1"))
    trade_id = f"{source_name}|{variant}|{signal['entry_time_utc']}"

    if trade_exists(con, trade_id):
        return None

    now = utc_now_iso()
    con.execute(
        """
        INSERT INTO shadow_trades (
            id, candidate_family, candidate_variant, source_name, interval,
            entry_time_utc, planned_exit_time_utc, direction, direction_label,
            entry_price, cost_usd, status, reason, created_at_utc, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
        """,
        (
            trade_id,
            family,
            variant,
            source_name,
            interval,
            signal["entry_time_utc"],
            signal["planned_exit_time_utc"],
            int(signal["direction"]),
            signal["direction_label"],
            float(signal["entry_price"]),
            float(cost_usd),
            signal.get("reason"),
            now,
            now,
        ),
    )
    con.commit()

    return {
        "id": trade_id,
        "candidate_variant": variant,
        "source_name": source_name,
        "entry_time_utc": signal["entry_time_utc"],
        "planned_exit_time_utc": signal["planned_exit_time_utc"],
        "direction_label": signal["direction_label"],
        "entry_price": float(signal["entry_price"]),
        "reason": signal.get("reason"),
    }


def initial_last_processed_time(con: sqlite3.Connection, market_df: pd.DataFrame) -> pd.Timestamp:
    meta = get_meta(con, "last_processed_bar_time_utc")
    if meta:
        return pd.to_datetime(meta, utc=True)

    trade_event = latest_trade_event_time(con)
    if trade_event is not None:
        return trade_event

    # First ever shadow run: do not backfill historical shadow trades.
    # Start from the latest available bar and wait for future bars.
    return pd.to_datetime(market_df["time_utc"].iloc[-1], utc=True)


def run_scan(con: sqlite3.Connection, market_df: pd.DataFrame, cfg: Dict[str, Any], cost_usd: float) -> Dict[str, Any]:
    candidate = cfg.get("candidate", {}) or {}
    interval = str(candidate.get("interval", "1h"))

    last_processed = initial_last_processed_time(con, market_df)
    scan_df = market_df[market_df["time_utc"] > last_processed].copy().reset_index(drop=False)

    closed_all: list[Dict[str, Any]] = []
    opened_all: list[Dict[str, Any]] = []
    signals_seen: list[Dict[str, Any]] = []

    if scan_df.empty:
        # Still try to close an open trade if current market already passed its planned exit.
        current_time = pd.to_datetime(market_df["time_utc"].iloc[-1], utc=True)
        closed_all.extend(close_due_trades_until(con, market_df, current_time, cost_usd))
        set_meta(con, "last_processed_bar_time_utc", current_time.isoformat())
        return {
            "last_processed_before": last_processed.isoformat(),
            "last_processed_after": current_time.isoformat(),
            "scanned_bars": 0,
            "closed": closed_all,
            "opened": opened_all,
            "signals_seen": signals_seen,
        }

    for _, row in scan_df.iterrows():
        original_idx = int(row["index"])
        bar_time = pd.to_datetime(row["time_utc"], utc=True)

        closed = close_due_trades_until(con, market_df, bar_time, cost_usd)
        closed_all.extend(closed)

        signal = candidate_signal_at(market_df, original_idx, candidate)
        if signal is not None:
            signals_seen.append(signal)
            opened = maybe_open_signal(con, signal, cfg, cost_usd=cost_usd)
            if opened is not None:
                opened_all.append(opened)

        set_meta(con, "last_processed_bar_time_utc", bar_time.isoformat())

    return {
        "last_processed_before": last_processed.isoformat(),
        "last_processed_after": pd.to_datetime(scan_df["time_utc"].iloc[-1], utc=True).isoformat(),
        "scanned_bars": int(len(scan_df)),
        "closed": closed_all,
        "opened": opened_all,
        "signals_seen": signals_seen,
    }


def profit_factor(values: np.ndarray) -> Optional[float]:
    if values.size == 0:
        return None
    wins = values[values > 0]
    losses = values[values <= 0]
    loss_abs = abs(float(losses.sum()))
    if loss_abs == 0:
        return None
    return float(wins.sum() / loss_abs)


def closed_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "closed_count": 0,
            "total_net_usd": 0.0,
            "profit_factor": None,
            "win_rate": 0.0,
            "last_20_net_usd": 0.0,
            "long_total_net_usd": 0.0,
            "short_total_net_usd": 0.0,
        }

    net = pd.to_numeric(df["net_usd"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    last20 = net[-20:] if len(net) >= 20 else net

    long_total = float(pd.to_numeric(df.loc[df["direction_label"] == "long", "net_usd"], errors="coerce").fillna(0.0).sum())
    short_total = float(pd.to_numeric(df.loc[df["direction_label"] == "short", "net_usd"], errors="coerce").fillna(0.0).sum())

    return {
        "closed_count": int(len(net)),
        "total_net_usd": float(net.sum()),
        "profit_factor": profit_factor(net),
        "win_rate": float((net > 0).mean()) if len(net) else 0.0,
        "last_20_net_usd": float(last20.sum()) if len(last20) else 0.0,
        "long_total_net_usd": long_total,
        "short_total_net_usd": short_total,
    }


def kill_switch_status(metrics: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    ks = cfg.get("kill_switch", {}) or {}
    closed = int(metrics.get("closed_count", 0))
    min_closed = int(ks.get("min_closed_trades_for_eval", 20))

    checks = {
        "enough_closed_for_eval": closed >= min_closed,
        "total_not_below_stop": float(metrics.get("total_net_usd", 0.0)) > float(ks.get("stop_if_total_net_below_usd", -500.0)),
        "last20_not_below_stop": float(metrics.get("last_20_net_usd", 0.0)) > float(ks.get("stop_if_last_20_net_below_usd", -350.0)),
        "long_not_below_stop": float(metrics.get("long_total_net_usd", 0.0)) > float(ks.get("stop_if_long_total_below_usd", -350.0)),
        "short_not_below_stop": float(metrics.get("short_total_net_usd", 0.0)) > float(ks.get("stop_if_short_total_below_usd", -350.0)),
    }

    pf = metrics.get("profit_factor")
    if closed >= min_closed:
        checks["pf_not_below_stop"] = pf is not None and float(pf) >= float(ks.get("stop_if_profit_factor_below_after_min_trades", 0.95))
    else:
        checks["pf_not_below_stop"] = True

    if closed < min_closed:
        return {
            "status": "collecting",
            "reason": f"Need at least {min_closed} closed shadow trades before kill-switch evaluation.",
            "checks": checks,
        }

    if all(checks.values()):
        return {
            "status": "active",
            "reason": "Forward shadow remains active under current kill-switch rules.",
            "checks": checks,
        }

    failed = [k for k, v in checks.items() if not v]
    return {
        "status": "kill_switch_triggered",
        "reason": "Forward shadow failed kill-switch checks: " + ",".join(failed),
        "checks": checks,
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 3E Forward Shadow Scan")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Candidate")
    lines.append("")
    lines.append(f"- variant: `{payload['candidate']['variant']}`")
    lines.append(f"- interval: `{payload['candidate']['interval']}`")
    lines.append("")
    lines.append("## This run")
    lines.append("")
    lines.append(f"- latest bar: `{payload['market']['latest_bar_time_utc']}`")
    lines.append(f"- scanned bars: `{payload['scan']['scanned_bars']}`")
    lines.append(f"- signals seen: `{len(payload['scan']['signals_seen'])}`")
    lines.append(f"- closed this run: `{len(payload['closed_this_run'])}`")
    lines.append(f"- opened this run: `{len(payload['opened_this_run'])}`")
    lines.append(f"- open trades: `{payload['shadow_state']['open_count']}`")
    lines.append(f"- closed trades: `{payload['shadow_state']['closed_count']}`")
    lines.append("")
    lines.append("## Closed shadow metrics")
    lines.append("")
    for k, v in payload["closed_metrics"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3E forward-shadow scanner. Logs candidate signals over missed bars; places no orders.")
    parser.add_argument("--config", default="configs/stage3d.yaml")
    parser.add_argument("--primary-db", default=None)
    parser.add_argument("--shadow-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get("candidate", {}) or {}
    data_cfg = cfg.get("data", {}) or {}
    cost_cfg = cfg.get("cost_model", {}) or {}
    shadow_cfg = cfg.get("shadow", {}) or {}

    interval = str(candidate.get("interval", "1h"))
    primary_db = args.primary_db or data_cfg.get("primary_db_path", "data/store/xauusd.sqlite")
    shadow_db = args.shadow_db or shadow_cfg.get("db_path", "data/shadow/forward_shadow.sqlite")
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))

    cost_usd = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))

    market_df = load_market_df(primary_db, interval)
    market_df = prepare_candidate_columns(market_df, candidate)
    latest_bar_time = market_df["time_utc"].iloc[-1].isoformat()

    shadow_con = connect_shadow_db(shadow_db)
    ensure_shadow_schema(shadow_con)

    scan = run_scan(shadow_con, market_df, cfg, cost_usd=cost_usd)

    open_count = len(open_trades(shadow_con))
    closed_df = closed_trades_df(shadow_con)
    metrics = closed_metrics(closed_df)
    ks_status = kill_switch_status(metrics, cfg)

    opened = scan["opened"]
    closed = scan["closed"]
    signals_seen = scan["signals_seen"]

    if ks_status["status"] == "kill_switch_triggered":
        decision_status = "forward_shadow_kill_switch_triggered"
    elif opened:
        decision_status = "forward_shadow_opened_signal"
    elif closed:
        decision_status = "forward_shadow_closed_trade"
    elif signals_seen:
        decision_status = "forward_shadow_signal_seen_but_not_opened"
    else:
        decision_status = "forward_shadow_no_signal"

    reason = ks_status["reason"] if ks_status["status"] == "kill_switch_triggered" else "Forward shadow scan completed; no orders placed."

    payload = {
        "ok": True,
        "stage": "stage3e_forward_shadow_scan",
        "generated_at_utc": utc_now_iso(),
        "candidate": {
            "family": candidate.get("family"),
            "variant": candidate.get("variant"),
            "interval": interval,
        },
        "market": {
            "primary_db": primary_db,
            "latest_bar_time_utc": latest_bar_time,
            "rows": int(len(market_df)),
        },
        "shadow_db": shadow_db,
        "scan": scan,
        "closed_this_run": closed,
        "opened_this_run": opened,
        "latest_signal": signals_seen[-1] if signals_seen else None,
        "shadow_state": {
            "open_count": int(open_count),
            "closed_count": int(len(closed_df)),
        },
        "closed_metrics": metrics,
        "kill_switch": ks_status,
        "decision": {
            "status": decision_status,
            "reason": reason,
        },
        "warning": "Diagnostic only. No order placement. No paper-order. No live trading.",
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_json = report_dir / f"stage3d_forward_shadow_summary_{stamp}.json"
    summary_md = report_dir / f"stage3d_forward_shadow_summary_{stamp}.md"

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    shadow_con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    shadow_con.commit()
    shadow_con.close()

    print(
        json.dumps(
            {
                "ok": True,
                "decision": payload["decision"],
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "shadow_db": shadow_db,
                "scanned_bars": scan["scanned_bars"],
                "signals_seen": len(signals_seen),
                "opened_count": len(opened),
                "closed_count_this_run": len(closed),
                "open_count": open_count,
                "closed_count": len(closed_df),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
