# Stage 21A Trend Pullback and Exhaustion Lite Discovery

Stage21A continues discovery after Stage20A produced watchlist-only results.

It uses fast M15 proxy replay and explores behavior families that are not simply another version of the current active candidates.

## Families

```text
1. H1 trend pullback continuation long/short
2. M15 impulse exhaustion reversal long/short
3. NY open continuation after London trend
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage21a_trend_pullback_lite_discovery
cat data/reports/stage21a_trend_pullback_lite_discovery/stage21a_trend_pullback_lite_discovery.md
```

For a faster debug run:

```bash
python3 -m app.stage21a_trend_pullback_lite_discovery --fast
```

## Decisions

```text
TREND_PULLBACK_CANDIDATES_FOR_EXACT_REPLAY
TREND_PULLBACK_WATCHLIST_ONLY
NO_TREND_PULLBACK_CANDIDATES
```

Per-variant:

```text
PROMOTE_STAGE21B_EXACT_REPLAY
KEEP_LITE_WATCHLIST
REJECT_LITE_WEAK
```

## Important

Stage21A is M15 proxy discovery only.

Do not add Stage21A candidates to Stage18A directly. Promoted candidates must pass Stage21B exact M1 replay first.

## Hard rule

Research discovery only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
