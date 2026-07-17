# Stage175 — H64L Closeout and Exact Locked T1 Holdout Refresh

## Why this stage exists

Stage174 closes the H64L rescue. The next candidate is not a new high-sweep thesis: Stage38A already tested the family and locked one formulation. Stage175 therefore runs exactly one formulation and first verifies that the rebuilt engine reproduces the archived 94-trade result.

## Locked formulation

```text
side = LONG
entry = V1_CLOSE_ACCEPTANCE
level = previous UTC-day high
target = 1.5R
time stop = 5 H1 bars
D1 MA = 50 completed daily bars
H4 MA = 50 completed H4 bars
macro = supportive OR archived neutral/non-hostile rule
sweep distance >= 0.10 ATR(H1,14)
signal range <= 2.0 ATR
stop = signal low - 0.10 ATR
stop distance = 0.50 to 2.50 ATR
cost = p90 spread, 49 points × 0.01
locked filter:
  D1 distance above MA50 >= 5%
  H4 distance above MA50 >= 2%
  ATR(H1,14) / entry price >= 0.30%
```

No alternative entry, level, target, time stop, threshold, direction, or cost is evaluated.

## Parity gate

Before the new holdout is interpreted, the implementation must reproduce the archived result through 2026-06-16:

```text
trades = 94
PF = 1.7004909028
avg R = 0.2597330945
net R = 24.41491088
max drawdown = 7.13049755R
```

A parity failure is an integration/reproduction failure, not a negative strategy result.

## Final 20% holdout gates

```text
holdout trades >= 30
p90 cost-stressed PF >= 1.10
avg R > 0
max drawdown <= 8R
max positive-month contribution share <= 55%
max positive-year contribution share <= 70%
at least 3 positive months
locked filter must beat the exact raw comparator on PF and avg R
```

Possible decisions:

```text
SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER
KILL_T1_COMMERCIAL_LOW_HOLDOUT_FREQUENCY_NO_WAIT
KILL_T1_LOCKED_HOLDOUT_FAILURE_NO_ML
INCONCLUSIVE_BLOCKED_ARCHIVED_ENGINE_PARITY_FAILED
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest \
  tests/test_stage175_h64l_closeout_and_t1_locked_holdout_refresh.py

python3 app/stage175_h64l_closeout_and_t1_locked_holdout_refresh.py \
  --root ~/Desktop/xauusd-trader \
  --config configs/stage175_h64l_closeout_and_t1_locked_holdout_refresh.json
```

## Outputs

```text
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_summary.json
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_decision.md
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_h64l_closeout.json
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_t1_locked_trades.csv
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_t1_raw_comparator_trades.csv
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_t1_period_metrics.csv
reports/stage175_h64l_closeout_and_t1_locked_holdout_refresh/stage175_t1_gate_checks.csv
```

## Hard controls

- No orders, demo, paper, or live.
- No ML.
- No variant grid.
- No new COT scan.
- No forward waiting as substitute for holdout evidence.
