# Stage144B Demo Execution Ledger Reconciliation Hotfix

Stage144B replaces the Stage144 reconciliation logic without adding any execution behavior.

It fixes two operational blockers observed after Stage146C:

1. `TIME_EXIT` rows in the Stage134 trade log are close-management events, not new entry attempts.
2. Some MT5 exit deals have blank magic/comment, but still share the same `position_id` as the Stage134 entry deal. These must be paired as closed outcomes.

Stage144B remains read-only:

- no order send
- no position modification
- no account changes

Expected effect on the latest run:

- no open position should remain when MT5 Toolbox shows no open XAUUSD position
- successful buy attempts should be counted from `DEMO_BUY_ATTEMPT` rows only
- latest `2026-07-02T20:00:00Z|D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65` should be matched to the exit deal at `2026-07-02T23:14:17Z` with profit `11.17`
