# Stage34A — Parallel Fast-Path Repair / Intake Gate

Purpose: do not wait passively while Stage33E collects the next h13+h14 confirmation batch. Stage34A scans the existing Stage32C dense forward ledger for sibling groups, repaired subsets, and alternative fast-path families.

This stage is research-only:

```text
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
```

## Inputs

```text
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
```

## Outputs

```text
data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_parallel_fast_path_repair_intake.md
data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_summary.json
data/reports/stage34a_parallel_fast_path_repair_intake/candidate_set_diagnostics.csv
data/reports/stage34a_parallel_fast_path_repair_intake/parallel_acceleration_queue.csv
data/reports/stage34a_parallel_fast_path_repair_intake/repair_or_kill_queue.csv
data/reports/stage34a_parallel_fast_path_repair_intake/member_quality_summary.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage34a_parallel_fast_path_repair_intake
```

## Interpretation

- `PRECOMMERCIAL_REVIEW_CANDIDATE_RESEARCH_ONLY`: candidate set can go to a strict pre-paper research gate, still no execution.
- `SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY`: keep it alive only for short confirmation.
- `ACCELERATE_COLLECTION_RESEARCH_ONLY`: promising but not enough evidence.
- `REPAIR_OR_KILL_RESEARCH_ONLY`: do not wait; repair or kill.
