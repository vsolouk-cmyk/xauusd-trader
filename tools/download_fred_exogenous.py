#!/usr/bin/env python3
"""Download FRED macro/exogenous series into data/exogenous/*.csv.

Output format required by Stage31A:
    timestamp,close
    2022-05-02T00:00:00Z,103.21

Research/shadow infrastructure only. No trading/order behavior.

This script is standalone and GitHub-friendly. It supports partial-safe and
per-series refreshes so a transient failure for one FRED endpoint does not force
re-downloading every source.

Environment variables:
- FRED_EXOGENOUS_OUT_DIR: output directory, default data/exogenous
- FRED_EXOGENOUS_START_DATE: first date kept, default 2022-05-01
- FRED_EXOGENOUS_SERIES: all, or comma list like us10y,vix,oil
- FRED_EXOGENOUS_STRICT: 1 to fail when any selected source fails, default 0
- FRED_EXOGENOUS_ATTEMPTS: per-source attempts, default 4
- FRED_EXOGENOUS_REQUEST_DELAY: seconds between selected series, default 3
- FRED_EXOGENOUS_MIN_REAL_ROWS: minimum rows to accept a real file, default 50
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

OUT_DIR = Path(os.getenv("FRED_EXOGENOUS_OUT_DIR", "data/exogenous"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_SUCCESS_DIR = OUT_DIR / "_artifact_success"

START_DATE = os.getenv("FRED_EXOGENOUS_START_DATE", "2022-05-01")
SELECTED_SERIES_RAW = os.getenv("FRED_EXOGENOUS_SERIES", "all")
MIN_REAL_ROWS = int(os.getenv("FRED_EXOGENOUS_MIN_REAL_ROWS", "50"))
MAX_ATTEMPTS = int(os.getenv("FRED_EXOGENOUS_ATTEMPTS", "4"))
REQUEST_DELAY = float(os.getenv("FRED_EXOGENOUS_REQUEST_DELAY", "3"))
STRICT = os.getenv("FRED_EXOGENOUS_STRICT", "0") == "1"


@dataclass(frozen=True)
class FredSeries:
    alias: str
    filename: str
    series_id: str
    description: str


SERIES: dict[str, FredSeries] = {
    "dxy": FredSeries(
        alias="dxy",
        filename="dxy.csv",
        series_id="DTWEXBGS",
        description="FRED broad U.S. dollar index proxy, not ICE DXY.",
    ),
    "us10y": FredSeries(
        alias="us10y",
        filename="us10y.csv",
        series_id="DGS10",
        description="10-year nominal U.S. Treasury yield.",
    ),
    "real_yield": FredSeries(
        alias="real_yield",
        filename="real_yield.csv",
        series_id="DFII10",
        description="10-year real yield / TIPS constant maturity.",
    ),
    "vix": FredSeries(
        alias="vix",
        filename="vix.csv",
        series_id="VIXCLS",
        description="CBOE VIX close.",
    ),
    "spx": FredSeries(
        alias="spx",
        filename="spx.csv",
        series_id="SP500",
        description="S&P 500 close from FRED.",
    ),
    "oil": FredSeries(
        alias="oil",
        filename="oil.csv",
        series_id="DCOILWTICO",
        description="WTI crude oil price from FRED.",
    ),
}


def _series_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for alias, spec in SERIES.items():
        lookup[alias.lower()] = alias
        lookup[spec.filename.lower()] = alias
        lookup[spec.filename.lower().replace(".csv", "")] = alias
        lookup[spec.series_id.lower()] = alias
    return lookup


def parse_selected_series(raw: str) -> list[FredSeries]:
    raw = (raw or "all").strip()
    if raw.lower() in {"all", "*", "any", ""}:
        return list(SERIES.values())

    lookup = _series_lookup()
    selected_aliases: list[str] = []
    bad_tokens: list[str] = []
    for token in raw.replace(";", ",").split(","):
        token_norm = token.strip().lower()
        if not token_norm:
            continue
        alias = lookup.get(token_norm)
        if alias is None:
            bad_tokens.append(token.strip())
            continue
        if alias not in selected_aliases:
            selected_aliases.append(alias)

    if bad_tokens:
        allowed = ", ".join(SERIES.keys())
        raise SystemExit(
            f"Invalid FRED_EXOGENOUS_SERIES token(s): {bad_tokens}. "
            f"Allowed aliases: all, {allowed}"
        )
    if not selected_aliases:
        raise SystemExit("No valid FRED series selected.")
    return [SERIES[a] for a in selected_aliases]


def _download_with_curl(url: str, dest: Path) -> None:
    """Use system curl because it is usually more robust on macOS/GHA."""
    base_cmd = [
        "curl",
        "--http1.1",
        "-L",
        "--fail",
        "--retry", "8",
        "--retry-delay", "5",
        "--retry-max-time", "240",
        "--connect-timeout", "20",
        "--max-time", "240",
        "-H", "User-Agent: xauusd-trader-fred-exogenous/1.2",
        "-o", str(dest),
        url,
    ]
    all_errors_cmd = base_cmd[:]
    all_errors_cmd.insert(6, "--retry-all-errors")
    try:
        subprocess.run(all_errors_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        # curl exits with 2 for unknown option on older versions. In that case,
        # retry without --retry-all-errors; otherwise re-raise the original error.
        if exc.returncode == 2:
            subprocess.run(base_cmd, check=True)
        else:
            raise


def _first_present(cols: Iterable[str], candidates: list[str]) -> str | None:
    lower_to_real = {str(c).lower(): str(c) for c in cols}
    for c in candidates:
        if c in cols:
            return c
        if c.lower() in lower_to_real:
            return lower_to_real[c.lower()]
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


def _copy_success_to_artifact(filename: str) -> None:
    src = OUT_DIR / filename
    if src.exists() and existing_real_rows(src) >= MIN_REAL_ROWS:
        ARTIFACT_SUCCESS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, ARTIFACT_SUCCESS_DIR / filename)


def download_one(spec: FredSeries) -> dict[str, object]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec.series_id}"
    output_path = OUT_DIR / spec.filename
    last_error = ""

    print(f"Downloading {spec.series_id} -> {spec.filename} ({spec.alias})")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with tempfile.TemporaryDirectory() as td:
                raw_path = Path(td) / f"{spec.series_id}.csv"
                _download_with_curl(url, raw_path)
                out = normalize_fred_csv(raw_path, spec.series_id)

            rows = len(out)
            if rows < MIN_REAL_ROWS:
                raise RuntimeError(f"too_few_rows rows={rows} min={MIN_REAL_ROWS}")

            out.to_csv(output_path, index=False)
            _copy_success_to_artifact(spec.filename)
            print(f"Saved {output_path} rows={rows}")
            return {
                "alias": spec.alias,
                "filename": spec.filename,
                "series_id": spec.series_id,
                "status": "downloaded",
                "rows": rows,
                "existing_rows": existing_real_rows(output_path),
                "url": url,
                "output_path": str(output_path),
                "artifact_success_path": str(ARTIFACT_SUCCESS_DIR / spec.filename),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - manifest must capture any failure.
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"WARN {spec.series_id} attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(10 * attempt, 45))

    preserved_rows = existing_real_rows(output_path)
    if preserved_rows >= MIN_REAL_ROWS:
        _copy_success_to_artifact(spec.filename)
        print(f"Preserving existing {output_path} rows={preserved_rows} after failed refresh")
        return {
            "alias": spec.alias,
            "filename": spec.filename,
            "series_id": spec.series_id,
            "status": "preserved_existing_after_failed_refresh",
            "rows": preserved_rows,
            "existing_rows": preserved_rows,
            "url": url,
            "output_path": str(output_path),
            "artifact_success_path": str(ARTIFACT_SUCCESS_DIR / spec.filename),
            "error": last_error,
        }

    print(f"ERROR {spec.series_id} failed and no real existing output is available")
    return {
        "alias": spec.alias,
        "filename": spec.filename,
        "series_id": spec.series_id,
        "status": "failed",
        "rows": 0,
        "existing_rows": preserved_rows,
        "url": url,
        "output_path": str(output_path),
        "artifact_success_path": "",
        "error": last_error,
    }


def prepare_success_dir() -> None:
    if ARTIFACT_SUCCESS_DIR.exists():
        shutil.rmtree(ARTIFACT_SUCCESS_DIR)
    ARTIFACT_SUCCESS_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    selected = parse_selected_series(SELECTED_SERIES_RAW)
    prepare_success_dir()

    print(f"FRED_EXOGENOUS_START_DATE={START_DATE}")
    print(f"FRED_EXOGENOUS_OUT_DIR={OUT_DIR}")
    print(f"FRED_EXOGENOUS_SERIES={SELECTED_SERIES_RAW}")
    print(f"FRED selected aliases={','.join(s.alias for s in selected)}")
    print(f"FRED_EXOGENOUS_ATTEMPTS={MAX_ATTEMPTS}")
    print(f"FRED_EXOGENOUS_REQUEST_DELAY={REQUEST_DELAY}")
    print(f"FRED_EXOGENOUS_STRICT={int(STRICT)}")

    manifest: list[dict[str, object]] = []
    for idx, spec in enumerate(selected):
        manifest.append(download_one(spec))
        if idx < len(selected) - 1 and REQUEST_DELAY > 0:
            print(f"Sleeping {REQUEST_DELAY:.1f}s before next selected series")
            time.sleep(REQUEST_DELAY)

    manifest_df = pd.DataFrame(manifest)
    manifest_path = OUT_DIR / "fred_download_manifest.csv"
    manifest_df.to_csv(manifest_path, index=False)
    shutil.copy2(manifest_path, ARTIFACT_SUCCESS_DIR / "fred_download_manifest.csv")
    (ARTIFACT_SUCCESS_DIR / "fred_selected_series.txt").write_text(
        ",".join(s.alias for s in selected) + "\n", encoding="utf-8"
    )

    usable_statuses = ["downloaded", "preserved_existing_after_failed_refresh"]
    loaded = int((manifest_df["status"].isin(usable_statuses)).sum())
    failed = int((manifest_df["status"] == "failed").sum())
    print(f"Saved {manifest_path}")
    print(f"Artifact-success dir: {ARTIFACT_SUCCESS_DIR}")
    print(f"FRED refresh summary: usable_sources={loaded} failed_sources={failed} selected={len(manifest)}")

    if STRICT and failed:
        raise RuntimeError(f"FRED strict mode failed: failed_sources={failed}")

    if loaded == 0:
        print("WARN: no usable selected FRED source downloaded.")
    print("Done.")


if __name__ == "__main__":
    main()
