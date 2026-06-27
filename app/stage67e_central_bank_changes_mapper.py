#!/usr/bin/env python3
"""
Stage67E - WGC central-bank changes mapper.

Local-only parser for World Gold Council central bank changes workbook.
It extracts the Monthly sheet into:
  data/exogenous/central_bank_demand.csv                 (monthly net change, tonnes)
  data/exogenous/wgc_raw_extracted/central_bank_changes_monthly_global.csv
and updates:
  data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
with a lag-safe daily-forward-filled 3-month rolling sum:
  central_bank_demand_tonnes_3m

No internet, no broker, no order, no threshold tuning.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

STAGE = "Stage67E_CENTRAL_BANK_CHANGES_MAPPER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE67E",
    "NO_INTERNET_DOWNLOAD_FROM_STAGE67E",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DATA_MAPPER_ONLY",
]

NS_MAIN = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def sha256_path(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return float(x)
    s = str(x).strip().replace(",", "")
    if not s or s in {"-", "—", "na", "n/a", "NA", "N/A"}:
        return None
    try:
        v = float(s)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def col_index(cell_ref: str) -> int:
    m = re.match(r"([A-Z]+)", cell_ref)
    if not m:
        raise ValueError(f"bad cell ref {cell_ref!r}")
    letters = m.group(1)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx


def excel_serial_to_date(serial: float) -> date:
    # Excel 1900 serial system, compatible with openpyxl/pandas convention.
    return (datetime(1899, 12, 30) + timedelta(days=float(serial))).date()


def month_end(d: date) -> date:
    if d.month == 12:
        nxt = date(d.year + 1, 1, 1)
    else:
        nxt = date(d.year, d.month + 1, 1)
    return nxt - timedelta(days=1)


class XlsxReader:
    def __init__(self, path: Path):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.shared_strings = self._read_shared_strings()
        self.sheets = self._read_sheets()

    def _read_shared_strings(self) -> List[str]:
        if "xl/sharedStrings.xml" not in self.zf.namelist():
            return []
        root = ET.fromstring(self.zf.read("xl/sharedStrings.xml"))
        strings: List[str] = []
        for si in root.findall("m:si", NS_MAIN):
            parts = [t.text or "" for t in si.findall(".//m:t", NS_MAIN)]
            strings.append("".join(parts))
        return strings

    def _read_sheets(self) -> Dict[str, str]:
        workbook = ET.fromstring(self.zf.read("xl/workbook.xml"))
        rels = ET.fromstring(self.zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        result: Dict[str, str] = {}
        for sheet in workbook.find("m:sheets", NS_MAIN):
            name = sheet.attrib["name"]
            rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = relmap[rid]
            if not target.startswith("xl/"):
                target = "xl/" + target
            result[name] = target
        return result

    def sheet_names(self) -> List[str]:
        return list(self.sheets.keys())

    def read_sheet_cells(self, sheet_name: str) -> Dict[int, Dict[int, Any]]:
        real_name = None
        for name in self.sheets:
            if name.lower() == sheet_name.lower():
                real_name = name
                break
        if not real_name:
            raise ValueError(f"sheet {sheet_name!r} not found; sheets={self.sheet_names()}")
        root = ET.fromstring(self.zf.read(self.sheets[real_name]))
        rows: Dict[int, Dict[int, Any]] = {}
        for row in root.findall(".//m:row", NS_MAIN):
            r = int(row.attrib["r"])
            out: Dict[int, Any] = {}
            for c in row.findall("m:c", NS_MAIN):
                ref = c.attrib.get("r", "")
                if not ref:
                    continue
                ci = col_index(ref)
                v_elem = c.find("m:v", NS_MAIN)
                if v_elem is None:
                    continue
                raw = v_elem.text
                ctype = c.attrib.get("t")
                val: Any = raw
                if ctype == "s":
                    try:
                        val = self.shared_strings[int(raw)]
                    except Exception:
                        val = raw
                else:
                    try:
                        if raw is not None and re.fullmatch(r"[-+]?\d+(\.\d+)?([Ee][-+]?\d+)?", raw):
                            val = float(raw)
                            if float(val).is_integer():
                                # keep date serials and integers readable; values are re-floated downstream.
                                val = int(val)
                    except Exception:
                        val = raw
                out[ci] = val
            if out:
                rows[r] = out
        return rows


def find_changes_workbook(download_dir: Path, config: Dict[str, Any]) -> Optional[Path]:
    explicit = config.get("central_bank_changes_path")
    if explicit:
        p = Path(explicit).expanduser()
        if p.exists():
            return p
    patterns = config.get("central_bank_changes_globs") or [
        "Changes_latest*.xlsx",
        "Changes_in_World_Official_Gold_Reserves*.xlsx",
        "*Changes*Official*Gold*Reserves*.xlsx",
        "*Changes*.xlsx",
    ]
    candidates: List[Path] = []
    for pat in patterns:
        candidates.extend(download_dir.glob(pat))
    candidates = sorted(set(candidates), key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    return candidates[0] if candidates else None


def parse_monthly_changes_xlsx(path: Path, config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    reader = XlsxReader(path)
    sheet_name = config.get("monthly_sheet_name", "Monthly")
    rows = reader.read_sheet_cells(sheet_name)
    header_row = int(config.get("monthly_header_row", 8))
    data_start_row = int(config.get("monthly_data_start_row", 9))
    first_month_col = int(config.get("monthly_first_month_col", 4))  # D
    country_col = int(config.get("country_col", 2))

    if header_row not in rows:
        raise ValueError(f"header row {header_row} not found in sheet {sheet_name}")
    header = rows[header_row]
    date_cols: List[Tuple[int, date, date]] = []
    for ci, val in sorted(header.items()):
        if ci < first_month_col:
            continue
        serial = safe_float(val)
        if serial is None:
            continue
        try:
            m_start = excel_serial_to_date(serial)
            # WGC headers are month starts; use month-end to avoid assuming the full-month change was known on day 1.
            date_cols.append((ci, m_start, month_end(m_start)))
        except Exception:
            continue

    if len(date_cols) < 60:
        raise ValueError(f"too few monthly date columns parsed: {len(date_cols)}")

    data_rows = []
    for r, vals in sorted(rows.items()):
        if r < data_start_row:
            continue
        country = vals.get(country_col)
        if country is None or str(country).strip() == "":
            continue
        data_rows.append((r, str(country).strip(), vals))

    if len(data_rows) < 25:
        raise ValueError(f"too few country rows parsed: {len(data_rows)}")

    monthly: List[Dict[str, Any]] = []
    for ci, m_start, m_end in date_cols:
        total = 0.0
        contributors = 0
        nonzero = 0
        for _r, _country, vals in data_rows:
            v = safe_float(vals.get(ci))
            if v is None:
                continue
            total += v
            contributors += 1
            if abs(v) > 1e-12:
                nonzero += 1
        monthly.append(
            {
                "date_utc": m_end.isoformat(),
                "month_start_utc": m_start.isoformat(),
                "monthly_net_change_tonnes": round(total, 10),
                "contributor_count": contributors,
                "nonzero_country_count": nonzero,
            }
        )

    # Add rolling 3M sum on monthly cadence.
    for i, row in enumerate(monthly):
        if i < 2:
            row["central_bank_demand_tonnes_3m"] = None
        else:
            row["central_bank_demand_tonnes_3m"] = round(
                sum(float(monthly[j]["monthly_net_change_tonnes"]) for j in range(i - 2, i + 1)),
                10,
            )

    parse_info = {
        "status": "PASS",
        "source": str(path),
        "sheet_names": reader.sheet_names(),
        "selected_sheet": sheet_name,
        "header_row": header_row,
        "data_start_row": data_start_row,
        "month_column_count": len(date_cols),
        "country_row_count": len(data_rows),
        "min_month_start": monthly[0]["month_start_utc"] if monthly else None,
        "max_month_start": monthly[-1]["month_start_utc"] if monthly else None,
        "min_date_utc": monthly[0]["date_utc"] if monthly else None,
        "max_date_utc": monthly[-1]["date_utc"] if monthly else None,
        "latest_monthly_net_change_tonnes": monthly[-1]["monthly_net_change_tonnes"] if monthly else None,
        "latest_3m_sum_tonnes": monthly[-1]["central_bank_demand_tonnes_3m"] if monthly else None,
    }
    return monthly, parse_info


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            out = {k: row.get(k) for k in fieldnames}
            w.writerow(out)


def parse_iso_date(s: str) -> Optional[date]:
    if s is None:
        return None
    text = str(s).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def latest_month_for_date(monthly: List[Dict[str, Any]], d: date) -> Optional[Dict[str, Any]]:
    # monthly sorted by date_utc ascending, small enough for linear scan. Keeps code dependency-free.
    best = None
    for row in monthly:
        md = parse_iso_date(str(row.get("date_utc")))
        if md and md <= d:
            best = row
        elif md and md > d:
            break
    return best


def update_macro_dataset(root: Path, monthly: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    macro_path = root / config.get(
        "macro_dataset_path",
        "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    )
    if not macro_path.exists():
        return {"status": "FAIL", "error": f"macro dataset not found: {macro_path}"}

    before_hash = sha256_path(macro_path)
    rows = read_csv_dicts(macro_path)
    if not rows:
        return {"status": "FAIL", "error": "macro dataset empty"}

    cols = list(rows[0].keys())
    date_col = "feature_date_utc" if "feature_date_utc" in cols else "date_utc" if "date_utc" in cols else None
    if not date_col:
        return {"status": "FAIL", "error": f"macro dataset has no date column; columns={cols}"}

    if "central_bank_demand" not in cols:
        cols.append("central_bank_demand")
    if "central_bank_demand_tonnes_3m" not in cols:
        cols.append("central_bank_demand_tonnes_3m")

    coverage = 0
    latest_feature_date = None
    latest_value = None
    latest_month_used = None
    for row in rows:
        d = parse_iso_date(row.get(date_col, ""))
        if not d:
            row["central_bank_demand"] = ""
            row["central_bank_demand_tonnes_3m"] = ""
            continue
        latest_feature_date = d.isoformat()
        m = latest_month_for_date(monthly, d)
        if m is None or m.get("central_bank_demand_tonnes_3m") in (None, ""):
            row["central_bank_demand"] = ""
            row["central_bank_demand_tonnes_3m"] = ""
            continue
        row["central_bank_demand"] = str(m["monthly_net_change_tonnes"])
        row["central_bank_demand_tonnes_3m"] = str(m["central_bank_demand_tonnes_3m"])
        coverage += 1
        latest_value = m["central_bank_demand_tonnes_3m"]
        latest_month_used = m["date_utc"]

    backup_dir = macro_path.parent / "_repair_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{macro_path.stem}_before_stage67e_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
    shutil.copy2(macro_path, backup_path)

    with macro_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    after_hash = sha256_path(macro_path)
    return {
        "status": "PASS",
        "macro_path": str(macro_path),
        "rows": len(rows),
        "date_col": date_col,
        "latest_feature_date": latest_feature_date,
        "coverage_rows": coverage,
        "coverage_pct": round(coverage / len(rows) * 100.0, 4),
        "latest_central_bank_demand_tonnes_3m": latest_value,
        "latest_month_used": latest_month_used,
        "hash_before": before_hash,
        "hash_after": after_hash,
        "hash_changed": before_hash != after_hash,
        "backup_path": str(backup_path),
    }


def run_child(cmd: List[str], timeout_seconds: int) -> Dict[str, Any]:
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
        return {
            "attempted": True,
            "cmd": cmd,
            "returncode": p.returncode,
            "status": "PASS" if p.returncode == 0 else "FAIL",
            "stdout_tail": p.stdout[-2000:],
            "stderr_tail": p.stderr[-2000:],
            "timeout_seconds": timeout_seconds,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "attempted": True,
            "cmd": cmd,
            "returncode": None,
            "status": "TIMEOUT",
            "stdout_tail": (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
            "stderr_tail": (e.stderr or "")[-2000:] if isinstance(e.stderr, str) else "",
            "timeout_seconds": timeout_seconds,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage67e_central_bank_changes_mapper.json")
    ap.add_argument("--out", default="reports/stage67e_central_bank_changes_mapper")
    ap.add_argument("--run-readiness", action="store_true")
    ap.add_argument("--run-frequency", action="store_true")
    ap.add_argument("--timeout-seconds", type=int, default=120)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config: Dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)

    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    download_dir = Path(config.get("download_dir", str(Path.home() / "Downloads"))).expanduser()
    issues: List[str] = []
    source = find_changes_workbook(download_dir, config)
    if not source:
        issues.append("CENTRAL_BANK_CHANGES_XLSX_NOT_FOUND")
        summary = {
            "stage": STAGE,
            "root": str(root),
            "config": str(config_path.relative_to(root)) if str(config_path).startswith(str(root)) else str(config_path),
            "generated_utc": utc_now(),
            "status": "STAGE67E_COMPLETE_WITH_ISSUES_NO_PROMOTION",
            "decision": "STAGE67E_STOP_CENTRAL_BANK_CHANGES_SOURCE_MISSING_NO_ORDER",
            "classification": "S67E_STOP_SOURCE_MISSING",
            "issues": issues,
            "hard_blocks": HARD_BLOCKS,
        }
        (out_dir / "stage67e_central_bank_changes_mapper_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"stage": STAGE, "status": summary["status"], "decision": summary["decision"]}, indent=2))
        return 2

    try:
        monthly, parse_info = parse_monthly_changes_xlsx(source, config)
    except Exception as e:
        issues.append("CENTRAL_BANK_CHANGES_PARSE_EXCEPTION")
        parse_info = {"status": "FAIL", "source": str(source), "error": str(e)}
        monthly = []

    source_refresh: Dict[str, Any] = {
        "download_dir": str(download_dir),
        "selected_source": str(source),
        "parse_info": parse_info,
    }

    raw_output = None
    canonical_output = None
    macro_update = {"status": "SKIPPED"}
    if monthly and parse_info.get("status") == "PASS":
        raw_output = root / config.get(
            "raw_monthly_output_path",
            "data/exogenous/wgc_raw_extracted/central_bank_changes_monthly_global.csv",
        )
        write_csv(
            raw_output,
            monthly,
            ["date_utc", "month_start_utc", "monthly_net_change_tonnes", "central_bank_demand_tonnes_3m", "contributor_count", "nonzero_country_count"],
        )

        canonical_rows = [{"date_utc": row["date_utc"], "value": row["monthly_net_change_tonnes"]} for row in monthly]
        canonical_output = root / config.get("central_bank_demand_path", "data/exogenous/central_bank_demand.csv")
        write_csv(canonical_output, canonical_rows, ["date_utc", "value"])

        macro_update = update_macro_dataset(root, monthly, config)
        if macro_update.get("status") != "PASS":
            issues.append("MACRO_CENTRAL_BANK_UPDATE_FAILED")

    if not monthly:
        issues.append("CENTRAL_BANK_CHANGES_NO_MONTHLY_ROWS")

    readiness_run = {"attempted": False, "status": "SKIPPED"}
    if args.run_readiness and macro_update.get("status") == "PASS":
        readiness_cmd = [
            sys.executable,
            str(root / "app/stage66j3_direct_readiness_after_refresh.py"),
            "--root", str(root),
            "--config", str(root / "configs/stage66j3_direct_readiness_after_refresh.json"),
            "--out", str(root / "reports/stage66j3_direct_readiness_after_refresh"),
        ]
        readiness_run = run_child(readiness_cmd, args.timeout_seconds)
        if readiness_run.get("status") != "PASS":
            issues.append("STAGE66J3_TIMEOUT_OR_FAILURE")

    frequency_run = {"attempted": False, "status": "SKIPPED"}
    if args.run_frequency and macro_update.get("status") == "PASS":
        frequency_cmd = [
            sys.executable,
            str(root / "app/stage68_signal_frequency_audit.py"),
            "--root", str(root),
            "--config", str(root / "configs/stage68_signal_frequency_audit.json"),
            "--out", str(root / "reports/stage68_signal_frequency_audit"),
        ]
        frequency_run = run_child(frequency_cmd, args.timeout_seconds)
        if frequency_run.get("status") != "PASS":
            issues.append("STAGE68_TIMEOUT_OR_FAILURE")

    ok = parse_info.get("status") == "PASS" and macro_update.get("status") == "PASS" and not any(i.endswith("FAILED") for i in issues)
    if ok:
        status = "STAGE67E_COMPLETE_NO_PROMOTION"
        decision = "STAGE67E_CENTRAL_BANK_CHANGES_MAPPED_REBUILD_COMPLETE_NO_ORDER"
        classification = "S67E_CENTRAL_BANK_3M_READY"
    else:
        status = "STAGE67E_COMPLETE_WITH_ISSUES_NO_PROMOTION"
        decision = "STAGE67E_STOP_CENTRAL_BANK_CHANGES_OR_MACRO_ISSUE_NO_ORDER"
        classification = "S67E_STOP_OR_PARTIAL"

    outputs = {
        "summary_json": str(out_dir / "stage67e_central_bank_changes_mapper_summary.json"),
        "report_md": str(out_dir / "stage67e_central_bank_changes_mapper_report.md"),
        "raw_monthly_csv": str(raw_output) if raw_output else None,
        "central_bank_demand_csv": str(canonical_output) if canonical_output else None,
        "ledger_csv": "data/forward_shadow/stage67e_central_bank_changes_mapper_ledger.csv",
    }

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path.relative_to(root)) if str(config_path).startswith(str(root)) else str(config_path),
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "source_refresh": source_refresh,
        "macro_update": macro_update,
        "readiness_run": readiness_run,
        "frequency_run": frequency_run,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_notes": [
            "Stage67E uses WGC Monthly changes, not the latest holdings cross-section.",
            "Monthly changes are aggregated globally and converted into a 3-month rolling sum.",
            "Monthly headers are treated as month starts and conservatively aligned to month-end before daily forward-fill.",
            "No order, broker, EA, paper-live, or live path is authorized.",
        ],
        "outputs": outputs,
    }

    with (out_dir / "stage67e_central_bank_changes_mapper_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report = [
        "# Stage67E Central Bank Changes Mapper",
        "",
        "## Decision",
        "",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        "",
        "## Source parse",
        "",
        "```json",
        json.dumps(parse_info, indent=2),
        "```",
        "",
        "## Macro update",
        "",
        "```json",
        json.dumps(macro_update, indent=2),
        "```",
        "",
        "## Readiness run",
        "",
        "```json",
        json.dumps(readiness_run, indent=2),
        "```",
        "",
        "## Frequency run",
        "",
        "```json",
        json.dumps(frequency_run, indent=2),
        "```",
        "",
        "## Issues",
        "",
    ]
    if issues:
        report.extend([f"- `{x}`" for x in issues])
    else:
        report.append("- none")
    report.extend(["", "## Hard blocks", ""])
    report.extend([f"- `{x}`" for x in HARD_BLOCKS])
    (out_dir / "stage67e_central_bank_changes_mapper_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    # Append small ledger row.
    ledger_path = root / "data/forward_shadow/stage67e_central_bank_changes_mapper_ledger.csv"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_exists = ledger_path.exists()
    with ledger_path.open("a", encoding="utf-8", newline="") as f:
        fieldnames = ["generated_utc", "status", "decision", "source", "max_month", "latest_3m_sum", "macro_rows", "coverage_pct"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not ledger_exists:
            w.writeheader()
        w.writerow({
            "generated_utc": summary["generated_utc"],
            "status": status,
            "decision": decision,
            "source": str(source),
            "max_month": parse_info.get("max_date_utc"),
            "latest_3m_sum": parse_info.get("latest_3m_sum_tonnes"),
            "macro_rows": macro_update.get("rows"),
            "coverage_pct": macro_update.get("coverage_pct"),
        })

    print(json.dumps({
        "stage": STAGE,
        "status": status,
        "decision": decision,
        "classification": classification,
        "latest_3m_sum_tonnes": parse_info.get("latest_3m_sum_tonnes"),
        "macro_coverage_pct": macro_update.get("coverage_pct"),
        "summary_json": str(out_dir / "stage67e_central_bank_changes_mapper_summary.json"),
        "report_md": str(out_dir / "stage67e_central_bank_changes_mapper_report.md"),
    }, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
