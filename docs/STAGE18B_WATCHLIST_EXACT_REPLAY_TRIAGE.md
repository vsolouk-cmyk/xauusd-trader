# Stage 18B Watchlist Exact M1 Replay Triage

Stage 18B continues discovery while Stage18A keeps active shadow candidates running.

It exact-replays the Stage17A watchlist candidates using AMarkets M1 path.

## Why

Stage17A found:

```text
1 promoted candidate
12 watchlist candidates
```

The promoted candidate already became Stage17B/17D.  
Stage18B tests the watchlist candidates more strictly before any forward-shadow design.

## Candidates tested

```text
asia_high_breakout_long_h32_cool0
asia_high_breakout_long_h32_cool4
pdl_sweep_reclaim_long_controlled_h4_cool0
pdl_sweep_reclaim_long_controlled_h4_cool4
pdl_sweep_reclaim_long_controlled_h8_cool0
pdl_sweep_reclaim_long_controlled_h8_cool4
asia_low_breakdown_short_h32_cool0
asia_low_breakdown_short_h32_cool4
pdl_breakdown_continuation_short_h32_cool0
compressed_range_up_break_long_h8_cool0
compressed_range_up_break_long_h8_cool4
pdh_breakout_continuation_long_h32_cool0
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18b_watchlist_exact_replay_triage
cat data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_replay_triage.md
```

## Checks

```text
- exact M1 path replay
- cost x1/x2/x4
- 70/30 and 80/20 chronological splits
- 2026 segment
- year/quarter breadth
- bootstrap lower tail
```

## Decisions

```text
EXACT_WATCHLIST_PROMOTIONS_FOUND
EXACT_WATCHLIST_POSITIVE_ONLY
NO_WATCHLIST_SURVIVED_EXACT_REPLAY
```

Per-candidate decisions:

```text
PROMOTE_STAGE18C_FORWARD_SHADOW_DESIGN
KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE
REJECT_EXACT_REPLAY_WEAK
REJECT_TOO_FEW_EXACT_EVENTS
```

## Hard rule

Research triage only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
