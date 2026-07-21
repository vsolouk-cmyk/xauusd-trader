# Stage179 — Selected Candidate Commercial Audit

## Purpose

Stage178 promoted `logistic__direction_24h` to controlled paper design. Stage179
performs the final bounded audit needed before enabling a parallel shadow
ledger. It is not another broad research stage.

It checks:

- exact parity with the Stage178 selected holdout ledger;
- cost stress through 10 bps;
- moving-block bootstrap uncertainty;
- same-timestamp always-long comparison;
- full-holdout always-long comparison;
- long/short decomposition;
- month/year/session concentration;
- drawdown cap.

## Decisions

- `AUTHORIZE_PARALLEL_CONTROLLED_SHADOW_PAPER`
- `RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_DIAGNOSTIC`
- `KILL_STAGE178_SELECTED_CANDIDATE`

A PASS authorizes only a shadow signal ledger. It does not authorize broker,
demo, or live orders.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage179_selected_candidate_commercial_audit.py
```

## Outputs

```text
reports/stage179_selected_candidate_commercial_audit/stage179_summary.json
reports/stage179_selected_candidate_commercial_audit/stage179_decision.md
reports/stage179_selected_candidate_commercial_audit/stage179_cost_stress.csv
reports/stage179_selected_candidate_commercial_audit/stage179_direction_metrics.csv
reports/stage179_selected_candidate_commercial_audit/stage179_bootstrap.json
reports/stage179_selected_candidate_commercial_audit/stage179_shadow_paper_contract.json
reports/stage179_selected_candidate_commercial_audit/stage179_reconciled_holdout_trades.csv
```
