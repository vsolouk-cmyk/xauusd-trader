"""Download FRED macro/exogenous series into data/exogenous/*.csv.

Output format required by Stage31A:
    timestamp,close
    2022-05-02T00:00:00Z,103.21

This script is intentionally standalone so it can run both locally and in
GitHub Actions. It is partial-safe: a transient failure for one FRED series
(e.g., HTTP 504) does not abort the whole refresh. Successful series are saved,
failed series are recorded in a manifest, and Stage31A can continue with the
sources that were actually downloaded.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

OUT_DIR = Path(os.getenv("FRED_EXOGENOUS_OUT_DIR", "data/exogenous"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = os.getenv("FRED_EXOGENOUS_START_DATE", "2022-05-01")
MIN_REAL_ROWS = int(os.getenv("FRED_EXOGENOUS_MIN_REAL_ROWS", "50"))
MAX_ATTEMPTS = int(os.getenv("FRED_EXOGENOUS_ATTEMPTS", "4"))
STRICT = os.getenv("FRED_EXOGENOUS_STRICT", "0") == "1"

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
    """Use system curl because it is usually more robust on macOS/GHA."""
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry", "8",
        "--retry-delay", "5",
        "--retry-max-time", "180",
        "--connect-timeout", "20",
        "--max-time", "180",
        "-H", "User-Agent: xauusd-trader-fred-exogenous/1.1",
        "-o", str(dest),
        url,
    ]

    # Available on GitHub's curl and most modern macOS curl versions. If it is
    # not supported locally, retry without it.
    cmd_with_all_errors = cmd[:]
    cmd_with_all_errors.insert(5, "--retry-all-errors")
    try:
        subprocess.run(cmd_with_all_errors, check=True)
    except subprocess.CalledProcessError as exc:
        # curl exits with 2 for unknown option on older versions. In that case,
        # retry without --retry-all-errors; otherwise re-raise the original HTTP/network error.
        if exc.returncode == 2:
            subprocess.run(cmd, check=True)
        else:
            raise


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


def existing_real_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
    except Exception:
        return 0
    if not {"timestamp", "close"}.issubset(df.columns):
        return 0
    vals = pd.to_numeric(df["close"].replace(".", pd.NA), errors="coerce")
    return int(vals.notna().sum())


def download_one(filename: str, series_id: str) -> dict:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    output_path = OUT_DIR / filename
    last_error = ""

    print(f"Downloading {series_id} -> {filename}")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with tempfile.TemporaryDirectory() as td:
                raw_path = Path(td) / f"{series_id}.csv"
                _download_with_curl(url, raw_path)
                out = normalize_fred_csv(raw_path, series_id)

            rows = len(out)
            if rows < MIN_REAL_ROWS:
                raise RuntimeError(f"too_few_rows rows={rows} min={MIN_REAL_ROWS}")

            out.to_csv(output_path, index=False)
            print(f"Saved {output_path} rows={rows}")
            return {
                "filename": filename,
                "series_id": series_id,
                "status": "downloaded",
                "rows": rows,
                "existing_rows": existing_real_rows(output_path),
                "url": url,
                "output_path": str(output_path),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - manifest must capture any failure.
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"WARN {series_id} attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(10 * attempt, 30))

    preserved_rows = existing_real_rows(output_path)
    if preserved_rows >= MIN_REAL_ROWS:
        print(f"Preserving existing {output_path} rows={preserved_rows} after failed refresh")
        return {
            "filename": filename,
            "series_id": series_id,
            "status": "preserved_existing_after_failed_refresh",
            "rows": preserved_rows,
            "existing_rows": preserved_rows,
            "url": url,
            "output_path": str(output_path),
            "error": last_error,
        }

    print(f"ERROR {series_id} failed and no real existing output is available")
    return {
        "filename": filename,
        "series_id": series_id,
        "status": "failed",
        "rows": 0,
        "existing_rows": preserved_rows,
        "url": url,
        "output_path": str(output_path),
        "error": last_error,
    }


def main() -> None:
    print(f"FRED_EXOGENOUS_START_DATE={START_DATE}")
    print(f"FRED_EXOGENOUS_OUT_DIR={OUT_DIR}")
    print(f"FRED_EXOGENOUS_ATTEMPTS={MAX_ATTEMPTS}")
    print(f"FRED_EXOGENOUS_STRICT={int(STRICT)}")

    manifest = [download_one(filename, series_id) for filename, series_id in SERIES.items()]
    manifest_df = pd.DataFrame(manifest)
    manifest_path = OUT_DIR / "fred_download_manifest.csv"
    manifest_df.to_csv(manifest_path, index=False)

    loaded = int((manifest_df["status"].isin(["downloaded", "preserved_existing_after_failed_refresh"])).sum())
    failed = int((manifest_df["status"] == "failed").sum())
    print(f"Saved {manifest_path}")
    print(f"FRED refresh summary: usable_sources={loaded} failed_sources={failed} total={len(manifest)}")

    if STRICT and failed:
        raise RuntimeError(f"FRED strict mode failed: failed_sources={failed}")

    if loaded == 0:
        print("WARN: no usable FRED source downloaded; Stage31A will likely remain template-only.")
    print("Done.")


if __name__ == "__main__":
    main()
