# Stage66H No-Broker Dry-Run Paper-Order Ticket Generator

## Purpose

Stage66H converts the Stage66G readiness design into a no-broker dry-run paper-order ticket workflow.

This stage is still non-executing. It does not connect to a broker, does not place a paper order, does not promote an EA, and does not authorize paper-live or live trading.

## Required input state

Stage66H requires:

- Stage66G decision: `CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER`
- Stage66G classification: `G_PASS_FAST_DESIGN_READY`
- Stage66G must still show no order authorization and no broker authorization
- Fresh macro dataset
- H64L v2 rule-lock
- A fresh H64L v2 active signal

If the current H64L v2 signal is not active, Stage66H must output:

```text
WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET
```

That is the expected result while the latest macro state remains inactive.

## H64L v2 conditions

```text
gold_sma20_over_50 > 0
dxy_ret_20d < 0
real_yield_change_20d < 0
etf_flow_tonnes_3m > 0
central_bank_demand_tonnes_3m > 0
gold_sma50_over_200 > 0
```

## Ticket behavior

When the signal becomes active, Stage66H writes:

```text
reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket.json
```

The ticket is a manual review artifact only. It contains:

- dry-run side: `BUY_XAUUSD_REFERENCE_ONLY`
- reference entry date and close from external D1 data
- fixed 120-trading-day horizon reference
- conservative notional fraction capped at 5%
- stop-after-first-adverse-move design guard
- non-execution guards proving no broker/order/live path is authorized

## Outputs

```text
reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket_generator_summary.json
reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket_generator_report.md
reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket.json
```

The ticket JSON exists only if the signal is active and all gates pass.

## Hard blocks

- `NO_AUTOMATED_ORDER`
- `NO_BROKER_CONNECTION`
- `NO_EA_PROMOTION`
- `NO_PAPER_LIVE`
- `NO_LIVE`
- `NO_ORDER_AUTHORIZATION_FROM_STAGE66H`
- `NO_THRESHOLD_TUNING`
- `NO_PROMOTION_FROM_DRY_RUN_TICKET_ONLY`

## Next stage

If Stage66H outputs `WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET`, keep Stage66H as a daily/no-order readiness check while also starting complementary thesis work if frequency remains too low.

If Stage66H outputs `DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER`, the next step is manual review plus a later explicit authorization package. Stage66H itself does not authorize any broker or paper order.
