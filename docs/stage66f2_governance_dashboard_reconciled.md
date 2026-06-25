# Stage66F2 Governance Dashboard Reconciled

## Purpose

Stage66F2 fixes a wiring problem in the original Stage66F dashboard: after Stage66A3 writes the exact reconstructed H64L v2 rule-lock and Stage66A is rerun with the reconciled config, the dashboard must read the reconciled Stage66A output, not the legacy Stage66A output.

This is not a new strategy, not a threshold change, and not promotion. It is a dashboard input-path correction.

## Expected input

- Stage66 data integrity crosscheck: PASS
- Stage66A3 exact rule-lock resolver: exact match written
- Stage66A rerun with `configs/stage66a_h64l_concentration_audit_reconciled_v2.json`
- Stage66B rolling-origin replay already available

## Expected decision when A and B pass

If reconciled Stage66A class is `A_PASS_FAST` and Stage66B class is `B_PASS_FAST`, the dashboard decision becomes:

`PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2`

This only unlocks Stage66C paper-execution simulator design. It does not authorize any order, broker connection, EA promotion, paper-live, or live trading.

## Hard blocks

- NO_PAPER_ORDER
- NO_EA_PROMOTION
- NO_PAPER_LIVE
- NO_LIVE
- NO_BROKER_CONNECTION
- NO_ORDER_AUTHORIZATION_FROM_STAGE66
- NO_THRESHOLD_TUNING
- NO_PROMOTION_FROM_DASHBOARD_ONLY
