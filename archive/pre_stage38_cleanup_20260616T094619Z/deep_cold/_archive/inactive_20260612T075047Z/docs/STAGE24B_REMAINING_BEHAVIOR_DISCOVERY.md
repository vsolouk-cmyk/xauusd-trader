# Stage24B Remaining Behavior Discovery

Stage24B is a research/shadow-only discovery module. It does not modify Stage18A v2 or Stage23D and does not authorize EA, paper, live, or orders.

## Purpose

Stage24A tested failed-breakout/fade/reclaim behavior and produced no promotion candidate. Stage24B moves to a different remaining-behavior cluster:

1. Previous-day compression / inside-range breakout continuation.
2. NY open impulse continuation after a London drive.
3. Asia-London directional alignment continuation.

## Runtime control

Environment variables:

```bash
STAGE24B_MAX_RUNTIME_SECONDS=180
STAGE24B_EXACT_RESERVED_SECONDS=45
STAGE24B_MAX_CANDIDATES_TOTAL=84
STAGE24B_MAX_EXACT=12
STAGE24B_MAX_EXACT_PER_FAMILY=4
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage24b_remaining_behavior_discovery
cat data/reports/stage24b_remaining_behavior_discovery/stage24b_remaining_behavior_discovery.md
```

Fast diagnostic run:

```bash
cd ~/Desktop/xauusd-trader
STAGE24B_MAX_RUNTIME_SECONDS=150 STAGE24B_EXACT_RESERVED_SECONDS=45 STAGE24B_MAX_CANDIDATES_TOTAL=60 STAGE24B_MAX_EXACT=9 python3 -m app.stage24b_remaining_behavior_discovery
cat data/reports/stage24b_remaining_behavior_discovery/stage24b_remaining_behavior_discovery.md
```
