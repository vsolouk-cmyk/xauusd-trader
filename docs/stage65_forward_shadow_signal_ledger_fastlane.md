# Stage65 - Forward Shadow Signal Ledger Fastlane (No Order)

This stage starts the prospective daily signal ledger for the locked Stage64 survivor:

- `H64L_H1_FULL_MACRO_TAILWIND_LONG`
- horizon: 120 trading days
- benchmark: external spot trend-only reference

It does not generate orders. It does not connect to a broker. It does not authorize paper-live or live trading.

## Purpose

Stage64S confirmed external spot D1 transfer as a research survivor and allowed only no-order forward-shadow design. Stage65 converts that decision into an append-only operational ledger.

## Behavior

The runner:

1. verifies Stage64S decision;
2. reads the Stage64K lag-safe macro feature dataset;
3. reads the external spot D1 reference;
4. evaluates the locked H1 rule only on the latest feature row;
5. appends one daily signal-state row if that feature date is not already recorded;
6. creates a pending 120-trading-day observation entry only when the signal is active;
7. updates matured observations if the external spot file later contains enough forward data;
8. writes a report and summary.

## Forbidden

- no order generation
- no broker connection
- no EA promotion
- no paper-live
- no live trading
- no historical event-calendar filtering
- no post-hoc exclusion
- no threshold tuning
- no rescue filter
- no new hypothesis scan

## Forward governance minimums

The stage tracks the suggested minimums from Stage64S, but it does not promote the strategy:

- at least 5 new prospective signals;
- at least 180 calendar days of forward ledger time;
- all rows must remain as-of lag-safe;
- no manual override backfill.

Even if these minimums are reached later, broker-specific execution governance is still required before paper or live.
