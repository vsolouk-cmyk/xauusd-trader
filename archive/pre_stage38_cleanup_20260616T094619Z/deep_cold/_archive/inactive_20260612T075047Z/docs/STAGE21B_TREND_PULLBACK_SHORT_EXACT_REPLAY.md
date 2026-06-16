# Stage 21B Trend Pullback Continuation Short Exact M1 Replay

Stage21A promoted one M15-proxy candidate:

```text
trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8
```

Stage21B validates it with exact M1 path replay.

## Candidate

```text
family: trend_pullback_continuation_short
side: SHORT

H1 trend filter:
  sma20_slope5 < 0
  h1_close_minus_sma20 <= -5.0

M15 pullback/rejection:
  high >= ema20_m15 - 0.5
  close < ema20_m15

session:
  New York only

entry:
  next M15 open

exit:
  time exit after 8 M15 bars = 120 minutes

cooldown:
  4 M15 bars
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage21b_trend_pullback_short_exact_replay
cat data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_trend_pullback_short_exact_replay.md
```

## Decisions

```text
EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN
EXACT_REPLAY_KEEP_WATCHLIST_ONLY
EXACT_REPLAY_REJECT_WEAK
EXACT_REPLAY_REJECT_TOO_FEW_EVENTS
```

## Important

Stage21B is exact historical validation, not forward proof.

Do not add this candidate to Stage18A unless the final decision is:

```text
EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
