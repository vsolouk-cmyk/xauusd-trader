"""
Stage32A-HF1 — Commercial Candidate Supply Orchestrator for XAUUSD.

Purpose:
- Keep the project moving toward the fastest safe commercially usable system.
- Keep data refresh, observation, discovery, lineage validation, forward tracking,
  candidate aggregation, and commercial-readiness diagnostics visible in one run.
- Avoid turning the project into research-only reporting: every report explicitly
  separates commercial blockers from research artifacts.

Safety:
- Research/shadow only.
- No EA changes.
- No paper/live/order authorization.
- SQLite DB remains the source of truth and is inspected through schema introspection.

Designed to be defensive:
- Optional arms may fail without hiding the failure.
- Missing reports/DB tables become visible diagnostics, not uncaught assumptions.
- It does not require pandas; stage modules may require pandas themselves.
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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
OUT_DIR = REPORT_ROOT / "research_shadow_orchestrator"
DEFAULT_DB = ROOT / "data" / "local" / "xauusd_local_store.sqlite"

# Broad report discovery; intentionally includes older active arms because they
# may still be relevant for candidate supply and transition diagnostics.
REPORT_GLOBS = [
    "active_shadow_suite*/**/*.md",
    "stage16*/**/*.md",
    "stage18*/**/*.md",
    "stage23*/**/*.md",
    "stage25*/**/*.md",
    "stage27*/**/*.md",
    "stage28*/**/*.md",
    "stage29*/**/*.md",
    "stage30*/**/*.md",
    "stage31*/**/*.md",
    "stage32*/**/*.md",
]

CANDIDATE_CSV_GLOBS = [
    "**/*candidate*.csv",
    "**/*confirmation*.csv",
    "**/*audit*.csv",
    "**/*validation*.csv",
    "**/*tracker*.csv",
    "**/*registry*.csv",
    "**/*shortlist*.csv",
    "**/*gate*.csv",
    "**/*family*.csv",
]

PREFERRED_CANDIDATE_FIELDS = [
    "candidate_name",
    "strategy_name",
    "lineage",
    "family",
    "pattern_family",
    "setup",
    "overlay",
    "gate",
    "macro_feature",
    "macro_gate",
    "direction",
    "events",
    "event_count",
    "n_events",
    "count",
    "confirmed_events",
    "trades",
    "recent_signal_rows",
    "latest_recent_entry_ts",
    "latest_signal_ts",
    "pf",
    "PF",
    "profit_factor",
    "confirmed_pf_x4",
    "confirmed_pf_x6",
    "avgR",
    "avg_r",
    "wr",
    "win_rate",
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
class ModuleSpec:
    arm: str
    module: str
    required: bool = False
    group: str = "misc"
    enabled_by_default: bool = True


@dataclass
class ModuleRun:
    arm: str
    module: str
    group: str
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


def truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def csv_env(name: str) -> List[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XAUUSD Stage32A-HF1 commercial candidate supply orchestrator.")
    parser.add_argument(
        "--mode",
        choices=["aggregate", "observation", "supply", "full"],
        default=os.getenv("XAUUSD_ORCH_MODE", "observation"),
        help=(
            "aggregate only builds dashboards from existing artifacts; observation runs active/shadow; "
            "supply also runs discovery/lineage arms; full also runs extra env modules."
        ),
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
        default=truthy_env("XAUUSD_ORCH_FAIL_ON_CORE_ERROR", "0"),
        help="Return non-zero if a required/core module fails.",
    )
    parser.add_argument(
        "--skip-module-runs",
        action="store_true",
        default=truthy_env("XAUUSD_ORCH_SKIP_MODULE_RUNS", "0"),
        help="Only aggregate existing reports/registry; do not run modules.",
    )
    parser.add_argument(
        "--run-data-refresh-arm",
        action="store_true",
        default=truthy_env("XAUUSD_ORCH_RUN_DATA_REFRESH_ARM", "0"),
        help=(
            "Run app.stage16e_amarkets_csv_refresh_cycle as a separate arm before the active suite. "
            "Default is off because active_shadow_suite already attempts this import first."
        ),
    )
    parser.add_argument(
        "--run-discovery-arms",
        action="store_true",
        default=truthy_env("XAUUSD_ORCH_RUN_DISCOVERY_ARMS", "0"),
        help="Run candidate-supply discovery and lineage arms even in observation mode.",
    )
    parser.add_argument(
        "--skip-active-wrapper",
        action="store_true",
        default=truthy_env("XAUUSD_ORCH_SKIP_ACTIVE_WRAPPER", "0"),
        help="Skip app.run_active_shadow_suite_with_exogenous_watchlist.",
    )
    return parser.parse_args(argv)


def base_specs(args: argparse.Namespace) -> List[ModuleSpec]:
    specs: List[ModuleSpec] = []

    # Data refresh is kept explicit in the orchestrator report. It is not enabled
    # by default because the active suite already invokes Stage16E first; running
    # it twice is wasteful and may scan Downloads twice.
    if args.run_data_refresh_arm:
        specs.append(ModuleSpec(
            arm="data_refresh_amarkets_csv_import",
            module="app.stage16e_amarkets_csv_refresh_cycle",
            required=False,
            group="data_refresh",
        ))

    if not args.skip_active_wrapper:
        specs.append(ModuleSpec(
            arm="active_shadow_suite_with_exogenous_watchlist",
            module="app.run_active_shadow_suite_with_exogenous_watchlist",
            required=True,
            group="observation",
        ))

    run_supply = args.mode in {"supply", "full"} or args.run_discovery_arms
    if run_supply:
        specs.extend([
            ModuleSpec(
                arm="candidate_supply_discovery_factory",
                module="app.stage28a_discovery_factory_batch_runner",
                required=False,
                group="discovery",
            ),
            ModuleSpec(
                arm="lineage_gate_discovery",
                module="app.stage27b_db_first_lineage_gate_discovery",
                required=False,
                group="lineage_discovery",
            ),
            ModuleSpec(
                arm="h1_atr_gate_validation",
                module="app.stage27c_db_first_h1_atr_gate_validation",
                required=False,
                group="lineage_validation",
            ),
            ModuleSpec(
                arm="forward_safe_meta_gate_validation",
                module="app.stage28c_forward_safe_meta_gate_validation",
                required=False,
                group="lineage_validation",
            ),
            ModuleSpec(
                arm="forward_safe_meta_gate_tracker",
                module="app.stage28d_forward_safe_meta_gate_tracker",
                required=False,
                group="forward_tracking",
            ),
            ModuleSpec(
                arm="high_range_regime_continuation_discovery",
                module="app.stage29a_high_range_regime_continuation_discovery",
                required=False,
                group="discovery",
            ),
            ModuleSpec(
                arm="ml_candidate_pool_builder",
                module="app.stage30a_candidate_pool_builder_ml_dataset",
                required=False,
                group="candidate_pool",
            ),
            ModuleSpec(
                arm="ml_lite_feature_ranker",
                module="app.stage30b_ml_lite_feature_ranker",
                required=False,
                group="candidate_pool",
            ),
        ])

    if args.mode == "full":
        for module in csv_env("XAUUSD_ORCH_EXTRA_MODULES"):
            specs.append(ModuleSpec(
                arm=module.split(".")[-1],
                module=module,
                required=False,
                group="extra",
            ))
    return specs


def module_plan(args: argparse.Namespace) -> List[ModuleSpec]:
    if args.mode == "aggregate":
        return []
    return base_specs(args)


def run_module(spec: ModuleSpec, timeout_sec: int) -> ModuleRun:
    start = utc_now()
    safe_arm = re.sub(r"[^A-Za-z0-9_.-]+", "_", spec.arm)
    stdout_log = OUT_DIR / f"{safe_arm}.stdout.log"
    stderr_log = OUT_DIR / f"{safe_arm}.stderr.log"
    cmd = [sys.executable, "-m", spec.module]
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
        arm=spec.arm,
        module=spec.module,
        group=spec.group,
        required=spec.required,
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
        decisions=";".join(decisions[:40]),
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
        if not text or text.lower() in {"nan", "none", "null", ""}:
            return None
        return float(text)
    except Exception:
        return None


def safe_int_like(value: Any) -> Optional[int]:
    val = safe_float(value)
    if val is None:
        return None
    return int(round(val))


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
    macro_feature = first_present(row, ["macro_feature"])
    parts = [p for p in [name, family, overlay, macro_feature] if p]
    if parts:
        return " | ".join(parts)
    return source


def candidate_stage(source_csv: str) -> str:
    m = re.search(r"(stage\d+[a-z]?)", source_csv, flags=re.IGNORECASE)
    return m.group(1).lower() if m else "unknown"


def candidate_family(row: Dict[str, Any], source_csv: str) -> str:
    fam = first_present(row, ["family", "pattern_family"])
    if fam:
        return fam
    identity = str(row.get("candidate_identity", ""))
    if "london" in identity.lower():
        return "london"
    if "ny" in identity.lower():
        return "ny"
    if "real_yield" in identity.lower() or "us10y" in identity.lower():
        return "exogenous_macro"
    return candidate_stage(source_csv)


def score_candidate(row: Dict[str, Any]) -> float:
    """Heuristic priority score for review ordering only; not a trading score."""
    pf = None
    for key in ["confirmed_pf_x4", "confirmed_pf_x6", "pf", "PF", "profit_factor"]:
        pf = safe_float(row.get(key))
        if pf is not None:
            break
    events = None
    for key in ["confirmed_events", "event_count", "events", "n_events", "count", "trades"]:
        events = safe_float(row.get(key))
        if events is not None:
            break
    boot = safe_float(row.get("boot_p05_total_x4"))
    stress = safe_float(row.get("stress_0.20_total_x4"))
    recent = safe_float(row.get("recent_signal_rows"))
    avg_r = None
    for key in ["avgR", "avg_r", "avg_R"]:
        avg_r = safe_float(row.get(key))
        if avg_r is not None:
            break
    score = 0.0
    if pf is not None:
        score += min(pf, 25.0) * 4.0
    if events is not None:
        score += min(events, 1000.0) * 0.04
    if boot is not None:
        score += min(max(boot, -200.0), 300.0) * 0.08
    if stress is not None:
        score += min(max(stress, -200.0), 300.0) * 0.04
    if recent is not None:
        score += min(recent, 100.0) * 2.0
    if avg_r is not None:
        score += min(max(avg_r, -5.0), 10.0) * 4.0
    return round(score, 6)


def density_bucket(row: Dict[str, Any]) -> str:
    recent = safe_float(row.get("recent_signal_rows"))
    latest = str(row.get("latest_recent_entry_ts", row.get("latest_signal_ts", ""))).strip()
    events = None
    for key in ["confirmed_events", "event_count", "events", "n_events", "count", "trades"]:
        events = safe_float(row.get(key))
        if events is not None:
            break
    if recent is not None:
        if recent <= 0:
            return "NO_RECENT_FORWARD_ACTIVITY"
        if recent < 5:
            return "LOW_RECENT_FORWARD_ACTIVITY"
        return "RECENT_FORWARD_ACTIVITY_PRESENT"
    if latest:
        return "HAS_LATEST_SIGNAL_TS_NO_RECENT_COUNT"
    if events is not None:
        if events < 30:
            return "LOW_HISTORICAL_DENSITY"
        if events < 100:
            return "MODERATE_HISTORICAL_DENSITY"
        return "HISTORICAL_DENSITY_PRESENT_FORWARD_UNKNOWN"
    return "UNKNOWN_DENSITY"


def commercial_blocker(row: Dict[str, Any]) -> str:
    decision = str(row.get("decision", "")).upper()
    bucket = str(row.get("density_bucket", density_bucket(row)))
    if "REJECT" in decision or "ERROR" in decision:
        return "REJECTED_OR_ERROR_SOURCE"
    if bucket in {"NO_RECENT_FORWARD_ACTIVITY", "LOW_RECENT_FORWARD_ACTIVITY", "LOW_HISTORICAL_DENSITY"}:
        return "CANDIDATE_SUPPLY_DENSITY_BLOCKER"
    if bucket == "UNKNOWN_DENSITY":
        return "FORWARD_DENSITY_UNKNOWN"
    return "REVIEW_READY_NOT_PROMOTED"


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
                    stage = candidate_stage(source)
                    family = candidate_family({**row, "candidate_identity": identity}, source)
                    key = f"{identity}::{source}::{idx}"
                    record: Dict[str, Any] = {
                        "candidate_id": key,
                        "candidate_identity": identity,
                        "family_key": family,
                        "stage": stage,
                        "source_csv": source,
                        "source_row": idx + 2,  # csv line including header
                        "priority_score_review_only": score_candidate(row),
                    }
                    for field in PREFERRED_CANDIDATE_FIELDS:
                        if field in row and row[field] != "":
                            record[field] = row[field]
                    record["density_bucket"] = density_bucket(record)
                    record["commercial_blocker"] = commercial_blocker(record)
                    compact_raw = {k: v for k, v in row.items() if v != ""}
                    record["raw_json"] = json.dumps(compact_raw, ensure_ascii=False, sort_keys=True)
                    records[key] = record
        except Exception as exc:
            key = f"CSV_READ_ERROR::{rel(csv_path)}"
            records[key] = {
                "candidate_id": key,
                "candidate_identity": "CSV_READ_ERROR",
                "family_key": "error",
                "stage": candidate_stage(rel(csv_path)),
                "source_csv": rel(csv_path),
                "source_row": "",
                "priority_score_review_only": -9999,
                "density_bucket": "UNKNOWN_DENSITY",
                "commercial_blocker": "REJECTED_OR_ERROR_SOURCE",
                "decision": f"CSV_READ_ERROR: {type(exc).__name__}: {exc}",
                "raw_json": "{}",
            }
    return sorted(records.values(), key=lambda r: float(r.get("priority_score_review_only", 0)), reverse=True)


def maybe_max_float(values: Iterable[Any]) -> Optional[float]:
    nums = [safe_float(v) for v in values]
    nums = [v for v in nums if v is not None]
    return max(nums) if nums else None


def latest_text(values: Iterable[Any]) -> str:
    vals = sorted([str(v).strip() for v in values if str(v).strip()])
    return vals[-1] if vals else ""


def build_candidate_supply_summary(candidate_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in candidate_rows:
        groups.setdefault(str(row.get("candidate_identity", "UNKNOWN")), []).append(row)
    summaries: List[Dict[str, Any]] = []
    for identity, rows in groups.items():
        best_score = maybe_max_float(r.get("priority_score_review_only") for r in rows) or 0.0
        recent_max = maybe_max_float(r.get("recent_signal_rows") for r in rows)
        event_max = maybe_max_float(
            first_present(r, ["confirmed_events", "event_count", "events", "n_events", "count", "trades"])
            for r in rows
        )
        latest = latest_text(first_present(r, ["latest_recent_entry_ts", "latest_signal_ts"]) for r in rows)
        blockers = sorted(set(str(r.get("commercial_blocker", "")) for r in rows if str(r.get("commercial_blocker", ""))))
        buckets = sorted(set(str(r.get("density_bucket", "")) for r in rows if str(r.get("density_bucket", ""))))
        stages = sorted(set(str(r.get("stage", "")) for r in rows if str(r.get("stage", ""))))
        families = sorted(set(str(r.get("family_key", "")) for r in rows if str(r.get("family_key", ""))))
        if recent_max is None or recent_max <= 0:
            commercial_readiness = "BLOCKED_LOW_FORWARD_CADENCE"
        elif event_max is not None and event_max < 30:
            commercial_readiness = "BLOCKED_LOW_EVENT_DENSITY"
        elif any("REJECTED" in b for b in blockers):
            commercial_readiness = "BLOCKED_REJECTED_OR_ERROR_SOURCE"
        else:
            commercial_readiness = "REVIEW_READY_RESEARCH_SHADOW_ONLY"
        summaries.append({
            "candidate_identity": identity,
            "best_priority_score_review_only": round(best_score, 6),
            "source_row_count": len(rows),
            "source_csv_count": len(set(str(r.get("source_csv", "")) for r in rows)),
            "families": ";".join(families),
            "stages": ";".join(stages),
            "density_buckets": ";".join(buckets),
            "commercial_blockers": ";".join(blockers),
            "latest_signal_ts": latest,
            "max_recent_signal_rows": "" if recent_max is None else recent_max,
            "max_event_count": "" if event_max is None else event_max,
            "commercial_readiness": commercial_readiness,
        })
    return sorted(
        summaries,
        key=lambda r: (
            0 if r.get("commercial_readiness") == "REVIEW_READY_RESEARCH_SHADOW_ONLY" else 1,
            -float(r.get("best_priority_score_review_only", 0) or 0),
            str(r.get("candidate_identity", "")),
        ),
    )


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=? LIMIT 1", (table,))
    return cur.fetchone() is not None


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]
    except Exception:
        return []


def choose_col(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


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
            columns = table_columns(conn, name)
            row_count: Any = ""
            if obj_type == "table":
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {quote_ident(name)}")
                    row_count = cur.fetchone()[0]
                except Exception as exc:
                    row_count = f"COUNT_ERROR: {type(exc).__name__}"
            rows.append({
                "object": obj_type,
                "name": name,
                "status": "ok",
                "row_count": row_count,
                "columns": ",".join(columns[:80]),
            })
        conn.close()
    except Exception as exc:
        rows.append({
            "object": "database",
            "name": rel(db_path),
            "status": f"open_error: {type(exc).__name__}: {exc}",
            "row_count": "",
            "columns": "",
        })
    return rows


def db_data_freshness(db_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not db_path.exists():
        return [{"area": "database", "item": rel(db_path), "status": "missing", "row_count": "", "first_utc": "", "last_utc": ""}]
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        if table_exists(conn, "bars"):
            cols = table_columns(conn, "bars")
            tf_col = choose_col(cols, ["timeframe", "tf"])
            time_col = choose_col(cols, ["utc_time", "time", "timestamp", "datetime"])
            source_col = choose_col(cols, ["source"])
            if tf_col and time_col:
                source_expr = quote_ident(source_col) if source_col else "'unknown'"
                query = (
                    f"SELECT {quote_ident(tf_col)} AS timeframe, {source_expr} AS source, COUNT(*) AS row_count, "
                    f"MIN({quote_ident(time_col)}) AS first_utc, MAX({quote_ident(time_col)}) AS last_utc "
                    f"FROM bars GROUP BY {quote_ident(tf_col)}, {source_expr} ORDER BY {quote_ident(tf_col)}, source"
                )
                for r in conn.execute(query).fetchall():
                    rows.append({
                        "area": "bars",
                        "item": f"{r['source']}::{r['timeframe']}",
                        "status": "ok",
                        "row_count": r["row_count"],
                        "first_utc": r["first_utc"],
                        "last_utc": r["last_utc"],
                    })
            else:
                rows.append({"area": "bars", "item": "schema", "status": f"missing_time_or_timeframe_cols: {cols}", "row_count": "", "first_utc": "", "last_utc": ""})
        for table in ["dryrun_signals", "dryrun_outcomes", "event_pipeline_runs", "event_pipeline_staging", "event_impact_validation_summary"]:
            if not table_exists(conn, table):
                continue
            cols = table_columns(conn, table)
            time_col = choose_col(cols, ["generated_utc", "imported_utc", "entry_utc", "signal_closed_h1_utc", "event_time_utc", "utc_time"])
            count = conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]
            first_utc = last_utc = ""
            if time_col:
                r = conn.execute(
                    f"SELECT MIN({quote_ident(time_col)}), MAX({quote_ident(time_col)}) FROM {quote_ident(table)}"
                ).fetchone()
                first_utc, last_utc = r[0], r[1]
            rows.append({"area": "table", "item": table, "status": "ok", "row_count": count, "first_utc": first_utc, "last_utc": last_utc})
        conn.close()
    except Exception as exc:
        rows.append({"area": "database", "item": rel(db_path), "status": f"freshness_error: {type(exc).__name__}: {exc}", "row_count": "", "first_utc": "", "last_utc": ""})
    return rows


def source_counts(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "UNKNOWN")
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def commercial_readiness_summary(
    module_runs: List[ModuleRun],
    candidate_rows: List[Dict[str, Any]],
    candidate_summary: List[Dict[str, Any]],
    db_freshness: List[Dict[str, Any]],
) -> Dict[str, Any]:
    required_errors = [m for m in module_runs if m.required and m.returncode != 0]
    optional_errors = [m for m in module_runs if (not m.required) and m.returncode != 0]
    review_ready = [r for r in candidate_summary if r.get("commercial_readiness") == "REVIEW_READY_RESEARCH_SHADOW_ONLY"]
    blocked_low_cadence = [r for r in candidate_summary if r.get("commercial_readiness") == "BLOCKED_LOW_FORWARD_CADENCE"]
    blocked_low_density = [r for r in candidate_summary if r.get("commercial_readiness") == "BLOCKED_LOW_EVENT_DENSITY"]
    bars_items = [r for r in db_freshness if r.get("area") == "bars"]
    latest_bar = latest_text(r.get("last_utc") for r in bars_items)

    blockers: List[str] = []
    if required_errors:
        blockers.append("REQUIRED_OPERATIONAL_ARM_ERROR")
    if not bars_items:
        blockers.append("DB_BARS_FRESHNESS_UNKNOWN_OR_MISSING")
    if not review_ready:
        blockers.append("NO_REVIEW_READY_FORWARD_ACTIVE_CANDIDATE")
    if blocked_low_cadence:
        blockers.append("LOW_CADENCE_CANDIDATE_SUPPLY")
    if optional_errors:
        blockers.append("OPTIONAL_DISCOVERY_OR_VALIDATION_ERRORS_VISIBLE")

    decision = "COMMERCIAL_TRANSITION_BLOCKED_RESEARCH_SHADOW_ONLY"
    if review_ready and not required_errors:
        decision = "COMMERCIAL_REVIEW_QUEUE_AVAILABLE_RESEARCH_SHADOW_ONLY"
    if not candidate_rows:
        decision = "COMMERCIAL_TRANSITION_BLOCKED_NO_CANDIDATE_REGISTRY_RESEARCH_SHADOW_ONLY"

    return {
        "decision": decision,
        "candidate_registry_rows": len(candidate_rows),
        "candidate_identity_count": len(candidate_summary),
        "review_ready_candidate_count": len(review_ready),
        "blocked_low_forward_cadence_count": len(blocked_low_cadence),
        "blocked_low_event_density_count": len(blocked_low_density),
        "required_module_errors": len(required_errors),
        "optional_module_errors": len(optional_errors),
        "latest_bar_utc_seen": latest_bar,
        "dominant_blockers": blockers,
        "density_bucket_counts": source_counts(candidate_rows, "density_bucket"),
        "commercial_blocker_counts": source_counts(candidate_rows, "commercial_blocker"),
        "stage_counts": source_counts(candidate_rows, "stage"),
        "family_counts": source_counts(candidate_rows, "family_key"),
    }


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


def stage_decision(module_runs: List[ModuleRun], candidate_rows: List[Dict[str, Any]], commercial_summary: Dict[str, Any]) -> str:
    required_errors = [m for m in module_runs if m.required and m.returncode != 0]
    if required_errors:
        return "STAGE32A_HF1_COMPLETED_WITH_CORE_ERRORS_RESEARCH_SHADOW_ONLY"
    if not candidate_rows:
        return "STAGE32A_HF1_COMPLETED_NO_CANDIDATE_REGISTRY_RESEARCH_SHADOW_ONLY"
    if commercial_summary.get("review_ready_candidate_count", 0):
        return "STAGE32A_HF1_HAS_REVIEW_QUEUE_RESEARCH_SHADOW_ONLY"
    return "STAGE32A_HF1_LOW_DENSITY_CANDIDATE_SUPPLY_BLOCKER_RESEARCH_SHADOW_ONLY"


def sanitize_md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def md_kv_block(lines: List[str], payload: Dict[str, Any]) -> None:
    lines.append("```text")
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            lines.append(f"{key} = {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
        else:
            lines.append(f"{key} = {value}")
    lines.append("```")


def write_markdown_report(
    args: argparse.Namespace,
    module_runs: List[ModuleRun],
    report_summaries: List[ReportSummary],
    candidate_rows: List[Dict[str, Any]],
    candidate_summary: List[Dict[str, Any]],
    db_rows: List[Dict[str, Any]],
    db_freshness: List[Dict[str, Any]],
    commercial_summary: Dict[str, Any],
) -> str:
    decision = stage_decision(module_runs, candidate_rows, commercial_summary)
    required_errors = [m for m in module_runs if m.required and m.returncode != 0]
    optional_errors = [m for m in module_runs if (not m.required) and m.returncode != 0]

    report_path = OUT_DIR / "research_shadow_orchestrator.md"
    lines: List[str] = []
    lines.append("# XAUUSD Stage32A-HF1 — Commercial Candidate Supply Orchestrator")
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
    lines.append("PRIMARY_CURRENT_BOTTLENECK = CANDIDATE_SUPPLY_DENSITY_AND_FORWARD_CADENCE")
    lines.append("```")
    lines.append("")
    lines.append("## Commercial acceleration guardrail")
    lines.append("")
    lines.append(
        "This is not a research detour. The orchestrator keeps AMarkets/FRED data freshness, "
        "active observation, discovery, lineage validation, forward tracking, and candidate aggregation "
        "visible together so the system can move toward commercial use as soon as evidence supports it."
    )
    lines.append("")
    lines.append("## Run configuration")
    lines.append("")
    md_kv_block(lines, {
        "mode": args.mode,
        "db": args.db,
        "skip_module_runs": args.skip_module_runs,
        "run_data_refresh_arm": args.run_data_refresh_arm,
        "run_discovery_arms": args.run_discovery_arms,
        "skip_active_wrapper": args.skip_active_wrapper,
        "timeout_sec": args.timeout_sec,
    })
    lines.append("")
    lines.append("## Module runs")
    lines.append("")
    lines.append("| group | arm | module | required | returncode | status | duration_sec | stdout | stderr |")
    lines.append("|---|---|---|---:|---:|---|---:|---|---|")
    if module_runs:
        for run in module_runs:
            lines.append(
                f"| {run.group} | {run.arm} | `{run.module}` | {str(run.required).lower()} | {run.returncode} | "
                f"{run.status} | {run.duration_sec} | `{run.stdout_log}` | `{run.stderr_log}` |"
            )
    else:
        lines.append("| none | n/a | n/a | false | 0 | skipped | 0 | n/a | n/a |")
    lines.append("")
    lines.append("## Commercial readiness summary")
    lines.append("")
    md_kv_block(lines, commercial_summary)
    lines.append("")
    lines.append("## Candidate supply summary — aggregated by identity")
    lines.append("")
    if candidate_summary:
        lines.append("| rank | readiness | best_score | identity | source_rows | max_recent | max_events | latest_signal_ts | blockers |")
        lines.append("|---:|---|---:|---|---:|---:|---:|---|---|")
        for idx, row in enumerate(candidate_summary[:30], start=1):
            lines.append(
                f"| {idx} | {sanitize_md_cell(row.get('commercial_readiness',''))} | "
                f"{row.get('best_priority_score_review_only','')} | {sanitize_md_cell(row.get('candidate_identity',''))} | "
                f"{row.get('source_row_count','')} | {row.get('max_recent_signal_rows','')} | {row.get('max_event_count','')} | "
                f"{sanitize_md_cell(row.get('latest_signal_ts',''))} | {sanitize_md_cell(row.get('commercial_blockers',''))} |"
            )
    else:
        lines.append("No candidate identities were found under `data/reports`.")
    lines.append("")
    lines.append("## Top candidate registry rows — review only")
    lines.append("")
    if candidate_rows:
        lines.append("| rank | priority_score | density | blocker | candidate_identity | source_csv | decision | latest_recent_entry_ts | recent_signal_rows |")
        lines.append("|---:|---:|---|---|---|---|---|---|---:|")
        for idx, row in enumerate(candidate_rows[:20], start=1):
            latest = first_present(row, ["latest_recent_entry_ts", "latest_signal_ts"])
            recent = first_present(row, ["recent_signal_rows"])
            lines.append(
                f"| {idx} | {row.get('priority_score_review_only', '')} | {sanitize_md_cell(row.get('density_bucket',''))} | "
                f"{sanitize_md_cell(row.get('commercial_blocker',''))} | {sanitize_md_cell(row.get('candidate_identity', ''))} | "
                f"`{sanitize_md_cell(row.get('source_csv', ''))}` | {sanitize_md_cell(row.get('decision', ''))} | "
                f"{sanitize_md_cell(latest)} | {sanitize_md_cell(recent)} |"
            )
    else:
        lines.append("No candidate CSV rows were found under `data/reports`.")
    lines.append("")
    lines.append("## Data freshness / DB-first status")
    lines.append("")
    lines.append("| area | item | status | row_count | first_utc | last_utc |")
    lines.append("|---|---|---|---:|---|---|")
    for row in db_freshness[:80]:
        lines.append(
            f"| {sanitize_md_cell(row.get('area',''))} | `{sanitize_md_cell(row.get('item',''))}` | "
            f"{sanitize_md_cell(row.get('status',''))} | {row.get('row_count','')} | "
            f"{sanitize_md_cell(row.get('first_utc',''))} | {sanitize_md_cell(row.get('last_utc',''))} |"
        )
    lines.append("")
    lines.append("## Latest discovered reports")
    lines.append("")
    lines.append("| modified_utc | path | decisions |")
    lines.append("|---|---|---|")
    for summary in report_summaries[:35]:
        lines.append(
            f"| {summary.modified_utc} | `{sanitize_md_cell(summary.path)}` | {sanitize_md_cell(summary.decisions)} |"
        )
    lines.append("")
    lines.append("## Database object manifest")
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
    lines.append("## Operational interpretation")
    lines.append("")
    lines.append("```text")
    lines.append("1. Observation alone is insufficient if the candidate pool remains low-cadence.")
    lines.append("2. Keep active/shadow tracking running, but use supply/full modes to keep discovery and lineage validation alive.")
    lines.append("3. Treat low-cadence Stage31 candidates as watchlist/status, not as the primary commercial candidate pool.")
    lines.append("4. Use candidate_supply_summary.csv/json to decide whether the next patch should expand density, repair a discovery arm, or enrich calendar events.")
    lines.append("5. Any paper/live/EA transition still requires explicit evidence and explicit user authorization.")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for p in [
        OUT_DIR / "research_shadow_orchestrator.md",
        OUT_DIR / "candidate_registry.csv",
        OUT_DIR / "candidate_registry.json",
        OUT_DIR / "candidate_supply_summary.csv",
        OUT_DIR / "candidate_supply_summary.json",
        OUT_DIR / "commercial_readiness_summary.json",
        OUT_DIR / "db_data_freshness.csv",
        OUT_DIR / "db_data_freshness.json",
        OUT_DIR / "module_runs.csv",
        OUT_DIR / "report_manifest.csv",
        OUT_DIR / "stage_status_manifest.csv",
    ]:
        lines.append(f"- `{rel(p)}`")
    lines.append("")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return decision


def main(argv: Optional[Sequence[str]] = None) -> int:
    ensure_dirs()
    args = parse_args(argv)

    module_runs: List[ModuleRun] = []
    if not args.skip_module_runs:
        for spec in module_plan(args):
            module_runs.append(run_module(spec, args.timeout_sec))

    report_summaries = discover_reports()
    candidate_rows = build_candidate_registry()
    candidate_summary = build_candidate_supply_summary(candidate_rows)
    db_path = Path(args.db)
    db_rows = introspect_db(db_path)
    db_freshness = db_data_freshness(db_path)
    commercial_summary = commercial_readiness_summary(module_runs, candidate_rows, candidate_summary, db_freshness)

    write_csv(OUT_DIR / "module_runs.csv", [asdict(m) for m in module_runs])
    write_json(OUT_DIR / "module_runs.json", [asdict(m) for m in module_runs])
    write_csv(OUT_DIR / "report_manifest.csv", [asdict(r) for r in report_summaries])
    write_json(OUT_DIR / "report_manifest.json", [asdict(r) for r in report_summaries])
    write_csv(OUT_DIR / "candidate_registry.csv", candidate_rows)
    write_json(OUT_DIR / "candidate_registry.json", candidate_rows)
    write_csv(OUT_DIR / "candidate_supply_summary.csv", candidate_summary)
    write_json(OUT_DIR / "candidate_supply_summary.json", candidate_summary)
    write_json(OUT_DIR / "commercial_readiness_summary.json", commercial_summary)
    write_csv(OUT_DIR / "stage_status_manifest.csv", db_rows)
    write_json(OUT_DIR / "stage_status_manifest.json", db_rows)
    write_csv(OUT_DIR / "db_data_freshness.csv", db_freshness)
    write_json(OUT_DIR / "db_data_freshness.json", db_freshness)

    decision = write_markdown_report(
        args=args,
        module_runs=module_runs,
        report_summaries=report_summaries,
        candidate_rows=candidate_rows,
        candidate_summary=candidate_summary,
        db_rows=db_rows,
        db_freshness=db_freshness,
        commercial_summary=commercial_summary,
    )
    print(decision)
    print(f"commercial_decision={commercial_summary.get('decision')}")
    print(f"report={rel(OUT_DIR / 'research_shadow_orchestrator.md')}")
    print(f"candidate_registry={rel(OUT_DIR / 'candidate_registry.csv')}")
    print(f"candidate_supply_summary={rel(OUT_DIR / 'candidate_supply_summary.csv')}")

    if args.fail_on_core_error and any(m.required and m.returncode != 0 for m in module_runs):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
