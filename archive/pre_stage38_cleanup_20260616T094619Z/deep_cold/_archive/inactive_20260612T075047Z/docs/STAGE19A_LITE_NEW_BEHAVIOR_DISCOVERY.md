# Stage 19A Lite New Behavior Discovery

Stage19A continues discovery without repeating slow Stage18C-style exhaustive grids.

It uses a fast M15 proxy replay first, then promotes only promising candidates to a later Stage19B exact M1 replay.

## Families tested

```text
1. PDH sweep rejection short
2. Asia fakeout reversal long/short
3. London-to-New-York handoff continuation/reversal
4. Compression expansion breakout long/short
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage19a_lite_new_behavior_discovery
cat data/reports/stage19a_lite_new_behavior_discovery/stage19a_lite_new_behavior_discovery.md
```

For a faster debug run:

```bash
python3 -m app.stage19a_lite_new_behavior_discovery --fast
```

## Decisions

```text
NEW_BEHAVIOR_CANDIDATES_FOR_EXACT_REPLAY
LITE_DISCOVERY_WATCHLIST_ONLY
NO_NEW_BEHAVIOR_CANDIDATES
```

Per-variant:

```text
PROMOTE_STAGE19B_EXACT_REPLAY
KEEP_LITE_WATCHLIST
REJECT_LITE_WEAK
```

## Important

Stage19A is not exact execution replay.

Do not add Stage19A candidates to Stage18A directly. Promoted candidates must pass Stage19B exact M1 replay first.

## Hard rule

Research discovery only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
