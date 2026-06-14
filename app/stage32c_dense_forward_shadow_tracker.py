"""
Stage32C — Dense Forward Shadow Tracker for XAUUSD.

Purpose:
- Turn the Stage32B dense shadow intake queue into a recurring tracker that
  produces forward-observable signal snapshots and a persistent research-shadow ledger.
- Prioritize signal production from dense families instead of waiting for low-cadence
  macro/watchlist candidates.
- Keep the commercial objective explicit: fastest safe path toward a usable trading
  system, without EA/paper/live/order authorization.

Inputs by default:
- data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv
- data/local/xauusd_local_store.sqlite
- app.stage28a_discovery_factory_batch_runner registry/DB-first loader/event logic

Outputs:
- data/reports/stage32c_dense_forward_shadow_tracker/stage32c_dense_forward_shadow_tracker.md
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_snapshot.csv/json
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv/json
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv/json
- data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_family_summary.csv/json
- data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json

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

COMMERCIAL_GOAL = "FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM"
ROOT = Path.cwd()
REPORT_ROOT = ROOT / "data" / "reports"
OUT_DIR = REPORT_ROOT / "stage32c_dense_forward_shadow_tracker"
DEFAULT_QUEUE = REPORT_ROOT / "stage32b_dense_forward_shadow_intake" / "shadow_intake_queue.csv"
DEFAULT_DB = ROOT / "data" / "local" / "xauusd_local_store.sqlite"

DEFAULT_LOOKBACK_DAYS = int(os.getenv("STAGE32C_LOOKBACK_DAYS", "30"))
DEFAULT_MAX_VARIANTS_PER_FAMILY = int(os.getenv("STAGE32C_MAX_VARIANTS_PER_FAMILY", "4"))
DEFAULT_MIN_SIGNALS_BEFORE_REVIEW = int(os.getenv("STAGE32C_MIN_SIGNALS_BEFORE_REVIEW", "20"))
DEFAULT_MAX_TOTAL_SPECS = int(os.getenv("STAGE32C_MAX_TOTAL_SPECS", "32"))


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


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "null"}:
            return default
        val = float(text)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def strip_code(value: Any) -> str:
    return str(value or "").strip().strip("`").strip()


def normalize_identity(value: Any) -> str:
    text = strip_code(value)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_candidate_name(identity: str) -> str:
    left = identity.split("|", 1)[0].strip()
    return left


def extract_family(row: Dict[str, Any]) -> str:
    family = normalize_identity(row.get("family") or row.get("pattern_family") or "")
    if family:
        return family
    identity = normalize_identity(row.get("candidate_identity") or row.get("identity") or "")
    if "|" in identity:
        return identity.split("|", 1)[1].strip()
    return identity


def is_primary_queue(row: Dict[str, Any]) -> bool:
    return normalize_identity(row.get("tier")).upper() == "PRIMARY_DENSE" or "PRIMARY" in normalize_identity(row.get("group")).upper()


def is_secondary_queue(row: Dict[str, Any]) -> bool:
    return normalize_identity(row.get("tier")).upper() == "SECONDARY_REPAIR" or "SECONDARY" in normalize_identity(row.get("group")).upper()


def import_stage28a() -> Any:
    try:
        import app.stage28a_discovery_factory_batch_runner as stage28a  # type: ignore
        return stage28a
    except Exception as exc:  # pragma: no cover - reported to user
        raise RuntimeError(f"Could not import app.stage28a_discovery_factory_batch_runner: {type(exc).__name__}: {exc}")


def pf(values: Sequence[float]) -> float:
    vals = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    if not vals:
        return 0.0
    pos = sum(x for x in vals if x > 0)
    neg = -sum(x for x in vals if x < 0)
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return pos / neg


def choose_specs_from_queue(stage28a: Any, queue_rows: List[Dict[str, Any]], m15: Any, daily: Any, lookback_days: int, max_variants_per_family: int, max_total_specs: int) -> Tuple[List[Any], List[Dict[str, Any]]]:
    registry = list(stage28a.registry())
    by_name = {str(spec.name): spec for spec in registry}
    by_family: Dict[str, List[Any]] = defaultdict(list)
    for spec in registry:
        by_family[str(spec.family)].append(spec)

    selection_notes: List[Dict[str, Any]] = []
    selected: List[Any] = []
    selected_names = set()

    def add_spec(spec: Any, source: str, queue_row: Dict[str, Any], recent_count: Optional[int] = None) -> None:
        if spec.name in selected_names:
            return
        if len(selected) >= max_total_specs:
            return
        selected.append(spec)
        selected_names.add(spec.name)
        selection_notes.append({
            "candidate": spec.name,
            "family": spec.family,
            "source": source,
            "queue_rank": queue_row.get("rank", ""),
            "queue_group": queue_row.get("group", ""),
            "queue_tier": queue_row.get("tier", ""),
            "queue_identity": queue_row.get("candidate_identity", ""),
            "recent_opportunity_count_for_selection": recent_count if recent_count is not None else "",
        })

    # First route exact secondary/repair variants, because these are explicit names.
    for row in queue_rows:
        identity = normalize_identity(row.get("candidate_identity"))
        cand = extract_candidate_name(identity)
        if cand in by_name and (is_secondary_queue(row) or "_h" in cand):
            add_spec(by_name[cand], "exact_queue_variant", row)

    # Then expand primary family aggregate rows into the most active recent variants.
    for row in queue_rows:
        if not is_primary_queue(row):
            continue
        family = extract_family(row)
        specs = by_family.get(family, [])
        if not specs:
            continue
        ranked: List[Tuple[int, str, Any]] = []
        for spec in specs:
            cnt = count_recent_opportunities(stage28a, spec, m15, daily, lookback_days, include_rows=False)[0]
            ranked.append((cnt, spec.name, spec))
        ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
        added = 0
        for cnt, _name, spec in ranked:
            if added >= max_variants_per_family:
                break
            add_spec(spec, "primary_family_recent_expansion", row, cnt)
            added += 1

    return selected, selection_notes


def recent_dates_from_daily(daily: Any, lookback_days: int) -> Any:
    import pandas as pd  # local import; this module is only useful when pandas is installed
    if len(daily) == 0:
        return daily
    latest = pd.to_datetime(daily.index.max(), utc=True)
    cutoff = latest - pd.Timedelta(days=int(lookback_days))
    idx = pd.to_datetime(daily.index, utc=True)
    return daily.loc[idx >= cutoff]


def count_recent_opportunities(stage28a: Any, spec: Any, m15: Any, daily: Any, lookback_days: int, include_rows: bool = True) -> Tuple[int, List[Dict[str, Any]]]:
    recent_daily = recent_dates_from_daily(daily, lookback_days)
    rows: List[Dict[str, Any]] = []
    for date, drow in recent_daily.iterrows():
        entry = stage28a._entry_bar(m15, date, int(spec.entry_hour))
        if entry is None:
            continue
        ok, direction, reason = stage28a._event_passes(spec, drow, entry)
        if not ok or direction is None:
            continue
        if include_rows:
            rows.append({
                "candidate": spec.name,
                "family": spec.family,
                "entry_time": str(entry.name),
                "entry_hour": int(spec.entry_hour),
                "direction": int(direction),
                "entry_price": float(entry["close"]),
                "horizon_min": int(spec.horizon_min),
                "tp_atr": float(spec.tp_atr),
                "sl_atr": float(spec.sl_atr),
                "trigger_reason": reason,
                "params_json": json.dumps(dict(spec.params), sort_keys=True),
            })
    return len(rows) if include_rows else int(sum(1 for _ in rows)) if rows else _count_only(stage28a, spec, m15, recent_daily), rows


def _count_only(stage28a: Any, spec: Any, m15: Any, recent_daily: Any) -> int:
    count = 0
    for date, drow in recent_daily.iterrows():
        entry = stage28a._entry_bar(m15, date, int(spec.entry_hour))
        if entry is None:
            continue
        ok, direction, _reason = stage28a._event_passes(spec, drow, entry)
        if ok and direction is not None:
            count += 1
    return count


def add_replay_outcomes(stage28a: Any, m1: Any, m15: Any, signal_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    import pandas as pd
    import numpy as np

    if not signal_rows:
        return []
    m15_atr = stage28a._atr(m15, 20)
    latest_m1 = pd.to_datetime(m1.index.max(), utc=True) if len(m1) else pd.NaT
    cost = float(getattr(stage28a, "RT_COST_X1", 0.35))
    out: List[Dict[str, Any]] = []
    for row in signal_rows:
        r = dict(row)
        entry_time = pd.to_datetime(r["entry_time"], utc=True)
        horizon_min = int(safe_float(r.get("horizon_min"), 180) or 180)
        direction = int(safe_float(r.get("direction"), 0) or 0)
        entry_price = float(safe_float(r.get("entry_price"), 0.0) or 0.0)
        atr = None
        if entry_time in m15_atr.index and pd.notna(m15_atr.loc[entry_time]):
            atr = float(m15_atr.loc[entry_time])
        if atr is None or not np.isfinite(atr) or atr <= 0:
            try:
                bar = m15.loc[entry_time]
                atr = float(bar["high"] - bar["low"])
            except Exception:
                atr = 0.0
        r["atr"] = atr
        horizon_end = entry_time + pd.Timedelta(minutes=horizon_min)
        r["horizon_end_utc"] = horizon_end.isoformat()
        if pd.isna(latest_m1) or latest_m1 < horizon_end or atr <= 0 or direction == 0:
            r.update({
                "outcome_status": "OPEN_OR_INCOMPLETE_M1_PATH",
                "exit_time": "",
                "exit_price": "",
                "exit_reason": "",
                "gross": "",
                "net_x1": "",
                "net_x4": "",
                "net_x6": "",
            })
        else:
            replay = stage28a._m1_replay(m1, entry_time, direction, entry_price, atr, horizon_min, float(r.get("tp_atr") or 0.6), float(r.get("sl_atr") or 0.65))
            gross = float(replay.get("gross", 0.0))
            r.update({
                "outcome_status": "RESOLVED_M1_REPLAY_SHADOW",
                "exit_time": str(replay.get("exit_time", "")),
                "exit_price": replay.get("exit_price", ""),
                "exit_reason": replay.get("exit_reason", ""),
                "gross": gross,
                "net_x1": gross - cost,
                "net_x4": gross - 4 * cost,
                "net_x6": gross - 6 * cost,
            })
        r["signal_key"] = f"{r.get('candidate')}|{r.get('entry_time')}|{r.get('direction')}"
        out.append(r)
    return out


def merge_ledger(snapshot_rows: List[Dict[str, Any]], ledger_path: Path) -> List[Dict[str, Any]]:
    prev = read_csv(ledger_path)
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in prev:
        key = str(row.get("signal_key") or f"{row.get('candidate')}|{row.get('entry_time')}|{row.get('direction')}")
        if key:
            by_key[key] = row
    for row in snapshot_rows:
        key = str(row.get("signal_key") or f"{row.get('candidate')}|{row.get('entry_time')}|{row.get('direction')}")
        if key:
            by_key[key] = row
    rows = list(by_key.values())
    rows.sort(key=lambda r: (str(r.get("entry_time", "")), str(r.get("candidate", ""))))
    return rows


def summarize_candidates(rows: List[Dict[str, Any]], min_signals_before_review: int) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get("candidate") or "UNKNOWN")].append(r)
    out: List[Dict[str, Any]] = []
    for cand, vals in groups.items():
        family = str(vals[0].get("family") or "")
        resolved = [r for r in vals if r.get("outcome_status") == "RESOLVED_M1_REPLAY_SHADOW"]
        net_x4_vals = [safe_float(r.get("net_x4")) for r in resolved]
        net_x4 = [float(x) for x in net_x4_vals if x is not None]
        signal_count = len(vals)
        latest = max((str(r.get("entry_time") or "") for r in vals), default="")
        pf_x4 = pf(net_x4)
        avg_x4 = sum(net_x4) / len(net_x4) if net_x4 else 0.0
        win_rate = sum(1 for x in net_x4 if x > 0) / len(net_x4) if net_x4 else 0.0
        if signal_count >= min_signals_before_review and len(resolved) >= min_signals_before_review and pf_x4 >= 1.05 and avg_x4 > 0:
            readiness = "DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY"
        elif signal_count > 0:
            readiness = "FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY"
        else:
            readiness = "NO_RECENT_SIGNAL_RESEARCH_ONLY"
        out.append({
            "candidate": cand,
            "family": family,
            "signal_count": signal_count,
            "resolved_count": len(resolved),
            "latest_signal_ts": latest,
            "pf_x4": round(pf_x4, 6) if math.isfinite(pf_x4) else "inf",
            "avg_net_x4": round(avg_x4, 6),
            "win_rate_x4": round(win_rate, 6),
            "readiness": readiness,
        })
    out.sort(key=lambda r: (str(r.get("readiness")) == "DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY", int(r.get("signal_count") or 0), float(r.get("avg_net_x4") or 0.0)), reverse=True)
    return out


def summarize_families(candidate_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in candidate_summary:
        groups[str(r.get("family") or "UNKNOWN")].append(r)
    out: List[Dict[str, Any]] = []
    for fam, vals in groups.items():
        signals = sum(int(v.get("signal_count") or 0) for v in vals)
        resolved = sum(int(v.get("resolved_count") or 0) for v in vals)
        review_ready = sum(1 for v in vals if v.get("readiness") == "DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY")
        latest = max((str(v.get("latest_signal_ts") or "") for v in vals), default="")
        out.append({
            "family": fam,
            "candidate_count": len(vals),
            "signal_count": signals,
            "resolved_count": resolved,
            "review_ready_candidate_count": review_ready,
            "latest_signal_ts": latest,
            "recommendation": "REVIEW_DENSE_FORWARD_CANDIDATES" if review_ready else ("KEEP_COLLECTING_FORWARD_SAMPLES" if signals else "NO_RECENT_FORWARD_SIGNAL"),
        })
    out.sort(key=lambda r: (int(r.get("review_ready_candidate_count") or 0), int(r.get("signal_count") or 0)), reverse=True)
    return out


def markdown_table(rows: List[Dict[str, Any]], cols: Sequence[str], limit: int = 30) -> List[str]:
    lines: List[str] = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for row in rows[:limit]:
        vals = []
        for c in cols:
            vals.append(str(row.get(c, "")).replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def write_report(summary: Dict[str, Any], selection_notes: List[Dict[str, Any]], candidate_summary: List[Dict[str, Any]], family_summary: List[Dict[str, Any]], snapshot_rows: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage32C — Dense Forward Shadow Tracker\n")
    lines.append(f"Generated UTC: {summary['generated_utc']}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    for key in ["decision", "execution_status", "no_ea_change", "no_paper_live", "no_order_authorization", "commercial_goal", "primary_objective"]:
        lines.append(f"{key.upper()} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Why this stage exists\n")
    lines.append("Stage32B produced a dense intake queue. Stage32C connects that queue to recurring signal collection so the project can move faster toward a commercially usable system without waiting on low-cadence watchlist candidates.\n")
    lines.append("## Summary\n")
    lines.append("```text")
    for key in [
        "queue_rows", "selected_specs", "snapshot_signal_rows", "ledger_signal_rows", "candidate_summary_rows",
        "family_summary_rows", "review_queue_candidate_count", "lookback_days", "min_signals_before_review",
        "latest_m1_utc", "latest_h1_utc",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```\n")
    lines.append("## Selected specs from Stage32B queue\n")
    if selection_notes:
        lines.extend(markdown_table(selection_notes, ["candidate", "family", "source", "queue_rank", "recent_opportunity_count_for_selection"], limit=40))
    else:
        lines.append("No specs selected.\n")
    lines.append("\n## Candidate forward-shadow summary\n")
    if candidate_summary:
        lines.extend(markdown_table(candidate_summary, ["candidate", "family", "signal_count", "resolved_count", "latest_signal_ts", "pf_x4", "avg_net_x4", "readiness"], limit=40))
    else:
        lines.append("No recent dense forward-shadow signals found.\n")
    lines.append("\n## Family summary\n")
    if family_summary:
        lines.extend(markdown_table(family_summary, ["family", "candidate_count", "signal_count", "resolved_count", "review_ready_candidate_count", "recommendation"], limit=30))
    else:
        lines.append("No family summary available.\n")
    lines.append("\n## Latest signal snapshot\n")
    latest_rows = sorted(snapshot_rows, key=lambda r: str(r.get("entry_time", "")), reverse=True)
    if latest_rows:
        lines.extend(markdown_table(latest_rows, ["entry_time", "candidate", "family", "direction", "outcome_status", "exit_reason", "net_x4"], limit=40))
    else:
        lines.append("No recent signals in the current lookback window.\n")
    lines.append("\n## Operational interpretation\n")
    lines.append("```text")
    lines.append("1. This is still research/shadow only; no EA, paper/live, or order authorization.")
    lines.append("2. If signal_count grows but review_queue_candidate_count remains zero, next step is repair/tightening of dense variants, not calendar enrichment.")
    lines.append("3. If at least one candidate reaches the review queue, inspect its forward ledger before any commercial transition discussion.")
    lines.append("4. Stage31 macro/exogenous candidates remain watchlist-only unless they become forward-active.")
    lines.append("```\n")
    lines.append("## Output files\n")
    for p in [
        OUT_DIR / "stage32c_dense_forward_shadow_tracker.md",
        OUT_DIR / "dense_forward_signal_snapshot.csv",
        OUT_DIR / "dense_forward_signal_ledger.csv",
        OUT_DIR / "dense_forward_candidate_summary.csv",
        OUT_DIR / "dense_forward_family_summary.csv",
        OUT_DIR / "stage32c_summary.json",
    ]:
        lines.append(f"- `{rel(p)}`")
    (OUT_DIR / "stage32c_dense_forward_shadow_tracker.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage32C dense forward shadow tracker.")
    parser.add_argument("--queue", default=os.getenv("STAGE32C_QUEUE", str(DEFAULT_QUEUE)), help="Stage32B shadow_intake_queue.csv path")
    parser.add_argument("--db", default=os.getenv("TRADING_DB", str(DEFAULT_DB)), help="SQLite DB path")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--max-variants-per-family", type=int, default=DEFAULT_MAX_VARIANTS_PER_FAMILY)
    parser.add_argument("--min-signals-before-review", type=int, default=DEFAULT_MIN_SIGNALS_BEFORE_REVIEW)
    parser.add_argument("--max-total-specs", type=int, default=DEFAULT_MAX_TOTAL_SPECS)
    return parser.parse_args(argv)


def run(args: Optional[argparse.Namespace] = None) -> Dict[str, Any]:
    ensure_dirs()
    args = args or parse_args()
    generated_utc = iso(utc_now())
    queue_path = Path(args.queue)
    db_path = Path(args.db)
    queue_rows = read_csv(queue_path)

    base_summary: Dict[str, Any] = {
        "generated_utc": generated_utc,
        "execution_status": "RESEARCH_SHADOW_ONLY",
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "commercial_goal": COMMERCIAL_GOAL,
        "primary_objective": "COLLECT_FORWARD_OBSERVABLE_SAMPLES_FROM_DENSE_FAMILIES",
        "queue_path": rel(queue_path),
        "db_path": rel(db_path),
        "lookback_days": int(args.lookback_days),
        "min_signals_before_review": int(args.min_signals_before_review),
        "max_variants_per_family": int(args.max_variants_per_family),
        "max_total_specs": int(args.max_total_specs),
        "queue_rows": len(queue_rows),
    }

    if not queue_rows:
        summary = dict(base_summary)
        summary.update({
            "decision": "STAGE32C_BLOCKED_NO_STAGE32B_QUEUE_RESEARCH_SHADOW_ONLY",
            "selected_specs": 0,
            "snapshot_signal_rows": 0,
            "ledger_signal_rows": 0,
            "candidate_summary_rows": 0,
            "family_summary_rows": 0,
            "review_queue_candidate_count": 0,
            "latest_m1_utc": "",
            "latest_h1_utc": "",
            "error": f"Queue not found or empty: {queue_path}",
        })
        write_json(OUT_DIR / "stage32c_summary.json", summary)
        write_report(summary, [], [], [], [])
        return summary

    try:
        stage28a = import_stage28a()
        m1, h1, m15, db_meta = stage28a.load_market(db_path)
        daily = stage28a._build_daily_features(m15, h1)
        specs, selection_notes = choose_specs_from_queue(
            stage28a=stage28a,
            queue_rows=queue_rows,
            m15=m15,
            daily=daily,
            lookback_days=int(args.lookback_days),
            max_variants_per_family=int(args.max_variants_per_family),
            max_total_specs=int(args.max_total_specs),
        )
        signal_seed_rows: List[Dict[str, Any]] = []
        for spec in specs:
            _cnt, rows = count_recent_opportunities(stage28a, spec, m15, daily, int(args.lookback_days), include_rows=True)
            signal_seed_rows.extend(rows)
        snapshot_rows = add_replay_outcomes(stage28a, m1, m15, signal_seed_rows)
        snapshot_rows.sort(key=lambda r: (str(r.get("entry_time", "")), str(r.get("candidate", ""))))
        ledger_rows = merge_ledger(snapshot_rows, OUT_DIR / "dense_forward_signal_ledger.csv")
        candidate_summary = summarize_candidates(ledger_rows, int(args.min_signals_before_review))
        family_summary = summarize_families(candidate_summary)
        review_ready = [r for r in candidate_summary if r.get("readiness") == "DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY"]
        if review_ready:
            decision = "STAGE32C_HAS_DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY"
        elif snapshot_rows:
            decision = "STAGE32C_DENSE_FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY"
        else:
            decision = "STAGE32C_NO_RECENT_DENSE_FORWARD_SIGNAL_RESEARCH_SHADOW_ONLY"
        latest_m1 = str(m1.index.max()) if len(m1) else ""
        latest_h1 = str(h1.index.max()) if len(h1) else ""
        summary = dict(base_summary)
        summary.update({
            "decision": decision,
            "selected_specs": len(specs),
            "snapshot_signal_rows": len(snapshot_rows),
            "ledger_signal_rows": len(ledger_rows),
            "candidate_summary_rows": len(candidate_summary),
            "family_summary_rows": len(family_summary),
            "review_queue_candidate_count": len(review_ready),
            "latest_m1_utc": latest_m1,
            "latest_h1_utc": latest_h1,
            "db_meta": db_meta,
        })
        write_csv(OUT_DIR / "selected_dense_specs.csv", selection_notes)
        write_json(OUT_DIR / "selected_dense_specs.json", selection_notes)
        write_csv(OUT_DIR / "dense_forward_signal_snapshot.csv", snapshot_rows)
        write_json(OUT_DIR / "dense_forward_signal_snapshot.json", snapshot_rows)
        write_csv(OUT_DIR / "dense_forward_signal_ledger.csv", ledger_rows)
        write_json(OUT_DIR / "dense_forward_signal_ledger.json", ledger_rows)
        write_csv(OUT_DIR / "dense_forward_candidate_summary.csv", candidate_summary)
        write_json(OUT_DIR / "dense_forward_candidate_summary.json", candidate_summary)
        write_csv(OUT_DIR / "dense_forward_family_summary.csv", family_summary)
        write_json(OUT_DIR / "dense_forward_family_summary.json", family_summary)
        write_json(OUT_DIR / "stage32c_summary.json", summary)
        write_report(summary, selection_notes, candidate_summary, family_summary, snapshot_rows)
        return summary
    except Exception as exc:
        summary = dict(base_summary)
        summary.update({
            "decision": "STAGE32C_ERROR_RESEARCH_SHADOW_ONLY",
            "selected_specs": 0,
            "snapshot_signal_rows": 0,
            "ledger_signal_rows": 0,
            "candidate_summary_rows": 0,
            "family_summary_rows": 0,
            "review_queue_candidate_count": 0,
            "latest_m1_utc": "",
            "latest_h1_utc": "",
            "error": f"{type(exc).__name__}: {exc}",
        })
        write_json(OUT_DIR / "stage32c_summary.json", summary)
        write_report(summary, [], [], [], [])
        return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(summary.get("decision"))
    print(f"report={rel(OUT_DIR / 'stage32c_dense_forward_shadow_tracker.md')}")
    print(f"snapshot={rel(OUT_DIR / 'dense_forward_signal_snapshot.csv')}")
    print(f"ledger={rel(OUT_DIR / 'dense_forward_signal_ledger.csv')}")
    return 0 if "ERROR" not in str(summary.get("decision")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
