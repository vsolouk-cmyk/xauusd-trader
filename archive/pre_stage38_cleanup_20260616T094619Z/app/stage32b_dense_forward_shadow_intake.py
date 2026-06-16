"""
Stage32B — Dense Forward Shadow Intake Builder for XAUUSD.

Purpose:
- Convert the Stage32A-HF1 candidate-supply dashboard into an actionable
  research/shadow intake queue.
- Prioritize historically dense, non-exogenous candidate families that can
  produce forward-observable samples faster than low-cadence macro/watchlist
  candidates.
- Keep the commercial objective explicit: fastest safe path toward a usable
  trading system, without EA/paper/live/order authorization.

Inputs by default:
- data/reports/research_shadow_orchestrator/candidate_supply_summary.csv
- data/reports/research_shadow_orchestrator/candidate_registry.csv
- data/reports/research_shadow_orchestrator/commercial_readiness_summary.json

Outputs:
- data/reports/stage32b_dense_forward_shadow_intake/stage32b_dense_forward_shadow_intake.md
- data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv/json
- data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.csv/json
- data/reports/stage32b_dense_forward_shadow_intake/rejected_but_dense_review.csv/json
- data/reports/stage32b_dense_forward_shadow_intake/stage32b_summary.json

Safety:
- Research/shadow only.
- No EA changes.
- No paper/live.
- No order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
ORCH_DIR = REPORT_ROOT / "research_shadow_orchestrator"
OUT_DIR = REPORT_ROOT / "stage32b_dense_forward_shadow_intake"

DEFAULT_SUPPLY_SUMMARY = ORCH_DIR / "candidate_supply_summary.csv"
DEFAULT_REGISTRY = ORCH_DIR / "candidate_registry.csv"
DEFAULT_COMMERCIAL = ORCH_DIR / "commercial_readiness_summary.json"

MACRO_TOKENS = {
    "exogenous_macro",
    "stage31b",
    "stage31c",
    "stage31d",
    "stage31e",
    "stage31f",
    "real_yield",
    "us10y",
    "dxy",
    "vix",
    "spx",
    "oil",
    "macro",
}

GENERIC_IDENTITY_TOKENS = {
    "data/reports/",
    "candidate_registry.csv",
    "stage30b_family_holdout.csv",
}

COMMERCIAL_GOAL = "FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        val = float(text)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except Exception:
        return None


def safe_int(value: Any, default: int = 0) -> int:
    val = safe_float(value)
    if val is None:
        return default
    return int(round(val))


def split_semis(value: Any) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [x.strip() for x in re.split(r"[;|]", text) if x.strip()]


def read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [{str(k): ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None} for row in reader]


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        seen = set()
        fields: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    fields.append(key)
                    seen.add(key)
        fieldnames = fields or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"json_read_error": f"{type(exc).__name__}: {exc}"}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Stage32B dense forward shadow intake queue.")
    parser.add_argument("--candidate-supply-summary", default=os.getenv("STAGE32B_SUPPLY_SUMMARY", str(DEFAULT_SUPPLY_SUMMARY)))
    parser.add_argument("--candidate-registry", default=os.getenv("STAGE32B_CANDIDATE_REGISTRY", str(DEFAULT_REGISTRY)))
    parser.add_argument("--commercial-summary", default=os.getenv("STAGE32B_COMMERCIAL_SUMMARY", str(DEFAULT_COMMERCIAL)))
    parser.add_argument("--out-dir", default=os.getenv("STAGE32B_OUT_DIR", str(OUT_DIR)))
    parser.add_argument("--min-event-count", type=int, default=int(os.getenv("STAGE32B_MIN_EVENT_COUNT", "500")))
    parser.add_argument("--strong-event-count", type=int, default=int(os.getenv("STAGE32B_STRONG_EVENT_COUNT", "1000")))
    parser.add_argument("--max-variants-per-family", type=int, default=int(os.getenv("STAGE32B_MAX_VARIANTS_PER_FAMILY", "4")))
    parser.add_argument("--max-total-queue", type=int, default=int(os.getenv("STAGE32B_MAX_TOTAL_QUEUE", "24")))
    parser.add_argument("--min-forward-samples", type=int, default=int(os.getenv("STAGE32B_MIN_FORWARD_SAMPLES", "20")))
    parser.add_argument("--target-forward-days", type=int, default=int(os.getenv("STAGE32B_TARGET_FORWARD_DAYS", "30")))
    parser.add_argument("--include-repair-candidates", action="store_true", default=os.getenv("STAGE32B_INCLUDE_REPAIR", "1").lower() in {"1", "true", "yes", "on"})
    parser.add_argument("--include-exogenous-watchlist", action="store_true", default=os.getenv("STAGE32B_INCLUDE_EXOGENOUS_WATCHLIST", "0").lower() in {"1", "true", "yes", "on"})
    return parser.parse_args(argv)


def primary_family(row: Dict[str, Any]) -> str:
    families = split_semis(row.get("families"))
    identity = str(row.get("candidate_identity", ""))
    # Prefer semantic family names over stage labels.
    for fam in families:
        if fam and not re.fullmatch(r"stage\d+[a-z]?", fam, flags=re.IGNORECASE):
            return fam
    if families:
        return families[0]
    parts = [p.strip() for p in identity.split("|") if p.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return "unknown_family"


def is_exogenous(row: Dict[str, Any]) -> bool:
    blob = " ".join([
        str(row.get("candidate_identity", "")),
        str(row.get("families", "")),
        str(row.get("stages", "")),
    ]).lower()
    return any(token.lower() in blob for token in MACRO_TOKENS)


def is_generic_identity(row: Dict[str, Any]) -> bool:
    ident = str(row.get("candidate_identity", "")).lower()
    return any(tok in ident for tok in GENERIC_IDENTITY_TOKENS)


def has_rejected_source(row: Dict[str, Any]) -> bool:
    blockers = str(row.get("commercial_blockers", "")).upper()
    readiness = str(row.get("commercial_readiness", "")).upper()
    return "REJECTED_OR_ERROR_SOURCE" in blockers or "REJECT" in readiness or "ERROR" in readiness


def max_event_count(row: Dict[str, Any]) -> float:
    return safe_float(row.get("max_event_count")) or 0.0


def max_recent_count(row: Dict[str, Any]) -> float:
    return safe_float(row.get("max_recent_signal_rows")) or 0.0


def priority_score(row: Dict[str, Any]) -> float:
    return safe_float(row.get("best_priority_score_review_only")) or 0.0


def classify_row(row: Dict[str, Any], min_event_count: int, strong_event_count: int) -> Tuple[str, str, str]:
    events = max_event_count(row)
    recent = max_recent_count(row)
    exog = is_exogenous(row)
    generic = is_generic_identity(row)
    rejected = has_rejected_source(row)

    if recent > 0 and not exog and not rejected and not generic:
        return (
            "STAGE32B_FORWARD_ACTIVE_INTAKE_PRIORITY",
            "PRIMARY_FORWARD_ACTIVE",
            "Forward activity exists; route to active shadow review queue.",
        )
    if exog:
        return (
            "STAGE32B_EXOGENOUS_WATCHLIST_ONLY",
            "WATCHLIST_EXOGENOUS",
            "Macro/exogenous candidates remain low-cadence watchlist, not the primary commercial supply path.",
        )
    if events < min_event_count:
        return (
            "STAGE32B_LOW_DENSITY_REJECT_FOR_PRIMARY_INTAKE",
            "REJECT_LOW_DENSITY",
            "Historical event count is below dense-intake threshold.",
        )
    if generic:
        return (
            "STAGE32B_GENERIC_AGGREGATE_ROW_REPAIR_FIRST",
            "SECONDARY_REPAIR",
            "Row is an aggregate/file-level identity; inspect family-level source before primary intake.",
        )
    if rejected:
        return (
            "STAGE32B_DENSE_REJECTED_REPAIR_QUEUE",
            "SECONDARY_REPAIR",
            "Dense but rejected/error-tagged; repair/retest before forward intake.",
        )
    if events >= strong_event_count:
        return (
            "STAGE32B_STRONG_DENSE_SHADOW_INTAKE",
            "PRIMARY_DENSE",
            "Strong historical density; route to dense forward shadow intake.",
        )
    return (
        "STAGE32B_DENSE_SHADOW_INTAKE",
        "PRIMARY_DENSE",
        "Dense enough for forward shadow intake.",
    )


def queue_score(row: Dict[str, Any], queue_tier: str) -> float:
    events = max_event_count(row)
    score = priority_score(row)
    source_count = safe_float(row.get("source_csv_count")) or 0.0
    source_rows = safe_float(row.get("source_row_count")) or 0.0
    recent = max_recent_count(row)
    value = 0.0
    value += min(events, 3000.0) * 0.08
    value += min(max(score, -50.0), 120.0) * 0.50
    value += min(source_count, 20.0) * 1.5
    value += min(source_rows, 100.0) * 0.10
    value += min(recent, 50.0) * 5.0
    if queue_tier == "PRIMARY_FORWARD_ACTIVE":
        value += 80.0
    elif queue_tier == "PRIMARY_DENSE":
        value += 40.0
    elif queue_tier == "SECONDARY_REPAIR":
        value += 10.0
    elif queue_tier == "WATCHLIST_EXOGENOUS":
        value -= 60.0
    else:
        value -= 100.0
    return round(value, 6)


def enrich_candidates(rows: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        family = primary_family(row)
        classification, tier, rationale = classify_row(row, args.min_event_count, args.strong_event_count)
        action = {
            "PRIMARY_FORWARD_ACTIVE": "ADD_TO_FORWARD_ACTIVE_SHADOW_REVIEW",
            "PRIMARY_DENSE": "ADD_TO_DENSE_FORWARD_SHADOW_INTAKE",
            "SECONDARY_REPAIR": "REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE",
            "WATCHLIST_EXOGENOUS": "KEEP_WATCHLIST_ONLY",
            "REJECT_LOW_DENSITY": "DO_NOT_ROUTE_TO_PRIMARY_INTAKE",
        }.get(tier, "DO_NOT_ROUTE_TO_PRIMARY_INTAKE")
        enriched.update({
            "stage32b_classification": classification,
            "queue_tier": tier,
            "stage32b_action": action,
            "primary_family": family,
            "is_exogenous_watchlist": str(is_exogenous(row)).upper(),
            "is_generic_identity": str(is_generic_identity(row)).upper(),
            "has_rejected_or_error_source": str(has_rejected_source(row)).upper(),
            "numeric_max_event_count": max_event_count(row),
            "numeric_max_recent_signal_rows": max_recent_count(row),
            "numeric_priority_score": priority_score(row),
            "queue_score": queue_score(row, tier),
            "target_forward_days": args.target_forward_days,
            "min_forward_samples_before_review": args.min_forward_samples,
            "research_shadow_only": "TRUE",
            "no_ea_no_paper_live_no_order": "TRUE",
            "rationale": rationale,
        })
        out.append(enriched)
    return sorted(out, key=lambda r: (-float(r.get("queue_score", 0) or 0), -float(r.get("numeric_max_event_count", 0) or 0), str(r.get("candidate_identity", ""))))


def build_family_triage(enriched: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        groups[str(row.get("primary_family", "unknown_family"))].append(row)
    triage: List[Dict[str, Any]] = []
    for family, rows in groups.items():
        max_events = max((float(r.get("numeric_max_event_count", 0) or 0) for r in rows), default=0.0)
        max_score = max((float(r.get("queue_score", 0) or 0) for r in rows), default=0.0)
        primary_count = sum(1 for r in rows if str(r.get("queue_tier")) in {"PRIMARY_DENSE", "PRIMARY_FORWARD_ACTIVE"})
        repair_count = sum(1 for r in rows if str(r.get("queue_tier")) == "SECONDARY_REPAIR")
        exog_count = sum(1 for r in rows if str(r.get("queue_tier")) == "WATCHLIST_EXOGENOUS")
        low_count = sum(1 for r in rows if str(r.get("queue_tier")) == "REJECT_LOW_DENSITY")
        stages = sorted(set(";".join(str(r.get("stages", "")) for r in rows).split(";")) - {""})
        if primary_count:
            rec = "ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE"
        elif repair_count and max_events >= args.min_event_count:
            rec = "REPAIR_DENSE_VARIANTS_THEN_RETEST"
        elif exog_count:
            rec = "KEEP_AS_LOW_CADENCE_WATCHLIST"
        else:
            rec = "LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW"
        triage.append({
            "family": family,
            "candidate_identity_count": len(rows),
            "max_event_count": max_events,
            "max_queue_score": round(max_score, 6),
            "primary_intake_candidate_count": primary_count,
            "repair_candidate_count": repair_count,
            "exogenous_watchlist_count": exog_count,
            "low_density_count": low_count,
            "stages": ";".join(stages),
            "recommendation": rec,
        })
    return sorted(triage, key=lambda r: (
        0 if r["primary_intake_candidate_count"] else (1 if r["repair_candidate_count"] else 2),
        -float(r["max_event_count"]),
        -float(r["max_queue_score"]),
        str(r["family"]),
    ))


def build_shadow_queue(enriched: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    per_family: Dict[str, int] = defaultdict(int)

    def maybe_add(row: Dict[str, Any], queue_group: str) -> None:
        if len(selected) >= args.max_total_queue:
            return
        family = str(row.get("primary_family", "unknown_family"))
        if per_family[family] >= args.max_variants_per_family:
            return
        item = dict(row)
        item["shadow_queue_group"] = queue_group
        item["shadow_queue_rank"] = len(selected) + 1
        selected.append(item)
        per_family[family] += 1

    primary = [r for r in enriched if str(r.get("queue_tier")) in {"PRIMARY_FORWARD_ACTIVE", "PRIMARY_DENSE"}]
    repair = [r for r in enriched if str(r.get("queue_tier")) == "SECONDARY_REPAIR"]
    exog = [r for r in enriched if str(r.get("queue_tier")) == "WATCHLIST_EXOGENOUS"]

    for row in primary:
        maybe_add(row, "PRIMARY_DENSE_FORWARD_SHADOW")
    if args.include_repair_candidates:
        for row in repair:
            maybe_add(row, "SECONDARY_REPAIR_THEN_SHADOW")
    if args.include_exogenous_watchlist:
        for row in exog:
            maybe_add(row, "WATCHLIST_ONLY_NOT_PRIMARY")

    for idx, row in enumerate(selected, start=1):
        row["shadow_queue_rank"] = idx
    return selected


def dense_repair_rows(enriched: List[Dict[str, Any]], min_event_count: int) -> List[Dict[str, Any]]:
    rows = [r for r in enriched if str(r.get("queue_tier")) == "SECONDARY_REPAIR" and float(r.get("numeric_max_event_count", 0) or 0) >= min_event_count]
    return sorted(rows, key=lambda r: (-float(r.get("numeric_max_event_count", 0) or 0), -float(r.get("queue_score", 0) or 0)))


def write_stage32b_markdown(
    args: argparse.Namespace,
    commercial: Dict[str, Any],
    enriched: List[Dict[str, Any]],
    family_triage: List[Dict[str, Any]],
    shadow_queue: List[Dict[str, Any]],
    repair_rows: List[Dict[str, Any]],
    decision: str,
    summary: Dict[str, Any],
    out_dir: Path,
) -> None:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines: List[str] = []
    lines.append("# XAUUSD Stage32B — Dense Forward Shadow Intake Builder")
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
    lines.append(f"COMMERCIAL_GOAL = {COMMERCIAL_GOAL}")
    lines.append("PRIMARY_OBJECTIVE = INCREASE_FORWARD_OBSERVABLE_CANDIDATE_SUPPLY")
    lines.append("```")
    lines.append("")
    lines.append("## Why this stage exists")
    lines.append("")
    lines.append(
        "Stage32A-HF1 showed that the infrastructure is running, but commercial transition is blocked because "
        "there is no review-ready forward-active candidate. Stage32B therefore stops ranking by historical beauty "
        "alone and builds a dense forward-shadow intake queue from families that can realistically generate "
        "forward samples faster."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("```text")
    for key, value in summary.items():
        if isinstance(value, (dict, list)):
            lines.append(f"{key} = {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
        else:
            lines.append(f"{key} = {value}")
    lines.append("```")
    lines.append("")
    lines.append("## Input commercial blocker context")
    lines.append("")
    lines.append("```text")
    for key in ["decision", "candidate_identity_count", "review_ready_candidate_count", "blocked_low_forward_cadence_count", "latest_bar_utc_seen", "dominant_blockers"]:
        if key in commercial:
            value = commercial[key]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            lines.append(f"{key} = {value}")
    lines.append("```")
    lines.append("")
    lines.append("## Shadow intake queue")
    lines.append("")
    if shadow_queue:
        lines.append("| rank | group | tier | family | events | score | candidate_identity | action | rationale |")
        lines.append("|---:|---|---|---|---:|---:|---|---|---|")
        for row in shadow_queue[:40]:
            lines.append(
                f"| {row.get('shadow_queue_rank','')} | {cell(row.get('shadow_queue_group',''))} | {cell(row.get('queue_tier',''))} | "
                f"{cell(row.get('primary_family',''))} | {row.get('numeric_max_event_count','')} | {row.get('queue_score','')} | "
                f"{cell(row.get('candidate_identity',''))} | {cell(row.get('stage32b_action',''))} | {cell(row.get('rationale',''))} |"
            )
    else:
        lines.append("No dense forward-shadow intake queue could be built from the current candidate supply summary.")
    lines.append("")
    lines.append("## Family density triage")
    lines.append("")
    lines.append("| rank | family | candidates | max_events | primary | repair | exogenous | recommendation |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---|")
    for idx, row in enumerate(family_triage[:30], start=1):
        lines.append(
            f"| {idx} | {cell(row.get('family',''))} | {row.get('candidate_identity_count','')} | {row.get('max_event_count','')} | "
            f"{row.get('primary_intake_candidate_count','')} | {row.get('repair_candidate_count','')} | {row.get('exogenous_watchlist_count','')} | "
            f"{cell(row.get('recommendation',''))} |"
        )
    lines.append("")
    lines.append("## Dense but repair-first candidates")
    lines.append("")
    if repair_rows:
        lines.append("| rank | family | events | score | candidate_identity | blockers |")
        lines.append("|---:|---|---:|---:|---|---|")
        for idx, row in enumerate(repair_rows[:30], start=1):
            lines.append(
                f"| {idx} | {cell(row.get('primary_family',''))} | {row.get('numeric_max_event_count','')} | {row.get('queue_score','')} | "
                f"{cell(row.get('candidate_identity',''))} | {cell(row.get('commercial_blockers',''))} |"
            )
    else:
        lines.append("No dense repair-first candidates were found.")
    lines.append("")
    lines.append("## Operational interpretation")
    lines.append("")
    lines.append("```text")
    lines.append("1. Keep Stage31 macro/exogenous candidates as watchlist only unless they become forward-active.")
    lines.append("2. Use the queue to focus forward-shadow observation on dense families first.")
    lines.append("3. Secondary repair candidates are not promotion candidates; they are fast-path candidates for retest/repair because they have density.")
    lines.append("4. No EA/paper/live/order transition is authorized by this report.")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for p in [
        out_dir / "stage32b_dense_forward_shadow_intake.md",
        out_dir / "shadow_intake_queue.csv",
        out_dir / "shadow_intake_queue.json",
        out_dir / "family_density_triage.csv",
        out_dir / "family_density_triage.json",
        out_dir / "rejected_but_dense_review.csv",
        out_dir / "rejected_but_dense_review.json",
        out_dir / "stage32b_summary.json",
    ]:
        lines.append(f"- `{rel(p)}`")
    lines.append("")
    (out_dir / "stage32b_dense_forward_shadow_intake.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    supply_path = Path(args.candidate_supply_summary)
    registry_path = Path(args.candidate_registry)
    commercial_path = Path(args.commercial_summary)

    rows = read_csv(supply_path)
    commercial = read_json(commercial_path)
    registry_exists = registry_path.exists()
    enriched = enrich_candidates(rows, args)
    family_triage = build_family_triage(enriched, args)
    shadow_queue = build_shadow_queue(enriched, args)
    repair = dense_repair_rows(enriched, args.min_event_count)

    primary_count = sum(1 for r in shadow_queue if str(r.get("shadow_queue_group")) == "PRIMARY_DENSE_FORWARD_SHADOW")
    repair_count = sum(1 for r in shadow_queue if str(r.get("shadow_queue_group")) == "SECONDARY_REPAIR_THEN_SHADOW")
    exog_watchlist_rows = sum(1 for r in enriched if str(r.get("queue_tier")) == "WATCHLIST_EXOGENOUS")

    if primary_count > 0:
        decision = "STAGE32B_DENSE_FORWARD_SHADOW_INTAKE_QUEUE_READY_RESEARCH_SHADOW_ONLY"
    elif repair_count > 0:
        decision = "STAGE32B_DENSE_REPAIR_QUEUE_READY_RESEARCH_SHADOW_ONLY"
    elif rows:
        decision = "STAGE32B_NO_PRIMARY_DENSE_FORWARD_INTAKE_RESEARCH_SHADOW_ONLY"
    else:
        decision = "STAGE32B_NO_CANDIDATE_SUPPLY_INPUT_RESEARCH_SHADOW_ONLY"

    tier_counts: Dict[str, int] = defaultdict(int)
    class_counts: Dict[str, int] = defaultdict(int)
    for row in enriched:
        tier_counts[str(row.get("queue_tier", "UNKNOWN"))] += 1
        class_counts[str(row.get("stage32b_classification", "UNKNOWN"))] += 1

    summary = {
        "decision": decision,
        "commercial_goal": COMMERCIAL_GOAL,
        "candidate_supply_summary_path": rel(supply_path),
        "candidate_registry_path": rel(registry_path),
        "candidate_registry_exists": registry_exists,
        "commercial_summary_path": rel(commercial_path),
        "input_candidate_identity_rows": len(rows),
        "enriched_candidate_rows": len(enriched),
        "family_count": len(family_triage),
        "shadow_queue_rows": len(shadow_queue),
        "primary_shadow_queue_rows": primary_count,
        "secondary_repair_queue_rows": repair_count,
        "dense_repair_review_rows": len(repair),
        "exogenous_watchlist_rows": exog_watchlist_rows,
        "min_event_count": args.min_event_count,
        "strong_event_count": args.strong_event_count,
        "max_variants_per_family": args.max_variants_per_family,
        "max_total_queue": args.max_total_queue,
        "target_forward_days": args.target_forward_days,
        "min_forward_samples_before_review": args.min_forward_samples,
        "tier_counts": dict(sorted(tier_counts.items())),
        "classification_counts": dict(sorted(class_counts.items())),
        "research_shadow_only": True,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
    }

    queue_fields = [
        "shadow_queue_rank", "shadow_queue_group", "queue_tier", "stage32b_classification", "stage32b_action",
        "primary_family", "candidate_identity", "numeric_max_event_count", "numeric_max_recent_signal_rows",
        "numeric_priority_score", "queue_score", "source_row_count", "source_csv_count", "families", "stages",
        "density_buckets", "commercial_blockers", "commercial_readiness", "target_forward_days",
        "min_forward_samples_before_review", "rationale", "research_shadow_only", "no_ea_no_paper_live_no_order",
    ]
    triage_fields = [
        "family", "candidate_identity_count", "max_event_count", "max_queue_score", "primary_intake_candidate_count",
        "repair_candidate_count", "exogenous_watchlist_count", "low_density_count", "stages", "recommendation",
    ]

    write_csv(out_dir / "shadow_intake_queue.csv", shadow_queue, queue_fields)
    write_json(out_dir / "shadow_intake_queue.json", shadow_queue)
    write_csv(out_dir / "family_density_triage.csv", family_triage, triage_fields)
    write_json(out_dir / "family_density_triage.json", family_triage)
    write_csv(out_dir / "rejected_but_dense_review.csv", repair, queue_fields)
    write_json(out_dir / "rejected_but_dense_review.json", repair)
    write_json(out_dir / "stage32b_summary.json", summary)

    write_stage32b_markdown(args, commercial, enriched, family_triage, shadow_queue, repair, decision, summary, out_dir)

    print(decision)
    print(f"shadow_queue_rows={len(shadow_queue)}")
    print(f"primary_shadow_queue_rows={primary_count}")
    print(f"secondary_repair_queue_rows={repair_count}")
    print(f"report={rel(out_dir / 'stage32b_dense_forward_shadow_intake.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
