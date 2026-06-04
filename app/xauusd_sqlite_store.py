from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd


INTERVAL_SECONDS: Dict[str, int] = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1day": 86400,
}


def table_for_interval(interval: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(interval))
    if not re.match(r"^[A-Za-z_]", safe):
        safe = f"i_{safe}"
    return f"candles_{safe}"


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    return con


def ensure_interval_table(con: sqlite3.Connection, interval: str) -> None:
    table = table_for_interval(interval)
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            time_utc TEXT PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            provider TEXT NOT NULL,
            session_utc TEXT,
            fetched_at_utc TEXT,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_time ON {table}(time_utc)")
    con.commit()


def ensure_metadata_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    con.commit()


def ensure_schema(con: sqlite3.Connection, intervals: Iterable[str]) -> None:
    ensure_metadata_table(con)
    for interval in intervals:
        ensure_interval_table(con, interval)


def upsert_candles(con: sqlite3.Connection, interval: str, df: pd.DataFrame) -> int:
    ensure_interval_table(con, interval)
    table = table_for_interval(interval)

    required = ["time_utc", "open", "high", "low", "close", "symbol", "interval", "provider"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required store columns for {interval}: {missing}")

    before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    work = df.copy()
    work["time_utc"] = pd.to_datetime(work["time_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    # Normalize timezone string to ISO style +00:00.
    work["time_utc"] = work["time_utc"].str.replace(r"(\+0000)$", "+00:00", regex=True)

    if "volume" not in work.columns:
        work["volume"] = 0.0
    if "session_utc" not in work.columns:
        work["session_utc"] = None
    if "fetched_at_utc" not in work.columns:
        work["fetched_at_utc"] = None

    updated_at = pd.Timestamp.now(tz="UTC").isoformat()
    work["updated_at_utc"] = updated_at

    cols = [
        "time_utc",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "symbol",
        "interval",
        "provider",
        "session_utc",
        "fetched_at_utc",
        "updated_at_utc",
    ]
    records = work[cols].drop_duplicates(subset=["time_utc"], keep="last").to_records(index=False).tolist()

    con.executemany(
        f"""
        INSERT INTO {table} ({",".join(cols)})
        VALUES ({",".join(["?"] * len(cols))})
        ON CONFLICT(time_utc) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            symbol=excluded.symbol,
            interval=excluded.interval,
            provider=excluded.provider,
            session_utc=excluded.session_utc,
            fetched_at_utc=excluded.fetched_at_utc,
            updated_at_utc=excluded.updated_at_utc
        """,
        records,
    )
    con.commit()

    after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return int(after - before)


def trim_interval(con: sqlite3.Connection, interval: str, max_rows: int) -> int:
    if max_rows <= 0:
        return 0
    table = table_for_interval(interval)
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    extra = int(count) - int(max_rows)
    if extra <= 0:
        return 0
    con.execute(
        f"""
        DELETE FROM {table}
        WHERE time_utc IN (
            SELECT time_utc FROM {table}
            ORDER BY time_utc ASC
            LIMIT ?
        )
        """,
        (extra,),
    )
    con.commit()
    return extra


def read_interval(con: sqlite3.Connection, interval: str) -> pd.DataFrame:
    ensure_interval_table(con, interval)
    table = table_for_interval(interval)
    df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY time_utc ASC", con)
    if df.empty:
        return df
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df["date_utc"] = df["time_utc"].dt.date.astype(str)
    df["hour_utc"] = df["time_utc"].dt.hour
    if "session_utc" not in df.columns or df["session_utc"].isna().all():
        hours = df["hour_utc"]
        df["session_utc"] = "other"
        df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
        df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
        df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
        df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"
    return df.reset_index(drop=True)


def interval_stats(con: sqlite3.Connection, interval: str) -> dict:
    ensure_interval_table(con, interval)
    table = table_for_interval(interval)
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows, MIN(time_utc) AS start_utc, MAX(time_utc) AS end_utc
        FROM {table}
        """
    ).fetchone()
    return {"interval": interval, "rows": int(row[0]), "start_utc": row[1], "end_utc": row[2]}


def latest_time(con: sqlite3.Connection, interval: str) -> Optional[pd.Timestamp]:
    stats = interval_stats(con, interval)
    if not stats.get("end_utc"):
        return None
    return pd.to_datetime(stats["end_utc"], utc=True)


def optimize(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    con.execute("VACUUM;")
    con.commit()
