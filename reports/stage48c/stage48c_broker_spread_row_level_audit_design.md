# Stage48C Broker Spread Row-Level Audit Design

## Purpose

Stage48C is a data-feasibility audit, not a trading scan.

Stage48B found:
- reference OHLC is ready,
- broker-real data is not yet confirmed,
- at least one SQLite schema candidate exists,
- some tables have numeric spread columns.

Therefore the only allowed next step is row-level spread audit.

## What this stage checks

- SQLite files under:
  - `data/local/xauusd_local_store.sqlite`
  - `data/store/xauusd.sqlite`
- Tables with timestamp + OHLC + numeric spread columns.
- Row-level filter for XAU-like symbols and requested timeframe.
- Numeric spread coverage.
- Spread distribution: median, p90, p95, p99.
- Coverage days and row count.
- Session spread summary if session column exists.

## What this stage does not do

- No signal generation.
- No baseline scan.
- No thesis tuning.
- No ML.
- No EA, paper-live, or live promotion.

## Decision logic

PASS only means broker spread data is usable enough for a later decision memo.

It does not mean any trading thesis is valid.

