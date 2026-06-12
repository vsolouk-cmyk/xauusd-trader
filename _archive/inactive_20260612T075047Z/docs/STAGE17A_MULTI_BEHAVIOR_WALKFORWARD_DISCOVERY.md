# Stage 17A Multi-Behavior Walk-Forward Discovery

Stage 17A expands research beyond a single validated setup.

## Principle

A successful behavior should enter forward-shadow collection, but it should not stop discovery.

Pipeline from here:

```text
Track A: keep validated behaviors in true-forward shadow collection
Track B: keep discovering and validating new behavior families
```

## Behavior families tested

```text
- previous-day low sweep reclaim long
- previous-day high sweep rejection short
- previous-day breakout continuation
- previous-day breakdown continuation
- Asia range breakout
- Asia range fakeout/reversal
- compressed range breakout
- H4 trend SMA reclaim/rejection
```

## Validation logic

Each behavior variant is tested with:

```text
- non-overlap spacing
- 4/8/16/32 M15-bar horizons
- cooldown 0/4
- cost x1/x2/x4
- chronological 80/20 split
- chronological 70/30 split
- 2026 segment
- frequency per month
- year breadth
```

## Decisions

```text
PROMOTE_STAGE17B_EXACT_REPLAY
WATCHLIST_ONLY
REJECT
REJECT_TOO_FEW_EVENTS
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage17a_multi_behavior_walkforward_discovery
cat data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_multi_behavior_walkforward_discovery.md
```

For quick debug only:

```bash
python3 -m app.stage17a_multi_behavior_walkforward_discovery --max-rows 20000
```

## Outputs

```text
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_multi_behavior_walkforward_discovery.md
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_multi_behavior_walkforward_discovery.json
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_behavior_summary.csv
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_promoted_candidates.csv
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_all_behavior_trades.csv
data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_year_breakdown.csv
```

## Hard rule

Research discovery only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
