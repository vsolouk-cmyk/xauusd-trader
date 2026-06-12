# Stage 19B Compression Expansion Breakout Exact M1 Replay

Stage19A promoted one M15-proxy candidate:

```text
compression_expansion_breakout_long_comp0.75_h8
```

Stage19B validates it with exact M1 path replay.

## Candidate

```text
family: compression_expansion_breakout_long
side: LONG
condition:
  H1 compression6 <= 0.75
  session = London or New York
  M15 close > prior rolling 16-bar local high
entry: next M15 open
exit: time exit after 8 M15 bars = 120 minutes
cooldown: 4 M15 bars
cost: 0.35 USD default
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage19b_compression_breakout_exact_replay
cat data/reports/stage19b_compression_breakout_exact_replay/stage19b_compression_breakout_exact_replay.md
```

## Decisions

```text
EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN
EXACT_REPLAY_KEEP_WATCHLIST_ONLY
EXACT_REPLAY_REJECT_WEAK
EXACT_REPLAY_REJECT_TOO_FEW_EVENTS
```

Stage19B is exact historical validation, not forward proof.

Do not add this candidate to Stage18A unless the final decision is:

```text
EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN
```

Hard rule: no EA change, no automatic trading, no paper/live authorization.
