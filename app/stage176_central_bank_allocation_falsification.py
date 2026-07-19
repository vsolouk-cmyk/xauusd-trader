#!/usr/bin/env python3
"""Stage176 — Central-bank accumulation allocation falsification.

Purpose
-------
Run one time-boxed, fail-closed audit of a low-frequency gold allocation thesis:

* input must be original WGC quarterly publication vintages, not a latest revised
  workbook silently projected backward;
* the formulation is embedded and immutable (no grid, no threshold search);
* a daily gold series with enough history is required for the 200D trend gate;
* outputs are research / decision-support only; no order, demo, paper or live path.

The executable first validates or constructs a WGC vintage manifest, then runs
historical-as-of allocation, fixed baselines, non-overlapping horizon tests,
leave-one-episode-out robustness and terminal decision gates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_lib
import json
import math
import random
import re
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage176_CENTRAL_BANK_ACCUMULATION_ALLOCATION_FALSIFICATION"
DEFAULT_OUT = "reports/stage176_central_bank_allocation_falsification"

# This is the research contract. Editing the JSON config cannot alter it.
LOCKED_CONTRACT: Dict[str, Any] = {
    "product_type": "QUARTERLY_GOLD_ALLOCATION_DECISION_ENGINE",
    "high_exposure": 1.0,
    "low_exposure": 0.0,
    "initial_state": "LOW",
    "trailing_purchase_quarters": 4,
    "prior_expanding_median_min_observations": 8,
    "trend_sma_trading_days": 200,
    "exit_consecutive_quarterly_declines": 2,
    "holdout_fraction": 0.20,
    "primary_switching_cost_bps": 10.0,
    "stress_switching_cost_bps": 20.0,
    "minimum_total_quarters": 56,
    "maximum_missing_quarters": 2,
    "minimum_high_episodes": 5,
    "minimum_calendar_eras": 3,
    "calendar_eras": [
        [2010, 2014, "ERA_2010_2014"],
        [2015, 2019, "ERA_2015_2019"],
        [2020, 2029, "ERA_2020_2029"],
    ],
    "maximum_single_episode_positive_excess_share": 0.70,
    "minimum_1q_observations_per_state": 8,
    "maximum_1q_permutation_pvalue": 0.10,
    "permutation_iterations": 10000,
    "permutation_seed": 176,
    "minimum_return_retention_vs_buy_hold": 0.80,
    "minimum_drawdown_reduction_vs_buy_hold": 0.25,
    "earliest_required_quarter": "2010Q1",
    "minimum_release_lag_days": 10,
    "maximum_release_lag_days": 180,
    "maximum_abs_quarterly_purchases_tonnes": 600.0,
    "maximum_duplicate_conflict_tonnes": 3.0,
    "minimum_extraction_confidence": 0.85,
    "price_minimum_start_date": "2010-03-31",
    "price_minimum_latest_lag_days": 30,
}


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class ProgressReporter:
    """Terminal heartbeat plus durable progress checkpoint.

    Every event is flushed to stderr, appended to a log, and atomically written
    to ``stage176_progress.json`` so a second terminal can inspect the run.
    """

    def __init__(self, out_dir: Path, enabled: bool = True) -> None:
        self.out_dir = out_dir
        self.enabled = bool(enabled)
        self.started_monotonic = time.monotonic()
        self.started_utc = utc_iso()
        self.log_path = out_dir / "stage176_progress.log"
        self.json_path = out_dir / "stage176_progress.json"
        out_dir.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        phase: str,
        message: str,
        *,
        current: Optional[int] = None,
        total: Optional[int] = None,
        status: str = "RUNNING",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.started_monotonic
        fraction = ""
        percent: Optional[float] = None
        if current is not None and total is not None and total > 0:
            percent = 100.0 * float(current) / float(total)
            fraction = f" {current}/{total} {percent:5.1f}%"
        line = f"[Stage176][{format_elapsed(elapsed)}][{phase}{fraction}] {message}"
        print(line, file=sys.stderr, flush=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
        payload = {
            "stage": STAGE,
            "status": status,
            "phase": phase,
            "message": message,
            "current": current,
            "total": total,
            "percent": percent,
            "started_utc": self.started_utc,
            "updated_utc": utc_iso(),
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_hms": format_elapsed(elapsed),
            "details": details or {},
        }
        tmp = self.json_path.with_suffix(".json.tmp")
        write_json(tmp, payload)
        tmp.replace(self.json_path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: Optional[datetime] = None) -> str:
    dt = (value or utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json_hash(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256_text(payload)


def write_json(path: Path, obj: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    ensure_parent(path)
    if fieldnames is None:
        fields: List[str] = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(str(key))
        fieldnames = fields
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_sep(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return max(["\t", ",", ";", "|"], key=line.count)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "original", "pass"}


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("−", "-")
    if not text or text.lower() in {"nan", "none", "null", ".", "-"}:
        return None
    try:
        x = float(text)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def parse_timestamp(value: Any) -> Optional[pd.Timestamp]:
    if value is None or str(value).strip() == "":
        return None
    x = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(x):
        return None
    return pd.Timestamp(x)


def quarter_end_from_label(label: str) -> pd.Timestamp:
    match = re.fullmatch(r"\s*(\d{4})\s*[Qq]([1-4])\s*", str(label))
    if not match:
        raise ValueError(f"Invalid quarter label: {label}")
    year, quarter = int(match.group(1)), int(match.group(2))
    month = quarter * 3
    return pd.Timestamp(year=year, month=month, day=1, tz="UTC") + pd.offsets.MonthEnd(0)


def quarter_label(value: Any) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return f"{ts.year}Q{((ts.month - 1) // 3) + 1}"


def quarter_sequence(start_label: str, end_label: str) -> List[str]:
    start = quarter_end_from_label(start_label)
    end = quarter_end_from_label(end_label)
    return [quarter_label(x) for x in pd.date_range(start, end, freq="QE")]


def contract_assertion(config: Dict[str, Any]) -> Dict[str, Any]:
    supplied = config.get("locked_contract")
    if supplied is None:
        return {"pass": False, "reason": "CONFIG_LOCKED_CONTRACT_MISSING"}
    differences = []
    all_keys = sorted(set(LOCKED_CONTRACT) | set(supplied))
    for key in all_keys:
        if supplied.get(key) != LOCKED_CONTRACT.get(key):
            differences.append({"key": key, "expected": LOCKED_CONTRACT.get(key), "actual": supplied.get(key)})
    return {
        "pass": not differences,
        "expected_sha256": stable_json_hash(LOCKED_CONTRACT),
        "supplied_sha256": stable_json_hash(supplied),
        "differences": differences,
    }


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def absolute_gold_url(base_url: str, href: str) -> Optional[str]:
    href = html_lib.unescape(href.strip())
    if not href or href.startswith("#") or href.startswith("mailto:"):
        return None
    url = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() not in {"www.gold.org", "gold.org"}:
        return None
    return urllib.parse.urlunparse(("https", "www.gold.org", parsed.path.rstrip("/"), "", "", ""))


def normalize_report_root(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    for token in ["/central-banks", "/notes-definitions", "/supply", "/investment", "/jewellery", "/technology"]:
        if token in path:
            path = path.split(token)[0]
    # Old Drupal child nodes sometimes append a numeric article id.
    path = re.sub(r"/\d{4,6}$", "", path)
    return urllib.parse.urlunparse(("https", "www.gold.org", path.rstrip("/"), "", "", ""))


def infer_quarter_from_text(text: str, url: str = "") -> Optional[str]:
    hay = f"{url} {text}".lower().replace("’", "'")
    hay = re.sub(r"[-_/]+", " ", hay)
    patterns = [
        r"q\s*([1-4])\s*(?:and\s*)?(?:full\s*year\s*)?(20\d{2}|201\d)",
        r"(20\d{2}|201\d)\s*q\s*([1-4])",
        r"full\s*year\s*(20\d{2}|201\d)",
    ]
    m = re.search(patterns[0], hay)
    if m:
        return f"{int(m.group(2))}Q{int(m.group(1))}"
    m = re.search(patterns[1], hay)
    if m:
        return f"{int(m.group(1))}Q{int(m.group(2))}"
    m = re.search(patterns[2], hay)
    if m:
        return f"{int(m.group(1))}Q4"
    return None


def extract_publication_timestamp(
    raw_html: str,
    *,
    visible_text: Optional[str] = None,
    quarter: Optional[str] = None,
) -> Optional[pd.Timestamp]:
    """Extract the original publication timestamp from metadata or visible page text.

    Several migrated WGC pages expose the publication date only in the rendered
    body (for example ``28 April, 2022``) and omit ``datePublished`` metadata.
    The fallback is constrained by the report quarter: only dates 10--180 days
    after quarter-end are eligible, which prevents footer/copyright dates from
    being mistaken for the publication date.
    """
    patterns = [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)',
        r'<time[^>]*datetime=["\']([^"\']+)',
        r'"dateCreated"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, raw_html, flags=re.I)
        if m:
            ts = parse_timestamp(m.group(1))
            if ts is not None:
                return ts

    text = visible_text if visible_text is not None else strip_html(raw_html)
    # The report date appears near the title. Limit the scan to reduce false
    # positives from copyright years and links to other reports.
    head = str(text)[:5000]
    month = (
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December"
    )
    raw_dates: List[str] = []
    raw_dates.extend(m.group(0) for m in re.finditer(rf"\b\d{{1,2}}\s+(?:{month})\s*,?\s+20\d{{2}}\b", head, flags=re.I))
    raw_dates.extend(m.group(0) for m in re.finditer(rf"\b(?:{month})\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s+20\d{{2}}\b", head, flags=re.I))
    candidates: List[pd.Timestamp] = []
    for value in raw_dates:
        cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value, flags=re.I)
        ts = parse_timestamp(cleaned)
        if ts is None:
            continue
        ts = ts.floor("D") + pd.Timedelta(hours=12)
        if quarter:
            qend = quarter_end_from_label(quarter)
            lag = (ts - qend).total_seconds() / 86400.0
            if not (
                float(LOCKED_CONTRACT["minimum_release_lag_days"])
                <= lag
                <= float(LOCKED_CONTRACT["maximum_release_lag_days"])
            ):
                continue
        candidates.append(ts)
    return min(candidates) if candidates else None


_DOWNLOAD_EXTENSIONS = (".xlsx", ".xls", ".pdf", ".zip")


def extract_download_links(raw_html: str, base_url: str) -> List[str]:
    """Return original WGC report attachments in deterministic priority order."""
    found: List[str] = []
    seen: set[str] = set()
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", raw_html, flags=re.I):
        href = html_lib.unescape(href.strip())
        url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.lower() not in {"www.gold.org", "gold.org"}:
            continue
        lower_path = parsed.path.lower()
        if "/download/file/" not in lower_path and not lower_path.endswith(_DOWNLOAD_EXTENSIONS):
            continue
        clean = urllib.parse.urlunparse(("https", "www.gold.org", parsed.path, "", parsed.query, ""))
        if clean not in seen:
            seen.add(clean)
            found.append(clean)

    def priority(url: str) -> Tuple[int, str]:
        path = urllib.parse.urlparse(url).path.lower()
        if path.endswith(".xlsx"):
            return (0, url)
        if path.endswith(".xls"):
            return (1, url)
        if path.endswith(".zip"):
            return (2, url)
        if path.endswith(".pdf"):
            return (3, url)
        return (4, url)

    return sorted(found, key=priority)




def extract_central_bank_section_links(raw_html: str, base_url: str) -> List[str]:
    """Find report sub-pages specifically devoted to central banks/official sector."""
    links: List[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", raw_html):
        href, anchor_html = match.group(1), match.group(2)
        anchor = strip_html(anchor_html).lower()
        combined = f"{href} {anchor}".lower().replace("&amp;", "&")
        if not re.search(r"central[\s-]*banks?|official[\s-]*sector", combined):
            continue
        absolute = absolute_gold_url(base_url, href)
        if absolute is None or "/gold-demand-trends/" not in absolute:
            continue
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    # Canonical named sections first; numeric Drupal child nodes second.
    return sorted(links, key=lambda u: (0 if "central-bank" in u.lower() or "official-sector" in u.lower() else 1, u))


def attachment_cache_path(cache_dir: Path, quarter: str, url: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    basename = Path(parsed.path).name or "attachment.bin"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{quarter}_{basename}")[-180:]
    return cache_dir / safe


def _number_from_cell(value: Any) -> Optional[float]:
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip().replace(",", "").replace("−", "-")
    # Do not treat year/quarter labels as values.
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None
    return parse_float(text)


def _quarter_header_score(text: str, quarter: str) -> float:
    year = int(quarter[:4])
    qnum = int(quarter[-1])
    normalized = str(text).lower().replace("’", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    exact_patterns = [
        rf"\bq\s*{qnum}\s*['-]?\s*{str(year)[-2:]}\b",
        rf"\bq\s*{qnum}\s+{year}\b",
        rf"\b{year}\s*q\s*{qnum}\b",
        rf"\b{year}\s+q\s*{qnum}\b",
    ]
    if any(re.search(pat, normalized) for pat in exact_patterns):
        return 0.34
    if re.search(rf"\bq\s*{qnum}\b", normalized):
        return 0.18
    return 0.0


def extract_excel_purchase_candidates(path: Path, quarter: str) -> List[Dict[str, Any]]:
    """Extract the report-quarter official-sector value from WGC tables.

    The workbook layouts change across vintages.  We therefore use the row label
    plus the column headers above each numeric cell, rather than fixed sheet or
    cell coordinates.  Exact quarter/year headers receive the strongest score.
    """
    candidates: List[Dict[str, Any]] = []
    try:
        book = pd.ExcelFile(path, engine="openpyxl")
    except Exception:
        return candidates
    label_re = re.compile(r"central\s+banks?|official\s+sector|central\s+bank\s+and\s+other\s+institutions", re.I)
    for sheet in book.sheet_names:
        try:
            frame = pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
        except Exception:
            continue
        if frame.empty:
            continue
        frame = frame.iloc[:1200, :220]
        sheet_head = " ".join(str(x) for x in frame.iloc[:20, :20].to_numpy().ravel() if pd.notna(x))
        for r in range(len(frame)):
            row_values = frame.iloc[r].tolist()
            for label_col, raw_label in enumerate(row_values):
                if pd.isna(raw_label) or not label_re.search(str(raw_label)):
                    continue
                label_text = str(raw_label)
                for col in range(label_col + 1, len(row_values)):
                    value = _number_from_cell(row_values[col])
                    if value is None or abs(value) > float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"]):
                        continue
                    header_values = []
                    for rr in range(max(0, r - 14), r):
                        cell = frame.iat[rr, col]
                        if pd.notna(cell):
                            header_values.append(str(cell))
                    header = " | ".join(header_values)
                    score = 0.58 + _quarter_header_score(header, quarter)
                    if _quarter_header_score(sheet_head, quarter) > 0 and re.search(rf"\bq\s*{quarter[-1]}\b", header.lower()):
                        score += 0.10
                    if re.search(r"annual|full\s*year|year\s*total|fy\b", header, flags=re.I):
                        score -= 0.28
                    if re.search(r"change|%|growth|yoy|year.on.year", header, flags=re.I):
                        score -= 0.25
                    candidates.append({
                        "value_tonnes": value,
                        "confidence": max(0.0, min(1.0, score)),
                        "method": "WGC_ATTACHMENT_EXCEL_TABLE",
                        "context": f"sheet={sheet}; label={label_text}; header={header}",
                        "start": r * 1000 + col,
                    })
    try:
        book.close()
    except Exception:
        pass
    dedup: Dict[Tuple[float, str], Dict[str, Any]] = {}
    for row in candidates:
        key = (round(float(row["value_tonnes"]), 6), str(row["method"]))
        if key not in dedup or float(row["confidence"]) > float(dedup[key]["confidence"]):
            dedup[key] = row
    return sorted(dedup.values(), key=lambda x: (-float(x["confidence"]), int(x["start"])))


def convert_legacy_xls(path: Path, work_dir: Path) -> Optional[Path]:
    """Convert legacy XLS to XLSX with the system LibreOffice when available."""
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "xlsx", "--outdir", str(work_dir), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception:
        return None
    candidate = work_dir / (path.stem + ".xlsx")
    return candidate if proc.returncode == 0 and candidate.exists() else None


def extract_pdf_text(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout if proc.returncode == 0 else ""



def _quarter_positions_in_line(line: str, quarter: str) -> List[int]:
    year = int(quarter[:4])
    yy = str(year)[-2:]
    qnum = quarter[-1]
    patterns = [
        rf"q\s*{qnum}\s*['’\-]?\s*{yy}\b",
        rf"q\s*{qnum}\s+{year}\b",
        rf"{year}\s*q\s*{qnum}\b",
    ]
    positions: List[int] = []
    for pattern in patterns:
        positions.extend(m.start() for m in re.finditer(pattern, line, flags=re.I))
    return positions


def extract_pdf_purchase_candidates(path: Path, quarter: str) -> List[Dict[str, Any]]:
    text = extract_pdf_text(path)
    if not text:
        return []
    candidates = extract_purchase_candidates(text, quarter)
    # Table rows sometimes separate the sector label and value without a verb.
    qnum = quarter[-1]
    year = quarter[:4]
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not re.search(r"central\s+banks?|official\s+sector", line, flags=re.I):
            continue
        header_lines = lines[max(0, idx - 12):idx]
        target_positions: List[int] = []
        for header_line in header_lines:
            target_positions.extend(_quarter_positions_in_line(header_line, quarter))
        nearby = " ".join(header_lines + [line])
        numeric_matches = list(re.finditer(r"(?<![\d.])([+-]?\d{1,4}(?:,\d{3})*(?:\.\d+)?)\s*(?:t|tonnes?)?\b", line))
        aligned_added = False
        if target_positions and numeric_matches:
            target = target_positions[-1]
            ranked = sorted(numeric_matches, key=lambda match: abs(match.start(1) - target))
            for match in ranked:
                value = parse_float(match.group(1))
                if value is None or 1900 <= abs(value) <= 2100 or abs(value) > float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"]):
                    continue
                candidates.append({
                    "value_tonnes": value,
                    "confidence": 0.99,
                    "method": "WGC_ATTACHMENT_PDF_ALIGNED_TABLE",
                    "context": f"line={line.strip()}; target_column={target}; nearby={nearby[:500]}",
                    "start": idx * 1000 + match.start(1),
                })
                aligned_added = True
                break
        if aligned_added:
            continue
        quarter_bonus = _quarter_header_score(nearby, quarter)
        for match in numeric_matches:
            value = parse_float(match.group(1))
            if value is None or abs(value) > float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"]):
                continue
            if 1900 <= abs(value) <= 2100:
                continue
            candidates.append({
                "value_tonnes": value,
                "confidence": min(1.0, 0.55 + quarter_bonus),
                "method": "WGC_ATTACHMENT_PDF_TABLE",
                "context": f"line={line.strip()}; nearby={nearby[:500]}",
                "start": idx * 1000 + match.start(1),
            })
    dedup: Dict[Tuple[float, str], Dict[str, Any]] = {}
    for row in candidates:
        key = (round(float(row["value_tonnes"]), 6), str(row["method"]))
        if key not in dedup or float(row["confidence"]) > float(dedup[key]["confidence"]):
            dedup[key] = row
    return sorted(dedup.values(), key=lambda x: (-float(x["confidence"]), int(x["start"])))


def extract_attachment_candidates(path: Path, quarter: str, work_dir: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return extract_excel_purchase_candidates(path, quarter)
    if suffix == ".xls":
        converted = convert_legacy_xls(path, work_dir)
        return extract_excel_purchase_candidates(converted, quarter) if converted else []
    if suffix == ".pdf":
        return extract_pdf_purchase_candidates(path, quarter)
    if suffix == ".zip":
        rows: List[Dict[str, Any]] = []
        try:
            with zipfile.ZipFile(path) as zf:
                extract_dir = work_dir / path.stem
                extract_dir.mkdir(parents=True, exist_ok=True)
                for info in zf.infolist():
                    if info.is_dir() or Path(info.filename).suffix.lower() not in _DOWNLOAD_EXTENSIONS[:-1]:
                        continue
                    target = extract_dir / Path(info.filename).name
                    with zf.open(info) as src, target.open("wb") as dst:
                        dst.write(src.read())
                    rows.extend(extract_attachment_candidates(target, quarter, work_dir))
        except Exception:
            return []
        return rows
    return []


_PURCHASE_PATTERNS: List[Tuple[str, float, str]] = [
    (r"central\s+banks?\s+(?:bought|purchased|added|acquired)\s+(?:a\s+net\s+)?(?:estimated\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.99, "CENTRAL_BANKS_VERB_VALUE"),
    (r"official\s+sector\s+(?:was|were|became|remained)?\s*(?:a\s+)?net\s+(?:buyer|purchaser)\s+(?:of\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.98, "OFFICIAL_SECTOR_NET_BUYER_VALUE"),
    (r"official\s+sector\s+(?:net\s+)?(?:purchases|buying|demand)\s+(?:totalled|totaled|reached|was|stood\s+at|amounted\s+to)?\s*(?:an\s+estimated\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.96, "OFFICIAL_SECTOR_CONTEXT_VALUE"),
    (r"central\s+banks?\s+and\s+other\s+(?:official\s+)?institutions?[^.]{0,100}?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.94, "CENTRAL_BANKS_OTHER_INSTITUTIONS_VALUE"),
    (r"central\s+bank\s+(?:gold\s+)?demand\s+(?:totalled|totaled|reached|was|stood\s+at|amounted\s+to)\s+(?:an\s+estimated\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.98, "CENTRAL_BANK_DEMAND_VALUE"),
    (r"(?:estimated\s+)?net\s+purchases\s+of\s+([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.93, "NET_PURCHASES_OF_VALUE"),
    (r"central\s+banks?[^.]{0,180}?(?:net\s+)?(?:buying|purchases|demand)[^.]{0,100}?([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\b", 0.90, "CENTRAL_BANK_CONTEXT_VALUE"),
    (r"([+-]?\d+(?:\.\d+)?)\s*(?:t|tonnes?)\s+(?:of\s+)?(?:net\s+)?(?:central\s+bank|official\s+sector)\s+(?:buying|purchases|demand)", 0.90, "VALUE_CENTRAL_BANK_CONTEXT"),
]


def extract_purchase_candidates(text: str, quarter: Optional[str] = None) -> List[Dict[str, Any]]:
    lower = text.lower().replace(",", "").replace("−", "-")
    rows: List[Dict[str, Any]] = []
    for pattern, confidence, method in _PURCHASE_PATTERNS:
        for m in re.finditer(pattern, lower, flags=re.I):
            value = parse_float(m.group(1))
            if value is None:
                continue
            context = lower[max(0, m.start() - 140): min(len(lower), m.end() + 140)]
            sentence_start = max(lower.rfind(".", 0, m.start()), lower.rfind(";", 0, m.start())) + 1
            next_period = lower.find(".", m.end())
            next_semicolon = lower.find(";", m.end())
            sentence_ends = [x for x in [next_period, next_semicolon] if x >= 0]
            sentence_end = min(sentence_ends) if sentence_ends else min(len(lower), m.end() + 220)
            local = lower[sentence_start:sentence_end]
            # Annual, YTD and multi-period values are common on report pages.
            # The requested report quarter must dominate those summaries.
            adjusted = confidence
            if any(token in local for token in ["year-to-date", "year to date", "ytd", "first half", "h1 buying", "h2 buying"]):
                adjusted -= 0.38
            if any(token in local for token in ["full year", "annual", "year total", "for the year"]):
                adjusted -= 0.30
            if quarter:
                qbonus = _quarter_header_score(local, quarter)
                adjusted += qbonus
                # Mentions of another explicit quarter near the value reduce confidence.
                qnum = quarter[-1]
                other_quarter = re.search(rf"\bq(?!{qnum}\b)[1-4]\b", local)
                if other_quarter and qbonus == 0:
                    adjusted -= 0.18
            elif re.search(r"\bq[1-4]\b", local):
                adjusted += 0.10
            if abs(value) > float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"]):
                adjusted -= 0.50
            rows.append({
                "value_tonnes": value,
                "confidence": max(0.0, min(1.0, adjusted)),
                "method": method,
                "context": context,
                "start": m.start(),
            })
    # De-duplicate exact value/context families; keep highest confidence.
    dedup: Dict[Tuple[float, str], Dict[str, Any]] = {}
    for row in rows:
        key = (round(float(row["value_tonnes"]), 6), str(row["method"]))
        if key not in dedup or row["confidence"] > dedup[key]["confidence"]:
            dedup[key] = row
    return sorted(dedup.values(), key=lambda r: (-float(r["confidence"]), int(r["start"])))


def choose_purchase_candidate(candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {"status": "NO_PURCHASE_VALUE_FOUND"}
    best = dict(candidates[0])
    runner = dict(candidates[1]) if len(candidates) > 1 else None
    conflicting = [
        c for c in candidates[1:]
        if abs(float(c["value_tonnes"]) - float(best["value_tonnes"])) > 3.0
        and float(c["confidence"]) >= float(best["confidence"]) - 0.03
    ]
    passed = (
        float(best["confidence"]) >= float(LOCKED_CONTRACT["minimum_extraction_confidence"])
        and not conflicting
        and abs(float(best["value_tonnes"])) <= float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"])
    )
    return {
        "status": "PASS" if passed else "AMBIGUOUS_OR_LOW_CONFIDENCE",
        "best": best,
        "runner_up": runner,
        "conflicts": conflicting,
    }


def fetch_url(
    url: str,
    config: Dict[str, Any],
    progress: Optional[ProgressReporter] = None,
    *,
    phase: str = "WGC_FETCH",
    label: str = "",
    extra_headers: Optional[Dict[str, str]] = None,
    permanent_http_statuses: Optional[Sequence[int]] = None,
) -> Tuple[bool, bytes, str]:
    attempts = max(1, int(config.get("max_retries", 2)) + 1)
    timeout = float(config.get("timeout_seconds", 35))
    delay = float(config.get("retry_backoff_seconds", 3.0))
    user_agent = str(config.get("user_agent", "Mozilla/5.0 Stage176 Research Audit"))
    context = ssl.create_default_context()
    last_error = ""
    for attempt in range(attempts):
        if progress is not None:
            progress.emit(
                phase,
                f"fetch start attempt={attempt + 1}/{attempts} timeout={timeout:.0f}s {label} url={url}",
                details={"url": url, "attempt": attempt + 1, "attempts": attempts, "timeout_seconds": timeout},
            )
        headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})
        req = urllib.request.Request(url, headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                content = response.read()
            if progress is not None:
                progress.emit(
                    phase,
                    f"fetch success bytes={len(content)} duration={time.monotonic() - started:.1f}s {label}",
                    details={"url": url, "bytes": len(content), "attempt": attempt + 1},
                )
            return True, content, ""
        except urllib.error.HTTPError as exc:
            last_error = f"HTTPError:{exc}"
            status_code = int(getattr(exc, "code", 0))
            permanent_set = {400, 404, 410}
            if permanent_http_statuses:
                permanent_set.update(int(code) for code in permanent_http_statuses)
            permanent = status_code in permanent_set
            if progress is not None:
                progress.emit(
                    phase,
                    f"fetch failed attempt={attempt + 1}/{attempts} duration={time.monotonic() - started:.1f}s error={last_error} permanent={permanent} {label}",
                    details={
                        "url": url,
                        "attempt": attempt + 1,
                        "error": last_error,
                        "http_status": status_code,
                        "permanent": permanent,
                    },
                )
            if permanent:
                if progress is not None:
                    progress.emit(phase, f"permanent HTTP status; skip without retry {label}")
                break
            if attempt + 1 < attempts:
                wait = min(60.0, delay * (2 ** attempt))
                if progress is not None:
                    progress.emit(phase, f"retry backoff {wait:.1f}s {label}")
                time.sleep(wait)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}:{exc}"
            if progress is not None:
                progress.emit(
                    phase,
                    f"fetch failed attempt={attempt + 1}/{attempts} duration={time.monotonic() - started:.1f}s error={last_error} {label}",
                    details={"url": url, "attempt": attempt + 1, "error": last_error},
                )
            if attempt + 1 < attempts:
                wait = min(60.0, delay * (2 ** attempt))
                if progress is not None:
                    progress.emit(phase, f"retry backoff {wait:.1f}s {label}")
                time.sleep(wait)
    return False, b"", last_error


def discover_report_urls(
    config: Dict[str, Any],
    progress: Optional[ProgressReporter] = None,
    checkpoint_path: Optional[Path] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    urls: set[str] = set()
    ledger: List[Dict[str, Any]] = []
    max_pages = int(config.get("max_index_pages", 12))
    max_failures = max(1, int(config.get("max_consecutive_index_failures", 3)))
    consecutive_failures = 0
    processed_pages = 0
    stopped_early = False
    template = str(config["index_url_template"])
    if progress is not None:
        progress.emit("WGC_INDEX", f"archive discovery started max_pages={max_pages}", current=0, total=max_pages)
    for page in range(max_pages):
        processed_pages = page + 1
        url = template.format(page=page)
        if progress is not None:
            progress.emit("WGC_INDEX", f"processing archive index page={page} discovered_reports={len(urls)}", current=page, total=max_pages)
        ok, content, error = fetch_url(url, config, progress, phase="WGC_INDEX_FETCH", label=f"index_page={page}")
        ledger.append({"kind": "INDEX", "url": url, "success": ok, "error": error, "bytes": len(content)})
        if checkpoint_path is not None:
            write_csv(checkpoint_path, ledger)
        if not ok:
            consecutive_failures += 1
            if progress is not None:
                progress.emit(
                    "WGC_INDEX",
                    f"index failure streak={consecutive_failures}/{max_failures}",
                    current=page + 1,
                    total=max_pages,
                )
            if consecutive_failures >= max_failures:
                stopped_early = True
                if progress is not None:
                    progress.emit("WGC_INDEX", "circuit breaker: consecutive index failures reached limit", current=processed_pages, total=max_pages, status="BLOCKED")
                break
            continue
        consecutive_failures = 0
        raw = content.decode("utf-8", errors="replace")
        found = 0
        for href in re.findall(r"href=[\"']([^\"']+)[\"']", raw, flags=re.I):
            absolute = absolute_gold_url(url, href)
            if absolute is None or "/gold-demand-trends" not in absolute:
                continue
            parsed_path = urllib.parse.urlparse(absolute).path.lower()
            # Only the global GDT report series is admissible. Regional,
            # translated and India-focus pages can duplicate a quarter with a
            # different publication time or non-global demand value.
            if not parsed_path.startswith("/goldhub/research/gold-demand-trends/gold-demand-trends-"):
                continue
            if any(token in parsed_path for token in ["-japanese", "india-focus", "us-gold-demand-trends"]):
                continue
            root = normalize_report_root(absolute)
            qlabel = infer_quarter_from_text(root, root)
            if qlabel is None:
                continue
            # Stage176's locked data contract begins at 2010Q1. Older report
            # pages are irrelevant and many legacy URL shapes return permanent
            # 404 responses, so they must never enter the fetch queue.
            if quarter_end_from_label(qlabel) < quarter_end_from_label(str(LOCKED_CONTRACT["earliest_required_quarter"])):
                continue
            if root not in urls:
                urls.add(root)
                found += 1
        if progress is not None:
            progress.emit(
                "WGC_INDEX",
                f"page complete new_reports={found} total_reports={len(urls)}",
                current=page + 1,
                total=max_pages,
            )
        if page >= 2 and found == 0:
            # Keep crawling only while the archive still yields unseen reports.
            stopped_early = True
            break
        time.sleep(float(config.get("request_delay_seconds", 0.2)))
    if progress is not None:
        progress.emit(
            "WGC_INDEX",
            f"archive discovery complete reports={len(urls)} processed_pages={processed_pages}",
            current=processed_pages,
            total=max_pages,
            status="BLOCKED" if stopped_early and not urls else "COMPLETE",
        )
    return sorted(urls, key=lambda item: quarter_end_from_label(infer_quarter_from_text("", item) or "9999Q4")), ledger


def extract_report_vintage(
    report_url: str,
    raw_html: str,
    snapshot_path: Path,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    text = strip_html(raw_html)
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    title = strip_html(title_match.group(1)) if title_match else text[:300]
    qlabel = infer_quarter_from_text(title, report_url)
    release = extract_publication_timestamp(raw_html, visible_text=text, quarter=qlabel)
    candidates = extract_purchase_candidates(text, qlabel)
    selected = choose_purchase_candidate(candidates)
    candidate_rows = []
    for rank, c in enumerate(candidates, start=1):
        candidate_rows.append({
            "report_url": report_url,
            "quarter": qlabel,
            "release_timestamp_utc": release.isoformat() if release is not None else None,
            "rank": rank,
            **c,
        })
    if qlabel is None or release is None or selected.get("status") != "PASS":
        return None, candidate_rows
    best = selected["best"]
    row = {
        "quarter": qlabel,
        "quarter_end_utc": quarter_end_from_label(qlabel).isoformat(),
        "release_timestamp_utc": release.isoformat(),
        "official_sector_purchases_tonnes": float(best["value_tonnes"]),
        "source_url": report_url,
        "source_file": str(snapshot_path),
        "source_sha256": sha256(snapshot_path),
        "source_kind": "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_REPORT_PAGE",
        "extraction_method": str(best["method"]),
        "extraction_confidence": float(best["confidence"]),
        "is_original_publication": True,
        "notes": "Quarter-specific value extracted from original WGC report page; latest revised workbook not used as historical vintage.",
    }
    return row, candidate_rows




def recover_vintage_from_sections(
    report_url: str,
    raw_html: str,
    config: Dict[str, Any],
    cache_dir: Path,
    progress: Optional[ProgressReporter] = None,
    *,
    label: str = "",
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Prefer the period-specific WGC central-bank section over report summaries."""
    qlabel = infer_quarter_from_text("", report_url) or "unknown"
    rows: List[Dict[str, Any]] = []
    ledger: List[Dict[str, Any]] = []
    for idx, section_url in enumerate(extract_central_bank_section_links(raw_html, report_url), start=1):
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{qlabel}_section_{urllib.parse.urlparse(section_url).path.strip('/')}")[-180:]
        snapshot = cache_dir / f"{safe}.html"
        payload: Optional[bytes] = None
        if snapshot.exists() and snapshot.stat().st_size > 500:
            payload = snapshot.read_bytes()
            ledger.append({"kind": "SECTION_CACHE", "url": section_url, "success": True, "error": "", "bytes": len(payload)})
            if progress is not None:
                progress.emit("WGC_SECTION", f"cache hit quarter={qlabel} section={idx} bytes={len(payload)} {label}")
        else:
            ok, content, error = fetch_url(
                section_url,
                config,
                progress,
                phase="WGC_SECTION_FETCH",
                label=f"quarter={qlabel} section={idx} {label}",
                extra_headers={"Referer": report_url},
            )
            ledger.append({"kind": "SECTION", "url": section_url, "success": ok, "error": error, "bytes": len(content)})
            if ok and len(content) > 500:
                snapshot.write_bytes(content)
                payload = content
        if payload is None:
            continue
        row, candidates = extract_report_vintage(section_url, payload.decode("utf-8", errors="replace"), snapshot)
        rows.extend(candidates)
        if row is not None:
            row["source_kind"] = "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_CENTRAL_BANK_SECTION"
            row["notes"] = "Quarter-specific value extracted from the original WGC central-bank section page."
            return row, rows, ledger
    return None, rows, ledger



def fetch_attachment_with_curl(
    url: str,
    report_url: str,
    config: Dict[str, Any],
    work_dir: Path,
    progress: Optional[ProgressReporter] = None,
    *,
    label: str = "",
) -> Tuple[bool, bytes, str]:
    """Browser-like curl fallback for WGC download endpoints that reject urllib."""
    work_dir.mkdir(parents=True, exist_ok=True)
    output = work_dir / ("curl_" + sha256_text(url)[:16] + ".bin")
    cookies = work_dir / ".wgc_cookies.txt"
    user_agent = str(config.get("user_agent", "Mozilla/5.0 Stage176 Research Audit"))
    timeout = max(10, int(float(config.get("timeout_seconds", 35))))
    try:
        # Establish a same-site cookie context. Failure here is non-fatal.
        subprocess.run(
            ["curl", "-L", "--silent", "--max-time", str(timeout), "-A", user_agent, "-c", str(cookies), "-o", "/dev/null", report_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 5,
            check=False,
        )
        proc = subprocess.run(
            [
                "curl", "-L", "--fail", "--silent", "--show-error",
                "--max-time", str(timeout), "-A", user_agent, "-e", report_url,
                "-b", str(cookies), "-c", str(cookies), "-o", str(output), url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 10,
            check=False,
        )
    except Exception as exc:
        return False, b"", f"CURL:{type(exc).__name__}:{exc}"
    if proc.returncode == 0 and output.exists() and output.stat().st_size > 500:
        payload = output.read_bytes()
        if progress is not None:
            progress.emit("WGC_ATTACHMENT_FETCH", f"curl fallback success bytes={len(payload)} {label}")
        return True, payload, ""
    error = proc.stderr.decode("utf-8", errors="replace").strip() if isinstance(proc.stderr, bytes) else str(proc.stderr).strip()
    if progress is not None:
        progress.emit("WGC_ATTACHMENT_FETCH", f"curl fallback failed returncode={proc.returncode} error={error} {label}")
    return False, b"", f"CURL_RETURN_{proc.returncode}:{error}"


def recover_vintage_from_attachments(
    report_url: str,
    raw_html: str,
    snapshot_path: Path,
    config: Dict[str, Any],
    attachment_cache_dir: Path,
    progress: Optional[ProgressReporter] = None,
    *,
    label: str = "",
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Recover a quarter value from original XLS/XLSX/PDF/ZIP attachments."""
    text = strip_html(raw_html)
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    title = strip_html(title_match.group(1)) if title_match else text[:300]
    qlabel = infer_quarter_from_text(title, report_url)
    release = extract_publication_timestamp(raw_html, visible_text=text, quarter=qlabel)
    if qlabel is None or release is None:
        return None, [], []
    links = extract_download_links(raw_html, report_url)
    max_links = max(1, int(config.get("maximum_attachments_per_report", 10)))
    attachment_cache_dir.mkdir(parents=True, exist_ok=True)
    work_dir = attachment_cache_dir / "_converted"
    candidate_rows: List[Dict[str, Any]] = []
    ledger: List[Dict[str, Any]] = []
    runtime_state = config.setdefault(
        "_runtime_attachment_fetch_state",
        {"disabled": False, "consecutive_forbidden": 0, "disable_reason": ""},
    )
    forbidden_limit = max(1, int(config.get("attachment_forbidden_circuit_breaker", 2)))
    for link_index, attachment_url in enumerate(links[:max_links], start=1):
        target = attachment_cache_path(attachment_cache_dir, qlabel, attachment_url)
        content: Optional[bytes] = None
        if target.exists() and target.stat().st_size > 500:
            content = target.read_bytes()
            ledger.append({"kind": "ATTACHMENT_CACHE", "url": attachment_url, "success": True, "error": "", "bytes": len(content)})
            if progress is not None:
                progress.emit("WGC_ATTACHMENT", f"cache hit quarter={qlabel} file={target.name} bytes={len(content)} {label}")
        elif bool(runtime_state.get("disabled", False)):
            error = str(runtime_state.get("disable_reason") or "ATTACHMENT_FETCH_DISABLED_AFTER_REPEATED_403")
            ledger.append({"kind": "ATTACHMENT_SKIPPED", "url": attachment_url, "success": False, "error": error, "bytes": 0})
            if progress is not None:
                progress.emit(
                    "WGC_ATTACHMENT_FETCH",
                    f"attachment network fetch disabled for this run; use page/section/cache only quarter={qlabel} "
                    f"attachment={link_index}/{min(len(links), max_links)} {label}",
                )
            continue
        else:
            ok, payload, error = fetch_url(
                attachment_url,
                config,
                progress,
                phase="WGC_ATTACHMENT_FETCH",
                label=f"quarter={qlabel} attachment={link_index}/{min(len(links), max_links)} {label}",
                extra_headers={
                    "Referer": report_url,
                    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,application/pdf,application/zip,*/*",
                },
                permanent_http_statuses={403},
            )
            forbidden = (not ok) and ("HTTP Error 403" in error or "HTTP_403" in error)
            if forbidden:
                runtime_state["consecutive_forbidden"] = int(runtime_state.get("consecutive_forbidden", 0)) + 1
                if progress is not None:
                    progress.emit(
                        "WGC_ATTACHMENT_FETCH",
                        f"403 is permanent for this attachment endpoint; skip curl and retry "
                        f"streak={runtime_state['consecutive_forbidden']}/{forbidden_limit} quarter={qlabel} {label}",
                    )
                if int(runtime_state["consecutive_forbidden"]) >= forbidden_limit:
                    runtime_state["disabled"] = True
                    runtime_state["disable_reason"] = "ATTACHMENT_FETCH_DISABLED_AFTER_REPEATED_403"
                    if progress is not None:
                        progress.emit(
                            "WGC_ATTACHMENT_FETCH",
                            "circuit breaker: repeated attachment 403 responses; disable uncached attachment downloads "
                            "for the rest of this run and continue with report/section evidence",
                            status="DEGRADED",
                        )
            elif not ok:
                curl_ok, curl_payload, curl_error = fetch_attachment_with_curl(
                    attachment_url,
                    report_url,
                    config,
                    attachment_cache_dir / "_curl",
                    progress,
                    label=f"quarter={qlabel} attachment={link_index}/{min(len(links), max_links)} {label}",
                )
                if curl_ok:
                    ok, payload, error = True, curl_payload, ""
                else:
                    error = f"{error};{curl_error}" if error else curl_error
            if ok:
                runtime_state["consecutive_forbidden"] = 0
            ledger.append({"kind": "ATTACHMENT", "url": attachment_url, "success": ok, "error": error, "bytes": len(payload)})
            if ok and len(payload) > 500:
                target.write_bytes(payload)
                content = payload
        if content is None:
            continue
        extracted = extract_attachment_candidates(target, qlabel, work_dir)
        for rank, candidate in enumerate(extracted, start=1):
            candidate_rows.append({
                "report_url": report_url,
                "quarter": qlabel,
                "release_timestamp_utc": release.isoformat(),
                "rank": rank,
                "attachment_url": attachment_url,
                "source_file": str(target),
                **candidate,
            })
        selected = choose_purchase_candidate(extracted)
        if selected.get("status") != "PASS":
            continue
        best = selected["best"]
        row = {
            "quarter": qlabel,
            "quarter_end_utc": quarter_end_from_label(qlabel).isoformat(),
            "release_timestamp_utc": release.isoformat(),
            "official_sector_purchases_tonnes": float(best["value_tonnes"]),
            "source_url": attachment_url,
            "source_file": str(target),
            "source_sha256": sha256(target),
            "source_kind": "WGC_GOLD_DEMAND_TRENDS_ORIGINAL_ATTACHMENT",
            "extraction_method": str(best["method"]),
            "extraction_confidence": float(best["confidence"]),
            "is_original_publication": True,
            "notes": "Quarter-specific value extracted from an original attachment linked by the WGC report page; latest revised workbook not used.",
        }
        return row, candidate_rows, ledger
    return None, candidate_rows, ledger


def collect_wgc_vintages(
    root: Path,
    config: Dict[str, Any],
    out_dir: Path,
    progress: Optional[ProgressReporter] = None,
) -> Dict[str, Any]:
    cache_dir = resolve(root, config["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    attachment_cache_dir = resolve(
        root,
        config.get("attachment_cache_dir", str(Path(config["cache_dir"]).parent / (Path(config["cache_dir"]).name + "_attachments"))),
    )
    attachment_cache_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "stage176_wgc_online_fetch_ledger.csv"
    candidate_path = out_dir / "stage176_wgc_extraction_candidates.csv"
    urls, fetch_ledger = discover_report_urls(config, progress, ledger_path)
    max_reports = int(config.get("maximum_reports", 90))
    selected_urls = urls[:max_reports]
    checkpoint_every = max(1, int(config.get("checkpoint_every_reports", 1)))
    max_failures = max(1, int(config.get("max_consecutive_report_failures", 8)))
    consecutive_failures = 0
    processed_reports = 0
    stopped_early = False
    rows: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    if progress is not None:
        progress.emit(
            "WGC_REPORTS",
            f"report collection started discovered={len(urls)} selected={len(selected_urls)} cache={cache_dir}",
            current=0,
            total=len(selected_urls),
        )
    for index, report_url in enumerate(selected_urls, start=1):
        processed_reports = index
        qlabel = infer_quarter_from_text("", report_url) or "unknown"
        if progress is not None:
            progress.emit(
                "WGC_REPORTS",
                f"report start quarter={qlabel} valid_rows={len(rows)} candidates={len(candidates)} url={report_url}",
                current=index - 1,
                total=len(selected_urls),
            )
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{qlabel}_{urllib.parse.urlparse(report_url).path.strip('/')}")[-180:]
        snapshot = cache_dir / f"{safe}.html"
        raw: Optional[bytes] = None
        source_url = report_url + "/central-banks"
        if snapshot.exists() and snapshot.stat().st_size > 500:
            raw = snapshot.read_bytes()
            source_url = report_url
            fetch_ledger.append({"kind": "REPORT_CACHE", "url": report_url, "success": True, "error": "", "bytes": len(raw)})
            consecutive_failures = 0
            if progress is not None:
                progress.emit(
                    "WGC_REPORTS",
                    f"cache hit quarter={qlabel} bytes={len(raw)}",
                    current=index,
                    total=len(selected_urls),
                )
        else:
            # Dedicated central-banks page is less ambiguous. Fall back to root.
            for url in [report_url + "/central-banks", report_url]:
                ok, content, error = fetch_url(
                    url,
                    config,
                    progress,
                    phase="WGC_REPORT_FETCH",
                    label=f"report={index}/{len(selected_urls)} quarter={qlabel}",
                )
                fetch_ledger.append({"kind": "REPORT", "url": url, "success": ok, "error": error, "bytes": len(content)})
                if ok and len(content) > 500:
                    raw = content
                    source_url = url
                    snapshot.write_bytes(content)
                    break
        if raw is None:
            consecutive_failures += 1
            if progress is not None:
                progress.emit(
                    "WGC_REPORTS",
                    f"report unavailable quarter={qlabel} failure_streak={consecutive_failures}/{max_failures}",
                    current=index,
                    total=len(selected_urls),
                )
            if index % checkpoint_every == 0:
                write_csv(ledger_path, fetch_ledger)
                write_csv(candidate_path, candidates)
            if consecutive_failures >= max_failures:
                stopped_early = True
                if progress is not None:
                    progress.emit(
                        "WGC_REPORTS",
                        "circuit breaker: consecutive report failures reached limit",
                        current=processed_reports,
                        total=len(selected_urls),
                        status="BLOCKED",
                    )
                break
            continue
        consecutive_failures = 0
        raw_html = raw.decode("utf-8", errors="replace")
        root_row, cand = extract_report_vintage(source_url, raw_html, snapshot)
        candidates.extend(cand)
        section_row, section_candidates, section_ledger = recover_vintage_from_sections(
            report_url,
            raw_html,
            config,
            cache_dir,
            progress,
            label=f"report={index}/{len(selected_urls)}",
        )
        candidates.extend(section_candidates)
        fetch_ledger.extend(section_ledger)
        # A dedicated central-bank section is more period-specific than a report
        # summary, which often mixes quarterly, YTD and full-year values.
        row = section_row or root_row
        attachment_candidates: List[Dict[str, Any]] = []
        if row is None:
            recovered, attachment_candidates, attachment_ledger = recover_vintage_from_attachments(
                report_url,
                raw_html,
                snapshot,
                config,
                attachment_cache_dir,
                progress,
                label=f"report={index}/{len(selected_urls)}",
            )
            candidates.extend(attachment_candidates)
            fetch_ledger.extend(attachment_ledger)
            if recovered is not None:
                row = recovered
        if row:
            rows.append(row)
            extraction = (
                f"PASS value={row['official_sector_purchases_tonnes']:.3f}t "
                f"release={row['release_timestamp_utc']} source_kind={row['source_kind']}"
            )
        else:
            extraction = (
                f"NO_VALID_ROW page_candidates={len(cand)} "
                f"section_candidates={len(section_candidates)} attachment_candidates={len(attachment_candidates)}"
            )
        if progress is not None:
            progress.emit(
                "WGC_REPORTS",
                f"report complete quarter={qlabel} extraction={extraction} valid_rows={len(rows)}",
                current=index,
                total=len(selected_urls),
            )
        if index % checkpoint_every == 0:
            write_csv(ledger_path, fetch_ledger)
            write_csv(candidate_path, candidates)
        time.sleep(float(config.get("request_delay_seconds", 0.2)))
    write_csv(ledger_path, fetch_ledger)
    write_csv(candidate_path, candidates)
    canonical = resolve(root, config["canonical_manifest_output"])
    unique_rows = 0
    if rows:
        # Earliest original release per quarter is the vintage contract.
        frame = pd.DataFrame(rows)
        frame["release_timestamp_utc"] = pd.to_datetime(frame["release_timestamp_utc"], utc=True)
        frame = frame.sort_values(["quarter", "release_timestamp_utc", "extraction_confidence"], ascending=[True, True, False])
        frame = frame.drop_duplicates("quarter", keep="first")
        unique_rows = int(len(frame))
        ensure_parent(canonical)
        frame.to_csv(canonical, index=False)
    if progress is not None:
        progress.emit(
            "WGC_REPORTS",
            f"collection complete unique_valid_quarters={unique_rows} raw_valid_rows={len(rows)} manifest={canonical}",
            current=processed_reports,
            total=len(selected_urls),
            status="BLOCKED" if stopped_early else "COMPLETE",
        )
    return {
        "status": "COLLECTED" if rows else "NO_VALID_VINTAGES_COLLECTED",
        "discovered_report_urls": len(urls),
        "selected_report_urls": len(selected_urls),
        "processed_report_urls": processed_reports,
        "stopped_early": stopped_early,
        "valid_quarter_rows": unique_rows,
        "raw_valid_rows": len(rows),
        "manifest_output": str(canonical),
        "candidate_output": str(candidate_path),
        "fetch_ledger_output": str(ledger_path),
        "attachment_cache_dir": str(attachment_cache_dir),
    }


def first_existing(root: Path, candidates: Sequence[str]) -> Optional[Path]:
    for item in candidates:
        p = resolve(root, item)
        if p.exists() and p.is_file():
            return p.resolve()
    return None


def load_vintage_manifest(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    aliases = {
        "quarter": ["quarter", "period", "quarter_label"],
        "quarter_end_utc": ["quarter_end_utc", "quarter_end", "period_end"],
        "release_timestamp_utc": ["release_timestamp_utc", "release_date_utc", "published_utc", "publication_date"],
        "official_sector_purchases_tonnes": ["official_sector_purchases_tonnes", "central_bank_demand_tonnes", "purchases_tonnes", "value_tonnes"],
        "source_url": ["source_url", "url"],
        "source_file": ["source_file", "file", "snapshot_path"],
        "source_sha256": ["source_sha256", "sha256"],
        "source_kind": ["source_kind", "source_type"],
        "extraction_method": ["extraction_method", "method"],
        "extraction_confidence": ["extraction_confidence", "confidence"],
        "is_original_publication": ["is_original_publication", "original_publication", "is_original"],
        "notes": ["notes", "comment"],
    }
    selected: Dict[str, Optional[str]] = {}
    for target, options in aliases.items():
        selected[target] = next((cmap[o] for o in options if o in cmap), None)
    required = ["release_timestamp_utc", "official_sector_purchases_tonnes", "source_sha256", "is_original_publication"]
    missing = [c for c in required if selected[c] is None]
    if missing:
        raise ValueError(f"Vintage manifest missing columns: {missing}; columns={list(raw.columns)}")
    rows = pd.DataFrame()
    if selected["quarter"] is not None:
        rows["quarter"] = raw[selected["quarter"]].astype(str).str.strip().str.upper()
    elif selected["quarter_end_utc"] is not None:
        qend = pd.to_datetime(raw[selected["quarter_end_utc"]], errors="coerce", utc=True)
        rows["quarter"] = qend.map(lambda x: quarter_label(x) if pd.notna(x) else None)
    else:
        raise ValueError("Vintage manifest needs quarter or quarter_end_utc")
    rows["quarter_end_utc"] = rows["quarter"].map(lambda q: quarter_end_from_label(q) if isinstance(q, str) and re.fullmatch(r"\d{4}Q[1-4]", q) else pd.NaT)
    rows["release_timestamp_utc"] = pd.to_datetime(raw[selected["release_timestamp_utc"]], errors="coerce", utc=True)
    rows["official_sector_purchases_tonnes"] = pd.to_numeric(raw[selected["official_sector_purchases_tonnes"]], errors="coerce")
    for col in ["source_url", "source_file", "source_sha256", "source_kind", "extraction_method", "notes"]:
        source = selected[col]
        rows[col] = raw[source].astype(str).str.strip() if source is not None else ""
    source = selected["extraction_confidence"]
    rows["extraction_confidence"] = pd.to_numeric(raw[source], errors="coerce") if source is not None else 1.0
    rows["is_original_publication"] = raw[selected["is_original_publication"]].map(parse_bool)
    return rows


def validate_vintage_manifest(frame: pd.DataFrame, root: Path) -> Tuple[Dict[str, Any], pd.DataFrame, List[Dict[str, Any]]]:
    rows = frame.copy()
    checks: List[Dict[str, Any]] = []
    rows = rows.dropna(subset=["quarter_end_utc", "release_timestamp_utc", "official_sector_purchases_tonnes"]).copy()
    rows["release_lag_days"] = (rows["release_timestamp_utc"] - rows["quarter_end_utc"]).dt.total_seconds() / 86400.0
    rows["source_hash_present"] = rows["source_sha256"].astype(str).str.fullmatch(r"[0-9a-fA-F]{64}").fillna(False)
    rows["source_file_exists"] = rows["source_file"].map(
        lambda x: bool(str(x).strip()) and resolve(root, str(x)).exists()
    )
    hash_cache: Dict[str, str] = {}
    def source_file_hash_match(row: pd.Series) -> bool:
        if not bool(row["source_file_exists"]):
            return False
        p = resolve(root, str(row["source_file"])).resolve()
        key = str(p)
        if key not in hash_cache:
            hash_cache[key] = sha256(p)
        return hash_cache[key].lower() == str(row["source_sha256"]).lower()
    rows["source_hash_matches_file"] = rows.apply(source_file_hash_match, axis=1)
    rows["source_url_present"] = rows["source_url"].astype(str).str.startswith("http")
    rows["source_traceable"] = rows["source_hash_present"] & (rows["source_hash_matches_file"] | rows["source_url_present"])
    rows["row_valid"] = (
        rows["is_original_publication"]
        & rows["source_traceable"]
        & rows["extraction_confidence"].fillna(0).ge(float(LOCKED_CONTRACT["minimum_extraction_confidence"]))
        & rows["official_sector_purchases_tonnes"].abs().le(float(LOCKED_CONTRACT["maximum_abs_quarterly_purchases_tonnes"]))
        & rows["release_lag_days"].between(
            float(LOCKED_CONTRACT["minimum_release_lag_days"]),
            float(LOCKED_CONTRACT["maximum_release_lag_days"]),
        )
    )
    invalid_rows = rows[~rows["row_valid"]].copy()
    valid = rows[rows["row_valid"]].copy()

    conflicts = []
    for q, group in valid.groupby("quarter"):
        span = float(group["official_sector_purchases_tonnes"].max() - group["official_sector_purchases_tonnes"].min())
        if len(group) > 1 and span > float(LOCKED_CONTRACT["maximum_duplicate_conflict_tonnes"]):
            conflicts.append({"quarter": q, "rows": int(len(group)), "value_span_tonnes": span})
    valid = valid.sort_values(["quarter_end_utc", "release_timestamp_utc"]).drop_duplicates("quarter", keep="first")
    valid = valid.sort_values("quarter_end_utc").reset_index(drop=True)

    if valid.empty:
        earliest = latest = None
        missing_quarters: List[str] = []
    else:
        earliest = str(valid.iloc[0]["quarter"])
        latest = str(valid.iloc[-1]["quarter"])
        expected = quarter_sequence(str(LOCKED_CONTRACT["earliest_required_quarter"]), latest)
        missing_quarters = sorted(set(expected) - set(valid["quarter"]))

    checks.extend([
        {"gate": "minimum_total_quarters", "pass": len(valid) >= int(LOCKED_CONTRACT["minimum_total_quarters"]), "actual": len(valid), "required": LOCKED_CONTRACT["minimum_total_quarters"]},
        {"gate": "earliest_required_quarter", "pass": earliest == str(LOCKED_CONTRACT["earliest_required_quarter"]), "actual": earliest, "required": LOCKED_CONTRACT["earliest_required_quarter"]},
        {"gate": "maximum_missing_quarters", "pass": len(missing_quarters) <= int(LOCKED_CONTRACT["maximum_missing_quarters"]), "actual": len(missing_quarters), "required": LOCKED_CONTRACT["maximum_missing_quarters"]},
        {"gate": "no_duplicate_conflicts", "pass": not conflicts, "actual": len(conflicts), "required": 0},
        {"gate": "all_rows_original_traceable", "pass": invalid_rows.empty, "actual": int(len(invalid_rows)), "required": 0},
    ])
    passed = all(bool(x["pass"]) for x in checks)
    result = {
        "status": "PASS" if passed else "FAIL",
        "valid_quarters": int(len(valid)),
        "earliest_quarter": earliest,
        "latest_quarter": latest,
        "missing_quarters": missing_quarters,
        "duplicate_conflicts": conflicts,
        "invalid_rows": int(len(invalid_rows)),
        "checks": checks,
    }
    audit_rows = rows.to_dict("records")
    return result, valid, audit_rows


def candidate_price_paths(root: Path, config: Dict[str, Any]) -> List[Path]:
    paths: List[Path] = []
    seen = set()
    for item in config.get("candidates", []):
        p = resolve(root, item)
        if p.exists() and p.is_file():
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                paths.append(p.resolve())
    for pattern in config.get("globs", []):
        for p in root.glob(pattern):
            if p.is_file() and p.suffix.lower() in {".csv", ".txt"}:
                rp = str(p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    paths.append(p.resolve())
    return paths[: int(config.get("maximum_candidates", 100))]


def load_gold_prices(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    date_col = next((cmap[k] for k in ["timestamp_utc", "timestamp", "datetime", "date_utc", "date", "time"] if k in cmap), None)
    if date_col is None and "<date>" in cmap:
        if "<time>" in cmap:
            stamps = raw[cmap["<date>"]].astype(str).str.strip() + " " + raw[cmap["<time>"]].astype(str).str.strip()
        else:
            stamps = raw[cmap["<date>"]]
    elif date_col is not None:
        stamps = raw[date_col]
    else:
        raise ValueError(f"No timestamp columns in {path}; columns={list(raw.columns)}")
    value_col = next((cmap[k] for k in ["close", "<close>", "gold_close", "price", "value", "usd"] if k in cmap), None)
    if value_col is None:
        raise ValueError(f"No gold close/value column in {path}; columns={list(raw.columns)}")
    x = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(stamps, errors="coerce", utc=True),
        "close": pd.to_numeric(raw[value_col], errors="coerce"),
    }).dropna()
    x = x[x["close"].between(100.0, 10000.0)].sort_values("timestamp_utc").drop_duplicates("timestamp_utc", keep="last")
    if x.empty:
        raise ValueError("No plausible gold rows")
    x["date"] = x["timestamp_utc"].dt.floor("D")
    daily = x.groupby("date", as_index=False).agg(close=("close", "last"), source_rows=("close", "size"))
    daily = daily.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    daily["sma200"] = daily["close"].rolling(int(LOCKED_CONTRACT["trend_sma_trading_days"]), min_periods=int(LOCKED_CONTRACT["trend_sma_trading_days"])).mean()
    return daily, {
        "path": str(path),
        "sha256": sha256(path),
        "raw_rows": int(len(raw)),
        "usable_rows": int(len(x)),
        "daily_rows": int(len(daily)),
        "start": daily["date"].min().isoformat(),
        "end": daily["date"].max().isoformat(),
        "median_source_rows_per_day": float(daily["source_rows"].median()),
        "value_column": str(value_col),
    }


def resolve_gold_price_source(root: Path, config: Dict[str, Any], latest_release: pd.Timestamp) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], List[Dict[str, Any]]]:
    inventory: List[Dict[str, Any]] = []
    valid: List[Tuple[pd.DataFrame, Dict[str, Any]]] = []
    for path in candidate_price_paths(root, config):
        try:
            daily, meta = load_gold_prices(path)
            start_ok = daily["date"].min() <= pd.Timestamp(LOCKED_CONTRACT["price_minimum_start_date"], tz="UTC")
            latest_needed = latest_release - pd.Timedelta(days=int(LOCKED_CONTRACT["price_minimum_latest_lag_days"]))
            end_ok = daily["date"].max() >= latest_needed.floor("D")
            sma_ok = int(daily["sma200"].notna().sum()) >= 1000
            meta.update({"start_ok": bool(start_ok), "end_ok": bool(end_ok), "sma_history_ok": bool(sma_ok), "valid": bool(start_ok and end_ok and sma_ok)})
            inventory.append(meta)
            if meta["valid"]:
                valid.append((daily, meta))
        except Exception as exc:  # noqa: BLE001
            inventory.append({"path": str(path), "valid": False, "error": f"{type(exc).__name__}:{exc}"})
    if not valid:
        return None, {"status": "NO_SINGLE_GOLD_SOURCE_WITH_REQUIRED_COVERAGE"}, inventory
    valid.sort(key=lambda item: (pd.Timestamp(item[1]["start"]), -int(item[1]["daily_rows"]), item[1]["path"]))
    daily, meta = valid[0]
    return daily, {"status": "PASS", **meta}, inventory


def last_price_row_on_or_before(prices: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Series]:
    subset = prices[prices["date"] <= ts.floor("D")]
    return subset.iloc[-1] if not subset.empty else None


def first_price_row_after(prices: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Series]:
    subset = prices[prices["date"] > ts.floor("D")]
    return subset.iloc[0] if not subset.empty else None


def build_decision_panel(vintages: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    x = vintages.copy().sort_values("quarter_end_utc").reset_index(drop=True)
    x["trailing_4q_purchases"] = x["official_sector_purchases_tonnes"].rolling(
        int(LOCKED_CONTRACT["trailing_purchase_quarters"]),
        min_periods=int(LOCKED_CONTRACT["trailing_purchase_quarters"]),
    ).sum()
    prior = x["trailing_4q_purchases"].shift(1)
    x["prior_expanding_median"] = prior.expanding(
        min_periods=int(LOCKED_CONTRACT["prior_expanding_median_min_observations"])
    ).median()
    x["two_consecutive_declines"] = (
        (x["official_sector_purchases_tonnes"] < x["official_sector_purchases_tonnes"].shift(1))
        & (x["official_sector_purchases_tonnes"].shift(1) < x["official_sector_purchases_tonnes"].shift(2))
    )
    rows = []
    state = str(LOCKED_CONTRACT["initial_state"])
    cb_state = str(LOCKED_CONTRACT["initial_state"])
    for _, row in x.iterrows():
        release = pd.Timestamp(row["release_timestamp_utc"])
        before = last_price_row_on_or_before(prices, release)
        after = first_price_row_after(prices, release)
        trend_ok = bool(before is not None and pd.notna(before["sma200"]) and float(before["close"]) > float(before["sma200"]))
        accumulation = bool(
            pd.notna(row["trailing_4q_purchases"])
            and pd.notna(row["prior_expanding_median"])
            and float(row["trailing_4q_purchases"]) > float(row["prior_expanding_median"])
        )
        exit_decline = bool(row["two_consecutive_declines"])
        previous_state = state
        previous_cb_state = cb_state
        if exit_decline:
            state = "LOW"
            cb_state = "LOW"
        else:
            if accumulation and trend_ok:
                state = "HIGH"
            if accumulation:
                cb_state = "HIGH"
        rows.append({
            **row.to_dict(),
            "price_observation_date": before["date"] if before is not None else pd.NaT,
            "price_observation_close": float(before["close"]) if before is not None else np.nan,
            "price_observation_sma200": float(before["sma200"]) if before is not None and pd.notna(before["sma200"]) else np.nan,
            "tradable_date": after["date"] if after is not None else pd.NaT,
            "tradable_close": float(after["close"]) if after is not None else np.nan,
            "trend_ok": trend_ok,
            "accumulation_above_prior_median": accumulation,
            "exit_two_quarter_decline": exit_decline,
            "candidate_previous_state": previous_state,
            "candidate_state": state,
            "central_bank_only_previous_state": previous_cb_state,
            "central_bank_only_state": cb_state,
            "price_only_state": "HIGH" if trend_ok else "LOW",
            "always_high_state": "HIGH",
        })
    panel = pd.DataFrame(rows)
    return panel.dropna(subset=["tradable_date", "tradable_close"]).reset_index(drop=True)


def state_exposure(state: Any) -> float:
    return float(LOCKED_CONTRACT["high_exposure"] if str(state).upper() == "HIGH" else LOCKED_CONTRACT["low_exposure"])


def build_interval_returns(panel: pd.DataFrame, switching_cost_bps: float) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    strategies = {
        "candidate": "candidate_state",
        "price_200d": "price_only_state",
        "central_bank_only": "central_bank_only_state",
        "buy_hold": "always_high_state",
    }
    previous_exposure = {key: 0.0 for key in strategies}
    for i in range(len(panel) - 1):
        cur, nxt = panel.iloc[i], panel.iloc[i + 1]
        gross = float(nxt["tradable_close"] / cur["tradable_close"] - 1.0)
        row: Dict[str, Any] = {
            "interval_index": i,
            "quarter": cur["quarter"],
            "quarter_end_utc": cur["quarter_end_utc"],
            "release_timestamp_utc": cur["release_timestamp_utc"],
            "start_date": cur["tradable_date"],
            "end_date": nxt["tradable_date"],
            "gold_gross_return": gross,
            "official_sector_purchases_tonnes": cur["official_sector_purchases_tonnes"],
            "trailing_4q_purchases": cur["trailing_4q_purchases"],
            "prior_expanding_median": cur["prior_expanding_median"],
            "trend_ok": bool(cur["trend_ok"]),
            "exit_two_quarter_decline": bool(cur["exit_two_quarter_decline"]),
        }
        for name, col in strategies.items():
            exposure = state_exposure(cur[col])
            switch = abs(exposure - previous_exposure[name])
            cost = switch * switching_cost_bps / 10000.0
            net = exposure * gross - cost
            row[f"{name}_state"] = cur[col]
            row[f"{name}_exposure"] = exposure
            row[f"{name}_switch_cost"] = cost
            row[f"{name}_net_return"] = net
            previous_exposure[name] = exposure
        rows.append(row)
    return pd.DataFrame(rows)


def max_drawdown(returns: pd.Series) -> float:
    s = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    equity = (1.0 + s).cumprod()
    peaks = equity.cummax()
    dd = 1.0 - equity / peaks
    return float(dd.max()) if len(dd) else 0.0


def annualized_metrics(returns: pd.Series, start: Any, end: Any) -> Dict[str, Any]:
    s = pd.to_numeric(returns, errors="coerce").dropna()
    if s.empty:
        return {"intervals": 0, "cumulative_return": None, "cagr": None, "max_drawdown": None, "calmar": None, "positive_interval_share": None}
    cumulative = float((1.0 + s).prod() - 1.0)
    years = max((pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25, 0.25)
    ending = max(1e-12, 1.0 + cumulative)
    cagr = float(ending ** (1.0 / years) - 1.0)
    dd = max_drawdown(s)
    calmar = float(cagr / dd) if dd > 0 else (float("inf") if cagr > 0 else None)
    return {
        "intervals": int(len(s)),
        "cumulative_return": cumulative,
        "cagr": cagr,
        "max_drawdown": dd,
        "calmar": calmar,
        "positive_interval_share": float((s > 0).mean()),
    }


def strategy_metrics(intervals: pd.DataFrame, partition: str) -> Dict[str, Any]:
    if intervals.empty:
        return {}
    out: Dict[str, Any] = {}
    for strategy in ["candidate", "price_200d", "central_bank_only", "buy_hold"]:
        metric = annualized_metrics(intervals[f"{strategy}_net_return"], intervals["start_date"].min(), intervals["end_date"].max())
        metric["high_interval_share"] = float((intervals[f"{strategy}_state"] == "HIGH").mean())
        metric["switches"] = int((intervals[f"{strategy}_exposure"].diff().fillna(intervals[f"{strategy}_exposure"]) != 0).sum())
        out[strategy] = metric
    out["partition"] = partition
    return out


def add_episode_ids(intervals: pd.DataFrame) -> pd.DataFrame:
    x = intervals.copy().reset_index(drop=True)
    state = x["candidate_state"].astype(str)
    x["candidate_episode_id"] = (state != state.shift(1)).cumsum().astype(int)
    x["candidate_episode_label"] = state + "_" + x["candidate_episode_id"].astype(str)
    return x


def episode_contributions(intervals: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    x = add_episode_ids(intervals)
    x["excess_vs_price_200d"] = x["candidate_net_return"] - x["price_200d_net_return"]
    grouped = x.groupby(["candidate_episode_id", "candidate_state"], as_index=False).agg(
        start_date=("start_date", "min"),
        end_date=("end_date", "max"),
        intervals=("interval_index", "size"),
        candidate_return=("candidate_net_return", lambda s: float((1.0 + s).prod() - 1.0)),
        price_200d_return=("price_200d_net_return", lambda s: float((1.0 + s).prod() - 1.0)),
        excess_sum=("excess_vs_price_200d", "sum"),
    )
    grouped["positive_excess"] = grouped["excess_sum"].clip(lower=0.0)
    positive_total = float(grouped["positive_excess"].sum())
    max_share = float(grouped["positive_excess"].max() / positive_total) if positive_total > 0 else None
    high = grouped[grouped["candidate_state"] == "HIGH"].copy()
    eras = set()
    for date in pd.to_datetime(high["start_date"], utc=True, errors="coerce").dropna():
        for a, b, label in LOCKED_CONTRACT["calendar_eras"]:
            if int(a) <= date.year <= int(b):
                eras.add(str(label))
                break
    summary = {
        "high_episode_count": int(len(high)),
        "all_episode_count": int(len(grouped)),
        "calendar_eras_with_high_episode": sorted(eras),
        "calendar_era_count": int(len(eras)),
        "positive_excess_total": positive_total,
        "maximum_single_episode_positive_excess_share": max_share,
    }
    return grouped, summary


def leave_one_episode_out(intervals: pd.DataFrame) -> Dict[str, Any]:
    x = add_episode_ids(intervals)
    episodes = sorted(x["candidate_episode_id"].unique())
    rows = []
    for episode in episodes:
        altered = x.copy()
        mask = altered["candidate_episode_id"] == episode
        altered.loc[mask, "candidate_net_return"] = altered.loc[mask, "price_200d_net_return"]
        candidate = float((1.0 + altered["candidate_net_return"]).prod() - 1.0)
        baseline = float((1.0 + altered["price_200d_net_return"]).prod() - 1.0)
        rows.append({"left_out_episode_id": int(episode), "candidate_minus_price_200d": candidate - baseline})
    values = [r["candidate_minus_price_200d"] for r in rows]
    return {
        "rows": rows,
        "median_excess": float(np.median(values)) if values else None,
        "minimum_excess": float(np.min(values)) if values else None,
        "positive_share": float(np.mean(np.array(values) > 0)) if values else None,
    }


def permutation_mean_test(high: Sequence[float], low: Sequence[float], iterations: int, seed: int) -> Dict[str, Any]:
    a = np.asarray(list(high), dtype=float)
    b = np.asarray(list(low), dtype=float)
    if len(a) == 0 or len(b) == 0:
        return {"status": "INSUFFICIENT_STATE_OBSERVATIONS", "high_n": len(a), "low_n": len(b)}
    observed = float(np.mean(a) - np.mean(b))
    pooled = np.concatenate([a, b]).copy()
    rng = np.random.default_rng(int(seed))
    exceed = 0
    for _ in range(int(iterations)):
        rng.shuffle(pooled)
        stat = float(np.mean(pooled[: len(a)]) - np.mean(pooled[len(a):]))
        if stat >= observed:
            exceed += 1
    pvalue = float((exceed + 1) / (int(iterations) + 1))
    return {
        "status": "PASS",
        "high_n": int(len(a)),
        "low_n": int(len(b)),
        "high_mean": float(np.mean(a)),
        "low_mean": float(np.mean(b)),
        "mean_difference": observed,
        "one_sided_permutation_pvalue": pvalue,
        "iterations": int(iterations),
        "seed": int(seed),
    }


def regime_horizon_tests(intervals: pd.DataFrame) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    oneq = permutation_mean_test(
        intervals.loc[intervals["candidate_state"] == "HIGH", "gold_gross_return"],
        intervals.loc[intervals["candidate_state"] == "LOW", "gold_gross_return"],
        int(LOCKED_CONTRACT["permutation_iterations"]),
        int(LOCKED_CONTRACT["permutation_seed"]),
    )
    cohorts = []
    for parity in [0, 1]:
        rows = []
        for i in range(parity, len(intervals) - 1, 2):
            gross_2q = float((1.0 + intervals.iloc[i]["gold_gross_return"]) * (1.0 + intervals.iloc[i + 1]["gold_gross_return"]) - 1.0)
            rows.append({"state": intervals.iloc[i]["candidate_state"], "return_2q": gross_2q})
        frame = pd.DataFrame(rows)
        if frame.empty:
            test = {"status": "INSUFFICIENT_STATE_OBSERVATIONS", "high_n": 0, "low_n": 0}
        else:
            test = permutation_mean_test(
                frame.loc[frame["state"] == "HIGH", "return_2q"],
                frame.loc[frame["state"] == "LOW", "return_2q"],
                int(LOCKED_CONTRACT["permutation_iterations"]),
                int(LOCKED_CONTRACT["permutation_seed"]) + parity + 1,
            )
        cohorts.append({"cohort_parity": parity, **test})
    twoq = {
        "status": "PASS" if cohorts and all(c.get("status") == "PASS" for c in cohorts) else "INSUFFICIENT_STATE_OBSERVATIONS",
        "cohorts": cohorts,
        "all_cohort_effect_signs_positive": bool(cohorts) and all(float(c.get("mean_difference", -1)) > 0 for c in cohorts if c.get("status") == "PASS") and all(c.get("status") == "PASS" for c in cohorts),
    }
    return oneq, twoq


def locked_holdout_cutoff(intervals: pd.DataFrame) -> pd.Timestamp:
    n = len(intervals)
    idx = min(n - 1, max(1, int(math.floor(n * (1.0 - float(LOCKED_CONTRACT["holdout_fraction"]))))))
    return pd.Timestamp(intervals.iloc[idx]["start_date"])


def evaluate_decision(
    vintage_status: Dict[str, Any],
    price_status: Dict[str, Any],
    episode_summary: Optional[Dict[str, Any]],
    development_metrics: Optional[Dict[str, Any]],
    holdout_metrics: Optional[Dict[str, Any]],
    holdout_intervals: Optional[pd.DataFrame],
    loo: Optional[Dict[str, Any]],
    oneq: Optional[Dict[str, Any]],
    twoq: Optional[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]], str]:
    if vintage_status.get("status") != "PASS":
        return "KILL_ASOF_DATA_CONTRACT_UNAVAILABLE", [], "WGC original-publication vintage contract failed."
    if price_status.get("status") != "PASS":
        return "KILL_ASOF_DATA_CONTRACT_UNAVAILABLE", [], "No single gold price source covers the historical-as-of period."
    assert episode_summary is not None and development_metrics is not None and holdout_metrics is not None and holdout_intervals is not None and loo is not None and oneq is not None and twoq is not None
    candidate_hold = holdout_metrics["candidate"]
    price_hold = holdout_metrics["price_200d"]
    buy_hold = holdout_metrics["buy_hold"]
    hold_states = sorted(set(holdout_intervals["candidate_state"].astype(str)))
    return_retention = (
        float(candidate_hold["cumulative_return"] / buy_hold["cumulative_return"])
        if buy_hold.get("cumulative_return") not in {None, 0} and float(buy_hold["cumulative_return"]) > 0
        else None
    )
    dd_reduction = (
        float(1.0 - candidate_hold["max_drawdown"] / buy_hold["max_drawdown"])
        if buy_hold.get("max_drawdown") not in {None, 0}
        else None
    )
    calmar_candidate = candidate_hold.get("calmar")
    calmar_price = price_hold.get("calmar")
    calmar_buy = buy_hold.get("calmar")
    calmar_superior = (
        calmar_candidate is not None and calmar_price is not None and calmar_buy is not None
        and float(calmar_candidate) > float(calmar_price)
        and float(calmar_candidate) > float(calmar_buy)
    )
    preservation = (
        return_retention is not None and dd_reduction is not None
        and return_retention >= float(LOCKED_CONTRACT["minimum_return_retention_vs_buy_hold"])
        and dd_reduction >= float(LOCKED_CONTRACT["minimum_drawdown_reduction_vs_buy_hold"])
    )
    gates = [
        {"gate": "minimum_high_episodes", "pass": episode_summary["high_episode_count"] >= int(LOCKED_CONTRACT["minimum_high_episodes"]), "actual": episode_summary["high_episode_count"], "required": LOCKED_CONTRACT["minimum_high_episodes"]},
        {"gate": "minimum_calendar_eras", "pass": episode_summary["calendar_era_count"] >= int(LOCKED_CONTRACT["minimum_calendar_eras"]), "actual": episode_summary["calendar_era_count"], "required": LOCKED_CONTRACT["minimum_calendar_eras"]},
        {"gate": "both_states_in_holdout", "pass": hold_states == ["HIGH", "LOW"], "actual": hold_states, "required": ["HIGH", "LOW"]},
        {"gate": "holdout_return_positive", "pass": candidate_hold.get("cumulative_return") is not None and float(candidate_hold["cumulative_return"]) > 0, "actual": candidate_hold.get("cumulative_return"), "required": "> 0"},
        {"gate": "incremental_value_vs_200d", "pass": candidate_hold.get("cumulative_return") is not None and price_hold.get("cumulative_return") is not None and float(candidate_hold["cumulative_return"]) > float(price_hold["cumulative_return"]), "actual": (candidate_hold.get("cumulative_return") or 0) - (price_hold.get("cumulative_return") or 0), "required": "> 0"},
        {"gate": "leave_one_episode_out_median_excess", "pass": loo.get("median_excess") is not None and float(loo["median_excess"]) > 0, "actual": loo.get("median_excess"), "required": "> 0"},
        {"gate": "episode_positive_excess_concentration", "pass": episode_summary.get("maximum_single_episode_positive_excess_share") is not None and float(episode_summary["maximum_single_episode_positive_excess_share"]) <= float(LOCKED_CONTRACT["maximum_single_episode_positive_excess_share"]), "actual": episode_summary.get("maximum_single_episode_positive_excess_share"), "required": LOCKED_CONTRACT["maximum_single_episode_positive_excess_share"]},
        {"gate": "1q_state_sample_power", "pass": oneq.get("status") == "PASS" and int(oneq.get("high_n", 0)) >= int(LOCKED_CONTRACT["minimum_1q_observations_per_state"]) and int(oneq.get("low_n", 0)) >= int(LOCKED_CONTRACT["minimum_1q_observations_per_state"]), "actual": {"high_n": oneq.get("high_n"), "low_n": oneq.get("low_n")}, "required": LOCKED_CONTRACT["minimum_1q_observations_per_state"]},
        {"gate": "1q_high_low_separation", "pass": oneq.get("status") == "PASS" and float(oneq.get("mean_difference", -1)) > 0 and float(oneq.get("one_sided_permutation_pvalue", 1)) <= float(LOCKED_CONTRACT["maximum_1q_permutation_pvalue"]), "actual": {"difference": oneq.get("mean_difference"), "p": oneq.get("one_sided_permutation_pvalue")}, "required": {"difference": ">0", "p_max": LOCKED_CONTRACT["maximum_1q_permutation_pvalue"]}},
        {"gate": "2q_nonoverlap_direction", "pass": bool(twoq.get("all_cohort_effect_signs_positive")), "actual": twoq.get("cohorts"), "required": "both non-overlapping cohort effects > 0"},
        {"gate": "risk_return_target", "pass": bool(calmar_superior or preservation), "actual": {"calmar_superior": calmar_superior, "return_retention": return_retention, "drawdown_reduction": dd_reduction}, "required": "Calmar beats buy-hold and 200D OR >=25% DD reduction with >=80% return retention"},
    ]
    power_gates = {"minimum_high_episodes", "minimum_calendar_eras", "both_states_in_holdout", "1q_state_sample_power", "2q_nonoverlap_direction"}
    failed = [g for g in gates if not bool(g["pass"])]
    if not failed:
        return "ALLOCATION_SHADOW_CANDIDATE", gates, "All fixed historical-as-of, incremental-value and robustness gates passed."
    if any(g["gate"] in power_gates for g in failed):
        return "INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE", gates, "Data contract passed, but the fixed sample cannot establish enough independent regime power."
    return "KILL_NO_INCREMENTAL_ALLOCATION_VALUE", gates, "The fixed allocation rule failed performance or incremental-value gates."


def format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.6f}"
    return str(value)


def write_decision_md(path: Path, summary: Dict[str, Any]) -> None:
    decision = summary["program_decision"]
    lines = [
        "# Stage176 Decision",
        "",
        f"Generated: {summary['generated_utc']}",
        "",
        "## Hard controls",
        "",
        "- Orders/demo/paper/live: forbidden.",
        "- ML: currently forbidden; conditional re-entry only after a baseline pass.",
        "- Broad scan, parameter grid and threshold reoptimization: forbidden.",
        "- Product: quarterly decision-support allocation, not an intraday generator.",
        "",
        "## Data contracts",
        "",
        f"WGC original-publication vintage contract: `{summary['wgc_vintage_preflight']['status']}`",
        f"Gold price source contract: `{summary['gold_price_source']['status']}`",
        "",
        "## Final decision",
        "",
        f"**`{decision}`**",
        "",
        summary.get("decision_reason", ""),
    ]
    if summary.get("holdout_metrics"):
        lines.extend(["", "## Holdout", ""])
        for name, metric in summary["holdout_metrics"].items():
            if name == "partition":
                continue
            lines.append(
                f"- {name}: return={format_metric(metric.get('cumulative_return'))}, "
                f"CAGR={format_metric(metric.get('cagr'))}, "
                f"maxDD={format_metric(metric.get('max_drawdown'))}, "
                f"Calmar={format_metric(metric.get('calmar'))}"
            )
    if summary.get("gate_checks"):
        lines.extend(["", "## Gate checks", ""])
        for gate in summary["gate_checks"]:
            lines.append(f"- `{gate['gate']}`: **{'PASS' if gate['pass'] else 'FAIL'}** — actual={gate['actual']}")
    lines.extend([
        "",
        "## Program consequence",
        "",
        "No execution bridge is authorized. A PASS permits quarterly shadow decision-support only. "
        "A KILL or LOW_POWER result is terminal for this formulation and triggers product-scope escalation, not another parameter search.",
    ])
    ensure_parent(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root: Path, config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    out_dir = resolve(root, config.get("output_dir", DEFAULT_OUT))
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_cfg = config.get("progress", {})
    progress = ProgressReporter(
        out_dir,
        enabled=bool(progress_cfg.get("enabled", True)) and not bool(getattr(args, "no_progress", False)),
    )
    progress.emit("START", f"run started root={root} output={out_dir}")
    contract = contract_assertion(config)
    if not contract["pass"]:
        progress.emit("CONTRACT", f"locked contract mismatch differences={contract['differences']}", status="FAILED")
        raise ValueError(f"Locked contract mismatch: {contract['differences']}")
    progress.emit("CONTRACT", "locked contract validated", status="COMPLETE")

    manifest_path = Path(args.vintage_manifest).expanduser().resolve() if args.vintage_manifest else first_existing(root, config["wgc_vintages"]["manifest_candidates"])
    collector_result: Dict[str, Any] = {"status": "NOT_RUN"}
    if manifest_path is not None:
        progress.emit("MANIFEST", f"local vintage manifest found path={manifest_path}", status="COMPLETE")
    if manifest_path is None and (args.online or bool(config["wgc_vintages"].get("online_collection", {}).get("enabled", False))):
        progress.emit("MANIFEST", "no valid local manifest; starting official WGC archive collection")
        collector_cfg = dict(config["wgc_vintages"]["online_collection"])
        collector_cfg.setdefault("checkpoint_every_reports", int(progress_cfg.get("checkpoint_every_reports", 1)))
        collector_cfg.setdefault("max_consecutive_index_failures", int(progress_cfg.get("max_consecutive_index_failures", 3)))
        collector_cfg.setdefault("max_consecutive_report_failures", int(progress_cfg.get("max_consecutive_report_failures", 8)))
        collector_result = collect_wgc_vintages(root, collector_cfg, out_dir, progress)
        manifest_path = first_existing(root, config["wgc_vintages"]["manifest_candidates"] + [config["wgc_vintages"]["online_collection"]["canonical_manifest_output"]])

    vintage_status: Dict[str, Any]
    vintages: Optional[pd.DataFrame] = None
    vintage_audit_rows: List[Dict[str, Any]] = []
    if manifest_path is None:
        vintage_status = {"status": "FAIL", "reason": "WGC_VINTAGE_MANIFEST_NOT_FOUND", "collector": collector_result}
        progress.emit("VINTAGE_PREFLIGHT", "manifest unavailable after collection", status="FAILED")
    else:
        try:
            progress.emit("VINTAGE_PREFLIGHT", f"validating manifest path={manifest_path}")
            raw_vintages = load_vintage_manifest(manifest_path)
            vintage_status, vintages, vintage_audit_rows = validate_vintage_manifest(raw_vintages, root)
            vintage_status.update({"path": str(manifest_path), "sha256": sha256(manifest_path), "collector": collector_result})
            progress.emit(
                "VINTAGE_PREFLIGHT",
                f"manifest validation status={vintage_status.get('status')} valid_quarters={len(vintages) if vintages is not None else 0}",
                status="COMPLETE" if vintage_status.get("status") == "PASS" else "FAILED",
            )
        except Exception as exc:  # noqa: BLE001
            vintage_status = {"status": "FAIL", "reason": f"{type(exc).__name__}:{exc}", "path": str(manifest_path), "collector": collector_result}
            progress.emit("VINTAGE_PREFLIGHT", f"manifest validation failed error={type(exc).__name__}:{exc}", status="FAILED")

    online_enabled = bool(config["wgc_vintages"].get("online_collection", {}).get("enabled", False))
    if vintage_status.get("status") != "PASS" and (args.online or online_enabled) and collector_result.get("status") == "NOT_RUN":
        progress.emit(
            "MANIFEST_REPAIR",
            "existing manifest failed the vintage contract; rebuilding from cached/original WGC publications",
        )
        collector_cfg = dict(config["wgc_vintages"]["online_collection"])
        collector_cfg.setdefault("checkpoint_every_reports", int(progress_cfg.get("checkpoint_every_reports", 1)))
        collector_cfg.setdefault("max_consecutive_index_failures", int(progress_cfg.get("max_consecutive_index_failures", 3)))
        collector_cfg.setdefault("max_consecutive_report_failures", int(progress_cfg.get("max_consecutive_report_failures", 8)))
        collector_result = collect_wgc_vintages(root, collector_cfg, out_dir, progress)
        rebuilt = resolve(root, config["wgc_vintages"]["online_collection"]["canonical_manifest_output"])
        if rebuilt.exists():
            manifest_path = rebuilt.resolve()
            try:
                raw_vintages = load_vintage_manifest(manifest_path)
                vintage_status, vintages, vintage_audit_rows = validate_vintage_manifest(raw_vintages, root)
                vintage_status.update({"path": str(manifest_path), "sha256": sha256(manifest_path), "collector": collector_result})
                progress.emit(
                    "VINTAGE_PREFLIGHT",
                    f"rebuilt manifest validation status={vintage_status.get('status')} valid_quarters={len(vintages) if vintages is not None else 0}",
                    status="COMPLETE" if vintage_status.get("status") == "PASS" else "FAILED",
                )
            except Exception as exc:  # noqa: BLE001
                vintage_status = {"status": "FAIL", "reason": f"{type(exc).__name__}:{exc}", "path": str(manifest_path), "collector": collector_result}
                vintages = None
                vintage_audit_rows = []
                progress.emit("VINTAGE_PREFLIGHT", f"rebuilt manifest validation failed error={type(exc).__name__}:{exc}", status="FAILED")
    write_csv(out_dir / "stage176_wgc_vintage_preflight.csv", vintage_audit_rows)

    price_status: Dict[str, Any] = {"status": "NOT_RUN"}
    price_inventory: List[Dict[str, Any]] = []
    prices: Optional[pd.DataFrame] = None
    if vintage_status.get("status") == "PASS" and vintages is not None and not vintages.empty:
        progress.emit("GOLD_PRICE", "resolving gold daily price source")
        prices, price_status, price_inventory = resolve_gold_price_source(root, config["gold_prices"], pd.Timestamp(vintages["release_timestamp_utc"].max()))
        progress.emit(
            "GOLD_PRICE",
            f"price source status={price_status.get('status')} path={price_status.get('path', '')}",
            status="COMPLETE" if price_status.get("status") == "PASS" else "FAILED",
        )
    write_csv(out_dir / "stage176_gold_price_inventory.csv", price_inventory)

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": utc_iso(),
        "root": str(root),
        "locked_contract": LOCKED_CONTRACT,
        "locked_contract_sha256": stable_json_hash(LOCKED_CONTRACT),
        "hard_controls": {
            "orders_allowed": False,
            "demo_allowed": False,
            "paper_order_allowed": False,
            "live_allowed": False,
            "ml_allowed_now": False,
            "ml_reentry_condition": "ONLY_AFTER_SIMPLE_CAUSAL_BASELINE_PASSES_LOCKED_MULTI_REGIME_HOLDOUT; ON_OFF_OR_INTERACTION_FILTER_ONLY",
            "broad_scan_allowed": False,
            "parameter_grid_allowed": False,
            "threshold_reoptimization_allowed": False,
        },
        "wgc_vintage_preflight": vintage_status,
        "gold_price_source": price_status,
    }

    if vintage_status.get("status") != "PASS" or price_status.get("status") != "PASS" or vintages is None or prices is None:
        decision, gates, reason = evaluate_decision(vintage_status, price_status, None, None, None, None, None, None, None)
        summary.update({"program_decision": decision, "decision_reason": reason, "gate_checks": gates})
    else:
        progress.emit("AUDIT", f"building historical-as-of decision panel quarters={len(vintages)}")
        panel = build_decision_panel(vintages, prices)
        if len(panel) < 20:
            vintage_status = {**vintage_status, "status": "FAIL", "reason": "INSUFFICIENT_TRADABLE_DECISION_ROWS"}
            decision, gates, reason = evaluate_decision(vintage_status, price_status, None, None, None, None, None, None, None)
            summary.update({"wgc_vintage_preflight": vintage_status, "program_decision": decision, "decision_reason": reason, "gate_checks": gates})
        else:
            progress.emit("AUDIT", f"decision panel complete rows={len(panel)}; computing interval returns and holdout")
            primary = build_interval_returns(panel, float(LOCKED_CONTRACT["primary_switching_cost_bps"]))
            stress = build_interval_returns(panel, float(LOCKED_CONTRACT["stress_switching_cost_bps"]))
            stress_cols = {c: f"stress_{c}" for c in stress.columns if c.endswith("_net_return") or c.endswith("_switch_cost")}
            primary = primary.merge(stress[["interval_index", *stress_cols.keys()]].rename(columns=stress_cols), on="interval_index", how="left")
            cutoff = locked_holdout_cutoff(primary)
            primary["partition"] = np.where(primary["start_date"] >= cutoff, "HOLDOUT", "DEVELOPMENT")
            development = primary[primary["partition"] == "DEVELOPMENT"].copy()
            holdout = primary[primary["partition"] == "HOLDOUT"].copy()
            dev_metrics = strategy_metrics(development, "DEVELOPMENT")
            hold_metrics = strategy_metrics(holdout, "HOLDOUT")
            episode_frame, episode_summary = episode_contributions(primary)
            loo = leave_one_episode_out(primary)
            oneq, twoq = regime_horizon_tests(primary)
            decision, gates, reason = evaluate_decision(
                vintage_status, price_status, episode_summary, dev_metrics, hold_metrics, holdout, loo, oneq, twoq
            )
            panel.to_csv(out_dir / "stage176_decision_panel.csv", index=False)
            primary.to_csv(out_dir / "stage176_interval_returns.csv", index=False)
            episode_frame.to_csv(out_dir / "stage176_episode_contributions.csv", index=False)
            write_json(out_dir / "stage176_1q_regime_test.json", oneq)
            write_json(out_dir / "stage176_2q_nonoverlap_test.json", twoq)
            write_csv(out_dir / "stage176_gate_checks.csv", gates)
            metric_rows = []
            for partition, metrics in [("DEVELOPMENT", dev_metrics), ("HOLDOUT", hold_metrics)]:
                for strategy, values in metrics.items():
                    if strategy == "partition":
                        continue
                    metric_rows.append({"partition": partition, "strategy": strategy, **values})
            write_csv(out_dir / "stage176_metrics.csv", metric_rows)
            progress.emit(
                "AUDIT",
                f"audit complete decision={decision} intervals={len(primary)} holdout_rows={len(holdout)}",
                status="COMPLETE",
            )
            summary.update({
                "decision_panel_rows": int(len(panel)),
                "interval_rows": int(len(primary)),
                "holdout_cutoff_utc": cutoff.isoformat(),
                "development_metrics": dev_metrics,
                "holdout_metrics": hold_metrics,
                "episode_summary": episode_summary,
                "leave_one_episode_out": loo,
                "one_quarter_regime_test": oneq,
                "two_quarter_nonoverlap_test": twoq,
                "gate_checks": gates,
                "program_decision": decision,
                "decision_reason": reason,
            })

    outputs = {
        "summary_json": str(out_dir / "stage176_summary.json"),
        "decision_md": str(out_dir / "stage176_decision.md"),
        "vintage_preflight_csv": str(out_dir / "stage176_wgc_vintage_preflight.csv"),
        "price_inventory_csv": str(out_dir / "stage176_gold_price_inventory.csv"),
        "decision_panel_csv": str(out_dir / "stage176_decision_panel.csv"),
        "interval_returns_csv": str(out_dir / "stage176_interval_returns.csv"),
        "metrics_csv": str(out_dir / "stage176_metrics.csv"),
        "gate_checks_csv": str(out_dir / "stage176_gate_checks.csv"),
        "episode_contributions_csv": str(out_dir / "stage176_episode_contributions.csv"),
        "one_quarter_test_json": str(out_dir / "stage176_1q_regime_test.json"),
        "two_quarter_test_json": str(out_dir / "stage176_2q_nonoverlap_test.json"),
    }
    summary["outputs"] = outputs
    write_json(out_dir / "stage176_summary.json", summary)
    write_decision_md(out_dir / "stage176_decision.md", summary)
    progress.emit(
        "DONE",
        f"run finished decision={summary['program_decision']} summary={out_dir / 'stage176_summary.json'}",
        status="COMPLETE",
    )
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="~/Desktop/xauusd-trader")
    parser.add_argument("--config", default="configs/stage176_central_bank_allocation_falsification.json")
    parser.add_argument("--vintage-manifest", default="", help="Explicit WGC vintage manifest path")
    parser.add_argument("--online", action="store_true", help="Attempt official WGC archive-page collection when no valid local manifest exists")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal heartbeat and stage176_progress checkpoints")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = resolve(root, args.config)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        summary = run(root, config, args)
        print(json.dumps({
            "stage": STAGE,
            "decision": summary["program_decision"],
            "summary": summary["outputs"]["summary_json"],
            "decision_md": summary["outputs"]["decision_md"],
        }, indent=2))
        return 0 if summary["program_decision"] in {
            "ALLOCATION_SHADOW_CANDIDATE",
            "KILL_NO_INCREMENTAL_ALLOCATION_VALUE",
            "INCONCLUSIVE_LOW_POWER_ESCALATE_PRODUCT_SCOPE",
        } else 2
    except Exception as exc:  # noqa: BLE001
        try:
            out_dir = resolve(root, config.get("output_dir", DEFAULT_OUT)) if "config" in locals() else root / DEFAULT_OUT
            ProgressReporter(out_dir, enabled=True).emit(
                "FATAL",
                f"{type(exc).__name__}:{exc}",
                status="FAILED",
            )
        except Exception:
            pass
        print(f"STAGE176_FATAL:{type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
