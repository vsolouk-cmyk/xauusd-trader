# Stage 17B PDH Breakout Continuation Exact Replay

Stage 17B validates the single Stage17A promoted candidate:

```text
pdh_breakout_continuation_long_h32_cool4
```

## Setup

```text
side = LONG
signal = M15 bar breaks above previous-day high and closes above PDH + 0.8
session = London or New York
entry = next M15 open
exit = 32 M15 bars later = 8 hours
cooldown = 4 M15 bars
source = AMarkets MT5 M1 exact path
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage17b_pdh_breakout_exact_replay
cat data/reports/stage17b_pdh_breakout_exact_replay/stage17b_pdh_breakout_exact_replay.md
```

## Checks

```text
- exact M1 time-exit replay
- cost x1/x2/x4
- chronological 70/30 and 80/20 splits
- 2026 segment
- year / quarter / session / hour breakdown
- bootstrap lower tail
- limited TP/SL geometry
```

## Possible decisions

```text
EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN
REJECT_EXACT_REPLAY_TOO_FEW_EVENTS
REJECT_EXACT_REPLAY_WEAK
COST_FRAGILE_EXACT_REPLAY
COST_X4_FRAGILE_EXACT_REPLAY
SPLIT_FRAGILE_EXACT_REPLAY
YEAR_FRAGILE_EXACT_REPLAY
CURRENT_2026_FRAGILE_EXACT_REPLAY
BOOTSTRAP_FRAGILE_EXACT_REPLAY
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
