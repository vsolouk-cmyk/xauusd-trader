#!/usr/bin/env python3
"""
Stage38F Gold ETF Source Availability Audit

Read-only source audit for free/no-cost gold ETF holdings/flow data sources.

This script does not create trading signals, baselines, orders, or alerts.
It only checks whether WGC and SPDR GLD data sources are reachable and whether
raw downloadable files can be saved for later parsing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

WGC_ETF_PAGE = "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows"
SPDR_GLD_PAGE = "https://www.spdrgoldshares.com/usa/gld/"
SPDR_HISTORICAL_ARCHIVE = (
    "https://api.spdrgoldshares.com/api/v1/historical-archive"
    "?exchange=NYSE&lang=en&product=gld"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

DOWNLOAD_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.ms-excel,application/octet-stream,*/*"
    ),
}


@dataclass
class FetchResult:
    name: str
    url: str
    status: str
    http_status: Optional[int]
    content_type: Optional[str]
    bytes_read: int
    sha256: Optional[str]
    saved_path: Optional[str]
    error: Optional[str]
    elapsed_sec: float


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return name[:180] or "download"


def fetch_url(
    name: str,
    url: str,
    out_dir: Path,
    *,
    save: bool,
    max_bytes: int,
    timeout: int,
    headers: Dict[str, str],
    allow_insecure_ssl: bool = False,
) -> Tuple[FetchResult, bytes]:
    t0 = time.time()
    data = b""
    status = "FAIL"
    http_status = None
    content_type = None
    saved_path = None
    sha = None
    error = None

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        context = None
        if allow_insecure_ssl:
            context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            http_status = getattr(resp, "status", None)
            content_type = resp.headers.get("Content-Type")
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                data = data[:max_bytes]
                status = "PASS_TRUNCATED"
            else:
                status = "PASS"

        sha = hashlib.sha256(data).hexdigest() if data else None
        if save and data:
            out_dir.mkdir(parents=True, exist_ok=True)
            parsed = urllib.parse.urlparse(url)
            suffix = Path(parsed.path).suffix
            if not suffix:
                if content_type and "spreadsheet" in content_type.lower():
                    suffix = ".xlsx"
                elif content_type and "excel" in content_type.lower():
                    suffix = ".xlsx"
                elif content_type and "json" in content_type.lower():
                    suffix = ".json"
                else:
                    suffix = ".bin"
            fn = safe_filename(name) + suffix
            path = out_dir / fn
            path.write_bytes(data)
            saved_path = str(path)
    except urllib.error.HTTPError as e:
        http_status = e.code
        content_type = e.headers.get("Content-Type") if e.headers else None
        try:
            data = e.read(min(max_bytes, 4096))
        except Exception:
            data = b""
        error = f"HTTPError: {e.code} {e.reason}"
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"

    elapsed = round(time.time() - t0, 3)
    return (
        FetchResult(
            name=name,
            url=url,
            status=status,
            http_status=http_status,
            content_type=content_type,
            bytes_read=len(data),
            sha256=sha,
            saved_path=saved_path,
            error=error,
            elapsed_sec=elapsed,
        ),
        data,
    )


def discover_xlsx_links(page_url: str, html: bytes) -> List[str]:
    text = html.decode("utf-8", errors="ignore")
    links = []
    for match in re.findall(r'href=["\']([^"\']+\.xlsx[^"\']*)["\']', text, flags=re.I):
        links.append(urllib.parse.urljoin(page_url, match))
    # Some WGC links may be embedded in JS or escaped strings.
    for match in re.findall(r'(?:https?:)?//[^\s"\']+\.xlsx[^\s"\']*', text, flags=re.I):
        if match.startswith("//"):
            match = "https:" + match
        links.append(match)
    for match in re.findall(r'(/download/file/[^\s"\']+\.xlsx[^\s"\']*)', text, flags=re.I):
        links.append(urllib.parse.urljoin(page_url, match))

    deduped = []
    seen = set()
    for link in links:
        link = link.replace("\\/", "/")
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def infer_decision(results: List[FetchResult], discovered_wgc_links: List[str]) -> Tuple[str, str, List[str]]:
    notes: List[str] = []
    by_name = {r.name: r for r in results}

    wgc_page_ok = by_name.get("wgc_page") and by_name["wgc_page"].status.startswith("PASS")
    spdr_page_ok = by_name.get("spdr_gld_page") and by_name["spdr_gld_page"].status.startswith("PASS")
    wgc_xlsx_ok = any(r.name.startswith("wgc_xlsx_") and r.status.startswith("PASS") for r in results)
    spdr_archive_ok = by_name.get("spdr_historical_archive") and by_name["spdr_historical_archive"].status.startswith("PASS")

    if not discovered_wgc_links:
        notes.append("no_wgc_xlsx_links_discovered_from_page_html")
    if wgc_page_ok and discovered_wgc_links and not wgc_xlsx_ok:
        notes.append("wgc_page_ok_but_xlsx_download_failed_or_blocked")
    if spdr_page_ok and not spdr_archive_ok:
        notes.append("spdr_page_ok_but_historical_archive_download_failed_or_blocked")

    if wgc_xlsx_ok or spdr_archive_ok:
        return "PASS", "PROCEED_TO_STAGE38F_DOWNLOAD_OR_PARSE_DESIGN", notes
    if wgc_page_ok or spdr_page_ok:
        return "WARN", "SOURCE_PAGE_AVAILABLE_BUT_DOWNLOAD_BLOCKED_USE_GITHUB_ACTIONS_ARTIFACT", notes
    return "FAIL", "ETF_SOURCES_NOT_REACHABLE_FROM_CURRENT_ENVIRONMENT", notes


def write_reports(report: dict, reports_dir: Path) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38f_gold_etf_source_availability_audit.json"
    md_path = reports_dir / "stage38f_gold_etf_source_availability_audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append("# Stage38F Gold ETF Source Availability Audit")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"status = {report['status']}")
    lines.append(f"decision = {report['decision']}")
    lines.append("```")
    lines.append("")
    lines.append("## Discovered WGC XLSX links")
    lines.append("")
    if report["discovered_wgc_xlsx_links"]:
        for link in report["discovered_wgc_xlsx_links"]:
            lines.append(f"- `{link}`")
    else:
        lines.append("None discovered.")
    lines.append("")
    lines.append("## Fetch results")
    lines.append("")
    for r in report["fetch_results"]:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append("```text")
        for k in ["status", "http_status", "content_type", "bytes_read", "sha256", "saved_path", "error", "elapsed_sec"]:
            lines.append(f"{k}: {r.get(k)}")
        lines.append("```")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    if report["notes"]:
        for n in report["notes"]:
            lines.append(f"- {n}")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("```text")
    lines.append("No strategy")
    lines.append("No backtest")
    lines.append("No optimizer")
    lines.append("No ML")
    lines.append("No Stage39")
    lines.append("No EA")
    lines.append("No paper-live")
    lines.append("No live order")
    lines.append("```")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", default="data/reports/stage38f_gold_etf_source_availability_audit")
    ap.add_argument("--raw-dir", default="data/etf/gold/source_audit/raw")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--max-bytes", type=int, default=25_000_000)
    ap.add_argument("--wgc-page", default=WGC_ETF_PAGE)
    ap.add_argument("--spdr-page", default=SPDR_GLD_PAGE)
    ap.add_argument("--spdr-archive-url", default=SPDR_HISTORICAL_ARCHIVE)
    ap.add_argument("--allow-insecure-ssl", action="store_true")
    args = ap.parse_args(argv)

    reports_dir = Path(args.reports_dir)
    raw_dir = Path(args.raw_dir)

    results: List[FetchResult] = []

    wgc_res, wgc_html = fetch_url(
        "wgc_page",
        args.wgc_page,
        raw_dir,
        save=True,
        max_bytes=args.max_bytes,
        timeout=args.timeout,
        headers=DEFAULT_HEADERS,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )
    results.append(wgc_res)
    wgc_links = discover_xlsx_links(args.wgc_page, wgc_html) if wgc_res.status.startswith("PASS") else []

    # Try at most first three discovered WGC xlsx links to avoid aggressive scraping.
    for i, link in enumerate(wgc_links[:3], start=1):
        res, _ = fetch_url(
            f"wgc_xlsx_{i}",
            link,
            raw_dir,
            save=True,
            max_bytes=args.max_bytes,
            timeout=args.timeout,
            headers=DOWNLOAD_HEADERS,
            allow_insecure_ssl=args.allow_insecure_ssl,
        )
        results.append(res)

    spdr_page_res, _ = fetch_url(
        "spdr_gld_page",
        args.spdr_page,
        raw_dir,
        save=True,
        max_bytes=args.max_bytes,
        timeout=args.timeout,
        headers=DEFAULT_HEADERS,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )
    results.append(spdr_page_res)

    spdr_archive_res, _ = fetch_url(
        "spdr_historical_archive",
        args.spdr_archive_url,
        raw_dir,
        save=True,
        max_bytes=args.max_bytes,
        timeout=args.timeout,
        headers=DOWNLOAD_HEADERS,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )
    results.append(spdr_archive_res)

    status, decision, notes = infer_decision(results, wgc_links)

    report = {
        "generated_utc": utc_now_iso(),
        "status": status,
        "decision": decision,
        "wgc_page": args.wgc_page,
        "spdr_page": args.spdr_page,
        "spdr_archive_url": args.spdr_archive_url,
        "discovered_wgc_xlsx_links": wgc_links,
        "fetch_results": [asdict(r) for r in results],
        "notes": notes,
    }

    json_path, md_path = write_reports(report, reports_dir)
    print(json.dumps({
        "status": status,
        "decision": decision,
        "fetch_count": len(results),
        "wgc_xlsx_links_discovered": len(wgc_links),
        "json_report": str(json_path),
        "md_report": str(md_path),
        "notes": notes,
    }, indent=2, ensure_ascii=False))
    return 0 if status in {"PASS", "WARN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
