# Stage23B — Continuation / No-Trade-Regime Discovery

Research-only discovery branch after Stage23A exact rejection.

## Purpose

Stage23A tested fade/reversal behavior after one-way London / Asia-London expansion / previous-day extreme conditions. Exact M1 diagnostic rejected the available candidates. Stage23B therefore tests the mirror hypothesis: when fade fails, continuation or a no-trade filter may be the useful information.

## Guardrails

- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- No watchlist-only candidates are added to Stage18A.

## Families

1. `london_oneway_continuation`
2. `asia_london_breakout_continuation`
3. `prev_day_extreme_breakout_continuation`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23b_continuation_no_trade_discovery
cat data/reports/stage23b_continuation_no_trade_discovery/stage23b_continuation_no_trade_discovery.md
```

## Fast diagnostic run

```bash
cd ~/Desktop/xauusd-trader
STAGE23B_MAX_RUNTIME_SECONDS=150 STAGE23B_EXACT_RESERVED_SECONDS=45 STAGE23B_MAX_CANDIDATES_TOTAL=54 STAGE23B_MAX_EXACT=9 python3 -m app.stage23b_continuation_no_trade_discovery
cat data/reports/stage23b_continuation_no_trade_discovery/stage23b_continuation_no_trade_discovery.md
```
