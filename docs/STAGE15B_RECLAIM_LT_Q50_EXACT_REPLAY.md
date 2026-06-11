# Stage 15B Reclaim-lt-q50 Exact Replay

Stage 15B validates the single Stage 15A candidate:

```text
setup = prev_day_low_sweep_rejection
side = LONG
branch = sweep_depth_ge_q50
regime = reclaim_lt_q50
horizon = 60 minutes
```

## Why

Stage 15A found a pre-trade regime condition:

```text
reclaim_lt_q50
```

But it must be validated with M1 path replay before any further system design.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage15b_reclaim_lt_q50_exact_replay
cat data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_reclaim_lt_q50_exact_replay.md
```

## What it checks

```text
- M1 exact time-exit replay
- cost x1/x2/x4
- chronological splits
- year distribution
- current 2026 segment
- bootstrap
- limited TP/SL geometry
```

## Possible decisions

```text
EXACT_REPLAY_VALIDATED_RESEARCH_CANDIDATE
EXACT_REPLAY_CANDIDATE_BUT_CURRENT_REGIME_FRAGILE
REJECT_TOO_FEW_EXACT_REPLAY_EVENTS
REJECT_TIME_EXIT_EXACT_REPLAY_WEAK
SPLIT_FRAGILE_EXACT_REPLAY
YEAR_FRAGILE_EXACT_REPLAY
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
