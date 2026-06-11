# Stage 20A London-to-NY Handoff Short Exact M1 Replay

Stage20A exact-replays the strongest London-to-NY handoff continuation SHORT variants from Stage19A watchlist.

## Behavior

```text
London bias = london_close - london_open
If London bias is negative enough,
then during New York session:
M15 close breaks below London low by buffer.
```

## Variants

```text
london_ny_handoff_continuation_short_bias2_h8
london_ny_handoff_continuation_short_bias3_h8
london_ny_handoff_continuation_short_bias2_h24
london_ny_handoff_continuation_short_bias1_h8
london_ny_handoff_continuation_short_bias2_h16
london_ny_handoff_continuation_short_bias3_h24
london_ny_handoff_continuation_short_bias1_h16
london_ny_handoff_continuation_short_bias1_h24
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage20a_london_ny_handoff_short_exact_replay
cat data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_london_ny_handoff_short_exact_replay.md
```

## Decisions

```text
HANDOFF_SHORT_PROMOTIONS_FOUND
HANDOFF_SHORT_WATCHLIST_ONLY
HANDOFF_SHORT_REJECTED
```

Per-variant:

```text
PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE
KEEP_EXACT_WATCHLIST_ONLY
REJECT_EXACT_WEAK
REJECT_TOO_FEW_EVENTS
```

## Important

Stage20A is exact historical validation, not forward proof.

Do not add watchlist-only variants to Stage18A.

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
