# Stage24C Remaining Behavior Discovery

Stage24C is a research/shadow-only discovery module. It does not modify Stage18A v2 or Stage23D and does not authorize EA, paper, live, or orders.

## Purpose

Stage24A and Stage24B did not produce promotion candidates. Stage24C moves to a fresh remaining-behavior cluster:

1. Previous-day expansion exhaustion reversal.
2. NY opening-range failed breakout reversal.
3. London midpoint-hold continuation.

## Runtime control

Environment variables:

```bash
STAGE24C_MAX_RUNTIME_SECONDS=180
STAGE24C_EXACT_RESERVED_SECONDS=45
STAGE24C_MAX_CANDIDATES_TOTAL=84
STAGE24C_MAX_EXACT=12
STAGE24C_MAX_EXACT_PER_FAMILY=4
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage24c_remaining_behavior_discovery
cat data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.md
```

Fast diagnostic run:

```bash
cd ~/Desktop/xauusd-trader
STAGE24C_MAX_RUNTIME_SECONDS=150 STAGE24C_EXACT_RESERVED_SECONDS=45 STAGE24C_MAX_CANDIDATES_TOTAL=60 STAGE24C_MAX_EXACT=9 python3 -m app.stage24c_remaining_behavior_discovery
cat data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.md
```
