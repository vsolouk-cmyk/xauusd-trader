#!/usr/bin/env python3
"""
Stage113 Fundamental + Economic Event Inbox Unifier

Purpose:
- Create a single manual-download inbox for all XAUUSD fundamental/event inputs.
- Copy/catalog user-downloaded files into ignored project data folders.
- Produce a reproducible manifest and a download guide.
- Do NOT connect to broker, MT5, paper-order, or live/order components.

This script intentionally avoids external network calls. It is an intake/manifest layer.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Dict, Iterable, List, Tuple

STAGE = "Stage113_FUNDAMENTAL_EVENT_INBOX_UNIFIER"

DEFAULT_INBOX_NAME = "xauusd_fundamental_event_inbox"

SOURCE_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("events_bls", ("bls", "cpi", "ppi", "employment", "payroll", "nfp", "jolts", "unemployment")),
    ("events_bea", ("bea", "gdp", "pce", "personal_income", "personal-income", "international_trade")),
    ("events_census", ("census", "retail", "durable", "housing", "construction", "manufacturing", "trade")),
    ("events_fomc", ("fomc", "fed", "minutes", "sep", "statement", "federal_reserve")),
    ("events_treasury", ("treasury", "auction", "fiscaldata", "fiscal_data")),
    ("cot_cftc", ("cftc", "cot", "commitments", "disagg", "legacy", "deacot")),
    ("gold_etf_wgc", ("wgc", "gold_etf", "gold-etf", "etf_flows", "etf-flows", "goldhub", "world_gold")),
    ("gld_spdr", ("gld", "spdr", "gold_shares")),
    ("central_bank_gold", ("central_bank", "central-bank", "cb_gold", "official_reserve", "reserve_asset", "wgc_cb")),
    ("fred_macro", ("fred", "dgs10", "dfii10", "t10yie", "dxy", "vix", "real_yield")),
    ("macro_misc", ("macro", "yield", "inflation", "dollar", "risk", "safe_haven")),
]

ALLOWED_EXTENSIONS = {
    ".csv", ".tsv", ".txt", ".json", ".xml", ".xlsx", ".xls", ".zip", ".html", ".htm"
}

GITIGNORE_LINES = [
    "data/fundamental_event_inbox/raw/",
    "data/fundamental_event_inbox/cache/",
    "data/fundamental_event_inbox/normalized/",
    "data/fundamental_event_inbox/manifests/",
    "data/economic_events_raw/",
    "data/economic_events_normalized/",
]

DOWNLOAD_GUIDE_ROWS = [
    {
        "bucket": "events/fred",
        "source": "FRED releases/dates",
        "what_to_download": "Release date calendar; useful as historical-as-of event calendar backbone.",
        "download_or_api": "https://api.stlouisfed.org/fred/releases/dates?api_key=YOUR_FRED_KEY&file_type=json&realtime_start=2011-01-01&realtime_end=2030-12-31",
        "manual_page": "https://fred.stlouisfed.org/docs/api/fred/releases_dates.html",
        "notes": "Requires FRED API key. Release date is source-published date, not guaranteed FRED availability timestamp.",
    },
    {
        "bucket": "events/bls",
        "source": "BLS schedule",
        "what_to_download": "CPI, PPI, Employment Situation/NFP, JOLTS release calendar pages/files.",
        "download_or_api": "https://www.bls.gov/schedule/",
        "manual_page": "https://www.bls.gov/bls/api_features.htm",
        "notes": "Official US labor/inflation release schedule and API for published series.",
    },
    {
        "bucket": "events/bea",
        "source": "BEA schedule/API",
        "what_to_download": "GDP, PCE, Personal Income and Outlays, trade-related release dates and series.",
        "download_or_api": "https://www.bea.gov/news/schedule/full",
        "manual_page": "https://www.bea.gov/resources/for-developers",
        "notes": "Official source. API key available from BEA. Schedule contains release times.",
    },
    {
        "bucket": "events/census",
        "source": "Census economic indicators",
        "what_to_download": "Retail sales, durable goods, housing starts, construction spending, trade indicators.",
        "download_or_api": "https://www.census.gov/economic-indicators/calendar-listview.html",
        "manual_page": "https://www.census.gov/economic-indicators/",
        "notes": "Official source for multiple high-impact US activity releases.",
    },
    {
        "bucket": "events/fomc",
        "source": "Federal Reserve FOMC calendar",
        "what_to_download": "FOMC meeting, statement, minutes and SEP dates.",
        "download_or_api": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "manual_page": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "notes": "Gold-critical event windows. Download manually as html/pdf/calendar snapshots if needed.",
    },
    {
        "bucket": "events/treasury",
        "source": "Treasury Fiscal Data",
        "what_to_download": "Treasury auction calendar/data and auction-risk windows.",
        "download_or_api": "https://fiscaldata.treasury.gov/datasets/upcoming-auctions/",
        "manual_page": "https://fiscaldata.treasury.gov/api-documentation/",
        "notes": "Useful for yield-pressure windows around auctions.",
    },
    {
        "bucket": "cot/cftc",
        "source": "CFTC COT historical compressed",
        "what_to_download": "Disaggregated or legacy COT historical CSV/ZIP; gold futures positioning.",
        "download_or_api": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm",
        "manual_page": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        "notes": "Official COT. Keep raw ZIP/CSV in inbox; normalized import remains a separate project stage.",
    },
    {
        "bucket": "gold_etf/wgc",
        "source": "World Gold Council ETF flows",
        "what_to_download": "Gold ETF holdings and flows xlsx downloads.",
        "download_or_api": "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
        "manual_page": "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
        "notes": "Often xlsx. Put raw xlsx into gold_etf/wgc bucket.",
    },
    {
        "bucket": "gld/spdr",
        "source": "SPDR Gold Shares",
        "what_to_download": "GLD historical holdings/price/premium data if export is available from page.",
        "download_or_api": "https://www.spdrgoldshares.com/usa/gld/",
        "manual_page": "https://www.spdrgoldshares.com/usa/gld/",
        "notes": "Manual download page; use only if WGC ETF data does not cover desired granularity.",
    },
    {
        "bucket": "fred_macro",
        "source": "FRED macro series",
        "what_to_download": "DGS10, DFII10, T10YIE, CPI/PCE proxies, daily rates if not already present.",
        "download_or_api": "https://fred.stlouisfed.org/docs/api/fred/",
        "manual_page": "https://fred.stlouisfed.org/docs/api/fred/",
        "notes": "Series-level observations are better downloaded by scripts once FRED key is configured.",
    },
]

README_TEXT = """# XAUUSD Fundamental + Event Inbox

Put all manual downloads here first, not directly into project data folders.

Recommended buckets:

- events/fred
- events/bls
- events/bea
- events/census
- events/fomc
- events/treasury
- cot/cftc
- gold_etf/wgc
- gld/spdr
- central_bank_gold
- fred_macro
- macro_misc

Then run:

python3 app/stage113_fundamental_event_inbox_unifier.py --root /Users/vahid/Desktop/xauusd-trader

The script will copy and catalog files into ignored project folders and produce manifests.
"""

def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(path: Path) -> str:
    raw = path.name.replace(os.sep, "_")
    return "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in raw)


def classify_source(path: Path) -> str:
    token = str(path).lower().replace(" ", "_")
    for source, needles in SOURCE_RULES:
        if any(n in token for n in needles):
            return source
    return "unknown_manual"


def iter_input_files(inbox_dir: Path) -> Iterable[Path]:
    if not inbox_dir.exists():
        return []
    files: List[Path] = []
    for p in sorted(inbox_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        files.append(p)
    return files


def ensure_inbox(downloads_dir: Path, inbox_name: str) -> Path:
    inbox_dir = downloads_dir / inbox_name
    buckets = sorted({row["bucket"] for row in DOWNLOAD_GUIDE_ROWS} | {
        "central_bank_gold", "macro_misc", "_processed", "_rejected"
    })
    for bucket in buckets:
        (inbox_dir / bucket).mkdir(parents=True, exist_ok=True)
    readme = inbox_dir / "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md"
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
    return inbox_dir


def append_gitignore(root: Path) -> List[str]:
    gitignore = root / ".gitignore"
    existing = set()
    if gitignore.exists():
        existing = set(line.strip() for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines())
    added = []
    with gitignore.open("a", encoding="utf-8") as f:
        for line in GITIGNORE_LINES:
            if line not in existing:
                if gitignore.stat().st_size > 0:
                    f.write("\n")
                f.write(line + "\n")
                existing.add(line)
                added.append(line)
    return added


def write_download_guide(out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "stage113_download_guide.csv"
    md_path = out_dir / "stage113_download_guide.md"

    fields = ["bucket", "source", "what_to_download", "download_or_api", "manual_page", "notes"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(DOWNLOAD_GUIDE_ROWS)

    lines = [
        "# Stage113 Download Guide",
        "",
        "Use this as the one-box download checklist before any event-aware or fundamental-aware discovery stage.",
        "",
        "| Bucket | Source | What to download | Link / API | Notes |",
        "|---|---|---|---|---|",
    ]
    for row in DOWNLOAD_GUIDE_ROWS:
        lines.append(
            f"| `{row['bucket']}` | {row['source']} | {row['what_to_download']} | {row['download_or_api']} | {row['notes']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, md_path


def copy_and_manifest(root: Path, inbox_dir: Path, project_data_dir: Path) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    raw_root = project_data_dir / "raw"
    manifest_dir = project_data_dir / "manifests"
    raw_root.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, str]] = []
    stats: Dict[str, int] = {"input_files": 0, "copied_files": 0, "duplicate_files": 0}

    seen_hashes = set()
    for file_path in iter_input_files(inbox_dir):
        if file_path.name == "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md":
            continue
        stats["input_files"] += 1
        digest = sha256_file(file_path)
        source = classify_source(file_path)
        rel_inbox = file_path.relative_to(inbox_dir)
        source_dir = raw_root / source
        source_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{digest[:12]}__{safe_name(file_path)}"
        dest = source_dir / dest_name

        duplicate = digest in seen_hashes or dest.exists()
        if duplicate:
            stats["duplicate_files"] += 1
        else:
            shutil.copy2(file_path, dest)
            stats["copied_files"] += 1
            seen_hashes.add(digest)

        rows.append({
            "stage": STAGE,
            "generated_utc": utc_now(),
            "source_bucket": source,
            "original_path": str(file_path),
            "relative_inbox_path": str(rel_inbox),
            "project_raw_path": str(dest),
            "filename": file_path.name,
            "suffix": file_path.suffix.lower(),
            "size_bytes": str(file_path.stat().st_size),
            "sha256": digest,
            "duplicate_or_existing": str(bool(duplicate)),
        })

    manifest_csv = manifest_dir / "stage113_fundamental_event_file_manifest.csv"
    fields = [
        "stage", "generated_utc", "source_bucket", "original_path", "relative_inbox_path",
        "project_raw_path", "filename", "suffix", "size_bytes", "sha256", "duplicate_or_existing"
    ]
    with manifest_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    return rows, stats


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--downloads-dir", default=str(Path.home() / "Downloads"), help="Downloads directory")
    ap.add_argument("--inbox-name", default=DEFAULT_INBOX_NAME, help="Inbox folder name under downloads-dir")
    ap.add_argument("--project-data-dir", default="data/fundamental_event_inbox", help="Ignored project data folder")
    ap.add_argument("--out", default="reports/stage113_fundamental_event_inbox_unifier", help="Report output dir")
    ap.add_argument("--no-copy", action="store_true", help="Only create folders/guide; do not copy inbox files")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    downloads_dir = Path(args.downloads_dir).expanduser().resolve()
    inbox_dir = ensure_inbox(downloads_dir, args.inbox_name)

    out_dir = (root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    guide_csv, guide_md = write_download_guide(out_dir)

    added_gitignore = append_gitignore(root)

    project_data_dir = (root / args.project_data_dir).resolve()
    rows: List[Dict[str, str]] = []
    stats: Dict[str, int] = {"input_files": 0, "copied_files": 0, "duplicate_files": 0}
    if not args.no_copy:
        rows, stats = copy_and_manifest(root, inbox_dir, project_data_dir)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": "STAGE113_COMPLETE_INTAKE_READY_NO_PROMOTION",
        "decision": "STAGE113_FUNDAMENTAL_EVENT_INBOX_READY_NO_ORDER",
        "classification": "INFRASTRUCTURE_ONLY_NO_ORDER",
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_MT5_OR_EA_CHANGE_FROM_STAGE113",
            "NO_PAPER_LIVE",
            "NO_LIVE",
        ],
        "root": str(root),
        "downloads_dir": str(downloads_dir),
        "manual_inbox_dir": str(inbox_dir),
        "project_data_dir": str(project_data_dir),
        "stats": stats,
        "added_gitignore_lines": added_gitignore,
        "download_guide_csv": str(guide_csv),
        "download_guide_md": str(guide_md),
        "manifest_csv": str(project_data_dir / "manifests" / "stage113_fundamental_event_file_manifest.csv"),
        "next": [
            "Download all manual official files into the single inbox buckets.",
            "Run this script again.",
            "Use the manifest to route source-specific normalizers in later stages.",
        ],
    }
    summary_path = out_dir / "stage113_fundamental_event_inbox_unifier_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_lines = [
        "# Stage113 Fundamental + Event Inbox Unifier",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- manual inbox: `{summary['manual_inbox_dir']}`",
        f"- project data dir: `{summary['project_data_dir']}`",
        f"- input files: `{stats['input_files']}`",
        f"- copied files: `{stats['copied_files']}`",
        f"- duplicate/existing files: `{stats['duplicate_files']}`",
        "",
        "## Gitignore additions",
        "",
    ]
    if added_gitignore:
        report_lines += [f"- `{line}`" for line in added_gitignore]
    else:
        report_lines.append("- No new .gitignore line was needed.")
    report_path = out_dir / "stage113_fundamental_event_inbox_unifier_report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": summary["decision"],
        "manual_inbox_dir": summary["manual_inbox_dir"],
        "input_files": stats["input_files"],
        "copied_files": stats["copied_files"],
        "summary_json": str(summary_path),
        "download_guide_md": str(guide_md),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
