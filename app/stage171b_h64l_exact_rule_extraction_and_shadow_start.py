#!/usr/bin/env python3
"""
Stage171B H64L Exact Rule Extraction and Shadow Start

Read-only governance/ops stage. It does not create MT5 signals, does not authorize
orders, and does not optimize thresholds. It extracts or reconstructs the locked
H64L rule evidence from Stage64 artifacts, maps H64L features to Stage170C
blockers, and creates a day-one manual shadow checklist/log template.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

H64L_FEATURES = [
    {
        "feature": "gold_trend_sma20_over_50",
        "provisional_condition": "gold_sma20_over_50 > 0",
        "source_family": "AMARKETS_BROKER_BARS",
        "mechanical_fix": "Use only completed daily bars; if evaluating at day D, compute SMA from closes through D-1 unless the D daily bar is fully closed and execution is at D+1 open/next valid bar.",
    },
    {
        "feature": "dxy_ret_20d",
        "provisional_condition": "dxy_ret_20d < 0",
        "source_family": "DXY_DAILY_OR_FRED_PROXY",
        "mechanical_fix": "Use DXY value only after its daily close/publication is available; for intraday evaluation, lag by at least one completed trading day unless available_time_utc is explicitly populated.",
    },
    {
        "feature": "real_yield_change_20d",
        "provisional_condition": "real_yield_change_20d < 0",
        "source_family": "REAL_YIELD_DAILY_FRED",
        "mechanical_fix": "Use real-yield data only after available_time_utc; if vintage availability is unknown, embargo same-day and use previous available daily observation only.",
    },
    {
        "feature": "etf_flow_tonnes_3m",
        "provisional_condition": "etf_flow_tonnes_3m > 0",
        "source_family": "ETF_GLD_WGC_FLOW",
        "mechanical_fix": "Use explicit publication/available_time_utc. If missing, apply conservative publication lag and use only already-published monthly/weekly/daily flow observations.",
    },
]

SEARCH_TERMS = ["H64L", "macro_tailwind", "tailwind", "dxy_ret_20d", "real_yield", "etf_flow", "gold_sma20", "sma20", "Stage64R", "stage64"]

@dataclass
class ArtifactHit:
    path: str
    size_bytes: int
    sha256_16: str
    term_hits: str
    likely_stage64: bool
    likely_rule_file: bool
    extracted_condition_clues: str


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return "READ_ERROR"


def safe_read_text(path: Path, max_bytes: int = 2_000_000) -> str:
    try:
        if path.stat().st_size > max_bytes:
            with path.open("rb") as f:
                raw = f.read(max_bytes)
            return raw.decode("utf-8", errors="ignore")
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def iter_candidate_files(root: Path) -> Iterable[Path]:
    include_suffixes = {".json", ".csv", ".md", ".txt", ".py", ".yaml", ".yml"}
    skip_parts = {".git", "__pycache__", ".pytest_cache", "node_modules", "venv", ".venv"}
    for base in [root / "data", root / "reports", root / "docs", root / "app"]:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in skip_parts for part in p.parts):
                continue
            if p.suffix.lower() not in include_suffixes:
                continue
            name = str(p).lower()
            if any(term.lower() in name for term in SEARCH_TERMS) or ("stage64" in name):
                yield p
                continue
            # Only text scan small-ish files to avoid slow repo scans.
            try:
                if p.stat().st_size <= 800_000:
                    txt = safe_read_text(p, max_bytes=200_000).lower()
                    if any(term.lower() in txt for term in SEARCH_TERMS):
                        yield p
            except Exception:
                continue


def extract_clues(text: str) -> List[str]:
    clues: List[str] = []
    patterns = [
        r"H64L[^\n\r]{0,160}",
        r"gold[_\w]*sma[^\n\r]{0,120}",
        r"dxy[_\w]*20d[^\n\r]{0,120}",
        r"real[_\w]*yield[^\n\r]{0,120}",
        r"etf[_\w]*flow[^\n\r]{0,120}",
        r"macro[_\w]*tailwind[^\n\r]{0,160}",
        r"z[^\n\r]{0,20}[=:]\s*[0-9]+\.?[0-9]*[^\n\r]{0,80}",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            s = " ".join(m.group(0).strip().split())
            if s and s not in clues:
                clues.append(s[:220])
            if len(clues) >= 12:
                return clues
    return clues


def artifact_inventory(root: Path) -> List[ArtifactHit]:
    hits: Dict[str, ArtifactHit] = {}
    for p in iter_candidate_files(root):
        txt = safe_read_text(p, max_bytes=500_000)
        low = (str(p) + "\n" + txt[:500_000]).lower()
        term_hits = [t for t in SEARCH_TERMS if t.lower() in low]
        clues = extract_clues(txt)
        key = str(p)
        try:
            size = p.stat().st_size
        except Exception:
            size = -1
        hits[key] = ArtifactHit(
            path=str(p),
            size_bytes=size,
            sha256_16=sha256_16(p),
            term_hits=";".join(term_hits),
            likely_stage64=("stage64" in str(p).lower()),
            likely_rule_file=bool(re.search(r"h64l|rule|locked|candidate|tailwind", str(p).lower() + " " + txt[:5000].lower())),
            extracted_condition_clues=" | ".join(clues),
        )
    # Sort most useful first.
    return sorted(hits.values(), key=lambda h: (not h.likely_rule_file, not h.likely_stage64, -len(h.term_hits), h.path))


def read_csv_dict(path: Path) -> List[Dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except Exception:
            dialect = csv.excel
        return list(csv.DictReader(f, dialect=dialect))


def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def map_blockers(contract_rows: List[Dict[str, str]], triage_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # Prefer Stage171 triage if supplied; enrich with mechanical fix and source mapping.
    by_feature: Dict[str, List[Dict[str, str]]] = {}
    for row in triage_rows:
        feat = row.get("feature") or row.get("h64l_feature") or ""
        if feat:
            by_feature.setdefault(feat, []).append(row)

    output: List[Dict[str, str]] = []
    for f in H64L_FEATURES:
        matched = by_feature.get(f["feature"], [])
        if matched:
            for row in matched:
                output.append({
                    "feature": f["feature"],
                    "provisional_condition": f["provisional_condition"],
                    "contract_source": row.get("contract source") or row.get("contract_source") or row.get("source_id") or "",
                    "stage170c_status": row.get("status") or row.get("historical_asof_status") or "",
                    "stage171_verdict": row.get("verdict") or "",
                    "risk": row.get("risk") or row.get("blocking_issue") or "",
                    "allowed_fix_type": "MECHANICAL_ASOF_ONLY_NO_THRESHOLD_CHANGE",
                    "mechanical_fix_required": f["mechanical_fix"],
                })
        else:
            # Fallback contract matching.
            lower_source = f["source_family"].lower()
            candidates = [r for r in contract_rows if any(token in (r.get("source_id", "") + r.get("source_group", "")).lower() for token in lower_source.split("_"))]
            if not candidates:
                candidates = [{}]
            for r in candidates[:2]:
                output.append({
                    "feature": f["feature"],
                    "provisional_condition": f["provisional_condition"],
                    "contract_source": r.get("source_id", f["source_family"]),
                    "stage170c_status": r.get("historical_asof_status", "UNKNOWN"),
                    "stage171_verdict": "NEEDS_TRIAGE_OR_CONTRACT_MATCH",
                    "risk": r.get("blocking_issue", "No explicit Stage171 triage row found."),
                    "allowed_fix_type": "MECHANICAL_ASOF_ONLY_NO_THRESHOLD_CHANGE",
                    "mechanical_fix_required": f["mechanical_fix"],
                })
    return output


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_shadow_template() -> List[Dict[str, str]]:
    header = {
        "date_utc": "YYYY-MM-DD",
        "check_time_utc": "HH:MM",
        "gold_sma20_over_50_status": "PASS/FAIL/UNKNOWN",
        "dxy_ret_20d_status": "PASS/FAIL/UNKNOWN",
        "real_yield_change_20d_status": "PASS/FAIL/UNKNOWN",
        "etf_flow_tonnes_3m_status": "PASS/FAIL/UNKNOWN",
        "event_guard_state": "LOW/MEDIUM/HIGH/UNKNOWN",
        "blackout_fomc_nfp_cpi_30m": "YES/NO/UNKNOWN",
        "h64l_shadow_signal": "HIT/NO_HIT/INCONCLUSIVE",
        "operator_notes": "manual log only; no orders",
        "source_links_or_files": "paths/links used",
    }
    return [header]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--stage171-summary", default="")
    ap.add_argument("--stage171-triage", default="")
    ap.add_argument("--stage170c-contract-report", default="")
    ap.add_argument("--data-asof-contract", default="")
    ap.add_argument("--audit-timebox-business-days", type=int, default=3)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    outdir = root / "reports" / "stage171b_h64l_exact_rule_extraction_and_shadow_start"
    outdir.mkdir(parents=True, exist_ok=True)

    stage171_summary = load_json(Path(args.stage171_summary).expanduser()) if args.stage171_summary else {}
    triage_rows = read_csv_dict(Path(args.stage171_triage).expanduser()) if args.stage171_triage else []
    contract_rows = read_csv_dict(Path(args.data_asof_contract).expanduser()) if args.data_asof_contract else []
    if not contract_rows and args.stage170c_contract_report:
        contract_rows = read_csv_dict(Path(args.stage170c_contract_report).expanduser())

    inv = artifact_inventory(root)
    inv_rows = [asdict(h) for h in inv]
    write_csv(outdir / "stage171b_h64l_artifact_inventory.csv", inv_rows)

    blocker_rows = map_blockers(contract_rows, triage_rows)
    write_csv(outdir / "stage171b_h64l_targeted_asof_fix_plan.csv", blocker_rows)

    shadow_rows = build_shadow_template()
    write_csv(outdir / "stage171b_h64l_manual_shadow_log_template.csv", shadow_rows)

    exact_rule_locked = False
    confidence = "LOW"
    supporting_artifacts = []
    # Heuristic: exact if any artifact clue mentions H64L and all four conditions/feature terms.
    for h in inv:
        terms = h.term_hits.lower() + " " + h.extracted_condition_clues.lower() + " " + h.path.lower()
        if "h64l" in terms and ("dxy" in terms) and ("real" in terms) and ("etf" in terms) and ("sma" in terms or "gold" in terms):
            supporting_artifacts.append(h.path)
    if supporting_artifacts:
        confidence = "MEDIUM_NEEDS_HUMAN_CONFIRMATION_FROM_STAGE64R_RAW_EPISODES"
    if stage171_summary.get("h64l_clues", {}).get("exact_rule_locked") is True:
        exact_rule_locked = True
        confidence = "HIGH_FROM_STAGE171_SUMMARY"

    locked_rule_candidate = {
        "rule_id": "H64L_RESCUE_LOCKED_RULE_CANDIDATE_V0_FROM_EXPERT_FEEDBACK_PENDING_STAGE64R_CONFIRMATION",
        "generated_utc": now_utc(),
        "exact_rule_locked": exact_rule_locked,
        "threshold_reoptimization_allowed": False,
        "allowed_changes": ["mechanical_asof_lag_fix", "completed_bar_execution_convention", "publication_availability_lag"],
        "disallowed_changes": ["threshold_search", "new_indicator_addition_for_h64l_rescue", "post_hoc_filtering", "GDELT_as_alpha"],
        "conditions": [f["provisional_condition"] for f in H64L_FEATURES],
        "execution_intent": "manual_shadow_log_only_until_asof_safety_passes_and_specialist_accepts_limited_demo_bridge",
        "event_guard_policy": "GDELT/news guard only; simple 30-minute blackout around FOMC/NFP/CPI for rescue track.",
        "confidence": confidence,
        "supporting_artifacts": supporting_artifacts[:20],
        "note": "This is not a new optimized rule. It is a reconstruction candidate from expert feedback until Stage64R raw rule/episode artifact confirms the exact locked rule.",
    }
    (outdir / "stage171b_h64l_locked_rule_candidate.json").write_text(json.dumps(locked_rule_candidate, indent=2, ensure_ascii=False), encoding="utf-8")

    blocking_features = [r for r in blocker_rows if "BLOCK" in (r.get("stage171_verdict", "") + r.get("stage170c_status", "")).upper() or "LOW" in r.get("stage170c_status", "").upper() or "NEEDS" in r.get("stage171_verdict", "").upper()]
    decision = "STAGE171B_START_SHADOW_LOGGING_AND_RUN_TARGETED_H64L_ASOF_FIXES"
    if not supporting_artifacts and not exact_rule_locked:
        decision = "STAGE171B_SHADOW_CAN_START_BUT_EXACT_STAGE64R_RULE_EXTRACTION_STILL_REQUIRED"
    if blocking_features:
        recommended = "START_MANUAL_SHADOW_LOGGING_NOW; COMPLETE_TARGETED_MECHANICAL_ASOF_FIXES_WITHIN_3_BUSINESS_DAYS; DO_NOT_OPTIMIZE_THRESHOLDS"
    else:
        recommended = "START_MANUAL_SHADOW_LOGGING_NOW; PREPARE_LIMITED_DEMO_BRIDGE_REVIEW_IF_RULE_CONFIRMED_AND_SIGNAL_HITS"

    summary = {
        "stage": "Stage171B_H64L_EXACT_RULE_EXTRACTION_AND_SHADOW_START",
        "generated_utc": now_utc(),
        "root": str(root),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
        "status": "STAGE171B_COMPLETE_READONLY_PARALLEL_RESCUE_SUPPORT_READY",
        "decision": decision,
        "severity": "HIGH",
        "recommended_action": recommended,
        "audit_timebox_business_days": args.audit_timebox_business_days,
        "exact_rule_locked": exact_rule_locked,
        "rule_confidence": confidence,
        "artifact_hits": len(inv_rows),
        "supporting_artifact_count": len(supporting_artifacts),
        "h64l_features_checked": len(H64L_FEATURES),
        "targeted_asof_fix_rows": len(blocker_rows),
        "blocking_or_needs_fix_rows": len(blocking_features),
        "stage171_prior_decision": stage171_summary.get("decision"),
        "hard_constraints": {
            "no_threshold_reoptimization": True,
            "manual_shadow_starts_immediately": True,
            "orders_allowed": False,
            "gdelt_news_guard_only": True,
            "incomplete_after_timebox": "INCONCLUSIVE_NOT_OPEN_ENDED_AUDIT",
        },
        "outputs": {
            "summary_json": str(outdir / "stage171b_h64l_exact_rule_extraction_summary.json"),
            "decision_md": str(outdir / "stage171b_decision.md"),
            "locked_rule_candidate_json": str(outdir / "stage171b_h64l_locked_rule_candidate.json"),
            "artifact_inventory_csv": str(outdir / "stage171b_h64l_artifact_inventory.csv"),
            "targeted_asof_fix_plan_csv": str(outdir / "stage171b_h64l_targeted_asof_fix_plan.csv"),
            "manual_shadow_log_template_csv": str(outdir / "stage171b_h64l_manual_shadow_log_template.csv"),
        },
        "next": [
            "Fill the manual shadow log daily from today; log-only, no orders.",
            "Open the top Stage64/Stage64R artifacts from the inventory and confirm exact H64L rule/episode-level evidence.",
            "Apply only mechanical as-of fixes for the four H64L features; no threshold changes.",
            "After three business days: PASS/FAIL/INCONCLUSIVE. If PASS plus at least one shadow hit, prepare limited 0.01-lot demo bridge review.",
        ],
    }
    (outdir / "stage171b_h64l_exact_rule_extraction_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = f"""# Stage171B H64L Exact Rule Extraction and Shadow Start

Generated UTC: `{summary['generated_utc']}`

Decision: `{decision}`  
Recommended action: `{recommended}`

## Core decision

Stage171B keeps the expert correction intact: H64L rescue is a parallel track, not audit-before-action. Manual shadow logging can start immediately while the targeted as-of audit runs under a {args.audit_timebox_business_days}-business-day timebox.

## Rule extraction status

- Exact rule locked: `{exact_rule_locked}`
- Rule confidence: `{confidence}`
- Artifact hits: `{len(inv_rows)}`
- Supporting artifacts with H64L-like clues: `{len(supporting_artifacts)}`

The provisional rule candidate is written to `stage171b_h64l_locked_rule_candidate.json`. It is not a new optimized rule and must be confirmed against Stage64R raw/episode-level artifacts.

## H64L targeted as-of status

Targeted fix rows: `{len(blocker_rows)}`  
Blocking/needs-fix rows: `{len(blocking_features)}`

Only mechanical as-of fixes are allowed:

- completed-bar convention for gold trend
- daily close/availability lag for DXY
- vintage/availability lag for real yield
- publication lag for ETF/GLD/WGC flow

No threshold changes are allowed.

## Manual shadow

The manual shadow log template is ready at `stage171b_h64l_manual_shadow_log_template.csv`. It is log-only. It must not write MT5 signals and must not authorize orders.

## Decision tree

```text
PASS + at least one shadow hit -> Stage172 limited 0.01-lot demo bridge review.
PASS + zero shadow hit -> keep waiting for H64L signal; start small Path B AUC test as hedge.
FAIL -> abandon H64L rescue; move to Path B or C.
INCONCLUSIVE -> continue shadow logging only; specialist decision required.
```
"""
    (outdir / "stage171b_decision.md").write_text(md, encoding="utf-8")

    print(json.dumps({"summary": summary, "outdir": str(outdir)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
