#!/usr/bin/env python3
"""
Stage53 paper-order simulator skeleton.

This is deliberately non-operational until Stage53 gates allow dry paper-order simulation design.
It never connects to a broker and never places, modifies, or closes any real or paper-live order.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

STAGE = "Stage53_PAPER_ORDER_SIMULATOR_SKELETON_NO_PROMOTION"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": repr(exc), "path": str(path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage53 paper-order simulator skeleton only")
    ap.add_argument("--root", default=".")
    ap.add_argument("--gate-summary", default="reports/stage53_forward_shadow_prep/stage53_forward_shadow_gate_summary.json")
    ap.add_argument("--out", default="reports/stage53_forward_shadow_prep")
    ap.add_argument("--force-skeleton-report", action="store_true", help="Write skeleton report even if gates are not passed; still no orders.")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    gate_path = (root / args.gate_summary).resolve() if not Path(args.gate_summary).is_absolute() else Path(args.gate_summary).resolve()
    gate = read_json(gate_path)
    decision = gate.get("decision")
    allowed = decision == "PAPER_ORDER_SIMULATION_DESIGN_ALLOWED_NO_PROMOTION"
    status = "SKELETON_BLOCKED_WAITING_FOR_GATES_NO_PROMOTION"
    if allowed:
        status = "SKELETON_READY_FOR_DRY_SIM_DESIGN_NO_PROMOTION"
    elif args.force_skeleton_report:
        status = "SKELETON_REPORT_ONLY_GATES_NOT_PASSED_NO_PROMOTION"

    summary = {
        "stage": STAGE,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "gate_decision": decision,
        "orders_created": 0,
        "broker_connection": "DISABLED",
        "paper_live_connection": "DISABLED",
        "simulated_only": True,
        "next_allowed_step": "CONTINUE_TRUE_FORWARD_SHADOW_UNTIL_STAGE53_GATES_PASS_NO_PROMOTION" if not allowed else "IMPLEMENT_DRY_PAPER_ORDER_SIMULATION_NO_PROMOTION",
        "paper_order_preview": gate.get("paper_order_preview", {}),
        "generated_utc": utc_now_iso(),
    }
    (out / "stage53_paper_order_skeleton_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Stage53 Paper-Order Simulator Skeleton",
        "",
        f"- status: `{status}`",
        f"- gate_decision: `{decision}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "- orders_created: `0`",
        "",
        "This file is a preparation skeleton only. It does not connect to any broker and does not submit orders.",
    ]
    (out / "stage53_paper_order_skeleton_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"stage": STAGE, "status": status, "orders_created": 0, "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
