# Stage24A Remaining Behavior Discovery

Research-only discovery branch for XAUUSD remaining behavior families.

## Purpose

Stage18A v2 remains the active operational forward-shadow runner, and Stage23D remains a separate one-candidate forward-shadow tracker. Stage24A continues discovery in parallel and does not promote any candidate operationally.

## Families

1. `asia_compression_failed_breakout_fade` — quiet Asia range followed by failed expansion/reclaim.
2. `london_compression_expansion_continuation` — London compression followed by NY expansion continuation.
3. `london_extreme_stoprun_reclaim` — NY stop-run/reclaim around London extremes.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage24a_remaining_behavior_discovery
cat data/reports/stage24a_remaining_behavior_discovery/stage24a_remaining_behavior_discovery.md
```

## Guardrails

- Research/shadow only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- Stage18A v2 and Stage23D are not modified.
