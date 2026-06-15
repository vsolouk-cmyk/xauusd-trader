# Stage34B — Parallel Repair / Filter Lab

Purpose: avoid passive waiting during Stage33E short confirmation by testing repaired subsets, inversion candidates, and alternative dense-family filters from the existing Stage32C forward ledger.

This stage is research-only.

It never authorizes:

```text
EA changes
paper-live
orders
commercial transition
```

## Inputs

```text
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_summary.json
data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json
```

## Outputs

```text
data/reports/stage34b_parallel_repair_filter_lab/stage34b_parallel_repair_filter_lab.md
data/reports/stage34b_parallel_repair_filter_lab/stage34b_summary.json
data/reports/stage34b_parallel_repair_filter_lab/repair_filter_candidate_diagnostics.csv
data/reports/stage34b_parallel_repair_filter_lab/precommercial_repair_filter_queue.csv
data/reports/stage34b_parallel_repair_filter_lab/short_confirmation_repair_filter_queue.csv
data/reports/stage34b_parallel_repair_filter_lab/parallel_acceleration_queue.csv
data/reports/stage34b_parallel_repair_filter_lab/repair_or_kill_queue.csv
data/reports/stage34b_parallel_repair_filter_lab/stage34b_action_plan.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage34b_parallel_repair_filter_lab
```

## Interpretation

If a pre-commercial repair-filter row appears, run a strict pre-paper gate on that repaired filter only.

If only short-confirmation rows appear, keep Stage33E active and avoid promotion.

If only acceleration rows appear, keep them as low-cost background collection and move to controlled intake expansion.

If everything is repair/kill, stop waiting and return to controlled intake expansion.
