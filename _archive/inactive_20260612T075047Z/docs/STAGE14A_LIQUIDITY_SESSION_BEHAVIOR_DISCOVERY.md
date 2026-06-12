# Stage 14A Liquidity / Session / Sweep Behavior Discovery

Stage 14A changes the direction from classic indicator testing to behavioral market-mechanism discovery.

It tests five hypotheses:

```text
1. Asia range sweep during London
2. London range sweep during New York
3. Previous-day high/low sweep and rejection
4. News/event first-spike failure/reversal
5. Failed breakout/reclaim around prior H4 levels
```

## Critical interpretation rule

If this stage fails, the conclusion is **not**:

```text
XAUUSD has no behavior.
```

The correct conclusion is:

```text
These tested hypotheses did not capture a tradable behavior.
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage14a_liquidity_session_behavior_discovery
cat data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.md
```

Optional fixed sweep buffer:

```bash
python3 -m app.stage14a_liquidity_session_behavior_discovery --buffer-usd 0.5
```

## Outputs

```text
data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.md
data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.json
data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_events.csv
data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_outcomes.csv
data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_summary.csv
```

## Hard rule

Research only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
