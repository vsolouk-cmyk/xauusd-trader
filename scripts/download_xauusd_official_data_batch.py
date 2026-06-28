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
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "XAUUSD_OFFICIAL_DATA_DOWNLOAD_BATCH_STAGE116C_ENVFILE_CENSUS_PATCH"
DEFAULT_INBOX = Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"
DEFAULT_FROM_YEAR = 2009
DEFAULT_TO_YEAR = 2026
FRED_SERIES = [
    "DFII10", "VIXCLS", "DTWEXBGS", "DGS10", "DGS2", "T10YIE", "T5YIE", "DFF", "WALCL", "BAMLH0A0HYM2",
]
BLS_SERIES = ["CUSR0000SA0", "CUSR0000SA0L1E", "CES0000000001", "LNS14000000", "LNS11300000", "CES0500000003"]
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
    if path.name == "stooq_dx_f_dxy_daily.csv":
        try:
            lines = [x for x in path.read_text(errors="ignore").splitlines() if x.strip()]
        except Exception:
            lines = []
        if len(lines) < 50:
            return "DXY_DIRECT_TOO_SHORT_OR_BLOCKED"
    return None


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
) -> Dict[str, object]:
    ensure_dir(out.parent)
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


def post_bls(out: Path, *, dry_run: bool = False) -> Dict[str, object]:
    ensure_dir(out.parent)
    payload: Dict[str, object] = {"seriesid": BLS_SERIES, "startyear": "2017", "endyear": "2026"}
    if env_present("BLS_API_KEY"):
        payload["startyear"] = str(DEFAULT_FROM_YEAR)
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


def marker_result(path: Path, text: str, *, dry_run: bool = False) -> Dict[str, object]:
    ensure_dir(path.parent)
    if not dry_run:
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
    ok = sum(1 for r in results if str(r.get("status")) in {"OK", "DRY_RUN"})
    warn = len(results) - ok
    elapsed = round(time.time() - started, 2)
    console(f"[{section_no:02d}/{total_sections:02d} DONE ] {name} | ok={ok} warn/fail={warn} | elapsed={elapsed}s", quiet=quiet)
    write_jsonl(log_path, {"event": "section_done", "section_no": section_no, "name": name, "ok": ok, "warn_or_fail": warn, "elapsed_sec": elapsed, "utc": utc_now()})
    return results


def build_sections(inbox: Path, years: List[int], *, include_cot_xls: bool, skip_wgc_direct: bool, dry_run: bool) -> List[Tuple[str, Sequence[Tuple[str, callable]]]]:
    sections: List[Tuple[str, Sequence[Tuple[str, callable]]]] = []

    sections.append((
        "FRED macro direct CSVs",
        [(sid, lambda sid=sid: curl_download(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", inbox / "fred_macro" / f"{sid}.csv", dry_run=dry_run)) for sid in FRED_SERIES],
    ))

    sections.append((
        "DXY direct candidate; DTWEXBGS remains official fallback",
        [("stooq_dx_f_dxy_daily.csv", lambda: curl_download("https://stooq.com/q/d/l/?s=dx.f&i=d", inbox / "macro_misc" / "dxy" / "stooq_dx_f_dxy_daily.csv", dry_run=dry_run))],
    ))

    if env_present("FRED_API_KEY"):
        key = os.environ["FRED_API_KEY"]
        fred_tasks = [("fred_releases_dates_2009_present.json", lambda key=key: curl_download(
            f"https://api.stlouisfed.org/fred/releases/dates?api_key={key}&file_type=json&realtime_start=2009-01-01&realtime_end=9999-12-31&include_release_dates_with_no_data=true",
            inbox / "events" / "fred" / "fred_releases_dates_2009_present.json", dry_run=dry_run))]
    else:
        fred_tasks = [("missing_FRED_API_KEY", lambda: {"output": "events/fred/fred_releases_dates_2009_present.json", "status": "SKIPPED_MISSING_FRED_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("Official economic-events backbone: FRED release dates", fred_tasks))

    sections.append((
        "CFTC COT disaggregated futures TXT zips",
        [(f"fut_disagg_txt_{y}.zip", lambda y=y: curl_download(f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{y}.zip", inbox / "cot" / "cftc" / f"fut_disagg_txt_{y}.zip", dry_run=dry_run)) for y in years],
    ))

    if include_cot_xls:
        sections.append((
            "Optional CFTC COT disaggregated futures XLS zips",
            [(f"fut_disagg_xls_{y}.zip", lambda y=y: curl_download(f"https://www.cftc.gov/files/dea/history/fut_disagg_xls_{y}.zip", inbox / "cot" / "cftc" / f"fut_disagg_xls_{y}.zip", dry_run=dry_run)) for y in years],
        ))

    sections.append(("BLS CPI / labor / payroll JSON", [("bls_core_macro.json", lambda: post_bls(inbox / "events" / "bls" / "bls_core_macro_2017_2026.json", dry_run=dry_run))]))

    if env_present("BEA_API_KEY"):
        key = os.environ["BEA_API_KEY"]
        bea_urls = {
            "bea_dataset_list.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATASETLIST&ResultFormat=JSON",
            "bea_nipa_table_names.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETPARAMETERVALUES&datasetname=NIPA&ParameterName=TableName&ResultFormat=JSON",
            "bea_nipa_T10101_gdp_q_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T10101&Frequency=Q&Year=ALL&ResultFormat=JSON",
            "bea_nipa_T20600_personal_income_m_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T20600&Frequency=M&Year=ALL&ResultFormat=JSON",
            "bea_nipa_T20804_pce_price_indexes_m_all.json": f"https://apps.bea.gov/api/data/?UserID={key}&method=GETDATA&datasetname=NIPA&TableName=T20804&Frequency=M&Year=ALL&ResultFormat=JSON",
        }
        bea_tasks = [(fn, lambda fn=fn, url=url: curl_download(url, inbox / "events" / "bea" / fn, dry_run=dry_run)) for fn, url in bea_urls.items()]
    else:
        bea_tasks = [("missing_BEA_API_KEY", lambda: {"output": "events/bea/*.json", "status": "SKIPPED_MISSING_BEA_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("BEA GDP / PCE / personal income JSON", bea_tasks))

    census_var_tasks = [(f"census_eits_{ds}_variables.json", lambda ds=ds: curl_download(f"https://api.census.gov/data/timeseries/eits/{ds}/variables.json", inbox / "events" / "census" / f"census_eits_{ds}_variables.json", dry_run=dry_run)) for ds in ["marts", "ftd", "resconst", "ressales"]]
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
                census_data_tasks.append((f"census_{ds}_{y}.json", lambda y=y, ds=ds, get=get, key=key: curl_download(f"https://api.census.gov/data/timeseries/eits/{ds}?get={get}&time={y}&key={key}", inbox / "events" / "census" / f"census_{ds}_{y}.json", dry_run=dry_run)))
    else:
        census_data_tasks = [("missing_CENSUS_API_KEY", lambda: {"output": "events/census/census_*_YYYY.json", "status": "SKIPPED_MISSING_CENSUS_API_KEY", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("Census EITS yearly datasets", census_data_tasks))

    sections.append(("Official economic-events backbone: FOMC calendar snapshot", [("fomc_calendars_2021_2027.html", lambda: curl_download("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", inbox / "events" / "fomc" / "fomc_calendars_2021_2027.html", dry_run=dry_run))]))

    sections.append((
        "Official economic-events backbone: Treasury auctions",
        [
            ("treasury_upcoming_auctions.csv", lambda: curl_download("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/upcoming_auctions?format=csv&page[size]=1000", inbox / "events" / "treasury" / "treasury_upcoming_auctions.csv", globoff=True, dry_run=dry_run)),
            ("treasury_auctions_query_recent.csv", lambda: curl_download("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?format=csv&page[size]=10000&sort=-auction_date", inbox / "events" / "treasury" / "treasury_auctions_query_recent.csv", globoff=True, dry_run=dry_run)),
        ],
    ))

    if not skip_wgc_direct:
        wgc_tasks = [
            ("ETF_Flows_2026-06-02_1536.xlsx", lambda: curl_download("https://www.gold.org/download/file/20888/ETF_Flows_2026-06-02_1536.xlsx", inbox / "gold_etf" / "wgc" / "ETF_Flows_2026-06-02_1536.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows", dry_run=dry_run)),
            ("ETF-Flows-Data-Methodology.pdf", lambda: curl_download("https://www.gold.org/download/file/16223/ETF-Flows-Data-Methodology.pdf", inbox / "gold_etf" / "wgc" / "ETF-Flows-Data-Methodology.pdf", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows", dry_run=dry_run)),
            ("World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", lambda: curl_download("https://www.gold.org/download/file/7739/World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", inbox / "central_bank_gold" / "World_official_gold_holdings_as_of_Jun2026_IFS.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run)),
            ("Changes_latest_as_of_Jun2026_IFS.xlsx", lambda: curl_download("https://www.gold.org/download/file/7741/Changes_latest_as_of_Jun2026_IFS.xlsx", inbox / "central_bank_gold" / "Changes_latest_as_of_Jun2026_IFS.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run)),
            ("Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", lambda: curl_download("https://www.gold.org/download/file/8052/Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", inbox / "central_bank_gold" / "Quarterly_gold_and_FX_Reserves_Q1_2026.xlsx", user_agent=True, referer="https://www.gold.org/goldhub/data/gold-reserves-by-country", dry_run=dry_run)),
        ]
    else:
        wgc_tasks = [("WGC manual preferred", lambda: {"output": "gold_etf/wgc + central_bank_gold", "status": "SKIPPED_WGC_DIRECT_BY_USER", "size_bytes": 0, "elapsed_sec": 0.0})]
    sections.append(("WGC ETF and central-bank direct attempts; browser fallback if blocked", wgc_tasks))

    sections.append(("SPDR GLD historical archive", [("spdr_gld_historical_archive.xlsx", lambda: curl_download("https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld", inbox / "gld" / "spdr" / "spdr_gld_historical_archive.xlsx", dry_run=dry_run))]))

    gold_price_text = "Manual: https://www.gold.org/goldhub/data/gold-prices -> Downloads -> Download xlsx Gold price averages in a range of currencies since 1978\n"
    sections.append(("WGC gold price averages manual marker", [("README_MANUAL_GOLD_PRICE_DOWNLOAD.txt", lambda: marker_result(inbox / "gold_price" / "wgc" / "README_MANUAL_GOLD_PRICE_DOWNLOAD.txt", gold_price_text, dry_run=dry_run))]))

    return sections


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--inbox", default=str(DEFAULT_INBOX))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-cot-xls", action="store_true")
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
    sections = build_sections(inbox, years, include_cot_xls=args.include_cot_xls, skip_wgc_direct=args.skip_wgc_direct, dry_run=args.dry_run)
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

    ok_count = sum(1 for r in all_results if str(r.get("status")) in {"OK", "DRY_RUN"})
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
        "elapsed_sec": round(time.time() - started, 2),
        "status": "DOWNLOAD_BATCH_COMPLETE" if warning_count == 0 else "DOWNLOAD_BATCH_COMPLETE_WITH_WARNINGS",
        "ok_or_dry_run_count": ok_count,
        "warning_or_fail_count": warning_count,
        "api_key_presence": {k: env_present(k) for k in API_ENV_KEYS},
        "env_files_loaded": env_files_loaded,
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
