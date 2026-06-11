# Stage26A DB-First Structured Behavior Discovery

Research/shadow-only discovery branch.

## Purpose

Stage26A continues discovery without repeating the broad Stage24-style entry grids. It uses a DB-first design and family-balanced exact replay.

## Guardrails

- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- No CSV fallback.
- Stage18A v2 remains the operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.

## Families

1. `htf_bias_pullback_continuation`
2. `breakout_pullback_continuation`
3. `session_transition_imbalance`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage26a_db_first_structured_behavior_discovery
cat data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_db_first_structured_behavior_discovery.md
```

## Fast diagnostic run

```bash
cd ~/Desktop/xauusd-trader
STAGE26A_MAX_RUNTIME_SECONDS=150 STAGE26A_EXACT_RESERVED_SECONDS=45 STAGE26A_MAX_CANDIDATES_TOTAL=54 STAGE26A_MAX_EXACT=9 python3 -m app.stage26a_db_first_structured_behavior_discovery
cat data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_db_first_structured_behavior_discovery.md
```
