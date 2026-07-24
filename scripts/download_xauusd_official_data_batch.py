#!/usr/bin/env python3
"""Download XAUUSD official macro/event/fundamental sources into one inbox.

Stage116C runner patch:
- operator-visible progress per section and per file
- elapsed time, file size, status and error tail
- JSONL run log plus summary JSON
- no API keys are hardcoded, printed, or written unmasked
- economic-events are handled as an official backbone: FRED releases, FOMC,
  Treasury auctions, and actual macro datasets from BLS/BEA/Census.

No order / MT5 / EA / broker action is performed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import zipfile
from urllib.parse import urlencode
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "XAUUSD_OFFICIAL_DATA_DOWNLOAD_BATCH_STAGE116C_EXISTING_PIPELINE_EVENT_HISTORY_EXTENSION"
DEFAULT_INBOX = Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"
DEFAULT_FROM_YEAR = 2009
DEFAULT_TO_YEAR = 2026
FRED_SERIES = [
    "DFII10", "VIXCLS", "DTWEXBGS", "DGS10", "DGS2", "T10YIE", "T5YIE", "DFF", "WALCL", "BAMLH0A0HYM2",
]
BLS_SERIES = ["CUSR0000SA0", "CUSR0000SA0L1E", "CES0000000001", "LNS14000000", "LNS11300000", "CES0500000003"]
# Core scheduled releases used by the bounded historical blackout replay.
# IDs are official FRED release identifiers.
FRED_CORE_RELEASES: Dict[int, Dict[str, str]] = {
    10: {"release_name": "Consumer Price Index", "source": "BLS", "category": "BLS_CPI"},
    11: {"release_name": "Employment Cost Index", "source": "BLS", "category": "BLS_ECI"},
    46: {"release_name": "Producer Price Index", "source": "BLS", "category": "BLS_PPI"},
    50: {"release_name": "Employment Situation", "source": "BLS", "category": "BLS_EMPLOYMENT_SITUATION"},
    192: {"release_name": "Job Openings and Labor Turnover Survey", "source": "BLS", "category": "BLS_JOLTS"},
    53: {"release_name": "Gross Domestic Product", "source": "BEA", "category": "BEA_GDP"},
    54: {"release_name": "Personal Income and Outlays", "source": "BEA", "category": "BEA_PERSONAL_INCOME_OUTLAYS"},
}
FRED_CORE_RELEASE_IDS = tuple(FRED_CORE_RELEASES)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/149 Safari/537.36"
API_ENV_KEYS = ["FRED_API_KEY", "BLS_API_KEY", "BEA_API_KEY", "CENSUS_API_KEY"]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env_present(name: str) -> bool:
    value = os.environ.get(name, "").strip()
    return bool(value and not value.startswith("PASTE_") and not value.startswith("PUT_"))


def load_env_file(path: Path, *, override: bool = False) -> List[str]:
    """Load KEY=VALUE lines from a local gitignored env file without printing values.

    Supported forms:
    - CENSUS_API_KEY=...
    - export CENSUS_API_KEY=...

    Existing environment variables are preserved unless override=True.
    """
    loaded: List[str] = []
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in API_ENV_KEYS:
            continue
        value = value.strip().strip('\"').strip("'")
        if not value:
            continue
        if override or not os.environ.get(key):
            os.environ[key] = value
            loaded.append(key)
    return loaded


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def scrub(text: str) -> str:
    """Mask any currently exported API key from user-visible/log strings."""
    out = text
    for key_name in API_ENV_KEYS:
        key = os.environ.get(key_name)
        if key:
            out = out.replace(key, f"${{{key_name}}}")
    return out


def size_text(n: int) -> str:
    value = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{n}B"


def content_issue(path: Path) -> Optional[str]:
    if not path.exists() or path.stat().st_size == 0:
        return "EMPTY_OR_MISSING"
    suffix = path.suffix.lower()
    try:
        head = path.read_bytes()[:4096].lower()
    except Exception:
        head = b""
    if suffix in {".csv", ".json", ".html", ".txt"}:
        # These may legitimately be text. Only flag obvious HTML for non-html outputs.
        if suffix != ".html" and (b"<html" in head or b"<!doctype html" in head):
            return "HTML_OR_BLOCKED"
    if suffix in {".xlsx", ".pdf", ".zip"}:
        if b"<html" in head or b"<!doctype html" in head or b"access denied" in head or b"forbidden" in head:
            return "HTML_OR_BLOCKED"
    if suffix == ".zip" and path.exists() and not zipfile.is_zipfile(path):
        return "NOT_A_VALID_ZIP"
    if path.name in {"fred_releases_dates_2009_present.json", "fred_release_dates_2009_2026.json"}:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("release_dates") if isinstance(payload, dict) else None
            declared = int(payload.get("count", 0)) if isinstance(payload, dict) else 0
            if not isinstance(rows, list) or not rows:
                return "FRED_RELEASE_DATES_EMPTY_OR_INVALID"
            if declared > len(rows):
                return "FRED_RELEASE_DATES_TRUNCATED"
            if not payload.get("pagination_complete", False):
                return "FRED_RELEASE_DATES_NOT_CANONICAL_PAGINATED"
        except Exception:
            return "FRED_RELEASE_DATES_INVALID_JSON"
    if path.name == "fred_core_release_dates_2009_present.json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("release_dates") if isinstance(payload, dict) else None
            ids = {int(x) for x in payload.get("release_ids", [])} if isinstance(payload, dict) else set()
            if payload.get("collection_mode") != "CORE_RELEASE_ID_ENDPOINTS":
                return "FRED_CORE_RELEASE_DATES_WRONG_COLLECTION_MODE"
            if ids != set(FRED_CORE_RELEASE_IDS):
                return "FRED_CORE_RELEASE_DATES_RELEASE_ID_COVERAGE"
            if not isinstance(rows, list) or not rows:
                return "FRED_CORE_RELEASE_DATES_EMPTY_OR_INVALID"
            observed = {int(row.get("release_id")) for row in rows if isinstance(row, dict) and row.get("release_id") is not None}
            if observed != set(FRED_CORE_RELEASE_IDS):
                return "FRED_CORE_RELEASE_DATES_MISSING_RELEASE_ROWS"
            dates = [str(row.get("date") or "") for row in rows if isinstance(row, dict)]
            if not any(date.startswith("2015-") for date in dates):
                return "FRED_CORE_RELEASE_DATES_NO_2015_HISTORY"
            if not payload.get("collection_complete", False):
                return "FRED_CORE_RELEASE_DATES_NOT_COMPLETE"
        except Exception:
            return "FRED_CORE_RELEASE_DATES_INVALID_JSON"
    if path.name == "stooq_dx_f_dxy_daily.csv":
        try:
            lines = [x for x in path.read_text(errors="ignore").splitlines() if x.strip()]
        except Exception:
            lines = []
        if len(lines) < 50:
            return "DXY_DIRECT_TOO_SHORT_OR_BLOCKED"
    return None



def existing_valid_skip_result(
    out: Path,
    *,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Optional[Dict[str, object]]:
    """Return a skip result when an existing output is already valid.

    This makes the downloader persistent/incremental by default:
    - existing non-empty files that pass content_issue() are not downloaded again
    - --force-refresh disables the skip
    - --refresh-stale-hours N refreshes valid files older than N hours
    """
    if force_refresh:
        return None
    if not out.exists() or out.stat().st_size <= 0:
        return None
    issue = content_issue(out)
    if issue is not None:
        return None
    age_hours = max(0.0, (time.time() - out.stat().st_mtime) / 3600.0)
    if refresh_stale_hours is not None and age_hours > refresh_stale_hours:
        return None
    return {
        "kind": "existing_file",
        "output": str(out),
        "status": "SKIPPED_EXISTING_VALID",
        "size_bytes": out.stat().st_size,
        "elapsed_sec": 0.0,
        "age_hours": round(age_hours, 2),
    }


OK_STATUSES = {"OK", "DRY_RUN", "SKIPPED_EXISTING_VALID"}

def write_jsonl(log_path: Path, row: Dict[str, object]) -> None:
    ensure_dir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def console(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(message, flush=True)


def curl_download(
    url: str,
    out: Path,
    *,
    globoff: bool = False,
    referer: Optional[str] = None,
    user_agent: bool = False,
    dry_run: bool = False,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Dict[str, object]:
    ensure_dir(out.parent)
    if not dry_run:
        skipped = existing_valid_skip_result(out, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)
        if skipped is not None:
            skipped["url"] = scrub(url)
            return skipped
    cmd: List[str] = ["curl"]
    if globoff:
        cmd.append("-g")
    cmd += ["-L", "--retry", "3", "--retry-delay", "3"]
    if user_agent:
        cmd += ["-A", UA]
    if referer:
        cmd += ["-e", referer]
    cmd += [url, "-o", str(out)]
    started = time.time()
    if dry_run:
        return {
            "kind": "curl",
            "output": str(out),
            "status": "DRY_RUN",
            "url": scrub(url),
            "elapsed_sec": 0.0,
            "size_bytes": 0,
        }
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    elapsed = round(time.time() - started, 2)
    size = out.stat().st_size if out.exists() else 0
    issue = content_issue(out)
    status = "OK" if cp.returncode == 0 and size > 0 and issue is None else (issue or "FAILED_OR_EMPTY")
    return {
        "kind": "curl",
        "output": str(out),
        "returncode": cp.returncode,
        "status": status,
        "size_bytes": size,
        "elapsed_sec": elapsed,
        "stderr_tail": scrub(cp.stderr[-500:]),
        "url": scrub(url),
    }


def download_fred_release_dates_paginated(
    out: Path,
    *,
    api_key: str,
    realtime_start: str = "2009-01-01",
    realtime_end: str = "9999-12-31",
    page_size: int = 1000,
    dry_run: bool = False,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Dict[str, object]:
    """Download the complete FRED releases/dates collection with pagination."""
    ensure_dir(out.parent)
    if not dry_run:
        skipped = existing_valid_skip_result(out, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)
        if skipped is not None:
            skipped["kind"] = "fred_release_dates_paginated"
            return skipped
    if dry_run:
        return {"kind": "fred_release_dates_paginated", "output": str(out), "status": "DRY_RUN", "size_bytes": 0, "elapsed_sec": 0.0, "page_size": page_size}
    started = time.time()
    all_rows: List[Dict[str, object]] = []
    seen: set[Tuple[str, str, str]] = set()
    offset = 0
    declared_count: Optional[int] = None
    page_no = 0
    tmp = out.with_suffix(out.suffix + ".page.tmp")
    try:
        while True:
            page_no += 1
            params = {
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": realtime_start,
                "realtime_end": realtime_end,
                "include_release_dates_with_no_data": "true",
                "limit": str(page_size),
                "offset": str(offset),
                "sort_order": "asc",
            }
            url = "https://api.stlouisfed.org/fred/releases/dates?" + urlencode(params)
            cp = subprocess.run(["curl", "-fsSL", "--retry", "3", "--retry-delay", "3", url, "-o", str(tmp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if cp.returncode != 0:
                raise RuntimeError(f"FRED page offset={offset} curl exit={cp.returncode}: {scrub(cp.stderr[-500:])}")
            payload = json.loads(tmp.read_text(encoding="utf-8"))
            rows = payload.get("release_dates")
            if not isinstance(rows, list):
                raise RuntimeError(f"FRED page offset={offset} missing release_dates list")
            if declared_count is None:
                declared_count = int(payload.get("count", len(rows)))
            added = 0
            for item in rows:
                if not isinstance(item, dict):
                    continue
                key = (str(item.get("release_id") or item.get("id") or ""), str(item.get("date") or item.get("release_date") or ""), str(item.get("release_name") or item.get("name") or ""))
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(item)
                added += 1
            console(f"        FRED release-calendar page {page_no}: offset={offset} received={len(rows)} added={added} total={len(all_rows)}/{declared_count}", quiet=False)
            offset += len(rows)
            if not rows or len(rows) < page_size or offset >= int(declared_count):
                break
            if page_no > 200:
                raise RuntimeError("FRED pagination exceeded 200 pages")
        if declared_count is None or len(all_rows) < declared_count:
            raise RuntimeError(f"FRED pagination incomplete: collected={len(all_rows)} declared_count={declared_count}")
        canonical = {"realtime_start": realtime_start, "realtime_end": realtime_end, "order_by": "release_id", "sort_order": "asc", "count": len(all_rows), "offset": 0, "limit": len(all_rows), "pagination_complete": True, "pages_downloaded": page_no, "release_dates": all_rows}
        out.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        issue = content_issue(out)
        if issue is not None:
            raise RuntimeError(f"canonical FRED output validation failed: {issue}")
        return {"kind": "fred_release_dates_paginated", "output": str(out), "status": "OK", "size_bytes": out.stat().st_size, "elapsed_sec": round(time.time() - started, 2), "pages_downloaded": page_no, "release_dates": len(all_rows), "declared_count": declared_count}
    finally:
        if tmp.exists():
            tmp.unlink()



def download_fred_core_release_dates(
    out: Path,
    *,
    api_key: str,
    from_year: int = 2009,
    to_year: int = DEFAULT_TO_YEAR,
    page_size: int = 10000,
    dry_run: bool = False,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Dict[str, object]:
    """Download complete release-date histories for the seven locked core releases.

    The global ``fred/releases/dates`` endpoint is intentionally not used here:
    its real-time window can leave a current-year-only cache that looks paginated.
    ``fred/release/dates`` is queried once per official release id and returns the
    complete release history for that release.
    """
    ensure_dir(out.parent)
    if not dry_run:
        skipped = existing_valid_skip_result(
            out,
            force_refresh=force_refresh,
            refresh_stale_hours=refresh_stale_hours,
        )
        if skipped is not None:
            skipped["kind"] = "fred_core_release_dates"
            return skipped
    if dry_run:
        return {
            "kind": "fred_core_release_dates",
            "output": str(out),
            "status": "DRY_RUN",
            "size_bytes": 0,
            "elapsed_sec": 0.0,
            "release_ids": list(FRED_CORE_RELEASE_IDS),
        }

    started = time.time()
    all_rows: List[Dict[str, object]] = []
    release_audit: List[Dict[str, object]] = []
    tmp = out.with_suffix(out.suffix + ".release.tmp")
    try:
        for release_index, release_id in enumerate(FRED_CORE_RELEASE_IDS, start=1):
            spec = FRED_CORE_RELEASES[release_id]
            offset = 0
            page_no = 0
            declared_count: Optional[int] = None
            release_rows: List[Dict[str, object]] = []
            while True:
                page_no += 1
                params = {
                    "api_key": api_key,
                    "file_type": "json",
                    "release_id": str(release_id),
                    "realtime_start": "1776-07-04",
                    "realtime_end": "9999-12-31",
                    "include_release_dates_with_no_data": "true",
                    "limit": str(page_size),
                    "offset": str(offset),
                    "sort_order": "asc",
                }
                url = "https://api.stlouisfed.org/fred/release/dates?" + urlencode(params)
                cp = subprocess.run(
                    ["curl", "-fsSL", "--retry", "3", "--retry-delay", "3", url, "-o", str(tmp)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if cp.returncode != 0:
                    raise RuntimeError(
                        f"FRED core release_id={release_id} offset={offset} "
                        f"curl exit={cp.returncode}: {scrub(cp.stderr[-500:])}"
                    )
                payload = json.loads(tmp.read_text(encoding="utf-8"))
                rows = payload.get("release_dates")
                if not isinstance(rows, list):
                    raise RuntimeError(
                        f"FRED core release_id={release_id} offset={offset} missing release_dates list"
                    )
                if declared_count is None:
                    declared_count = int(payload.get("count", len(rows)))
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    date = str(item.get("date") or item.get("release_date") or "")
                    if not date:
                        continue
                    try:
                        year = int(date[:4])
                    except Exception:
                        continue
                    if year < from_year or year > to_year:
                        continue
                    release_rows.append({
                        "release_id": release_id,
                        "release_name": spec["release_name"],
                        "source": spec["source"],
                        "category": spec["category"],
                        "date": date,
                    })
                console(
                    f"        FRED core {release_index}/{len(FRED_CORE_RELEASE_IDS)} "
                    f"release_id={release_id} {spec['release_name']}: "
                    f"page={page_no} offset={offset} received={len(rows)} "
                    f"kept={len(release_rows)} declared={declared_count}",
                    quiet=False,
                )
                offset += len(rows)
                if not rows or len(rows) < page_size or offset >= int(declared_count):
                    break
                if page_no > 20:
                    raise RuntimeError(f"FRED core release_id={release_id} pagination exceeded 20 pages")
            if declared_count is None or offset < declared_count:
                raise RuntimeError(
                    f"FRED core release_id={release_id} pagination incomplete: "
                    f"received={offset} declared_count={declared_count}"
                )
            if not release_rows:
                raise RuntimeError(
                    f"FRED core release_id={release_id} has no dates in {from_year}-{to_year}"
                )
            all_rows.extend(release_rows)
            release_audit.append({
                "release_id": release_id,
                "release_name": spec["release_name"],
                "source": spec["source"],
                "category": spec["category"],
                "api_declared_count": declared_count,
                "kept_count": len(release_rows),
                "first_date": min(str(row["date"]) for row in release_rows),
                "last_date": max(str(row["date"]) for row in release_rows),
                "pages_downloaded": page_no,
            })

        unique = {
            (int(row["release_id"]), str(row["date"])): row
            for row in all_rows
        }
        merged = [unique[key] for key in sorted(unique, key=lambda x: (x[1], x[0]))]
        canonical = {
            "collection_mode": "CORE_RELEASE_ID_ENDPOINTS",
            "endpoint": "https://api.stlouisfed.org/fred/release/dates",
            "from_year": from_year,
            "to_year": to_year,
            "release_ids": list(FRED_CORE_RELEASE_IDS),
            "release_specs": FRED_CORE_RELEASES,
            "collection_complete": True,
            "count": len(merged),
            "release_audit": release_audit,
            "release_dates": merged,
        }
        out.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        issue = content_issue(out)
        if issue is not None:
            raise RuntimeError(f"canonical FRED core output validation failed: {issue}")
        return {
            "kind": "fred_core_release_dates",
            "output": str(out),
            "status": "OK",
            "size_bytes": out.stat().st_size,
            "elapsed_sec": round(time.time() - started, 2),
            "release_ids": list(FRED_CORE_RELEASE_IDS),
            "release_dates": len(merged),
            "release_audit": release_audit,
        }
    finally:
        if tmp.exists():
            tmp.unlink()

def post_bls(
    out: Path,
    *,
    start_year: int = DEFAULT_FROM_YEAR,
    end_year: int = DEFAULT_TO_YEAR,
    dry_run: bool = False,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Dict[str, object]:
    ensure_dir(out.parent)
    if not dry_run:
        skipped = existing_valid_skip_result(out, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)
        if skipped is not None:
            return skipped
    payload: Dict[str, object] = {
        "seriesid": BLS_SERIES,
        "startyear": str(max(int(start_year), int(end_year) - 9)),
        "endyear": str(end_year),
    }
    if env_present("BLS_API_KEY"):
        payload["startyear"] = str(start_year)
        payload["registrationkey"] = os.environ["BLS_API_KEY"]
    body = json.dumps(payload)
    safe_payload = json.loads(scrub(body))
    started = time.time()
    if dry_run:
        return {"kind": "bls_post", "output": str(out), "status": "DRY_RUN", "payload": safe_payload, "elapsed_sec": 0.0, "size_bytes": 0}
    cmd = [
        "curl", "-L", "--retry", "3", "--retry-delay", "3", "-H", "Content-Type: application/json", "-X", "POST", "-d", body,
        "https://api.bls.gov/publicAPI/v2/timeseries/data/", "-o", str(out),
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    size = out.stat().st_size if out.exists() else 0
    issue = content_issue(out)
    status = "OK" if cp.returncode == 0 and size > 0 and issue is None else (issue or "FAILED_OR_EMPTY")
    return {
        "kind": "bls_post",
        "output": str(out),
        "returncode": cp.returncode,
        "status": status,
        "size_bytes": size,
        "elapsed_sec": round(time.time() - started, 2),
        "stderr_tail": scrub(cp.stderr[-500:]),
        "payload": safe_payload,
    }


def marker_result(
    path: Path,
    text: str,
    *,
    dry_run: bool = False,
    force_refresh: bool = False,
    refresh_stale_hours: Optional[float] = None,
) -> Dict[str, object]:
    ensure_dir(path.parent)
    if not dry_run:
        skipped = existing_valid_skip_result(path, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)
        if skipped is not None:
            return skipped
        path.write_text(text, encoding="utf-8")
    return {"kind": "marker", "output": str(path), "status": "DRY_RUN" if dry_run else "OK", "size_bytes": 0 if dry_run else path.stat().st_size, "elapsed_sec": 0.0}


DownloadTask = Tuple[str, callable]


def run_section(
    *,
    section_no: int,
    total_sections: int,
    name: str,
    tasks: Sequence[Tuple[str, callable]],
    log_path: Path,
    quiet: bool,
    verbose_files: bool,
) -> List[Dict[str, object]]:
    started = time.time()
    console(f"[{section_no:02d}/{total_sections:02d} START] {name} | items={len(tasks)} | {utc_now()}", quiet=quiet)
    write_jsonl(log_path, {"event": "section_start", "section_no": section_no, "total_sections": total_sections, "name": name, "items": len(tasks), "utc": utc_now()})
    results: List[Dict[str, object]] = []
    for idx, (label, fn) in enumerate(tasks, start=1):
        item_started = time.time()
        try:
            res = fn()
        except Exception as exc:  # keep batch running; report clearly.
            res = {"label": label, "status": "EXCEPTION", "error": repr(exc), "elapsed_sec": round(time.time() - item_started, 2), "size_bytes": 0}
        res.setdefault("label", label)
        res.setdefault("elapsed_sec", round(time.time() - item_started, 2))
        results.append(res)
        write_jsonl(log_path, {"event": "item_result", "section_no": section_no, "section": name, "item_no": idx, "item_total": len(tasks), **res, "utc": utc_now()})
        if verbose_files:
            out = Path(str(res.get("output", ""))).name if res.get("output") else label
            console(f"    [{idx:03d}/{len(tasks):03d}] {res.get('status')} {out} {size_text(int(res.get('size_bytes') or 0))} {res.get('elapsed_sec')}s", quiet=quiet)
    ok = sum(1 for r in results if str(r.get("status")) in OK_STATUSES)
    warn = len(results) - ok
    elapsed = round(time.time() - started, 2)
    console(f"[{section_no:02d}/{total_sections:02d} DONE ] {name} | ok={ok} warn/fail={warn} | elapsed={elapsed}s", quiet=quiet)
    write_jsonl(log_path, {"event": "section_done", "section_no": section_no, "name": name, "ok": ok, "warn_or_fail": warn, "elapsed_sec": elapsed, "utc": utc_now()})
    return results


def build_sections(
    inbox: Path,
    years: List[int],
    *,
    include_cot_xls: bool,
    skip_wgc_direct: bool,
    dry_run: bool,
    force_refresh: bool,
    refresh_stale_hours: Optional[float],
    event_core_only: bool = False,
) -> List[Tuple[str, Sequence[Tuple[str, callable]]]]:
    sections: List[Tuple[str, Sequence[Tuple[str, callable]]]] = []

    sections.append((
        "FRED macro direct CSVs",
        [(sid, lambda sid=sid: curl_download(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", inbox / "fred_macro" / f"{sid}.csv", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)) for sid in FRED_SERIES],
    ))

    sections.append((
        "DXY direct candidate; DTWEXBGS remains official fallback",
        [("stooq_dx_f_dxy_daily.csv", lambda: curl_download("https://stooq.com/q/d/l/?s=dx.f&i=d", inbox / "macro_misc" / "dxy" / "stooq_dx_f_dxy_daily.csv", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours))],
    ))

    if env_present("FRED_API_KEY"):
        key = os.environ["FRED_API_KEY"]
        fred_tasks = [
            (
                "fred_core_release_dates_2009_present.json",
                lambda key=key: download_fred_core_release_dates(
                    inbox / "events" / "fred" / "fred_core_release_dates_2009_present.json",
                    api_key=key,
                    from_year=min(years),
                    to_year=max(years),
                    dry_run=dry_run,
                    force_refresh=force_refresh,
                    refresh_stale_hours=refresh_stale_hours,
                ),
            )
        ]
        if not event_core_only:
            fred_tasks.append((
                "fred_releases_dates_2009_present.json",
                lambda key=key: download_fred_release_dates_paginated(
                    inbox / "events" / "fred" / "fred_releases_dates_2009_present.json",
                    api_key=key,
                    realtime_start="2009-01-01",
                    realtime_end="9999-12-31",
                    dry_run=dry_run,
                    force_refresh=force_refresh,
                    refresh_stale_hours=refresh_stale_hours,
                ),
            ))
    else:
        fred_tasks = [("missing_FRED_API_KEY", lambda: {"output": "events/fred/fred_core_release_dates_2009_present.json", "status": "SKIPPED_MISSING_FRED_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("Official economic-events backbone: FRED release dates", fred_tasks))

    sections.append((
        "CFTC COT disaggregated futures TXT zips",
        [(f"fut_disagg_txt_{y}.zip", lambda y=y: curl_download(f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{y}.zip", inbox / "cot" / "cftc" / f"fut_disagg_txt_{y}.zip", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)) for y in years],
    ))

    if include_cot_xls:
        sections.append((
            "Optional CFTC COT disaggregated futures XLS zips",
            [(f"fut_disagg_xls_{y}.zip", lambda y=y: curl_download(f"https://www.cftc.gov/files/dea/history/fut_disagg_xls_{y}.zip", inbox / "cot" / "cftc" / f"fut_disagg_xls_{y}.zip", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)) for y in years],
        ))

    sections.append((
        "BLS CPI / labor / payroll JSON",
        [(
            f"bls_core_macro_{min(years)}_{max(years)}.json",
            lambda: post_bls(
                inbox / "events" / "bls" / f"bls_core_macro_{min(years)}_{max(years)}.json",
                start_year=min(years), end_year=max(years), dry_run=dry_run,
                force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours,
            ),
        )],
    ))

    if env_present("BEA_API_KEY"):
        key = os.environ["BEA_API_KEY"]
        bea_urls = {
            "bea_dataset_list.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATASETLIST&ResultFormat=JSON",
            "bea_nipa_table_names.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETPARAMETERVALUES&datasetname=NIPA&ParameterName=TableName&ResultFormat=JSON",
            "bea_nipa_T10101_gdp_q_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T10101&Frequency=Q&Year=ALL&ResultFormat=JSON",
            "bea_nipa_T20600_personal_income_m_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T20600&Frequency=M&Year=ALL&ResultFormat=JSON",
            "bea_nipa_T20804_pce_price_indexes_m_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T20804&Frequency=M&Year=ALL&ResultFormat=JSON",
        }
        bea_tasks = [(fn, lambda fn=fn, url=url: curl_download(url, inbox / "events" / "bea" / fn, dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)) for fn, url in bea_urls.items()]
    else:
        bea_tasks = [("missing_BEA_API_KEY", lambda: {"output": "events/bea/*.json", "status": "SKIPPED_MISSING_BEA_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("BEA GDP / PCE / personal income JSON", bea_tasks))

    census_var_tasks = [(f"census_eits_{ds}_variables.json", lambda ds=ds: curl_download(f"https://api.census.gov/data/timeseries/eits/{ds}/variables.json", inbox / "events" / "census" / f"census_eits_{ds}_variables.json", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)) for ds in ["marts", "ftd", "resconst", "ressales"]]
    sections.append(("Census EITS metadata variables", census_var_tasks))

    if env_present("CENSUS_API_KEY"):
        key = os.environ["CENSUS_API_KEY"]
        params = {
            "marts": "data_type_code,time_slot_id,seasonally_adj,category_code,cell_value,error_data",
            "ftd": "data_type_code,time_slot_id,seasonally_adj,category_code,cell_value,error_data",
            "resconst": "data_type_code,time_slot_id,seasonally_adj,category_code,cell_value,error_data",
            "ressales": "data_type_code,time_slot_id,seasonally_adj,category_code,cell_value,error_data",
        }
        census_data_tasks = []
        for y in years:
            for ds, get in params.items():
                census_data_tasks.append((f"census_{ds}_{y}.json", lambda y=y, ds=ds, get=get, key=key: curl_download(f"https://api.census.gov/data/timeseries/eits/{ds}?get={get}&time={y}&key={key}", inbox / "events" / "census" / f"census_{ds}_{y}.json", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)))
    else:
        census_data_tasks = [("missing_CENSUS_API_KEY", lambda: {"output": "events/census/census_*_YYYY.json", "status": "SKIPPED_MISSING_CENSUS_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("Census EITS yearly datasets", census_data_tasks))

    fomc_tasks: List[Tuple[str, callable]] = [
        (
            "fomc_calendars_current.html",
            lambda: curl_download(
                "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                inbox / "events" / "fomc" / "fomc_calendars_current.html",
                user_agent=True, dry_run=dry_run, force_refresh=force_refresh,
                refresh_stale_hours=refresh_stale_hours,
            ),
        )
    ]
    for year in years:
        if year <= 2020:
            fomc_tasks.append((
                f"fomc_historical_{year}.html",
                lambda year=year: curl_download(
                    f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm",
                    inbox / "events" / "fomc" / f"fomc_historical_{year}.html",
                    user_agent=True, dry_run=dry_run, force_refresh=force_refresh,
                    refresh_stale_hours=refresh_stale_hours,
                ),
            ))
    sections.append(("Official economic-events backbone: FOMC current + historical pages", fomc_tasks))

    sections.append((
        "Official economic-events backbone: Treasury auctions",
        [
            ("treasury_upcoming_auctions.csv", lambda: curl_download("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/upcoming_auctions?format=csv&page[size]=1000", inbox / "events" / "treasury" / "treasury_upcoming_auctions.csv", globoff=True, dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
            ("treasury_auctions_query_recent.csv", lambda: curl_download("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?format=csv&page[size]=10000&sort=-auction_date", inbox / "events" / "treasury" / "treasury_auctions_query_recent.csv", globoff=True, dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
        ],
    ))

    if not skip_wgc_direct:
        wgc_tasks = [
            ("ETF_Flows_2026-06-02_1536.xlsx", lambda: curl_download("https://www.gold.org/download/file/20888/ETF_Flows_2026-06-02_1536.xlsx", inbox / "gold_etf" / "wgc" / "ETF_Flows_2026-06-02_1536.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
            ("ETF-Flows-Data-Methodology.pdf", lambda: curl_download("https://www.gold.org/download/file/16223/ETF-Flows-Data-Methodology.pdf", inbox / "gold_etf" / "wgc" / "ETF-Flows-Data-Methodology.pdf", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
            ("World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", lambda: curl_download("https://www.gold.org/download/file/7739/World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", inbox / "central_bank_gold" / "World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
            ("Changes_latest_as_of_Jun2026_IFS.xlsx", lambda: curl_download("https://www.gold.org/download/file/7741/Changes_latest_as_of_Jun2026_IFS.xlsx", inbox / "central_bank_gold" / "Changes_latest_as_of_Jun2026_IFS.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
            ("Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", lambda: curl_download("https://www.gold.org/download/file/8052/Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", inbox / "central_bank_gold" / "Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours)),
        ]
    else:
        wgc_tasks = [("WGC manual preferred", lambda: {"output": "gold_etf/wgc + central_bank_gold", "status": "SKIPPED_WGC_DIRECT_BY_USER", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("WGC ETF and central-bank direct attempts; browser fallback if blocked", wgc_tasks))

    sections.append(("SPDR GLD historical archive", [("spdr_gld_historical_archive.xlsx", lambda: curl_download("https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld", inbox / "gld" / "spdr" / "spdr_gld_historical_archive.xlsx", dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours))]))

    gold_price_text = "Manual: https://www.gold.org/goldhub/data/gold-prices -> Downloads -> Download xlsx Gold price averages in a range of currencies since 1978\n"
    sections.append(("WGC gold price averages manual marker", [("README_MANUAL_GOLD_PRICE_DOWNLOAD.txt", lambda: marker_result(inbox / "gold_price" / "wgc" / "README_MANUAL_GOLD_PRICE_DOWNLOAD.txt", gold_price_text, dry_run=dry_run, force_refresh=force_refresh, refresh_stale_hours=refresh_stale_hours))]))

    if event_core_only:
        allowed = {
            "Official economic-events backbone: FRED release dates",
            "BLS CPI / labor / payroll JSON",
            "BEA GDP / PCE / personal income JSON",
            "Official economic-events backbone: FOMC current + historical pages",
        }
        sections = [section for section in sections if section[0] in allowed]
    return sections


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--inbox", default=str(DEFAULT_INBOX))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-refresh", action="store_true", help="Download again even when a valid output file already exists")
    ap.add_argument("--refresh-stale-hours", type=float, default=None, help="Refresh valid existing files older than this many hours; omit to keep valid files")
    ap.add_argument("--include-cot-xls", action="store_true")
    ap.add_argument("--event-core-only", action="store_true", help="Download only FRED release dates, BLS, BEA and FOMC inputs needed by historical event context")
    ap.add_argument("--skip-wgc-direct", action="store_true", help="Skip WGC direct attempts if browser/manual download is preferred")
    ap.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR)
    ap.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-file-progress", action="store_true", help="Show only section start/done messages")
    ap.add_argument("--env-file", action="append", default=[], help="Local env file with API keys; values are not printed or committed")
    ap.add_argument("--no-default-env-files", action="store_true", help="Do not auto-load ~/.xauusd_official_data.env or inbox/.xauusd_official_data.env")
    args = ap.parse_args(argv)

    inbox = Path(args.inbox).expanduser()
    for rel in ["fred_macro", "macro_misc/dxy", "cot/cftc", "gold_etf/wgc", "central_bank_gold", "gld/spdr", "gold_price/wgc", "events/fred", "events/bls", "events/bea", "events/census", "events/fomc", "events/treasury", "docs_or_reference"]:
        ensure_dir(inbox / rel)

    env_files_loaded: List[str] = []
    env_file_candidates: List[Path] = []
    if not args.no_default_env_files:
        env_file_candidates.extend([Path.home() / ".xauusd_official_data.env", inbox / ".xauusd_official_data.env"])
    env_file_candidates.extend([Path(x).expanduser() for x in args.env_file])
    for env_path in env_file_candidates:
        loaded_keys = load_env_file(env_path)
        if loaded_keys:
            env_files_loaded.append(str(env_path))

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = inbox / "_logs"
    ensure_dir(log_dir)
    log_jsonl = log_dir / f"download_xauusd_official_data_batch_{run_id}.jsonl"
    summary_json = log_dir / "download_xauusd_official_data_batch_latest_summary.json"
    years = list(range(args.from_year, args.to_year + 1))

    console(f"{STAGE} | started={utc_now()} | inbox={inbox} | years={args.from_year}-{args.to_year}", quiet=args.quiet)
    console(f"API key presence: " + ", ".join([f"{k}={'yes' if env_present(k) else 'no'}" for k in API_ENV_KEYS]), quiet=args.quiet)
    if env_files_loaded:
        console("Env files loaded: " + ", ".join(env_files_loaded), quiet=args.quiet)
    console(f"Log: {log_jsonl}", quiet=args.quiet)

    started = time.time()
    sections = build_sections(
        inbox,
        years,
        include_cot_xls=args.include_cot_xls,
        skip_wgc_direct=args.skip_wgc_direct,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
        refresh_stale_hours=args.refresh_stale_hours,
        event_core_only=args.event_core_only,
    )
    all_results: List[Dict[str, object]] = []
    total_sections = len(sections)
    for section_no, (name, tasks) in enumerate(sections, start=1):
        all_results.extend(run_section(
            section_no=section_no,
            total_sections=total_sections,
            name=name,
            tasks=tasks,
            log_path=log_jsonl,
            quiet=args.quiet,
            verbose_files=not args.no_file_progress,
        ))

    ok_count = sum(1 for r in all_results if str(r.get("status")) in OK_STATUSES)
    warning_count = len(all_results) - ok_count
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "inbox": str(inbox),
        "dry_run": args.dry_run,
        "from_year": args.from_year,
        "to_year": args.to_year,
        "include_cot_xls": args.include_cot_xls,
        "skip_wgc_direct": args.skip_wgc_direct,
        "force_refresh": args.force_refresh,
        "refresh_stale_hours": args.refresh_stale_hours,
        "skipped_existing_valid_count": sum(1 for r in all_results if str(r.get("status")) == "SKIPPED_EXISTING_VALID"),
        "elapsed_sec": round(time.time() - started, 2),
        "status": "DOWNLOAD_BATCH_COMPLETE" if warning_count == 0 else "DOWNLOAD_BATCH_COMPLETE_WITH_WARNINGS",
        "ok_or_dry_run_count": ok_count,
        "warning_or_fail_count": warning_count,
        "api_key_presence": {k: env_present(k) for k in API_ENV_KEYS},
        "env_files_loaded": env_files_loaded,
        "event_core_only": args.event_core_only,
        "economic_events_policy": "Use official event backbone: FRED release dates, FOMC calendar, Treasury auctions, and BLS/BEA/Census actual macro datasets. Do not depend on old commercial economic-calendar feeds.",
        "results": all_results,
        "log_jsonl": str(log_jsonl),
        "summary_json": str(summary_json),
    }
    if not args.dry_run:
        summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    console(f"{STAGE} | finished={utc_now()} | status={summary['status']} | ok={ok_count} warn/fail={warning_count} | elapsed={summary['elapsed_sec']}s", quiet=args.quiet)
    console(json.dumps({k: summary[k] for k in ["status", "ok_or_dry_run_count", "warning_or_fail_count", "elapsed_sec", "log_jsonl", "summary_json"]}, indent=2, ensure_ascii=False), quiet=args.quiet)
    return 0 if args.dry_run or ok_count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
