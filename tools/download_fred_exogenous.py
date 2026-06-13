"""Download FRED macro/exogenous series into data/exogenous/*.csv.

Output format required by Stage31A:
    timestamp,close
    2022-05-02T00:00:00Z,103.21

This script is intentionally standalone so it can run both locally and in
GitHub Actions. It accepts both common FRED CSV date column names:
DATE and observation_date.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import pandas as pd

OUT_DIR = Path(os.getenv("FRED_EXOGENOUS_OUT_DIR", "data/exogenous"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = os.getenv("FRED_EXOGENOUS_START_DATE", "2022-05-01")

# File name -> FRED series id
SERIES = {
    # Dollar strength proxy, not ICE DXY. FRED broad USD index.
    "dxy.csv": "DTWEXBGS",
    # 10-year nominal US Treasury yield
    "us10y.csv": "DGS10",
    # 10-year real yield / TIPS constant maturity
    "real_yield.csv": "DFII10",
    # CBOE VIX
    "vix.csv": "VIXCLS",
    # S&P 500 index
    "spx.csv": "SP500",
    # WTI crude oil
    "oil.csv": "DCOILWTICO",
}


def _download_with_curl(url: str, dest: Path) -> None:
    """Use system curl first because it is usually more robust on macOS/GHA."""
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry", "3",
        "--retry-delay", "2",
        "--connect-timeout", "20",
        "--max-time", "120",
        "-o", str(dest),
        url,
    ]
    subprocess.run(cmd, check=True)


def _first_present(cols: Iterable[str], candidates: list[str]) -> str | None:
    colset = set(cols)
    for c in candidates:
        if c in colset:
            return c
    return None


def normalize_fred_csv(raw_path: Path, series_id: str) -> pd.DataFrame:
    df = pd.read_csv(raw_path)
    date_col = _first_present(df.columns, ["DATE", "observation_date", "date", "timestamp"])
    value_col = _first_present(df.columns, [series_id, "close", "value"])

    if date_col is None or value_col is None:
        raise RuntimeError(
            f"Unexpected FRED format for {series_id}: columns={list(df.columns)}"
        )

    out = df.rename(columns={date_col: "timestamp", value_col: "close"})[["timestamp", "close"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["close"] = pd.to_numeric(out["close"].replace(".", pd.NA), errors="coerce")
    out = out.dropna(subset=["timestamp", "close"])
    out = out[out["timestamp"] >= pd.Timestamp(START_DATE, tz="UTC")]
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def main() -> None:
    print(f"FRED_EXOGENOUS_START_DATE={START_DATE}")
    print(f"FRED_EXOGENOUS_OUT_DIR={OUT_DIR}")

    for filename, series_id in SERIES.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        print(f"Downloading {series_id} -> {filename}")

        with tempfile.TemporaryDirectory() as td:
            raw_path = Path(td) / f"{series_id}.csv"
            _download_with_curl(url, raw_path)
            out = normalize_fred_csv(raw_path, series_id)

        path = OUT_DIR / filename
        out.to_csv(path, index=False)
        print(f"Saved {path} rows={len(out)}")

        if len(out) < 50:
            raise RuntimeError(f"Too few rows for {series_id}: rows={len(out)}")

    print("Done.")


if __name__ == "__main__":
    main()
