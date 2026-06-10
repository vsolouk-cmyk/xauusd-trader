#!/usr/bin/env python3
"""
Stage 13A — Edge Audit / Strategy Triage

Purpose:
- Stop tool/report/stage sprawl.
- Audit whether the project has a tradable, repeatable, commercially useful XAUUSD edge.
- Produce a decision: KEEP_RESTRICTED_LONG_ONLY / REDESIGN_REQUIRED / STOP_TRADING_SYSTEM_BUILD.

This is NOT:
- a strategy lab
- a grid search
- an EA patch
- a dashboard polish task
- paper/live/order authorization

Hard rules:
- Audit only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage13a_edge_audit_triage")


@dataclass
class Evidence:
    area: str
    status: str
    verdict: str
    confidence: str
    source: str
    notes: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def glob_all(patterns: Iterable[str]) -> List[Path]:
    hits: List[Path] = []
    seen = set()
    for pat in patterns:
        for p in Path(".").glob(pat):
            if p.is_file() and str(p) not in seen:
                hits.append(p)
                seen.add(str(p))
    return sorted(hits, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)


def read_text(path: Optional[Path], max_chars: int = 200_000) -> str:
    if not path or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def read_csv(path: Optional[Path]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()


def find_latest_json(patterns: Iterable[str]) -> Optional[Path]:
    hits = glob_all(patterns)
    return hits[0] if hits else None


def find_latest_text(patterns: Iterable[str]) -> Optional[Path]:
    hits = glob_all(patterns)
    return hits[0] if hits else None


def number_from_text(text: str, key: str) -> Optional[float]:
    # Finds patterns like robust_candidate_count: `24` or "robust_candidate_count": 24
    pats = [
        rf"{re.escape(key)}\s*[:=]\s*`?(-?\d+(?:\.\d+)?)`?",
        rf'"{re.escape(key)}"\s*:\s*(-?\d+(?:\.\d+)?)',
    ]
    for pat in pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
    return None


def extract_decision_from_text(text: str) -> str:
    pats = [
        r"decision\s*[:=]\s*`?([A-Za-z0-9_\-]+)`?",
        r'"decision"\s*:\s*"([^"]+)"',
    ]
    for pat in pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def audit_long_thesis() -> Evidence:
    """
    Look for Stage8/Stage4 long evidence.

    This audit does not re-run strategy. It inventories previously generated evidence.
    """
    stage8_files = glob_all([
        "data/reports/stage8*/**/*",
        "archive/**/data/reports/stage8*/**/*",
        "data/reports/*stage8*/**/*",
        "archive/**/*stage8*/**/*",
    ])
    stage8_text_files = [p for p in stage8_files if p.suffix.lower() in {".md", ".json", ".csv", ".txt"}]
    combined = "\n".join(read_text(p, 50_000) for p in stage8_text_files[:30])

    # Known keywords from prior pipeline.
    has_stage8 = bool(stage8_text_files)
    has_pass = bool(re.search(r"\bPASS\b|short_candidate_found|forward-shadow candidate|PROMISING|robust", combined, re.IGNORECASE))
    robust_count = number_from_text(combined, "robust_candidate_count")
    selected_long = bool(re.search(r"h4_up|compression|liquidity|long|Stage 8D|forward-shadow", combined, re.IGNORECASE))

    # Stronger direct signal from Stage8C.
    if has_stage8 and (has_pass or (robust_count is not None and robust_count > 0) or selected_long):
        return Evidence(
            area="Long technical thesis",
            status="evidence_available",
            verdict="KEEP_RESTRICTED_LONG_ONLY",
            confidence="medium",
            source=str(stage8_text_files[0]) if stage8_text_files else "stage8 reports",
            notes=(
                "Prior Stage 8/8D evidence exists and supports keeping the long-only thesis as the only active forward-shadow path. "
                "However, this audit does not prove live edge; it only preserves the best existing candidate."
            ),
        )

    # Fallback: Stage12 report may say long-only remains active.
    stage12_md = find_latest_text([
        "data/reports/stage12a_consolidated_forward_shadow_report/*.md",
        "archive/**/data/reports/stage12a_consolidated_forward_shadow_report/*.md",
    ])
    stage12_text = read_text(stage12_md)
    if "Long-only validated forward-shadow remains" in stage12_text:
        return Evidence(
            area="Long technical thesis",
            status="evidence_available_via_consolidated_report",
            verdict="KEEP_RESTRICTED_LONG_ONLY",
            confidence="low_medium",
            source=str(stage12_md),
            notes=(
                "Stage 12A operational summary preserves long-only as the main active research/monitoring path. "
                "Original Stage 8 evidence was not fully re-opened by this audit, so confidence is lower than direct Stage8 evidence."
            ),
        )

    return Evidence(
        area="Long technical thesis",
        status="insufficient_evidence_in_files",
        verdict="REDESIGN_REQUIRED",
        confidence="low",
        source="stage8 reports not found or not parseable",
        notes="Audit could not locate enough Stage 8 evidence to justify keeping long thesis as a commercial candidate.",
    )


def audit_forward_activity() -> Evidence:
    stage12_json = find_latest_json([
        "data/reports/stage12a_consolidated_forward_shadow_report/*.json",
        "archive/**/data/reports/stage12a_consolidated_forward_shadow_report/*.json",
    ])
    j = read_json(stage12_json)
    long_state = j.get("long_signal_state", {})
    state = long_state.get("state", "")
    audit = j.get("input_audit", {})

    if state == "signal_file_found_with_rows" or audit.get("long_signal_rows_available") is True:
        return Evidence(
            area="Forward signal activity",
            status="active_rows_available",
            verdict="KEEP_MONITORING",
            confidence="high",
            source=str(stage12_json),
            notes="EA signal file has rows; forward telemetry is active.",
        )

    if state == "signal_file_found_zero_rows" or audit.get("long_signal_file_found") is True:
        return Evidence(
            area="Forward signal activity",
            status="file_found_zero_rows",
            verdict="REGIME_WAIT_OR_REDESIGN",
            confidence="high",
            source=str(stage12_json),
            notes=(
                "EA signal file exists but has zero signal rows. This is consistent with a long-only strategy being inactive during non-uptrend regimes. "
                "It is not a CSV/parser problem; it is an opportunity-frequency problem."
            ),
        )

    # Probe result fallback.
    probe = find_latest_json([
        "data/reports/stage12a_long_signal_file_probe/*.json",
        "archive/**/data/reports/stage12a_long_signal_file_probe/*.json",
    ])
    pj = read_json(probe)
    if pj.get("status") in {"file_exists_bom_only", "file_exists_empty", "file_exists_header_only"}:
        return Evidence(
            area="Forward signal activity",
            status=pj.get("status"),
            verdict="REGIME_WAIT_OR_REDESIGN",
            confidence="high",
            source=str(probe),
            notes="Probe confirms signal file exists but has no rows; no qualifying forward signal has been logged.",
        )

    return Evidence(
        area="Forward signal activity",
        status="missing_or_unknown",
        verdict="TELEMETRY_INCOMPLETE",
        confidence="low",
        source=str(stage12_json or probe or "missing"),
        notes="Forward telemetry is not complete enough to judge live opportunity rate.",
    )


def audit_short_thesis() -> Evidence:
    stage11c = find_latest_json([
        "data/reports/stage11c_recent_short_regime_diagnostic/*.json",
        "archive/**/data/reports/stage11c_recent_short_regime_diagnostic/*.json",
    ])
    stage11d = find_latest_json([
        "data/reports/stage11d_recent_short_watchlist_report/*.json",
        "archive/**/data/reports/stage11d_recent_short_watchlist_report/*.json",
    ])
    j = read_json(stage11c)
    d = read_json(stage11d)
    decision = j.get("decision", "") or d.get("decision", "")
    counts = j.get("verdict_counts", {})

    if decision == "recent_short_watchlist_only" or "RECENT_REGIME_WATCHLIST_ONLY" in counts:
        return Evidence(
            area="Short-side thesis",
            status="watchlist_only",
            verdict="REJECT_AS_TRADING_RULE",
            confidence="high",
            source=str(stage11c or stage11d),
            notes="Short-side candidates are recent-regime/short-term watchlist only; no all-history short research candidate was found.",
        )

    # MD fallback.
    txt_path = find_latest_text([
        "data/reports/stage11c_recent_short_regime_diagnostic/*.md",
        "archive/**/data/reports/stage11c_recent_short_regime_diagnostic/*.md",
    ])
    txt = read_text(txt_path)
    if "RECENT_REGIME_WATCHLIST_ONLY" in txt and "ALL_HISTORY_RESEARCH_CANDIDATE" not in txt:
        return Evidence(
            area="Short-side thesis",
            status="watchlist_only",
            verdict="REJECT_AS_TRADING_RULE",
            confidence="medium",
            source=str(txt_path),
            notes="Text report shows recent-watchlist only; do not promote short logic to EA.",
        )

    return Evidence(
        area="Short-side thesis",
        status="insufficient_or_missing",
        verdict="NO_SHORT_AUTHORIZATION",
        confidence="low",
        source=str(stage11c or stage11d or "missing"),
        notes="Audit could not find robust short evidence; short remains unauthorized.",
    )


def audit_macro_news() -> Evidence:
    stage10e = find_latest_json([
        "data/reports/stage10e_event_aware_guard_simulation/*.json",
        "archive/**/data/reports/stage10e_event_aware_guard_simulation/*.json",
    ])
    stage12 = find_latest_json([
        "data/reports/stage12a_consolidated_forward_shadow_report/*.json",
        "archive/**/data/reports/stage12a_consolidated_forward_shadow_report/*.json",
    ])
    j10 = read_json(stage10e)
    j12 = read_json(stage12)
    eg = j12.get("event_guard", {})
    decision = eg.get("decision", "") or j10.get("decision", "")

    if decision in {"no_event_guard_passed", "no_event_guard_active"}:
        return Evidence(
            area="Macro/news/event layer",
            status="available_but_no_guard",
            verdict="REPORT_ONLY",
            confidence="high",
            source=str(stage12 or stage10e),
            notes="Macro/news/event analysis did not justify a guard or directional trading rule. Keep as context/report only.",
        )

    # Fallback text.
    txt = read_text(find_latest_text([
        "data/reports/stage10e_event_aware_guard_simulation/*.md",
        "data/reports/stage12a_consolidated_forward_shadow_report/*.md",
        "archive/**/data/reports/stage10e_event_aware_guard_simulation/*.md",
        "archive/**/data/reports/stage12a_consolidated_forward_shadow_report/*.md",
    ]))
    if "did not justify" in txt or "report-only" in txt.lower():
        return Evidence(
            area="Macro/news/event layer",
            status="available_but_no_guard",
            verdict="REPORT_ONLY",
            confidence="medium",
            source="stage10e/stage12 text",
            notes="Text evidence says macro/news remains report-only.",
        )

    return Evidence(
        area="Macro/news/event layer",
        status="missing_or_unproven",
        verdict="REPORT_ONLY",
        confidence="low",
        source=str(stage12 or stage10e or "missing"),
        notes="No evidence found that macro/news adds tradeable edge. Keep as report-only.",
    )


def audit_complexity() -> Evidence:
    report_dirs = [p for p in Path("data/reports").glob("*") if p.is_dir()] if Path("data/reports").exists() else []
    stage_like = [p for p in report_dirs if re.search(r"stage\d+", p.name, re.IGNORECASE)]
    workflows = glob_all([".github/workflows/*.yml", ".github/workflows/*.yaml"])
    archive_dirs = [p for p in Path("archive").glob("**/*") if p.is_dir()] if Path("archive").exists() else []

    n_stages = len(stage_like)
    n_workflows = len(workflows)
    n_archives = len(archive_dirs)

    if n_stages >= 12 or n_workflows >= 4:
        verdict = "REDUCE_SCOPE"
        notes = f"High process complexity detected: stage_report_dirs={n_stages}, workflows={n_workflows}, archive_dirs={n_archives}. Stop creating support tooling unless tied to a decision."
        confidence = "high"
    else:
        verdict = "KEEP_SIMPLE"
        notes = f"Process complexity acceptable: stage_report_dirs={n_stages}, workflows={n_workflows}, archive_dirs={n_archives}."
        confidence = "medium"

    return Evidence(
        area="Engineering/process complexity",
        status="measured",
        verdict=verdict,
        confidence=confidence,
        source="local repo structure",
        notes=notes,
    )


def determine_final_decision(evidence: List[Evidence]) -> Tuple[str, List[str], List[str]]:
    ev = {e.area: e for e in evidence}

    long_v = ev.get("Long technical thesis").verdict if ev.get("Long technical thesis") else ""
    fwd_v = ev.get("Forward signal activity").verdict if ev.get("Forward signal activity") else ""
    short_v = ev.get("Short-side thesis").verdict if ev.get("Short-side thesis") else ""
    macro_v = ev.get("Macro/news/event layer").verdict if ev.get("Macro/news/event layer") else ""
    complexity_v = ev.get("Engineering/process complexity").verdict if ev.get("Engineering/process complexity") else ""

    actions: List[str] = []
    stop_rules: List[str] = []

    if long_v == "KEEP_RESTRICTED_LONG_ONLY":
        if fwd_v == "REGIME_WAIT_OR_REDESIGN":
            decision = "KEEP_RESTRICTED_LONG_ONLY_WITH_REGIME_WAIT"
            actions += [
                "Keep EA v2 long-only forward-shadow unchanged.",
                "Do not add short/news/order logic.",
                "Stop dashboard/parser polishing unless signal rows appear or a real operational failure occurs.",
                "Define a waiting window for forward evidence; if no long signal appears after the window, redesign thesis instead of adding tools.",
            ]
        elif fwd_v == "KEEP_MONITORING":
            decision = "KEEP_RESTRICTED_LONG_ONLY_COLLECT_FORWARD_EVIDENCE"
            actions += [
                "Continue long-only forward-shadow evidence collection.",
                "Compare forward outcomes against Stage 8 expectations after enough rows.",
                "Do not expand to short/news/paper/live yet.",
            ]
        else:
            decision = "KEEP_RESTRICTED_LONG_ONLY_BUT_FIX_TELEMETRY_ONCE"
            actions += [
                "Keep long-only thesis as the only candidate.",
                "Fix forward telemetry once, then stop tooling work.",
            ]
    else:
        decision = "REDESIGN_REQUIRED"
        actions += [
            "Do not keep extending current technical/news/short pipeline.",
            "Design one new thesis from market logic before coding.",
            "Require a pre-defined kill rule before any new backtest.",
        ]

    if short_v == "REJECT_AS_TRADING_RULE":
        stop_rules.append("No short EA/order/paper/live path from Stage 11 results.")
    if macro_v == "REPORT_ONLY":
        stop_rules.append("No macro/news guard or directional news trading from Stage 9/10 results.")
    if complexity_v == "REDUCE_SCOPE":
        stop_rules.append("No new dashboard/workflow/report stage unless it directly changes KEEP/REDESIGN/STOP decision.")
    stop_rules += [
        "No paper/live authorization.",
        "No EA order code.",
        "No grid expansion without a new explicit thesis and kill rule.",
    ]

    return decision, actions, stop_rules


def write_outputs(out_dir: Path, evidence: List[Evidence], final_decision: str, actions: List[str], stop_rules: List[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    ev_rows = [e.__dict__ for e in evidence]
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "final_decision": final_decision,
        "evidence": ev_rows,
        "recommended_actions": actions,
        "stop_rules": stop_rules,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_news_trading": False,
            "automatic_short_trading": False,
        },
    }

    json_path = out_dir / "stage13a_edge_audit_triage.json"
    csv_path = out_dir / "stage13a_evidence_inventory.csv"
    md_path = out_dir / "stage13a_edge_audit_triage.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame(ev_rows).to_csv(csv_path, index=False)

    lines = [
        "# Stage 13A Edge Audit / Strategy Triage",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: audit only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Authorization flags",
        "| Item | Status |",
        "|---|---|",
        "| Trade authorization | `False` |",
        "| EA change authorization | `False` |",
        "| Paper order authorization | `False` |",
        "| Live order authorization | `False` |",
        "| Automatic news trading | `False` |",
        "| Automatic short trading | `False` |",
        "",
        "## Evidence inventory",
        "| Area | Status | Verdict | Confidence | Source | Notes |",
        "|---|---|---|---|---|---|",
    ]

    for e in evidence:
        notes = e.notes.replace("|", "/")
        source = e.source.replace("|", "/")
        lines.append(f"| {e.area} | `{e.status}` | `{e.verdict}` | `{e.confidence}` | `{source}` | {notes} |")

    lines += [
        "",
        "## Recommended actions",
    ]
    for a in actions:
        lines.append(f"- {a}")

    lines += [
        "",
        "## Stop rules",
    ]
    for r in stop_rules:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Interpretation",
        "- This audit is designed to stop process drift.",
        "- If the final decision is `KEEP_RESTRICTED_LONG_ONLY_WITH_REGIME_WAIT`, the project should stop building support tooling and wait for valid long-regime forward evidence.",
        "- If no forward evidence appears within the chosen waiting window, the correct next move is thesis redesign, not dashboard expansion.",
        "- Short/news/macro layers remain report-only unless a future thesis proves incremental edge under strict controls.",
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- csv: `{csv_path}`",
        f"- md: `{md_path}`",
    ]

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def run(out_dir: Path) -> int:
    evidence = [
        audit_long_thesis(),
        audit_forward_activity(),
        audit_short_thesis(),
        audit_macro_news(),
        audit_complexity(),
    ]
    final_decision, actions, stop_rules = determine_final_decision(evidence)
    md_path = write_outputs(out_dir, evidence, final_decision, actions, stop_rules)

    print("Stage 13A edge audit / strategy triage: DONE")
    print(f"final_decision={final_decision}")
    for e in evidence:
        print(f"{e.area}: {e.verdict} ({e.status}, confidence={e.confidence})")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
