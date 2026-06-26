# Stage66G Controlled Paper-Order Readiness Design

Stage66G is a design-only readiness gate after Stage66C. It does not place orders, connect to a broker, promote an EA, or authorize paper-live/live trading.

## Purpose

Stage66C established that the reconciled H64L v2 rule survived position-level simulation with a conservative cost/feed penalty. Stage66G converts that evidence into a controlled paper-order readiness design.

The output is a readiness checklist and sizing band. The output is not an order instruction.

## Main logic

Stage66G requires:

- Stage66C decision: `PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER`
- closed positions at or above the configured minimum
- win rate at or above the configured threshold
- mean net return above the configured threshold
- stress-cost mean still positive enough
- base-band drawdown below the configured ceiling
- no catastrophic single trade loss
- no excessive year concentration

If these pass, the output is:

`CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER`

## Sizing design

Even when Band B passes, initial future paper-order readiness starts conservatively:

- initial design fraction: `B_conservative = 5%`
- maximum design fraction before new forward evidence: `B_base = 10%`
- no automated order
- no broker connection
- fresh H64L v2 signal required before any future authorization

## Required later step

If Stage66G passes, the next package should be Stage66H:

`no-broker paper-order dry-run ticket generator`

Stage66H should generate a reviewable dry-run ticket only. It must still not send any broker order.
