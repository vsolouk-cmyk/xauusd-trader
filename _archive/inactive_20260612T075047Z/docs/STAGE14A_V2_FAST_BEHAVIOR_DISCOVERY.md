# Stage 14A v2 Fast Liquidity / Session / Sweep Behavior Discovery

v2 fixes the slow first version.

## What changed

```text
1. Per-day session slices are cached.
2. The script avoids repeated index.strftime filtering inside loops.
3. Progress messages are printed.
4. --max-days is available for quick smoke tests.
```

## Stop old slow run

```text
Control + C
```

## Quick smoke test

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage14a_liquidity_session_behavior_discovery --max-days 120
cat data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.md
```

## Full run

```bash
python3 -m app.stage14a_liquidity_session_behavior_discovery
cat data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.md
```

## Critical interpretation rule

If this stage fails, the conclusion is not:

```text
XAUUSD has no behavior.
```

The correct conclusion is:

```text
These tested hypotheses did not capture a tradable behavior.
```

## Hard rule

Research only. No EA change, no automatic trading, no paper/live authorization.
