# Stage33C — Handoff Repaired Family Gate

Stage33B rejected the full h13/h14/h15 handoff family. The rejection was useful because it showed the weak sibling and latest tail weakness instead of waiting weeks for single-variant N=40.

Stage33C tests a repaired family:

- Keep: `handoff_align_follow_h13_tp06_sl065`
- Keep: `handoff_align_follow_h14_tp06_sl065`
- Exclude: `handoff_align_follow_h15_tp06_sl065`

It reads the Stage32C dense forward ledger and produces:

- `stage33c_handoff_repaired_family_gate.md`
- `stage33c_summary.json`
- `repaired_family_diagnostics.csv`
- `repaired_member_split_summary.csv`
- `repaired_cost_sensitivity_summary.csv`
- `repaired_tail_batch_summary.csv`
- `repaired_family_events.csv`

This is research-only. It does not authorize EA, paper-live, live, or orders.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage33c_handoff_repaired_family_gate
```

## Decision semantics

- `STAGE33C_REPAIRED_FAMILY_PRE_PAPER_RESEARCH_CANDIDATE_ONLY`: move to strict cost-aware pre-paper research gate, still no execution.
- `STAGE33C_REPAIRED_FAMILY_NEAR_MISS_KEEP_SHORT_SHADOW_RESEARCH_ONLY`: short targeted collection or tightening only.
- `STAGE33C_REPAIRED_FAMILY_FAIL_REPAIR_OR_KILL_RESEARCH_ONLY`: do not wait; return to intake expansion/repair.
- `STAGE33C_LEDGER_MISSING_RESEARCH_ONLY`: fix inputs.
