# Stage141 Demo Execution Outcome Ledger

Stage141 records the first completed demo execution outcome into a durable ledger.

It reads:
- Stage134 demo executor summary
- Stage138 discovery summary
- Stage140 closed deal outcome summary

It writes:
- `data/demo_execution/stage141_demo_execution_outcome_ledger.csv`
- `reports/stage141_demo_execution_outcome_ledger/stage141_demo_execution_outcome_ledger_summary.json`
- `reports/stage141_demo_execution_outcome_ledger/stage141_latest_demo_execution_outcome.csv`

Stage141 does not send orders and does not modify positions.

The ledger uses this duplicate key:
- `signal_key`
- `entry_deal_ticket`
- `exit_deal_ticket`

Operational use:
- If outcome is profit, continue demo loop on the next distinct signal.
- If outcome is loss, continue collecting but review if losses cluster.
- Do not duplicate the same already-closed signal.
