# Stage66K Complementary Backup Readiness Expansion

Stage66K expands daily readiness beyond the primary H64L v2 thesis and the selected D3 H60 complementary thesis.

It locks and monitors the two remaining Stage66D `PASS_FAST` backup candidates:

- `D1_DXY_REALYIELD_GOLD_TREND_SHORT_HORIZON_LONG_H60`
- `D4_VOL_RISK_OFF_REALYIELD_GOLD_LONG_H60`

This stage is not a broad scan. It does not register new variants and does not tune thresholds. It only uses Stage66D pass-fast candidates that were already found in the limited, pre-registered scan.

## Decisions

- `STAGE66K_BACKUP_RULE_LOCKS_READY_WAIT_SIGNALS_NO_ORDER`
  - Both backup rules are audit-ready, but neither has an active latest signal.
- `STAGE66K_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER`
  - At least one backup signal is active. Build Stage66L no-broker dry-run ticket generator for the active backup rule.
- `STAGE66K_BACKUP_AUDIT_NOT_READY_NO_ORDER`
  - At least one configured backup failed the locked audit gates.
- `STAGE66K_STOP_INPUT_OR_DATA_ISSUE_NO_ORDER`
  - Required input files, gates, or data freshness are invalid.

## Hard blocks

Stage66K never authorizes:

- automated order
- paper order
- broker connection
- EA promotion
- paper-live
- live
- threshold tuning
- rescue filtering

Any dry-run ticket for active backup signals must be handled by a later Stage66L package.
