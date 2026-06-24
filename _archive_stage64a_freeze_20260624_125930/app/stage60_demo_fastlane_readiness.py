#!/usr/bin/env python3
"""
Stage60 Demo Fast-Lane Readiness

Policy/readiness report for parallel demo-account execution sandbox. Demo can test
order plumbing earlier, but cannot replace true-forward evidence for edge promotion.
"""
from __future__ import annotations

import argparse, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

STAGE = "Stage60_DEMO_FASTLANE_READINESS_NO_PROMOTION"
NO_GO = "NO_GO"

def utcnow(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def resolve(root: Path, p: str|Path) -> Path:
    q=Path(p); return q if q.is_absolute() else root/q
def read_json(p: Path, default=None):
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))
def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def table_exists(conn, t):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

def state_meta(path: Path) -> Dict[str, Any]:
    out={"path": str(path), "found": path.exists(), "schema_ok": False, "total_signals": 0, "backfill_signals": None, "true_forward_signals": None, "evaluated_signals": None, "pending_signals": None}
    if not path.exists(): return out
    with sqlite3.connect(str(path)) as conn:
        if not table_exists(conn,"signals"): return out
        cols=[r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
        out["schema_ok"] = {"status","is_backfill"}.issubset(set(cols))
        out["total_signals"] = int(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0])
        out["backfill_signals"] = int(conn.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=1").fetchone()[0])
        out["true_forward_signals"] = int(conn.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=0").fetchone()[0])
        out["evaluated_signals"] = int(conn.execute("SELECT COUNT(*) FROM signals WHERE status='evaluated' AND COALESCE(is_backfill,0)=0").fetchone()[0])
        out["pending_signals"] = int(conn.execute("SELECT COUNT(*) FROM signals WHERE status='pending' AND COALESCE(is_backfill,0)=0").fetchone()[0])
    return out

def main():
    ap=argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--stage58b-state-db", default="data/shadow/stage58b_context_forward_shadow.sqlite")
    ap.add_argument("--stage59-summary", default="reports/stage59_context_forward_gates/stage59_context_forward_gate_summary.json")
    ap.add_argument("--out", default="reports/stage60_demo_fastlane")
    args=ap.parse_args(); root=Path(args.root).resolve(); out=resolve(root,args.out); out.mkdir(parents=True, exist_ok=True)
    st=state_meta(resolve(root,args.stage58b_state_db)); s59=read_json(resolve(root,args.stage59_summary),{}) or {}
    blockers=[]
    if not st["found"]: blockers.append("stage58b_state_db_missing")
    if not st["schema_ok"]: blockers.append("stage58b_state_schema_not_ready")
    if (st.get("backfill_signals") or 0)>0: blockers.append("backfill_contamination")
    # Demo fast-lane only means order plumbing sandbox, not edge validation.
    allow_design_demo_sandbox = len(blockers)==0
    summary={
        "stage": STAGE,
        "status": "DEMO_FASTLANE_READINESS_COMPLETE_NO_PROMOTION",
        "promotion": NO_GO, "EA": NO_GO, "paper_live": NO_GO, "live": NO_GO,
        "decision": "DEMO_EXECUTION_SANDBOX_DESIGN_ALLOWED_NO_EDGE_PROMOTION" if allow_design_demo_sandbox else "WAIT_DEMO_SANDBOX_BLOCKED_BY_TECHNICAL_READINESS_NO_PROMOTION",
        "next_allowed_step": "DESIGN_DEMO_EXECUTION_SANDBOX_WITH_DISABLED_LIVE_AND_TINY_RISK_NO_PROMOTION" if allow_design_demo_sandbox else "FIX_FORWARD_STATE_BEFORE_DEMO_SANDBOX_NO_PROMOTION",
        "state_meta": st,
        "stage59_decision": s59.get("decision"),
        "important_policy": {
            "demo_replaces_forward_shadow_for_edge": False,
            "demo_can_run_in_parallel_for_execution_plumbing": True,
            "live_requires_forward_and_demo_evidence": True,
            "paper_live_or_live_order_submission_allowed": False,
            "broker_connection_default": "DISABLED_UNTIL_EXPLICIT_DEMO_SANDBOX_STAGE"
        },
        "blockers": blockers,
        "allow_design_demo_sandbox": allow_design_demo_sandbox,
        "generated_utc": utcnow()
    }
    write_json(out/"stage60_demo_fastlane_readiness_summary.json", summary)
    lines=["# Stage60 Demo Fast-Lane Readiness", "", f"- status: `{summary['status']}`", f"- decision: `{summary['decision']}`", f"- next_allowed_step: `{summary['next_allowed_step']}`", f"- promotion: `{NO_GO}`", f"- EA: `{NO_GO}`", f"- paper_live: `{NO_GO}`", f"- live: `{NO_GO}`", "", "## Policy", "Demo-account execution can be started earlier as a broker/order-plumbing sandbox, but it does not replace true-forward evidence for statistical edge.", "", "## State", f"- true_forward_signals: `{st.get('true_forward_signals')}`", f"- evaluated_signals: `{st.get('evaluated_signals')}`", f"- backfill_signals: `{st.get('backfill_signals')}`", "", "## Interpretation", "Use demo to accelerate operational validation; keep forward-shadow as the edge evidence layer. No live or paper-live order submission is authorized."]
    (out/"stage60_demo_fastlane_readiness_report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
if __name__ == "__main__": main()
