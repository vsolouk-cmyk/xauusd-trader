"""
Stage32A — Multi-arm research/shadow orchestrator for XAUUSD.

Purpose:
- Keep multiple research arms alive without promoting anything to paper/live/EA.
- Run the current active-shadow + exogenous watchlist wrapper.
- Collect discovery/lineage/candidate outputs into a unified candidate registry.
- Produce one operational report for local and GitHub scheduled observation.

This module is intentionally defensive:
- It does not assume every Stage module exists.
- It does not require pandas.
- It uses SQLite schema introspection instead of hard-coded DB assumptions.
- It writes reports even when some arms fail, so failures remain visible.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
OUT_DIR = REPORT_ROOT / "research_shadow_orchestrator"
DEFAULT_DB = ROOT / "data" / "local" / "xauusd_local_store.sqlite"

CORE_MODULES: List[Tuple[str, str, bool]] = [
    (
        "active_shadow_suite_with_exogenous_watchlist",
        "app.run_active_shadow_suite_with_exogenous_watchlist",
        True,
    ),
]

# These patterns are deliberately broad because earlier stages have evolved names.
REPORT_GLOBS = [
    "active_shadow_suite*/**/*.md",
    "stage27*/**/*.md",
    "stage28*/**/*.md",
    "stage29*/**/*.md",
    "stage30*/**/*.md",
    "stage31*/**/*.md",
]

CANDIDATE_CSV_GLOBS = [
    "**/*candidate*.csv",
    "**/*confirmation*.csv",
    "**/*audit*.csv",
    "**/*validation*.csv",
    "**/*tracker*.csv",
    "**/*registry*.csv",
]

PREFERRED_CANDIDATE_FIELDS = [
    "candidate_name",
    "strategy_name",
    "lineage",
    "family",
    "overlay",
    "macro_feature",
    "macro_gate",
    "events",
    "event_count",
    "confirmed_events",
    "recent_signal_rows",
    "latest_recent_entry_ts",
    "pf",
    "PF",
    "confirmed_pf_x4",
    "confirmed_pf_x6",
    "total_R",
    "confirmed_total_x4",
    "boot_p05_total_x4",
    "stress_0.20_total_x4",
    "years_positive_x4",
    "decision",
]

DECISION_RE = re.compile(r"\b([A-Z0-9_]{8,}(?:_[A-Z0-9]+)*)\b")
KV_RE = re.compile(r"^\s*[-*]?\s*([A-Za-z0-9_.\- /]+?)\s*[:=]\s*(.+?)\s*$")


@dataclass
class ModuleRun:
    arm: str
    module: str
    required: bool
    returncode: int
    started_utc: str
    ended_utc: str
    duration_sec: float
    stdout_log: str
    stderr_log: str
    status: str


@dataclass
class ReportSummary:
    path: str
    modified_utc: str
    size_bytes: int
    decisions: str
    key_metrics_json: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XAUUSD multi-arm research/shadow orchestrator.")
    parser.add_argument(
        "--mode",
        choices=["observation", "full"],
        default=os.getenv("XAUUSD_ORCH_MODE", "observation"),
        help="observation runs safe status arms; full also allows optional modules from env.",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("TRADING_DB", str(DEFAULT_DB)),
        help="SQLite DB path. Defaults to data/local/xauusd_local_store.sqlite.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.getenv("XAUUSD_ORCH_TIMEOUT_SEC", "0")),
        help="Subprocess timeout per module. 0 means no timeout.",
    )
    parser.add_argument(
        "--fail-on-core-error",
        action="store_true",
        default=os.getenv("XAUUSD_ORCH_FAIL_ON_CORE_ERROR", "0") == "1",
        help="Return non-zero if a required/core module fails.",
    )
    parser.add_argument(
        "--skip-module-runs",
        action="store_true",
        default=os.getenv("XAUUSD_ORCH_SKIP_MODULE_RUNS", "0") == "1",
        help="Only aggregate existing reports/registry; do not run modules.",
    )
    return parser.parse_args(argv)


def module_plan(mode: str) -> List[Tuple[str, str, bool]]:
    plan = list(CORE_MODULES)
    extra_raw = os.getenv("XAUUSD_ORCH_EXTRA_MODULES", "").strip()
    if mode == "full" and extra_raw:
        for item in extra_raw.split(","):
            module = item.strip()
            if not module:
                continue
            arm_name = module.split(".")[-1]
            plan.append((arm_name, module, False))
    return plan


def run_module(arm: str, module: str, required: bool, timeout_sec: int) -> ModuleRun:
    start = utc_now()
    stdout_log = OUT_DIR / f"{arm}.stdout.log"
    stderr_log = OUT_DIR / f"{arm}.stderr.log"
    cmd = [sys.executable, "-m", module]
    timeout = None if timeout_sec <= 0 else timeout_sec
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        rc = int(proc.returncode)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        status = "ok" if rc == 0 else "error"
    except subprocess.TimeoutExpired as exc:
        rc = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTIMEOUT after {timeout_sec} seconds"
        status = "timeout"
    except Exception as exc:  # defensive reporting path
        rc = 125
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
        status = "exception"

    end = utc_now()
    stdout_log.write_text(stdout, encoding="utf-8")
    stderr_log.write_text(stderr, encoding="utf-8")
    return ModuleRun(
        arm=arm,
        module=module,
        required=required,
        returncode=rc,
        started_utc=iso(start),
        ended_utc=iso(end),
        duration_sec=round((end - start).total_seconds(), 3),
        stdout_log=rel(stdout_log),
        stderr_log=rel(stderr_log),
        status=status,
    )


def file_mtime_utc(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def extract_report_summary(path: Path) -> ReportSummary:
    text = path.read_text(encoding="utf-8", errors="replace")
    decisions = sorted(set(match.group(1) for match in DECISION_RE.finditer(text)))
    metrics: Dict[str, str] = {}
    for line in text.splitlines():
        match = KV_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().replace(" ", "_")[:80]
        value = match.group(2).strip()
        if len(value) > 160:
            value = value[:157] + "..."
        if key and key not in metrics:
            metrics[key] = value
        if len(metrics) >= 30:
            break
    return ReportSummary(
        path=rel(path),
        modified_utc=file_mtime_utc(path),
        size_bytes=path.stat().st_size,
        decisions=";".join(decisions[:30]),
        key_metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True),
    )


def discover_reports() -> List[ReportSummary]:
    reports: Dict[Path, ReportSummary] = {}
    if not REPORT_ROOT.exists():
        return []
    for pattern in REPORT_GLOBS:
        for path in REPORT_ROOT.glob(pattern):
            if path.is_file() and OUT_DIR not in path.parents:
                try:
                    reports[path] = extract_report_summary(path)
                except Exception:
                    continue
    return sorted(reports.values(), key=lambda r: r.modified_utc, reverse=True)


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        return float(text)
    except Exception:
        return None


def first_present(row: Dict[str, Any], keys: Iterable[str]) -> str:
    lower_map = {str(k).lower(): k for k in row.keys()}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is not None:
            val = row.get(actual)
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    return ""


def candidate_identity(row: Dict[str, Any], source: str) -> str:
    name = first_present(row, ["candidate_name", "strategy_name", "lineage", "setup", "rule_name", "name"])
    family = first_present(row, ["family", "pattern_family"])
    overlay = first_present(row, ["overlay", "gate", "macro_gate"])
    parts = [p for p in [name, family, overlay] if p]
    if parts:
        return " | ".join(parts)
    return source


def score_candidate(row: Dict[str, Any]) -> float:
    """Heuristic priority score for review ordering only; not a trading score."""
    pf = None
    for key in ["confirmed_pf_x4", "confirmed_pf_x6", "pf", "PF", "profit_factor"]:
        pf = safe_float(row.get(key))
        if pf is not None:
            break
    events = None
    for key in ["confirmed_events", "event_count", "events", "n_events", "count"]:
        events = safe_float(row.get(key))
        if events is not None:
            break
    boot = safe_float(row.get("boot_p05_total_x4"))
    stress = safe_float(row.get("stress_0.20_total_x4"))
    recent = safe_float(row.get("recent_signal_rows"))
    score = 0.0
    if pf is not None:
        score += min(pf, 25.0) * 4.0
    if events is not None:
        score += min(events, 500.0) * 0.05
    if boot is not None:
        score += min(max(boot, -200.0), 300.0) * 0.08
    if stress is not None:
        score += min(max(stress, -200.0), 300.0) * 0.04
    if recent is not None:
        score += min(recent, 50.0) * 2.0
    return round(score, 6)


def discover_candidate_csvs() -> List[Path]:
    paths: Dict[Path, None] = {}
    if not REPORT_ROOT.exists():
        return []
    for pattern in CANDIDATE_CSV_GLOBS:
        for path in REPORT_ROOT.glob(pattern):
            if path.is_file() and OUT_DIR not in path.parents:
                paths[path] = None
    return sorted(paths.keys())


def build_candidate_registry() -> List[Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    for csv_path in discover_candidate_csvs():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    continue
                for idx, raw_row in enumerate(reader):
                    row = {str(k): ("" if v is None else str(v).strip()) for k, v in raw_row.items() if k is not None}
                    identity = candidate_identity(row, rel(csv_path))
                    source = rel(csv_path)
                    key = f"{identity}::{source}::{idx}"
                    record: Dict[str, Any] = {
                        "candidate_id": key,
                        "candidate_identity": identity,
                        "source_csv": source,
                        "source_row": idx + 2,  # csv line including header
                        "priority_score_review_only": score_candidate(row),
                    }
                    for field in PREFERRED_CANDIDATE_FIELDS:
                        if field in row and row[field] != "":
                            record[field] = row[field]
                    # Preserve a compact raw payload for columns we did not anticipate.
                    compact_raw = {k: v for k, v in row.items() if v != ""}
                    record["raw_json"] = json.dumps(compact_raw, ensure_ascii=False, sort_keys=True)
                    records[key] = record
        except Exception as exc:
            key = f"CSV_READ_ERROR::{rel(csv_path)}"
            records[key] = {
                "candidate_id": key,
                "candidate_identity": "CSV_READ_ERROR",
                "source_csv": rel(csv_path),
                "source_row": "",
                "priority_score_review_only": -9999,
                "decision": f"CSV_READ_ERROR: {type(exc).__name__}: {exc}",
                "raw_json": "{}",
            }
    return sorted(records.values(), key=lambda r: float(r.get("priority_score_review_only", 0)), reverse=True)


def introspect_db(db_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not db_path.exists():
        return [{"object": "database", "name": rel(db_path), "status": "missing", "row_count": "", "columns": ""}]
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name")
        objects = cur.fetchall()
        for name, obj_type in objects:
            columns = []
            try:
                cur.execute(f"PRAGMA table_info({quote_ident(name)})")
                columns = [r[1] for r in cur.fetchall()]
            except Exception:
                columns = []
            row_count: Any = ""
            if obj_type == "table":
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {quote_ident(name)}")
                    row_count = cur.fetchone()[0]
                except Exception as exc:
                    row_count = f"COUNT_ERROR: {type(exc).__name__}"
            rows.append(
                {
                    "object": obj_type,
                    "name": name,
                    "status": "ok",
                    "row_count": row_count,
                    "columns": ",".join(columns[:80]),
                }
            )
        conn.close()
    except Exception as exc:
        rows.append(
            {
                "object": "database",
                "name": rel(db_path),
                "status": f"open_error: {type(exc).__name__}: {exc}",
                "row_count": "",
                "columns": "",
            }
        )
    return rows


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def stage_decision(module_runs: List[ModuleRun], candidate_rows: List[Dict[str, Any]]) -> str:
    required_errors = [m for m in module_runs if m.required and m.returncode != 0]
    if required_errors:
        return "STAGE32A_ORCHESTRATOR_COMPLETED_WITH_CORE_ERRORS_RESEARCH_SHADOW_ONLY"
    if candidate_rows:
        return "STAGE32A_ORCHESTRATOR_COMPLETED_WITH_CANDIDATE_REGISTRY_RESEARCH_SHADOW_ONLY"
    return "STAGE32A_ORCHESTRATOR_COMPLETED_NO_CANDIDATE_REGISTRY_RESEARCH_SHADOW_ONLY"


def write_markdown_report(
    args: argparse.Namespace,
    module_runs: List[ModuleRun],
    report_summaries: List[ReportSummary],
    candidate_rows: List[Dict[str, Any]],
    db_rows: List[Dict[str, Any]],
) -> str:
    decision = stage_decision(module_runs, candidate_rows)
    required_errors = [m for m in module_runs if m.required and m.returncode != 0]
    optional_errors = [m for m in module_runs if (not m.required) and m.returncode != 0]
    top_candidates = candidate_rows[:20]

    report_path = OUT_DIR / "research_shadow_orchestrator.md"
    lines: List[str] = []
    lines.append("# XAUUSD Stage32A — Multi-Arm Research/Shadow Orchestrator")
    lines.append("")
    lines.append(f"Generated UTC: {iso(utc_now())}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(decision)
    lines.append("EXECUTION_STATUS = RESEARCH_SHADOW_ONLY")
    lines.append("NO_EA_CHANGE = TRUE")
    lines.append("NO_PAPER_LIVE = TRUE")
    lines.append("NO_ORDER_AUTHORIZATION = TRUE")
    lines.append("COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM")
    lines.append("```")
    lines.append("")
    lines.append("## Commercial acceleration guardrail")
    lines.append("")
    lines.append(
        "This orchestrator is not a research detour. Its job is to keep discovery, lineage tracking, "
        "candidate aggregation, and forward observation moving in parallel so that low-cadence historical "
        "edges do not block faster movement toward a commercially usable system."
    )
    lines.append("")
    lines.append("## Module runs")
    lines.append("")
    lines.append("| arm | module | required | returncode | status | duration_sec | stdout | stderr |")
    lines.append("|---|---|---:|---:|---|---:|---|---|")
    if module_runs:
        for run in module_runs:
            lines.append(
                f"| {run.arm} | `{run.module}` | {str(run.required).lower()} | {run.returncode} | "
                f"{run.status} | {run.duration_sec} | `{run.stdout_log}` | `{run.stderr_log}` |"
            )
    else:
        lines.append("| none | n/a | false | 0 | skipped | 0 | n/a | n/a |")
    lines.append("")
    lines.append("## Registry summary")
    lines.append("")
    lines.append("```text")
    lines.append(f"candidate_registry_rows = {len(candidate_rows)}")
    lines.append(f"source_reports_loaded = {len(report_summaries)}")
    lines.append(f"db_objects_seen = {len(db_rows)}")
    lines.append(f"required_module_errors = {len(required_errors)}")
    lines.append(f"optional_module_errors = {len(optional_errors)}")
    lines.append("```")
    lines.append("")
    lines.append("## Top candidate registry rows — review only")
    lines.append("")
    if top_candidates:
        lines.append("| rank | priority_score | candidate_identity | source_csv | decision | latest_recent_entry_ts | recent_signal_rows |")
        lines.append("|---:|---:|---|---|---|---|---:|")
        for idx, row in enumerate(top_candidates, start=1):
            identity = sanitize_md_cell(str(row.get("candidate_identity", "")))
            source = sanitize_md_cell(str(row.get("source_csv", "")))
            dec = sanitize_md_cell(str(row.get("decision", "")))
            latest = sanitize_md_cell(str(row.get("latest_recent_entry_ts", "")))
            recent = sanitize_md_cell(str(row.get("recent_signal_rows", "")))
            lines.append(
                f"| {idx} | {row.get('priority_score_review_only', '')} | {identity} | `{source}` | {dec} | {latest} | {recent} |"
            )
    else:
        lines.append("No candidate CSV rows were found under `data/reports`.")
    lines.append("")
    lines.append("## Latest discovered reports")
    lines.append("")
    lines.append("| modified_utc | path | decisions |")
    lines.append("|---|---|---|")
    for summary in report_summaries[:30]:
        lines.append(
            f"| {summary.modified_utc} | `{sanitize_md_cell(summary.path)}` | {sanitize_md_cell(summary.decisions)} |"
        )
    lines.append("")
    lines.append("## Database status")
    lines.append("")
    lines.append("| object | name | status | row_count | columns_sample |")
    lines.append("|---|---|---|---:|---|")
    for row in db_rows[:80]:
        lines.append(
            f"| {row.get('object','')} | `{sanitize_md_cell(str(row.get('name','')))}` | "
            f"{sanitize_md_cell(str(row.get('status','')))} | {row.get('row_count','')} | "
            f"{sanitize_md_cell(str(row.get('columns',''))[:300])} |"
        )
    lines.append("")
    lines.append("## Next operational interpretation")
    lines.append("")
    lines.append("```text")
    lines.append("1. Keep active/shadow observation running on schedule.")
    lines.append("2. Keep discovery and lineage mining active; do not rely on low-cadence Stage31 candidates alone.")
    lines.append("3. Use candidate_registry.csv/json as the shared promotion-review surface.")
    lines.append("4. Add Stage32B calendar_events enrichment as an additional arm after this orchestrator is stable.")
    lines.append("5. Promotion requires separate explicit evidence and separate explicit authorization.")
    lines.append("```")
    lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return decision


def sanitize_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ensure_dirs()
    args = parse_args(argv)

    module_runs: List[ModuleRun] = []
    if not args.skip_module_runs:
        for arm, module, required in module_plan(args.mode):
            module_runs.append(run_module(arm, module, required, args.timeout_sec))

    report_summaries = discover_reports()
    candidate_rows = build_candidate_registry()
    db_rows = introspect_db(Path(args.db))

    write_csv(OUT_DIR / "module_runs.csv", [asdict(m) for m in module_runs])
    write_json(OUT_DIR / "module_runs.json", [asdict(m) for m in module_runs])
    write_csv(OUT_DIR / "report_manifest.csv", [asdict(r) for r in report_summaries])
    write_json(OUT_DIR / "report_manifest.json", [asdict(r) for r in report_summaries])
    write_csv(OUT_DIR / "candidate_registry.csv", candidate_rows)
    write_json(OUT_DIR / "candidate_registry.json", candidate_rows)
    write_csv(OUT_DIR / "stage_status_manifest.csv", db_rows)
    write_json(OUT_DIR / "stage_status_manifest.json", db_rows)

    decision = write_markdown_report(args, module_runs, report_summaries, candidate_rows, db_rows)
    print(decision)
    print(f"report={rel(OUT_DIR / 'research_shadow_orchestrator.md')}")
    print(f"candidate_registry={rel(OUT_DIR / 'candidate_registry.csv')}")

    if args.fail_on_core_error and any(m.required and m.returncode != 0 for m in module_runs):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
