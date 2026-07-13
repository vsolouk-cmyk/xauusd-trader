#!/usr/bin/env python3
"""Stage171H4 — persistent exact-DXY downloader for H64L forward shadow.

Source order:
1) Yahoo Finance DX-Y.NYB chart endpoint (ICE U.S. Dollar Index delayed series)
2) Stooq DX.F daily CSV (ICE USDX futures continuous series)
3) ICE-weighted DXY reconstruction from six official FRED FX series

The downloader is fail-closed: invalid/HTML/rate-limited responses never replace
an existing valid history. New data must pass range, return and overlap checks.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import shutil
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage171H4_EXACT_DXY_DOWNLOADER"
DEFAULT_OUT = "data/exogenous/dxy.csv"
DEFAULT_REPORT = "reports/stage171h4_exact_dxy_downloader"
YAHOO_SYMBOL = "DX-Y.NYB"

# ICE U.S. Dollar Index formula. FX orientations match the FRED series below.
DXY_CONSTANT = 50.14348112
FRED_SERIES = {
    "eurusd": "DEXUSEU",  # USD per EUR
    "usdjpy": "DEXJPUS",  # JPY per USD
    "gbpusd": "DEXUSUK",  # USD per GBP
    "usdcad": "DEXCAUS",  # CAD per USD
    "usdsek": "DEXSDUS",  # SEK per USD
    "usdchf": "DEXSZUS",  # CHF per USD
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_iso(value: Optional[dt.datetime] = None) -> str:
    x = (value or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    return x.isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def content_block_reason(data: bytes) -> Optional[str]:
    text = data[:16384].decode("utf-8", errors="replace").strip().lower()
    if not text:
        return "EMPTY_RESPONSE"
    checks = {
        "<!doctype": "HTML_RESPONSE_NOT_DATA",
        "<html": "HTML_RESPONSE_NOT_DATA",
        "too many requests": "RATE_LIMIT_RESPONSE",
        "access denied": "ACCESS_DENIED_RESPONSE",
        "cloudflare": "BOT_PROTECTION_RESPONSE",
        "captcha": "BOT_PROTECTION_RESPONSE",
    }
    for token, reason in checks.items():
        if token in text:
            return reason
    return None


def http_get(url: str, timeout: int, retries: int) -> Tuple[Optional[bytes], Dict[str, Any]]:
    attempts: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/149 Safari/537.36",
        "Accept": "application/json,text/csv,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    for idx in range(max(1, retries)):
        started = utc_now()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                reason = content_block_reason(data)
                row = {
                    "attempt": idx + 1,
                    "status": int(getattr(resp, "status", 200)),
                    "bytes": len(data),
                    "elapsed_seconds": round((utc_now() - started).total_seconds(), 3),
                    "content_type": str(resp.headers.get("Content-Type", "")),
                    "block_reason": reason,
                }
                attempts.append(row)
                if reason is None:
                    return data, {"ok": True, "url": url, "attempts": attempts}
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            attempts.append({
                "attempt": idx + 1,
                "status": int(exc.code),
                "bytes": len(body),
                "elapsed_seconds": round((utc_now() - started).total_seconds(), 3),
                "error": f"HTTPError:{exc.code}",
                "block_reason": content_block_reason(body),
            })
        except Exception as exc:  # noqa: BLE001
            attempts.append({
                "attempt": idx + 1,
                "elapsed_seconds": round((utc_now() - started).total_seconds(), 3),
                "error": f"{type(exc).__name__}:{exc}",
            })
        if idx + 1 < retries:
            time.sleep(min(20.0, 2.0 * (2**idx)))
    return None, {"ok": False, "url": url, "attempts": attempts}


def normalize_frame(df: pd.DataFrame, source: str, contract: str) -> pd.DataFrame:
    if df.empty:
        raise ValueError("empty frame")
    lower = {str(c).strip().lower(): c for c in df.columns}
    date_col = next((lower[x] for x in ["date_utc", "date", "timestamp", "observation_date"] if x in lower), None)
    value_col = next((lower[x] for x in ["value", "close", "adj close", "adjclose", "dxy"] if x in lower), None)
    if date_col is None or value_col is None:
        raise ValueError(f"schema not recognized: {list(df.columns)}")
    raw_date = df[date_col].astype(str).str.strip()
    dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    ymd = raw_date.str.fullmatch(r"\d{8}")
    if ymd.any():
        dates.loc[ymd] = pd.to_datetime(raw_date.loc[ymd], format="%Y%m%d", errors="coerce", utc=True)
    if (~ymd).any():
        dates.loc[~ymd] = pd.to_datetime(raw_date.loc[~ymd], errors="coerce", utc=True)
    out = pd.DataFrame({
        "date_utc": dates.dt.floor("D").dt.strftime("%Y-%m-%d"),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna().sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    out["source"] = source
    out["source_contract"] = contract
    out["available_after_utc"] = utc_iso()
    if len(out) < 21:
        raise ValueError(f"fewer than 21 rows: {len(out)}")
    return out


def parse_yahoo(data: bytes) -> pd.DataFrame:
    obj = json.loads(data.decode("utf-8"))
    chart = obj.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo chart error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart result missing")
    result = results[0]
    ts = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []
    if len(ts) != len(closes) or not ts:
        raise ValueError("Yahoo timestamp/close mismatch")
    rows = []
    for epoch, close in zip(ts, closes):
        if close is None:
            continue
        rows.append({
            "date": dt.datetime.fromtimestamp(int(epoch), tz=dt.timezone.utc).date().isoformat(),
            "close": close,
        })
    return normalize_frame(
        pd.DataFrame(rows),
        "YAHOO_FINANCE_DX-Y.NYB_DELAYED",
        "ICE_US_DOLLAR_INDEX_DELAYED_SERIES",
    )


def fetch_yahoo(start_date: dt.date, end_date: dt.date, timeout: int, retries: int) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    p1 = int(dt.datetime.combine(start_date, dt.time.min, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.combine(end_date + dt.timedelta(days=2), dt.time.min, tzinfo=dt.timezone.utc).timestamp())
    params = urllib.parse.urlencode({
        "period1": p1,
        "period2": p2,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    attempts: List[Dict[str, Any]] = []
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        url = f"https://{host}/v8/finance/chart/{urllib.parse.quote(YAHOO_SYMBOL)}?{params}"
        data, meta = http_get(url, timeout, retries)
        attempts.append(meta)
        if data is None:
            continue
        try:
            frame = parse_yahoo(data)
            return frame, {"ok": True, "source": "yahoo", "requests": attempts}
        except Exception as exc:  # noqa: BLE001
            attempts[-1]["parse_error"] = f"{type(exc).__name__}:{exc}"
    return None, {"ok": False, "source": "yahoo", "requests": attempts}


def parse_stooq(data: bytes) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text.splitlines() else ""
    sep = max([",", ";", "\t", "|"], key=first.count)
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception:
        df = pd.read_csv(io.StringIO(text), sep=sep, header=None)
    if not any(str(c).strip().lower() in {"date", "date_utc"} for c in df.columns):
        if df.shape[1] < 5:
            raise ValueError("Stooq schema too narrow")
        names = ["Date", "Open", "High", "Low", "Close", "Volume", "OpenInt"][: df.shape[1]]
        df.columns = names
    return normalize_frame(
        df,
        "STOOQ_DX.F_DAILY",
        "ICE_USDX_FUTURES_CONTINUOUS_SERIES",
    )


def fetch_stooq(start_date: dt.date, end_date: dt.date, timeout: int, retries: int) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    params = urllib.parse.urlencode({
        "s": "dx.f",
        "d1": start_date.strftime("%Y%m%d"),
        "d2": end_date.strftime("%Y%m%d"),
        "i": "d",
    })
    attempts: List[Dict[str, Any]] = []
    for host in ["stooq.com", "stooq.pl"]:
        url = f"https://{host}/q/d/l/?{params}"
        data, meta = http_get(url, timeout, retries)
        attempts.append(meta)
        if data is None:
            continue
        try:
            frame = parse_stooq(data)
            return frame, {"ok": True, "source": "stooq", "requests": attempts}
        except Exception as exc:  # noqa: BLE001
            attempts[-1]["parse_error"] = f"{type(exc).__name__}:{exc}"
    return None, {"ok": False, "source": "stooq", "requests": attempts}


def parse_fred_csv(data: bytes, series_id: str) -> pd.DataFrame:
    reason = content_block_reason(data)
    if reason:
        raise ValueError(reason)
    df = pd.read_csv(io.BytesIO(data))
    if "observation_date" not in df.columns or series_id not in df.columns:
        raise ValueError(f"FRED schema mismatch for {series_id}: {list(df.columns)}")
    out = pd.DataFrame({
        "date_utc": pd.to_datetime(df["observation_date"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d"),
        series_id: pd.to_numeric(df[series_id], errors="coerce"),
    }).dropna().sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    return out


def fetch_fred_reconstruction(timeout: int, retries: int) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    frames: List[pd.DataFrame] = []
    requests_meta: Dict[str, Any] = {}
    for alias, series_id in FRED_SERIES.items():
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?" + urllib.parse.urlencode({"id": series_id})
        data, meta = http_get(url, timeout, retries)
        requests_meta[series_id] = meta
        if data is None:
            return None, {"ok": False, "source": "fred_reconstruction", "requests": requests_meta, "failed_series": series_id}
        try:
            x = parse_fred_csv(data, series_id).rename(columns={series_id: alias})
            frames.append(x)
        except Exception as exc:  # noqa: BLE001
            requests_meta[series_id]["parse_error"] = f"{type(exc).__name__}:{exc}"
            return None, {"ok": False, "source": "fred_reconstruction", "requests": requests_meta, "failed_series": series_id}
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="date_utc", how="inner")
    for col in FRED_SERIES:
        merged = merged[merged[col] > 0]
    if len(merged) < 21:
        return None, {"ok": False, "source": "fred_reconstruction", "requests": requests_meta, "error": "LT_21_COMMON_DATES"}
    merged["value"] = (
        DXY_CONSTANT
        * merged["eurusd"].pow(-0.576)
        * merged["usdjpy"].pow(0.136)
        * merged["gbpusd"].pow(-0.119)
        * merged["usdcad"].pow(0.091)
        * merged["usdsek"].pow(0.042)
        * merged["usdchf"].pow(0.036)
    )
    out = merged[["date_utc", "value"]].copy()
    out["source"] = "ICE_WEIGHTED_DXY_RECONSTRUCTION_FROM_FRED_FX_FIXINGS"
    out["source_contract"] = "DXY_FORMULA_RECONSTRUCTION_VALIDATED_FALLBACK"
    out["available_after_utc"] = utc_iso()
    return out, {"ok": True, "source": "fred_reconstruction", "requests": requests_meta, "common_rows": int(len(out))}


def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["date_utc", "value", "source", "source_contract", "available_after_utc"])
    first = path.open("r", encoding="utf-8-sig", errors="replace").readline()
    sep = max([",", ";", "\t", "|"], key=first.count)
    df = pd.read_csv(path, sep=sep, low_memory=False)
    lower = {str(c).strip().lower(): c for c in df.columns}
    date_col = next((lower[x] for x in ["date_utc", "date", "timestamp"] if x in lower), None)
    value_col = next((lower[x] for x in ["value", "close", "dxy"] if x in lower), None)
    if date_col is None or value_col is None:
        raise ValueError(f"existing DXY schema invalid: {list(df.columns)}")
    out = pd.DataFrame({
        "date_utc": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.strftime("%Y-%m-%d"),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna().sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    for col, default in [
        ("source", "LEGACY_EXACT_DXY_HISTORY"),
        ("source_contract", "DXY_OR_ICE_USDX_FUTURES_SERIES"),
        ("available_after_utc", ""),
    ]:
        if col in lower:
            out[col] = df.loc[out.index, lower[col]].astype(str).values
        else:
            out[col] = default
    return out.reset_index(drop=True)


def quality_checks(incoming: pd.DataFrame, existing: pd.DataFrame, max_overlap_mape: float) -> Dict[str, Any]:
    values = pd.to_numeric(incoming["value"], errors="coerce")
    checks: Dict[str, Any] = {
        "rows": int(len(incoming)),
        "latest_date_utc": str(incoming.iloc[-1]["date_utc"]) if len(incoming) else None,
        "min_value": float(values.min()) if len(values) else None,
        "max_value": float(values.max()) if len(values) else None,
        "range_ok": bool(len(values) and values.between(60.0, 180.0).all()),
        "daily_return_ok": False,
        "overlap_rows": 0,
        "overlap_median_abs_pct": None,
        "overlap_ok": True,
    }
    returns = values.pct_change().abs().dropna()
    checks["daily_return_ok"] = bool(len(returns) and float(returns.max()) <= 0.12)
    if not existing.empty:
        overlap = incoming[["date_utc", "value"]].merge(
            existing[["date_utc", "value"]], on="date_utc", suffixes=("_new", "_old")
        )
        overlap = overlap[(overlap["value_old"] != 0) & overlap["value_new"].notna() & overlap["value_old"].notna()]
        checks["overlap_rows"] = int(len(overlap))
        if len(overlap) >= 10:
            diffs = ((overlap["value_new"] - overlap["value_old"]).abs() / overlap["value_old"].abs()).tolist()
            med = float(statistics.median(diffs))
            checks["overlap_median_abs_pct"] = med
            checks["overlap_ok"] = med <= max_overlap_mape
    checks["pass"] = bool(checks["range_ok"] and checks["daily_return_ok"] and checks["overlap_ok"])
    return checks


def merge_and_write(existing: pd.DataFrame, incoming: pd.DataFrame, out: Path, report_dir: Path) -> Dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        report_dir.mkdir(parents=True, exist_ok=True)
        backup = report_dir / f"dxy_pre_stage171h4_{utc_now().strftime('%Y%m%dT%H%M%SZ')}.csv"
        shutil.copy2(out, backup)
    combined = pd.concat([existing, incoming], ignore_index=True)
    combined["date_utc"] = pd.to_datetime(combined["date_utc"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    combined["value"] = pd.to_numeric(combined["value"], errors="coerce")
    combined = combined.dropna(subset=["date_utc", "value"]).sort_values("date_utc").drop_duplicates("date_utc", keep="last")
    fields = ["date_utc", "value", "source", "source_contract", "available_after_utc"]
    for col in fields:
        if col not in combined.columns:
            combined[col] = ""
    tmp = out.with_suffix(out.suffix + ".tmp")
    combined[fields].to_csv(tmp, index=False)
    tmp.replace(out)
    return {
        "rows": int(len(combined)),
        "latest_date_utc": str(combined.iloc[-1]["date_utc"]),
        "latest_value": float(combined.iloc[-1]["value"]),
        "backup": str(backup) if backup else None,
        "output": str(out),
        "sha256": sha256_file(out),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report-dir", default=DEFAULT_REPORT)
    ap.add_argument("--lookback-days", type=int, default=180)
    ap.add_argument("--timeout-seconds", type=int, default=40)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max-source-age-days", type=float, default=5.0)
    ap.add_argument("--max-overlap-mape", type=float, default=0.03)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = resolve(root, args.out)
    report_dir = resolve(root, args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    attempts: List[Dict[str, Any]] = []
    selected: Optional[pd.DataFrame] = None
    selected_name: Optional[str] = None
    quality: Optional[Dict[str, Any]] = None

    try:
        existing = load_existing(out)
    except Exception as exc:  # noqa: BLE001
        existing = pd.DataFrame(columns=["date_utc", "value", "source", "source_contract", "available_after_utc"])
        attempts.append({"source": "existing", "ok": False, "error": f"{type(exc).__name__}:{exc}"})

    end_date = generated.date()
    if not existing.empty:
        latest_existing = pd.to_datetime(existing["date_utc"], utc=True).max().date()
        start_date = min(latest_existing - dt.timedelta(days=60), end_date - dt.timedelta(days=args.lookback_days))
    else:
        start_date = end_date - dt.timedelta(days=args.lookback_days)

    fetchers = [
        ("yahoo_dx_y_nyb", lambda: fetch_yahoo(start_date, end_date, args.timeout_seconds, args.retries)),
        ("stooq_dx_f", lambda: fetch_stooq(start_date, end_date, args.timeout_seconds, args.retries)),
        ("fred_ice_formula_reconstruction", lambda: fetch_fred_reconstruction(args.timeout_seconds, args.retries)),
    ]
    for name, fn in fetchers:
        try:
            frame, meta = fn()
        except Exception as exc:  # noqa: BLE001
            frame, meta = None, {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
        meta["name"] = name
        if frame is not None:
            try:
                q = quality_checks(frame, existing, args.max_overlap_mape)
                meta["quality"] = q
                latest = pd.to_datetime(frame.iloc[-1]["date_utc"], utc=True)
                age_days = (pd.Timestamp(generated) - latest).total_seconds() / 86400.0
                meta["age_days"] = round(age_days, 3)
                meta["fresh"] = age_days <= args.max_source_age_days
                if q.get("pass") and meta["fresh"]:
                    selected = frame
                    selected_name = name
                    quality = q
                    attempts.append(meta)
                    break
            except Exception as exc:  # noqa: BLE001
                meta["quality_error"] = f"{type(exc).__name__}:{exc}"
        attempts.append(meta)

    output_meta: Dict[str, Any] = {}
    if selected is not None:
        output_meta = merge_and_write(existing, selected, out, report_dir)
        status = "STAGE171H4_EXACT_DXY_REFRESH_READY"
        decision = "USE_REFRESHED_EXACT_DXY_FOR_LOG_ONLY_H64L_FORWARD"
        ready = True
    else:
        status = "STAGE171H4_EXACT_DXY_REFRESH_BLOCKED"
        decision = "PRESERVE_EXISTING_DXY_BLOCK_FORWARD_IF_STALE"
        ready = False
        if out.exists():
            output_meta = {
                "output": str(out),
                "sha256": sha256_file(out),
                "preserved": True,
                "latest_date_utc": str(existing.iloc[-1]["date_utc"]) if not existing.empty else None,
            }

    summary = {
        "stage": STAGE,
        "generated_utc": utc_iso(generated),
        "status": status,
        "decision": decision,
        "ready": ready,
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "threshold_reoptimization_allowed": False,
        "selected_source": selected_name,
        "selected_quality": quality,
        "attempts": attempts,
        "output": output_meta,
    }
    (report_dir / "stage171h4_exact_dxy_downloader_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (report_dir / "stage171h4_decision.md").write_text(
        f"# Stage171H4 Exact DXY Downloader\n\nDecision: `{decision}`\n\nReady: `{ready}`\n\nSelected source: `{selected_name}`\n\nNo order/demo/live authorization.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
