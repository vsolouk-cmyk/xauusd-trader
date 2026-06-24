#!/usr/bin/env python3
"""
Stage38F Gold ETF Source Parse Audit

Read-only workbook parse audit for gold ETF source files downloaded by:
    app/stage38f_gold_etf_source_availability_audit.py

Purpose:
    - Inspect WGC and SPDR XLSX files without relying on fixed workbook schemas.
    - Identify candidate sheets for future ETF holdings/flow loaders.
    - Write JSON/MD reports and lightweight SQLite audit tables.

No strategy, no baseline, no ML, no Stage39, no EA, no paper/live.

Dependency policy:
    Uses only Python standard library. It reads XLSX files as zipped XML.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sqlite3
import sys
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET

AUDIT_TABLE = "stage38f_etf_source_parse_audit"
SHEET_TABLE = "stage38f_etf_source_parse_sheet_audit"

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

KEYWORDS_WGC = [
    "world gold council", "gold etf", "gold etfs", "flows", "flow", "holdings",
    "tonnes", "a$", "aum", "region", "fund", "etf",
]
KEYWORDS_SPDR = [
    "spdr", "gld", "gold shares", "shares outstanding", "ounces", "total net assets",
    "nav", "tonnes", "date", "gold oz", "gold ounces",
]
KEYWORDS_GENERIC = sorted(set(KEYWORDS_WGC + KEYWORDS_SPDR + [
    "date", "daily", "weekly", "monthly", "close", "price", "usd", "value",
]))

DATE_TEXT_PATTERNS = [
    re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),
    re.compile(r"^\d{1,2}-\d{1,2}-\d{2,4}$"),
    re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}$", re.I),
    re.compile(r"^\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{4}$", re.I),
]


def now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_text(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).replace("\xa0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if math.isfinite(float(x)):
            return float(x)
        return None
    s = norm_text(x)
    if not s:
        return None
    s = s.replace(",", "")
    if s in {"-", "—", "n/a", "NA", "N/A", "."}:
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        val = float(s)
        if math.isfinite(val):
            return val
    except Exception:
        return None
    return None


def looks_like_excel_date_serial(v: Any) -> bool:
    f = safe_float(v)
    if f is None:
        return False
    # Excel serials roughly covering 1990-2035.
    return 32874 <= f <= 49309 and abs(f - round(f)) < 1e-9


def looks_like_date_text(x: Any) -> bool:
    s = norm_text(x)
    if not s:
        return False
    if any(p.match(s) for p in DATE_TEXT_PATTERNS):
        return True
    # Try Python ISO parser for YYYY-MM-DD-like strings.
    try:
        dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def looks_like_date(x: Any) -> bool:
    return looks_like_date_text(x) or looks_like_excel_date_serial(x)


def col_letters_to_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    if not letters:
        return 0
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def xml_text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    parts: List[str] = []
    for t in elem.iter():
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def read_shared_strings(z: zipfile.ZipFile) -> List[str]:
    path = "xl/sharedStrings.xml"
    if path not in z.namelist():
        return []
    root = ET.fromstring(z.read(path))
    strings: List[str] = []
    for si in root.findall(f"{NS_MAIN}si"):
        strings.append(norm_text(xml_text(si)))
    return strings


def read_sheet_names_and_paths(z: zipfile.ZipFile) -> List[Tuple[str, str]]:
    names = z.namelist()
    if "xl/workbook.xml" not in names:
        # Fallback: raw worksheet paths.
        return [(Path(p).stem, p) for p in sorted(names) if p.startswith("xl/worksheets/") and p.endswith(".xml")]

    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rel_map: Dict[str, str] = {}
    rel_path = "xl/_rels/workbook.xml.rels"
    if rel_path in names:
        rel_root = ET.fromstring(z.read(rel_path))
        for rel in rel_root.findall(f"{NS_PKG_REL}Relationship"):
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if rid and target:
                if target.startswith("/"):
                    full = target.lstrip("/")
                elif target.startswith("xl/"):
                    full = target
                else:
                    full = "xl/" + target
                rel_map[rid] = full

    out: List[Tuple[str, str]] = []
    sheets = wb.find(f"{NS_MAIN}sheets")
    if sheets is not None:
        for sh in sheets.findall(f"{NS_MAIN}sheet"):
            name = sh.attrib.get("name", "sheet")
            rid = sh.attrib.get(f"{NS_REL}id")
            path = rel_map.get(rid or "")
            if path and path in names:
                out.append((name, path))

    if not out:
        out = [(Path(p).stem, p) for p in sorted(names) if p.startswith("xl/worksheets/") and p.endswith(".xml")]
    return out


def parse_sheet_rows(z: zipfile.ZipFile, sheet_path: str, shared: Sequence[str], max_rows: int = 20000) -> List[List[Any]]:
    root = ET.fromstring(z.read(sheet_path))
    sheet_data = root.find(f"{NS_MAIN}sheetData")
    if sheet_data is None:
        return []

    rows: List[List[Any]] = []
    for row_elem in sheet_data.findall(f"{NS_MAIN}row"):
        cells: Dict[int, Any] = {}
        max_idx = -1
        for c in row_elem.findall(f"{NS_MAIN}c"):
            ref = c.attrib.get("r", "")
            idx = col_letters_to_index(ref) if ref else max_idx + 1
            max_idx = max(max_idx, idx)
            t = c.attrib.get("t")
            v_elem = c.find(f"{NS_MAIN}v")
            value: Any = None
            if t == "s":
                raw = norm_text(v_elem.text if v_elem is not None else "")
                try:
                    si = int(raw)
                    value = shared[si] if 0 <= si < len(shared) else raw
                except Exception:
                    value = raw
            elif t == "inlineStr":
                value = xml_text(c.find(f"{NS_MAIN}is"))
            elif t == "str":
                value = norm_text(v_elem.text if v_elem is not None else "")
            else:
                raw = norm_text(v_elem.text if v_elem is not None else "")
                if raw == "":
                    value = ""
                else:
                    f = safe_float(raw)
                    value = f if f is not None else raw
            cells[idx] = value
        if cells:
            width = max(cells.keys()) + 1
            rows.append([cells.get(i, "") for i in range(width)])
        else:
            rows.append([])
        if len(rows) >= max_rows:
            break
    return rows


def row_text(row: Sequence[Any]) -> str:
    return " | ".join(norm_text(x) for x in row if norm_text(x))


def keyword_hits_for_rows(rows: Sequence[Sequence[Any]], keywords: Sequence[str], limit_rows: int = 250) -> Dict[str, int]:
    text = "\n".join(row_text(r).lower() for r in rows[:limit_rows])
    hits: Dict[str, int] = {}
    for kw in keywords:
        n = text.count(kw.lower())
        if n:
            hits[kw] = n
    return hits


def find_header_candidates(rows: Sequence[Sequence[Any]], max_scan_rows: int = 80) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for i, row in enumerate(rows[:max_scan_rows]):
        nonempty = [norm_text(x) for x in row if norm_text(x)]
        if len(nonempty) < 2:
            continue
        text_cells = [x for x in nonempty if safe_float(x) is None or looks_like_date_text(x)]
        text = " ".join(nonempty).lower()
        keyword_score = sum(1 for kw in KEYWORDS_GENERIC if kw.lower() in text)
        date_word = 1 if "date" in text or "period" in text or "month" in text or "week" in text else 0
        score = len(text_cells) + 4 * keyword_score + 3 * date_word
        if score >= 4:
            candidates.append({
                "row_index_0based": i,
                "row_index_1based": i + 1,
                "score": score,
                "nonempty_count": len(nonempty),
                "preview": nonempty[:16],
            })
    candidates.sort(key=lambda d: (-d["score"], d["row_index_0based"]))
    return candidates[:8]


def analyze_sheet(file_name: str, sheet_name: str, sheet_path: str, rows: Sequence[Sequence[Any]]) -> Dict[str, Any]:
    nonempty_rows = [r for r in rows if any(norm_text(x) for x in r)]
    max_cols = max((len(r) for r in nonempty_rows), default=0)
    cell_count = sum(len(r) for r in nonempty_rows)
    nonempty_cell_count = sum(1 for r in nonempty_rows for x in r if norm_text(x))
    numeric_count = sum(1 for r in nonempty_rows for x in r if safe_float(x) is not None)
    date_like_count = sum(1 for r in nonempty_rows for x in r if looks_like_date(x))

    hits_generic = keyword_hits_for_rows(nonempty_rows, KEYWORDS_GENERIC)
    hits_wgc = keyword_hits_for_rows(nonempty_rows, KEYWORDS_WGC)
    hits_spdr = keyword_hits_for_rows(nonempty_rows, KEYWORDS_SPDR)
    headers = find_header_candidates(nonempty_rows)

    sample_rows = []
    for r in nonempty_rows[:12]:
        vals = [norm_text(x) for x in r[:12]]
        if any(vals):
            sample_rows.append(vals)

    score_wgc = len(hits_wgc) * 2 + hits_wgc.get("flows", 0) + hits_wgc.get("holdings", 0) + hits_wgc.get("tonnes", 0)
    score_spdr = len(hits_spdr) * 2 + hits_spdr.get("gld", 0) + hits_spdr.get("ounces", 0) + hits_spdr.get("nav", 0)
    date_score = min(date_like_count, 50)
    numeric_score = min(numeric_count // 10, 50)

    parse_score = date_score + numeric_score + max(score_wgc, score_spdr) + min(len(headers) * 5, 20)
    if len(nonempty_rows) < 5:
        status = "LOW_CONTENT"
    elif parse_score >= 45:
        status = "PASS_CANDIDATE_SHEET"
    elif parse_score >= 20:
        status = "WATCH_CANDIDATE_SHEET"
    else:
        status = "NO_ETF_TABLE_EVIDENCE"

    inferred_source_type = "UNKNOWN"
    fn = file_name.lower()
    if "spdr" in fn or score_spdr > score_wgc + 3:
        inferred_source_type = "SPDR_GLD"
    elif "wgc" in fn or "gold.org" in fn or score_wgc > score_spdr + 3:
        inferred_source_type = "WGC_GOLD_ETF"
    elif score_wgc or score_spdr:
        inferred_source_type = "ETF_RELATED"

    return {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sheet_path": sheet_path,
        "status": status,
        "inferred_source_type": inferred_source_type,
        "nonempty_row_count": len(nonempty_rows),
        "max_col_count": max_cols,
        "nonempty_cell_count": nonempty_cell_count,
        "numeric_cell_count": numeric_count,
        "date_like_cell_count": date_like_count,
        "parse_score": parse_score,
        "keyword_hits_generic": hits_generic,
        "keyword_hits_wgc": hits_wgc,
        "keyword_hits_spdr": hits_spdr,
        "header_candidates": headers,
        "sample_rows": sample_rows,
    }


def discover_files(raw_dir: Path) -> List[Path]:
    files = []
    for p in sorted(raw_dir.rglob("*.xlsx")):
        if p.is_file() and not p.name.startswith("~$"):
            files.append(p)
    return files


def analyze_workbook(path: Path, max_rows_per_sheet: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "file_name": path.name,
        "file_path": str(path),
        "status": "UNKNOWN",
        "error": None,
        "size_bytes": path.stat().st_size if path.exists() else None,
        "sheet_count": 0,
        "sheets": [],
    }
    try:
        with zipfile.ZipFile(path, "r") as z:
            shared = read_shared_strings(z)
            sheets = read_sheet_names_and_paths(z)
            result["sheet_count"] = len(sheets)
            for sheet_name, sheet_path in sheets:
                try:
                    rows = parse_sheet_rows(z, sheet_path, shared, max_rows=max_rows_per_sheet)
                    result["sheets"].append(analyze_sheet(path.name, sheet_name, sheet_path, rows))
                except Exception as exc:
                    result["sheets"].append({
                        "file_name": path.name,
                        "sheet_name": sheet_name,
                        "sheet_path": sheet_path,
                        "status": "PARSE_FAIL",
                        "error": f"{type(exc).__name__}: {exc}",
                    })
        pass_sheets = [s for s in result["sheets"] if s.get("status") == "PASS_CANDIDATE_SHEET"]
        watch_sheets = [s for s in result["sheets"] if s.get("status") == "WATCH_CANDIDATE_SHEET"]
        if pass_sheets:
            result["status"] = "PASS"
        elif watch_sheets:
            result["status"] = "WATCH"
        else:
            result["status"] = "NO_USABLE_SHEET_FOUND"
    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def reset_tables(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(f'DROP TABLE IF EXISTS "{SHEET_TABLE}"')
    cur.execute(f'DROP TABLE IF EXISTS "{AUDIT_TABLE}"')
    cur.execute(f'''
        CREATE TABLE "{SHEET_TABLE}" (
            audit_id integer,
            file_name text,
            file_path text,
            sheet_name text,
            sheet_path text,
            status text,
            inferred_source_type text,
            nonempty_row_count integer,
            max_col_count integer,
            nonempty_cell_count integer,
            numeric_cell_count integer,
            date_like_cell_count integer,
            parse_score real,
            keyword_hits_json text,
            header_candidates_json text,
            sample_rows_json text,
            error text
        )
    ''')
    cur.execute(f'''
        CREATE TABLE "{AUDIT_TABLE}" (
            audit_id integer primary key,
            generated_utc text,
            status text,
            decision text,
            raw_dir text,
            files_discovered integer,
            workbooks_pass integer,
            workbooks_watch integer,
            workbooks_fail integer,
            sheet_pass_count integer,
            sheet_watch_count integer,
            wgc_candidate_sheet_count integer,
            spdr_candidate_sheet_count integer,
            warning_count integer,
            note_count integer,
            json_report text,
            md_report text
        )
    ''')
    con.commit()


def insert_audit_tables(con: sqlite3.Connection, audit: Dict[str, Any], workbook_results: Sequence[Dict[str, Any]]) -> None:
    reset_tables(con)
    cur = con.cursor()
    audit_id = 1
    for wb in workbook_results:
        for sh in wb.get("sheets", []):
            hits = {
                "generic": sh.get("keyword_hits_generic", {}),
                "wgc": sh.get("keyword_hits_wgc", {}),
                "spdr": sh.get("keyword_hits_spdr", {}),
            }
            cur.execute(f'''
                INSERT INTO "{SHEET_TABLE}" VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', [
                audit_id,
                wb.get("file_name"),
                wb.get("file_path"),
                sh.get("sheet_name"),
                sh.get("sheet_path"),
                sh.get("status"),
                sh.get("inferred_source_type"),
                sh.get("nonempty_row_count"),
                sh.get("max_col_count"),
                sh.get("nonempty_cell_count"),
                sh.get("numeric_cell_count"),
                sh.get("date_like_cell_count"),
                sh.get("parse_score"),
                json.dumps(hits, ensure_ascii=False),
                json.dumps(sh.get("header_candidates", []), ensure_ascii=False),
                json.dumps(sh.get("sample_rows", []), ensure_ascii=False),
                sh.get("error"),
            ])
    cur.execute(f'''
        INSERT INTO "{AUDIT_TABLE}" VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', [
        audit_id,
        audit["generated_utc"],
        audit["status"],
        audit["decision"],
        audit["raw_dir"],
        audit["files_discovered"],
        audit["workbooks_pass"],
        audit["workbooks_watch"],
        audit["workbooks_fail"],
        audit["sheet_pass_count"],
        audit["sheet_watch_count"],
        audit["wgc_candidate_sheet_count"],
        audit["spdr_candidate_sheet_count"],
        len(audit.get("warnings", [])),
        len(audit.get("notes", [])),
        audit.get("json_report"),
        audit.get("md_report"),
    ])
    con.commit()


def build_decision(workbook_results: Sequence[Dict[str, Any]], sheet_pass: int, sheet_watch: int, wgc_candidates: int, spdr_candidates: int) -> Tuple[str, str, List[str], List[str]]:
    warnings: List[str] = []
    notes: List[str] = []
    fail_count = sum(1 for w in workbook_results if w.get("status") == "FAIL")
    if fail_count:
        notes.append(f"workbook_parse_failures={fail_count}")

    if sheet_pass == 0 and sheet_watch == 0:
        return "FAIL", "NO_USABLE_ETF_XLSX_TABLE_FOUND", warnings, notes
    if spdr_candidates > 0 and wgc_candidates > 0:
        return "PASS", "PROCEED_TO_STAGE38F_ETF_LOADER_DESIGN_SPDR_FIRST_WGC_CROSSCHECK", warnings, notes
    if spdr_candidates > 0:
        return "PASS", "PROCEED_TO_STAGE38F_SPDR_GLD_LOADER_DESIGN", warnings, notes
    if wgc_candidates > 0:
        return "PASS", "PROCEED_TO_STAGE38F_WGC_ETF_LOADER_DESIGN", warnings, notes
    return "WATCH", "USABLE_XLSX_FOUND_BUT_SOURCE_TYPE_UNCLEAR_REVIEW_SHEETS", warnings, notes


def write_reports(reports_dir: Path, audit: Dict[str, Any], workbook_results: Sequence[Dict[str, Any]]) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38f_gold_etf_source_parse_audit.json"
    md_path = reports_dir / "stage38f_gold_etf_source_parse_audit.md"

    payload = {
        "audit": audit,
        "workbooks": workbook_results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage38F Gold ETF Source Parse Audit")
    lines.append("")
    lines.append(f"Generated UTC: `{audit['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"status = {audit['status']}")
    lines.append(f"decision = {audit['decision']}")
    lines.append(f"files_discovered = {audit['files_discovered']}")
    lines.append(f"sheet_pass_count = {audit['sheet_pass_count']}")
    lines.append(f"sheet_watch_count = {audit['sheet_watch_count']}")
    lines.append(f"wgc_candidate_sheet_count = {audit['wgc_candidate_sheet_count']}")
    lines.append(f"spdr_candidate_sheet_count = {audit['spdr_candidate_sheet_count']}")
    lines.append("```")
    lines.append("")
    if audit.get("notes"):
        lines.append("## Notes")
        lines.append("")
        for n in audit["notes"]:
            lines.append(f"- {n}")
        lines.append("")
    if audit.get("warnings"):
        lines.append("## Warnings")
        lines.append("")
        for w in audit["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Workbook summary")
    lines.append("")
    lines.append("| File | Status | Sheets | Size bytes | Error |")
    lines.append("|---|---:|---:|---:|---|")
    for wb in workbook_results:
        lines.append(
            f"| `{wb.get('file_name')}` | {wb.get('status')} | {wb.get('sheet_count')} | {wb.get('size_bytes')} | {wb.get('error') or ''} |"
        )
    lines.append("")

    lines.append("## Candidate sheets")
    lines.append("")
    lines.append("| File | Sheet | Status | Source type | Rows | Cols | Date-like | Numeric | Score |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    candidates = []
    for wb in workbook_results:
        for sh in wb.get("sheets", []):
            if sh.get("status") in {"PASS_CANDIDATE_SHEET", "WATCH_CANDIDATE_SHEET"}:
                candidates.append((wb, sh))
    candidates.sort(key=lambda x: (x[1].get("status") != "PASS_CANDIDATE_SHEET", -(x[1].get("parse_score") or 0)))
    for wb, sh in candidates[:40]:
        lines.append(
            f"| `{wb.get('file_name')}` | `{sh.get('sheet_name')}` | {sh.get('status')} | {sh.get('inferred_source_type')} | "
            f"{sh.get('nonempty_row_count')} | {sh.get('max_col_count')} | {sh.get('date_like_cell_count')} | "
            f"{sh.get('numeric_cell_count')} | {sh.get('parse_score')} |"
        )
    lines.append("")

    lines.append("## Top header candidates")
    lines.append("")
    for wb, sh in candidates[:10]:
        lines.append(f"### `{wb.get('file_name')}` / `{sh.get('sheet_name')}`")
        lines.append("")
        for h in sh.get("header_candidates", [])[:3]:
            preview = " | ".join(h.get("preview", []))
            lines.append(f"- row {h.get('row_index_1based')}, score {h.get('score')}: `{preview}`")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38F gold ETF XLSX source parse audit")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--raw-dir", default="data/etf/gold/source_audit/raw")
    ap.add_argument("--reports-dir", default="data/reports/stage38f_gold_etf_source_parse_audit")
    ap.add_argument("--max-rows-per-sheet", type=int, default=20000)
    args = ap.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    reports_dir = Path(args.reports_dir)
    files = discover_files(raw_dir)

    workbook_results: List[Dict[str, Any]] = []
    for p in files:
        workbook_results.append(analyze_workbook(p, args.max_rows_per_sheet))

    workbooks_pass = sum(1 for w in workbook_results if w.get("status") == "PASS")
    workbooks_watch = sum(1 for w in workbook_results if w.get("status") == "WATCH")
    workbooks_fail = sum(1 for w in workbook_results if w.get("status") == "FAIL")
    sheet_pass = sum(1 for w in workbook_results for s in w.get("sheets", []) if s.get("status") == "PASS_CANDIDATE_SHEET")
    sheet_watch = sum(1 for w in workbook_results for s in w.get("sheets", []) if s.get("status") == "WATCH_CANDIDATE_SHEET")
    wgc_candidates = sum(
        1 for w in workbook_results for s in w.get("sheets", [])
        if s.get("status") in {"PASS_CANDIDATE_SHEET", "WATCH_CANDIDATE_SHEET"}
        and s.get("inferred_source_type") == "WGC_GOLD_ETF"
    )
    spdr_candidates = sum(
        1 for w in workbook_results for s in w.get("sheets", [])
        if s.get("status") in {"PASS_CANDIDATE_SHEET", "WATCH_CANDIDATE_SHEET"}
        and s.get("inferred_source_type") == "SPDR_GLD"
    )

    status, decision, warnings, notes = build_decision(workbook_results, sheet_pass, sheet_watch, wgc_candidates, spdr_candidates)
    if not files:
        status = "FAIL"
        decision = "NO_XLSX_FILES_FOUND_IN_RAW_DIR"
        warnings.append(f"No xlsx files found under {raw_dir}")

    audit: Dict[str, Any] = {
        "generated_utc": now_utc_iso(),
        "status": status,
        "decision": decision,
        "raw_dir": str(raw_dir),
        "files_discovered": len(files),
        "workbooks_pass": workbooks_pass,
        "workbooks_watch": workbooks_watch,
        "workbooks_fail": workbooks_fail,
        "sheet_pass_count": sheet_pass,
        "sheet_watch_count": sheet_watch,
        "wgc_candidate_sheet_count": wgc_candidates,
        "spdr_candidate_sheet_count": spdr_candidates,
        "warnings": warnings,
        "notes": notes,
    }

    json_path, md_path = write_reports(reports_dir, audit, workbook_results)
    audit["json_report"] = str(json_path)
    audit["md_report"] = str(md_path)
    # Rewrite with report paths included.
    write_reports(reports_dir, audit, workbook_results)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        insert_audit_tables(con, audit, workbook_results)
    finally:
        con.close()

    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "files_discovered": audit["files_discovered"],
        "sheet_pass_count": audit["sheet_pass_count"],
        "sheet_watch_count": audit["sheet_watch_count"],
        "wgc_candidate_sheet_count": audit["wgc_candidate_sheet_count"],
        "spdr_candidate_sheet_count": audit["spdr_candidate_sheet_count"],
        "json_report": audit["json_report"],
        "md_report": audit["md_report"],
    }, indent=2))
    return 0 if audit["status"] in {"PASS", "WATCH"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
