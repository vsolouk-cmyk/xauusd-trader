#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def as_bool(x: Any) -> bool:
    return bool(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repository root")
    ap.add_argument("--config", required=True, help="Stage64I config path")
    ap.add_argument("--out", required=True, help="Output reports directory")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cfg = read_json(cfg_path)

    def cfg_file(key: str) -> Path:
        p = Path(cfg["inputs"][key])
        return (root / p).resolve() if not p.is_absolute() else p

    stage64h_summary_path = cfg_file("stage64h_summary")
    stage64e_summary_path = cfg_file("stage64e_summary")
    stage64d5_summary_path = cfg_file("stage64d5_summary")
    stage64f_summary_path = cfg_file("stage64f_summary")
    stage64g_summary_path = cfg_file("stage64g_summary")

    stage64h = read_json(stage64h_summary_path)
    stage64e = read_json(stage64e_summary_path)
    stage64d5 = read_json(stage64d5_summary_path)
    stage64f = read_json(stage64f_summary_path)
    stage64g = read_json(stage64g_summary_path)

    h_counts = stage64h.get("counts", {})
    corrected_survivors = int(h_counts.get("corrected_survivors", 0) or 0)
    uncorrected_watch = int(h_counts.get("uncorrected_watch_only", 0) or 0)

    best_candidates = stage64h.get("best_candidates", [])
    negative_excess_count = 0
    for c in best_candidates:
        try:
            if float(c.get("mean_excess_vs_b1_bps_per_eligible_day", 0.0)) < 0:
                negative_excess_count += 1
        except Exception:
            pass

    full_scope_blockers = stage64e.get("full_scope", {}).get("blockers", [])
    full_scope_still_blocked = bool(stage64e.get("full_scope", {}).get("still_blocked", True))
    source_warnings = []
    for src in [stage64h, stage64g, stage64f, stage64e, stage64d5]:
        source_warnings.extend(src.get("source_warnings", []) or [])
    source_warnings = sorted(set(source_warnings))

    reduced_scope_killed = corrected_survivors == 0
    benchmark_excess_failed = negative_excess_count > 0 and negative_excess_count == len(best_candidates) if best_candidates else True

    if reduced_scope_killed:
        reduced_scope_decision = "KILL_REDUCED_SCOPE_P0_PLUS_VIX_AS_PROMOTION_OR_VALIDATION_PATH"
    else:
        reduced_scope_decision = "KEEP_REDUCED_SCOPE_FOR_INDEPENDENT_CONFIRMATION_ONLY_NO_ORDER"

    if full_scope_still_blocked:
        next_allowed_step = "Stage64J_FULL_SCOPE_DATA_COMPLETION_OR_PROGRAM_STOP_DECISION_NO_ORDER"
        strategic_decision = "KILL_REDUCED_SCOPE_AND_REQUIRE_FULL_SCOPE_DATA_COMPLETION_OR_STOP"
    else:
        next_allowed_step = "Stage64J_FULL_SCOPE_THESIS_VALIDATION_DESIGN_NO_SCAN"
        strategic_decision = "KILL_REDUCED_SCOPE_AND_MOVE_ONLY_TO_FULL_SCOPE_PREDECLARED_DESIGN"

    decision_matrix = [
        {
            "path": "Reduced-scope P0+VIX validation path",
            "status": "FAILED",
            "evidence": f"corrected_survivors={corrected_survivors}; uncorrected_watch_only={uncorrected_watch}; benchmark_excess_failed={benchmark_excess_failed}",
            "decision": reduced_scope_decision,
            "allowed_next": "Reference only; no parameter tweaking; no rescue filter; no order path",
        },
        {
            "path": "Full macro-regime thesis",
            "status": "BLOCKED_BY_DATA_COMPLETION" if full_scope_still_blocked else "DATA_READY_FOR_DESIGN",
            "evidence": f"full_scope_blockers={len(full_scope_blockers)}",
            "decision": "Continue only if P1/P2 source acquisition is completed with lag-safe policy",
            "allowed_next": "ETF holdings/flows, central-bank demand, and event calendar acquisition/preflight",
        },
        {
            "path": "Broker/spot alignment",
            "status": "REQUIRED_BEFORE_COMMERCIALIZATION",
            "evidence": "; ".join(source_warnings) if source_warnings else "no source warning",
            "decision": "Do not claim broker XAUUSD validation from COMEX futures proxy",
            "allowed_next": "Acquire broker/spot D1 backfill or run proxy-vs-broker alignment audit",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "evidence": "Stage64H no corrected edge; reduced-scope proxy only; full scope incomplete",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    blockers = [
        "NO_PAPER_ORDER",
        "NO_EA_PROMOTION",
        "NO_PAPER_LIVE",
        "NO_LIVE",
        "NO_BROKER_CONNECTION",
        "NO_FULL_SCOPE_VALIDATION_CLAIM",
        "NO_REDUCED_SCOPE_PARAMETER_TWEAKING",
        "NO_RESCUE_FILTERING",
        "NO_NEW_INTRADAY_SCAN",
    ]

    summary = {
        "stage": "Stage64I_DECISION_MEMO_KILL_OR_DATA_COMPLETION_NO_ORDER",
        "status": "DECISION_MEMO_COMPLETE_NO_PROMOTION",
        "decision": strategic_decision,
        "reduced_scope_decision": reduced_scope_decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64h_summary": str(stage64h_summary_path),
            "stage64e_summary": str(stage64e_summary_path),
            "stage64d5_summary": str(stage64d5_summary_path),
            "stage64f_summary": str(stage64f_summary_path),
            "stage64g_summary": str(stage64g_summary_path),
        },
        "stage64h_evidence": {
            "corrected_survivors": corrected_survivors,
            "uncorrected_watch_only": uncorrected_watch,
            "best_candidate_rows": len(best_candidates),
            "negative_excess_vs_benchmark_count": negative_excess_count,
            "primary_benchmark_id": stage64h.get("design", {}).get("primary_benchmark_id"),
            "effective_test_count": stage64h.get("design", {}).get("effective_test_count"),
        },
        "full_scope_state": {
            "still_blocked": full_scope_still_blocked,
            "blocker_count": len(full_scope_blockers),
            "blockers": full_scope_blockers,
        },
        "source_warnings": source_warnings,
        "decision_matrix": decision_matrix,
        "hard_blocks": blockers,
        "next_allowed_step": next_allowed_step,
        "outputs": {
            "summary_json": str(out / "stage64i_decision_memo_kill_or_data_completion_summary.json"),
            "report_md": str(out / "stage64i_decision_memo_kill_or_data_completion_report.md"),
            "decision_matrix_csv": str(out / "stage64i_decision_matrix.csv"),
            "decision_matrix_json": str(out / "stage64i_decision_matrix.json"),
        },
    }

    write_json(out / "stage64i_decision_memo_kill_or_data_completion_summary.json", summary)
    write_json(out / "stage64i_decision_matrix.json", decision_matrix)
    write_csv(out / "stage64i_decision_matrix.csv", decision_matrix, ["path", "status", "evidence", "decision", "allowed_next"])

    report = []
    report.append("# Stage64I - Decision Memo: Kill or Data Completion (No Order)\n")
    report.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    report.append("## Status\n")
    report.append("- status: `DECISION_MEMO_COMPLETE_NO_PROMOTION`")
    report.append(f"- decision: `{strategic_decision}`")
    report.append(f"- reduced_scope_decision: `{reduced_scope_decision}`")
    report.append("- promotion/paper/live: `NO_GO`")
    report.append("- validation_allowed_for_order_or_promotion: `false`\n")
    report.append("## Executive conclusion\n")
    if reduced_scope_killed:
        report.append(
            "The reduced-scope P0+VIX proxy validation is killed as a promotion or continued validation path. "
            "Stage64H produced no corrected survivors and no uncorrected watch candidates. "
            "Although several candidate rules can look positive in absolute active-return terms, they failed versus the predeclared trend benchmark and did not establish a corrected, robust edge."
        )
    else:
        report.append(
            "The reduced-scope path is not promoted. Any continued use is limited to independent confirmation only, with no order path."
        )
    report.append(
        "\nThe full macro-regime thesis is not killed by this result, because the reduced scope explicitly excluded ETF flows, central-bank demand, and historical event-calendar risk. "
        "However, no new reduced-scope tuning, rescue filtering, or intraday scan is allowed. The only valid continuation is full-scope data completion and lag-safe preflight, or a program stop decision."
    )
    report.append("\n## Evidence from Stage64H\n")
    report.append(f"- corrected_survivors: `{corrected_survivors}`")
    report.append(f"- uncorrected_watch_only: `{uncorrected_watch}`")
    report.append(f"- candidate_decision_rows: `{h_counts.get('candidate_decision_rows')}`")
    report.append(f"- negative_excess_vs_benchmark_count_among_best_candidates: `{negative_excess_count}`")
    report.append(f"- primary_benchmark_id: `{stage64h.get('design', {}).get('primary_benchmark_id')}`")
    report.append(f"- effective_test_count: `{stage64h.get('design', {}).get('effective_test_count')}`\n")
    report.append("## Decision matrix\n")
    report.append("| path | status | decision | allowed_next |")
    report.append("|---|---|---|---|")
    for row in decision_matrix:
        report.append(f"| `{row['path']}` | `{row['status']}` | {row['decision']} | {row['allowed_next']} |")
    report.append("\n## Source and scope warnings\n")
    if source_warnings:
        for w in source_warnings:
            report.append(f"- {w}")
    else:
        report.append("- none")
    report.append("\n## Full-scope blockers retained\n")
    if full_scope_blockers:
        for b in full_scope_blockers:
            report.append(f"- `{b.get('manifest_id')}`: {b.get('issues')}")
    else:
        report.append("- none")
    report.append("\n## Operational decision\n")
    report.append("No paper-order, paper-live, live, EA promotion, broker connection, or full-scope validation claim is authorized by Stage64I.")
    report.append("Reduced-scope P0+VIX must not be tuned, rescued, or treated as a commercial candidate.")
    report.append("\n## Next allowed step\n")
    report.append(f"`{next_allowed_step}`\n")
    (out / "stage64i_decision_memo_kill_or_data_completion_report.md").write_text("\n".join(report), encoding="utf-8")

    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "reduced_scope_decision": summary["reduced_scope_decision"],
        "next_allowed_step": summary["next_allowed_step"],
        "summary": summary["outputs"]["summary_json"],
        "report": summary["outputs"]["report_md"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
