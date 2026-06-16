# Stage33B — Pre-Commercial Family Robustness Gate

## Purpose

Stage33B is a research-only gate that validates Stage33A family-level acceleration candidates before any EA, paper-live, or order-routing work.

It exists because waiting for a single dense variant to reach 40 samples can take weeks. Stage33A allowed sibling variants to be reviewed as a family; Stage33B tests whether that family is actually robust enough to justify the next diagnostic stage.

## Inputs

- `data/reports/stage33a_dense_family_robustness_gate/pre_commercial_acceleration_queue.csv`
- `data/reports/stage33a_dense_family_robustness_gate/stage33a_summary.json`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv`

## Outputs

- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_pre_commercial_family_robustness_gate.md`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/family_robustness_diagnostics.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/member_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/hour_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/weekday_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/tail_batch_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/cost_sensitivity_summary.csv`

## Command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage33b_pre_commercial_family_robustness_gate
```

## Decision logic

A family must pass:

- enough deduplicated effective events,
- at least two good sibling members,
- acceptable family PF / win rate / tail PF,
- drawdown threshold,
- cost stress at `0.50 x4`.

Stage33B never authorizes EA, paper-live, or order routing. A passing family moves only to Stage33C strict cost-aware pre-paper diagnostics.

## Kill principle

If the family fails, do not wait weeks for single-variant `N=40`. Move to repair, intake expansion, or kill the family.
