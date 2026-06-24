# Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT

## Purpose

Stage45 showed that recent candle-only thesis scans do not produce a robust shortlist under observed or realistic cost assumptions. Stage45C audits the broker/feed and transaction-cost realism before any further scan.

This stage is diagnostic-only:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Inputs

Default repo assumptions:

```text
DB: data/local/xauusd_local_store.sqlite
Table: bars
Source: amarkets_mt5
Symbol: XAUUSD
Default timeframes: M15,H1,M5
```

The script uses DB-first schema introspection and supports common aliases:

```text
time column: utc_time / timestamp / time / source_time
spread column: spread / spread_points / mt5_spread
OHLC: open, high, low, close
source/symbol/timeframe filters: case-insensitive and alias-aware
```

## What it measures

For each timeframe, Stage45C reports:

- loaded row count and date range
- timestamp gap profile
- spread-column availability
- spread conversion candidates
- selected spread mode
- spread bps profile: median, p90, p95, p99
- session/hour/weekday/quarter spread profile
- bar range bps profile
- median spread to median bar range ratio
- estimated total cost under extra slippage scenarios

## Why this stage is needed

Stage45 found:

```text
observed_costs_current_strict pass_count = 0
realistic_cost_improvement_plus4 pass_count = 0
aggressive_cost_improvement_plus8 pass_count = 0
very_low_cost_plus16_diagnostic_only pass_count = 4
```

So the next question is whether the broker/feed/spread/slippage environment itself is making otherwise weak edges impossible, or whether the project needs external context/reference data before scanning more candle-only theses.

## Outputs

```text
reports/stage45c/stage45c_feed_transaction_cost_realism_audit_summary.json
reports/stage45c/stage45c_feed_transaction_cost_realism_audit.md
reports/stage45c/stage45c_spread_by_group.csv
reports/stage45c/stage45c_estimated_cost_scenarios.csv
```

## Interpretation rules

Stage45C cannot rescue Stage41/42/43 candidates. It can only choose the next evidence-based direction:

```text
Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION
Stage45C2_BROKER_COST_REDUCTION_OR_FEED_COMPARISON
Stage45C2_COLLECT_BID_ASK_OR_REPAIR_SPREAD_DATA
```

## Anti-overfit rule

Do not remove bad spread/session/hour/quarter buckets after seeing this report to revive archived rows. Any future thesis must be predefined before testing.
