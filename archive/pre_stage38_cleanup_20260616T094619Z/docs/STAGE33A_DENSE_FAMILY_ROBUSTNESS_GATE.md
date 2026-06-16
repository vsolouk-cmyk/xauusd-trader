# Stage33A — Dense Family Robustness & Sample Acceleration Gate

## Purpose

Stage32F is an automated sample collector. It is useful, but it is too slow to be the only route toward commercial readiness because one narrow variant may need weeks to reach 40 forward samples.

Stage33A tests whether related dense variants can be treated as a family. The goal is to reduce time-to-decision without authorizing EA, paper/live, or orders.

## What it does

- Reads Stage32E focus queue, Stage32D diagnostics, and Stage32C candidate summary.
- Groups variants into sibling families, for example `handoff h13/h14/h15`.
- Computes family-level effective signal count.
- Uses ledger de-duplication if Stage32C ledger is available.
- Produces a pre-commercial acceleration queue for Stage33B diagnostics.

## What it does not do

- It does not authorize EA changes.
- It does not authorize paper/live.
- It does not authorize orders.
- It does not replace Stage32F automation.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage33a_dense_family_robustness_gate
```

## Outputs

```text
data/reports/stage33a_dense_family_robustness_gate/stage33a_dense_family_robustness_gate.md
data/reports/stage33a_dense_family_robustness_gate/family_robustness_summary.csv
data/reports/stage33a_dense_family_robustness_gate/candidate_family_membership.csv
data/reports/stage33a_dense_family_robustness_gate/pre_commercial_acceleration_queue.csv
data/reports/stage33a_dense_family_robustness_gate/stage33a_summary.json
```

## Decision meaning

- `STAGE33A_HAS_FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY`: a family is strong enough to run Stage33B robustness diagnostics.
- `STAGE33A_HAS_FAMILY_ACCELERATION_DIAGNOSTICS_RESEARCH_ONLY`: a family is promising, but still needs diagnostics or a few more samples.
- `STAGE33A_REPAIR_OR_KILL_WEAK_FAMILIES_RESEARCH_ONLY`: stop waiting for these families as a primary fast path.
- `STAGE33A_NO_ACCELERATION_FAMILY_KEEP_BACKGROUND_ONLY`: Stage32F can continue in the background, but the main route should move to intake expansion or new family discovery.

## Commercial rule

Stage33A is still research-only. Commercial transition remains blocked until a later robustness gate, paper-order gate, and execution-risk guard pass.
