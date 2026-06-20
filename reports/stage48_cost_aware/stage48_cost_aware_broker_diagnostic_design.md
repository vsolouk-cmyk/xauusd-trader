# Stage48 Cost-Aware Broker Diagnostic Design

## Purpose

This package continues Stage48 without creating a separate memo-only stage. It uses the Stage48F broker-real cost model and the AMarkets M5 MT5 export to run a frozen, cost-aware broker diagnostic.

This is not a promotion stage and does not authorize EA, paper-live, or live trading.

## Inputs

- Broker export: `~/Downloads/amarkets_xauusd_5m.csv`
- Cost model: `reports/stage48f/stage48f_cost_model.json`
- Timeframe: `M5`

## Frozen diagnostic

The diagnostic uses a small frozen liquidity-sweep reversal grid:

- lookback bars: `24,48,72`
- horizon bars: `12,24,48`
- sweep points: `10,20,30`

For each event:

- long if current low sweeps below the prior rolling low and closes back inside;
- short if current high sweeps above the prior rolling high and closes back inside;
- entry is current close;
- exit is close after the fixed horizon;
- broker-real costs are taken from the Stage48F cost model.

## Cost handling

The script reads:

- `recommended_cost_bps`
- `stress_cost_bps`
- `extreme_cost_bps`
- `selected_broker_time_offset_hours`

The offset is applied to the broker export timestamps before diagnostics.

## Decision rules

A diagnostic survivor requires all of the following:

- total trades >= 100
- OOS 2026 trades >= 30
- OOS stress mean net bps > 0
- OOS stress win rate >= 52%
- max year concentration <= 60%

Survivors do not authorize promotion. They only allow a hard audit. If no survivors exist, archive the diagnostic.
