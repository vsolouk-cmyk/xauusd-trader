# Stage70C K06 No-Order Shadow Candidate

## Purpose

Stage70C integrates the Stage70B-promoted champion `K06_RESILIENT_GOLD_VS_DXY` into a daily no-order shadow monitor. It evaluates only the latest macro row and appends an observation to a forward-shadow ledger.

## Locked champion

- Thesis: `K06_RESILIENT_GOLD_VS_DXY`
- Family: `GOLD_RESILIENCE_AGAINST_DXY`
- Direction: long
- Horizon: 120 trading days
- Conditions:
  - `gold_sma20_over_50 > 0`
  - `dxy_ret_20d > 0`
  - `real_yield_change_20d < 0`

## Scope

This stage is deliberately narrow:

- It does not run another megascan.
- It does not audit backlog items.
- It does not tune thresholds.
- It does not connect to a broker.
- It does not generate EA, paper-live, or live orders.

## Daily operating sequence

After refreshing the macro dataset:

1. Run Stage67D6.
2. Run Stage67E.
3. Run Stage68F as the old-policy daily monitor.
4. Run Stage70C as the K06 champion daily monitor.

## Decision outcomes

- `STAGE70C_K06_SHADOW_WAIT_SIGNAL_NO_ORDER`: K06 is inactive; keep observing.
- `STAGE70C_K06_SHADOW_SIGNAL_ACTIVE_REVIEW_ONLY_NO_ORDER`: K06 is active; manual review only.
- `STAGE70C_INPUT_OR_DATA_ISSUE_STOP_NO_ORDER`: input or schema issue; no review action.

## Backlog policy

Backlog remains registered but cannot interrupt K06 until K06 is closed, killed, parked with reason, or graduated by a separate governance decision.
