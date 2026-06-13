#!/usr/bin/env python3
"""Download FRED macro/exogenous series into data/exogenous/*.csv.

Output format required by Stage31A:
    timestamp,close
    2022-05-02T00:00:00Z,103.21

Research/shadow infrastructure only. No trading/order behavior.

This script is standalone and GitHub-friendly. It supports partial-safe and
per-series refreshes so a transient failure for one FRED source does not force
re-downloading every source.

Environment variables:
- FRED_API_KEY: optional/expected for endpoint_mode=api; GitHub secret preferred
- FRED_EXOGENOUS_OUT_DIR: output directory, default data/exogenous
- FRED_EXOGENOUS_START_DATE: first date kept, default 2022-05-01
- FRED_EXOGENOUS_SERIES: all, or comma list like us10y,vix,oil
- FRED_EXOGENOUS_ENDPOINT_MODE: api, graph, auto; default auto
- FRED_EXOGENOUS_GRAPH_FALLBACK: 1 to use fredgraph fallback after API failure, default 0
- FRED_EXOGENOUS_STRICT: 1 to fail when any selected source fails, default 0
- FRED_EXOGENOUS_ATTEMPTS: per-source attempts, default 3
- FRED_EXOGENOUS_REQUEST_DELAY: seconds between selected series, default 2
- FRED_EXOGENOUS_MIN_REAL_ROWS: minimum rows to accept a real file, default 50
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

OUT_DIR = Path(os.getenv("FRED_EXOGENOUS_OUT_DIR", "data/exogenous"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_SUCCESS_DIR = OUT_DIR / "_artifact_success"

START_DATE = os.getenv("FRED_EXOGENOUS_START_DATE", "2022-05-01")
SELECTED_SERIES_RAW = os.getenv("FRED_EXOGENOUS_SERIES", "all")
ENDPOINT_MODE = os.getenv("FRED_EXOGENOUS_ENDPOINT_MODE", "auto").strip().lower()
GRAPH_FALLBACK = os.getenv("FRED_EXOGENOUS_GRAPH_FALLBACK", "0") == "1"
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
MIN_REAL_ROWS = int(os.getenv("FRED_EXOGENOUS_MIN_REAL_ROWS", "50"))
MAX_ATTEMPTS = int(os.getenv("FRED_EXOGENOUS_ATTEMPTS", "3"))
REQUEST_DELAY = float(os.getenv("FRED_EXOGENOUS_REQUEST_DELAY", "2"))
STRICT = os.getenv("FRED_EXOGENOUS_STRICT", "0") == "1"
URL_TIMEOUT = float(os.getenv("FRED_EXOGENOUS_URL_TIMEOUT", "45"))

VALID_ENDPOINT_MODES = {"api", "graph", "auto"}
if ENDPOINT_MODE not in VALID_ENDPOINT_MODES:
    raise SystemExit(
        f"Invalid FRED_EXOGENOUS_ENDPOINT_MODE={ENDPOINT_MODE!r}. "
        f"Allowed: {', '.join(sorted(VALID_ENDPOINT_MODES))}"
    )


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


def _api_url(spec: FredSeries) -> str:
    if not FRED_API_KEY:
        raise RuntimeError(
            "FRED_API_KEY is required for FRED_EXOGENOUS_ENDPOINT_MODE=api. "
            "Set GitHub secret FRED_API_KEY or run with endpoint_mode=auto/graph."
        )
    params = {
        "series_id": spec.series_id,
        "observation_start": START_DATE,
        "file_type": "json",
        "api_key": FRED_API_KEY,
    }
    return "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)


def _graph_url(spec: FredSeries) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec.series_id}"


def _download_with_curl(url: str, dest: Path) -> None:
    """Use system curl for the legacy fredgraph endpoint."""
    base_cmd = [
        "curl",
        "--http1.1",
        "-L",
        "--fail",
        "--retry", "3",
        "--retry-delay", "3",
        "--retry-max-time", "120",
        "--connect-timeout", "15",
        "--max-time", "120",
        "-H", "User-Agent: xauusd-trader-fred-exogenous/1.3",
        "-o", str(dest),
        url,
    ]
    all_errors_cmd = base_cmd[:]
    all_errors_cmd.insert(6, "--retry-all-errors")
    try:
        subprocess.run(all_errors_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 2:
            subprocess.run(base_cmd, check=True)
        else:
            raise


def _open_url_json(url: str) -> dict[str, object]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "xauusd-trader-fred-exogenous/1.3",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as resp:  # noqa: S310 - fixed FRED URL only.
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    if "error_code" in data or "error_message" in data:
        raise RuntimeError(f"FRED API error: {data}")
    return data


def normalize_fred_api_json(data: dict[str, object], series_id: str) -> pd.DataFrame:
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise RuntimeError(f"Unexpected FRED API JSON for {series_id}: missing observations list")
    rows: list[dict[str, object]] = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        rows.append({"timestamp": item.get("date"), "close": item.get("value")})
    out = pd.DataFrame(rows, columns=["timestamp", "close"])
    return _normalize_timestamp_close(out, series_id)


def _first_present(cols: Iterable[str], candidates: list[str]) -> str | None:
    lower_to_real = {str(c).lower(): str(c) for c in cols}
    for c in candidates:
        if c in cols:
            return c
        if c.lower() in lower_to_real:
            return lower_to_real[c.lower()]
    return None


def _normalize_timestamp_close(df: pd.DataFrame, series_id: str) -> pd.DataFrame:
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


def normalize_fred_csv(raw_path: Path, series_id: str) -> pd.DataFrame:
    df = pd.read_csv(raw_path)
    return _normalize_timestamp_close(df, series_id)


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


def _fetch_via_api(spec: FredSeries) -> tuple[pd.DataFrame, str]:
    url = _api_url(spec)
    data = _open_url_json(url)
    out = normalize_fred_api_json(data, spec.series_id)
    safe_url = url.replace(FRED_API_KEY, "***") if FRED_API_KEY else url
    return out, safe_url


def _fetch_via_graph(spec: FredSeries) -> tuple[pd.DataFrame, str]:
    url = _graph_url(spec)
    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / f"{spec.series_id}.csv"
        _download_with_curl(url, raw_path)
        out = normalize_fred_csv(raw_path, spec.series_id)
    return out, url


def _endpoint_sequence() -> list[str]:
    if ENDPOINT_MODE == "api":
        return ["api", "graph"] if GRAPH_FALLBACK else ["api"]
    if ENDPOINT_MODE == "graph":
        return ["graph"]
    # auto mode: prefer API when a key exists; otherwise use legacy graph.
    seq = ["api"] if FRED_API_KEY else ["graph"]
    if FRED_API_KEY and GRAPH_FALLBACK:
        seq.append("graph")
    return seq


def fetch_one(spec: FredSeries) -> tuple[pd.DataFrame, str, str]:
    errors: list[str] = []
    for endpoint in _endpoint_sequence():
        try:
            if endpoint == "api":
                out, url = _fetch_via_api(spec)
            elif endpoint == "graph":
                out, url = _fetch_via_graph(spec)
            else:
                raise RuntimeError(f"unknown endpoint={endpoint}")
            return out, endpoint, url
        except Exception as exc:  # noqa: BLE001 - keep fallback/manifest robust.
            err = f"{endpoint}: {type(exc).__name__}: {exc}"
            errors.append(err)
            print(f"WARN {spec.series_id} endpoint failed: {err}")
    raise RuntimeError("; ".join(errors))


def download_one(spec: FredSeries) -> dict[str, object]:
    output_path = OUT_DIR / spec.filename
    last_error = ""
    endpoint_used = ""
    url_used = ""

    print(f"Downloading {spec.series_id} -> {spec.filename} ({spec.alias})")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            out, endpoint_used, url_used = fetch_one(spec)
            rows = len(out)
            if rows < MIN_REAL_ROWS:
                raise RuntimeError(f"too_few_rows rows={rows} min={MIN_REAL_ROWS}")

            out.to_csv(output_path, index=False)
            _copy_success_to_artifact(spec.filename)
            print(f"Saved {output_path} rows={rows} endpoint={endpoint_used}")
            return {
                "alias": spec.alias,
                "filename": spec.filename,
                "series_id": spec.series_id,
                "status": "downloaded",
                "rows": rows,
                "existing_rows": existing_real_rows(output_path),
                "endpoint": endpoint_used,
                "url": url_used,
                "output_path": str(output_path),
                "artifact_success_path": str(ARTIFACT_SUCCESS_DIR / spec.filename),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - manifest must capture any failure.
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"WARN {spec.series_id} attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(5 * attempt, 20))

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
            "endpoint": endpoint_used or ENDPOINT_MODE,
            "url": url_used,
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
        "endpoint": endpoint_used or ENDPOINT_MODE,
        "url": url_used,
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
    print(f"FRED_EXOGENOUS_ENDPOINT_MODE={ENDPOINT_MODE}")
    print(f"FRED_EXOGENOUS_GRAPH_FALLBACK={int(GRAPH_FALLBACK)}")
    print(f"FRED_API_KEY_PRESENT={int(bool(FRED_API_KEY))}")
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
