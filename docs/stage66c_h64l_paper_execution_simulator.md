# Stage66C H64L v2 Paper-Execution Simulator

Generated: 2026-06-25

## Purpose

Stage66C is the first position-level execution-realism layer after Stage66F2 opened the paper-simulation gate.

It is not a broker, order, EA, paper-live, or live-trading path. It is a no-order simulator that converts the reconciled H64L v2 daily macro signal into non-overlapping, close-to-close paper positions with pre-locked execution penalties and sizing bands.

## Why this stage exists

Stage66A and Stage66B showed that H64L v2 survived concentration audit and rolling-origin replay. Those stages still evaluated event returns, not actual position sequencing. Stage66C asks a more operational question:

```text
If we had one non-overlapping H64L v2 position at a time,
entered only after the sample was available,
paid conservative feed/execution penalties,
and held for the locked 120-trading-day horizon,
would the position-level equity behavior still justify moving to controlled paper-order design?
```

## Locked assumptions

```text
entry_rule = first_external_d1_close_on_or_after_sample_available_after_utc
entry_delay_trading_days = 0
holding_period_trading_days = 120
position_mode = single_position_non_overlapping
round_trip_execution_cost_bps = 35
feed_mismatch_penalty_bps = 15
default_total_penalty_bps = 50
stress_total_penalty_bps = [0, 50, 100, 200, 350]
```

These assumptions must not be tuned after seeing results.

## Sizing bands

Sizing is simulated only as equity exposure. It does not authorize orders.

```text
B_conservative = 5% notional exposure
B_base = 10% notional exposure
B_upper_paper_only = 20% notional exposure
```

## Decision rules

`PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER` requires:

```text
closed_positions >= 8
win_rate >= 55%
mean_net_return_bps >= 300
B_base max drawdown <= 8%
mean net return under 100 bps stress >= 200 bps
single worst trade not worse than -2200 bps
```

A pass does not authorize broker connection, EA promotion, paper-live, live, or any order. It only authorizes building the next controlled paper-order design package.

## Hard blocks

```text
NO_PAPER_ORDER
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_BROKER_CONNECTION
NO_ORDER_AUTHORIZATION_FROM_STAGE66C
NO_THRESHOLD_TUNING
NO_PROMOTION_FROM_SIMULATOR_ONLY
```

## Outputs

```text
reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_summary.json
reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_report.md
reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_positions.csv
```
