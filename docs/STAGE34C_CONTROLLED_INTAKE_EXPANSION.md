# Stage34C — Controlled Intake Expansion Plan

## Purpose

Stage34C prevents passive waiting while Stage33E collects the next h13+h14 confirmation events. It converts Stage34B queues into a targeted expansion plan for the next candidate-generation stage.

This is not general discovery. It is a controlled repair/intake planner with explicit kill-switches.

## Inputs

- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_summary.json`
- `data/reports/stage34b_parallel_repair_filter_lab/parallel_acceleration_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/short_confirmation_repair_filter_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/repair_or_kill_queue.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json`

## Outputs

- `data/reports/stage34c_controlled_intake_expansion/stage34c_controlled_intake_expansion.md`
- `data/reports/stage34c_controlled_intake_expansion/stage34c_summary.json`
- `data/reports/stage34c_controlled_intake_expansion/controlled_intake_plan.csv`
- `data/reports/stage34c_controlled_intake_expansion/repair_or_kill_enforced_queue.csv`
- `data/reports/stage34c_controlled_intake_expansion/background_collection_queue.csv`

## Rules

- No EA change.
- No paper-live.
- No order authorization.
- Do not wait for single-variant N=40 by default.
- Do not open broad discovery unless controlled intake fails.
- Keep Stage33E as background confirmation only.
