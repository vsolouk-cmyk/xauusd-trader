# Stage175B — Dual-Source Parity Repair

## Executive purpose

Stage175 correctly kept H64L closed, but its T1 parity check compared the archived Stage38A metrics with trades regenerated from the latest AMarkets CSV. That is not a valid engine-parity test because Stage38A was produced from the archived SQLite `bars` table.

Stage175B is an integration repair:

1. rebuild archived parity from the exact archived SQLite H1 bars and macro table;
2. compare regenerated parity trades with the archived Stage38A ledger when available;
3. infer the current CSV timestamp shift through OHLC fingerprinting against the archived broker bars;
4. evaluate the final 20% holdout only after source alignment.

No strategy parameter, threshold, variant, direction, target, stop or holding period is changed.

## Hard controls

```text
orders/demo/paper/live = forbidden
ML = forbidden
broad scan = forbidden
threshold reoptimization = forbidden
H64L signal path = closed
```

## Why the repair is necessary

The original Stage38A test read:

```text
data/local/xauusd_local_store.sqlite::bars
source = amarkets_mt5
symbol = XAUUSD
timeframe = 1h
```

Stage175 instead rebuilt parity from the current Downloads CSV. A current broker export can include a different start date, corrected historical bars or a different server-time representation. Therefore a metric difference cannot be attributed to engine logic until the exact archived input is replayed.

## Source contracts

### Archived parity source

```text
archive/_archive_stage64a_freeze_20260624_125930/data/local/xauusd_local_store.sqlite
```

Required tables:

```text
bars
macro_daily_regime
```

### Current refresh source

```text
~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv
```

The current CSV is accepted only if one integer-hour shift in `[-5,+5]` gives a unique OHLC match to the archived broker series.

Default alignment gates:

```text
overlap rows >= 10000
OHLC match share >= 98%
best shift lead over runner-up >= 2 percentage points
OHLC tolerance <= 0.011 price units
```

Failure is blocking and must not be bypassed by manually choosing a convenient shift.

## Parity gates

Metric parity remains:

```text
trades = 94 ± 1
PF = 1.7004909028 ± 0.03
avg R = 0.2597330945 ± 0.01
net R = 24.41491088 ± 0.75
max DD = 7.13049755 ± 0.50
```

When the archived ledger exists, trade-level parity is also required:

```text
Jaccard >= 0.98
missing regenerated trades <= 1
extra regenerated trades <= 1
max common-trade R difference <= 0.000001
```

## Final T1 gates

Only after parity and source alignment pass:

```text
holdout trades >= 30
PF >= 1.10
avg R > 0
max DD <= 8R
largest positive month share <= 55%
largest positive year share <= 70%
positive months >= 3
locked filter PF > raw comparator PF
locked filter avg R > raw comparator avg R
```

Possible decisions:

```text
SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER
KILL_T1_COMMERCIAL_LOW_HOLDOUT_FREQUENCY_NO_WAIT
KILL_T1_LOCKED_HOLDOUT_FAILURE_NO_ML
INCONCLUSIVE_BLOCKED_DUAL_SOURCE_PARITY_REPAIR_FAILED
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m unittest   tests/test_stage175b_dual_source_parity_repair.py

python3 app/stage175b_dual_source_parity_repair.py   --root ~/Desktop/xauusd-trader   --config configs/stage175b_dual_source_parity_repair.json
```

## Outputs

```text
reports/stage175b_dual_source_parity_repair/stage175b_summary.json
reports/stage175b_dual_source_parity_repair/stage175b_decision.md
reports/stage175b_dual_source_parity_repair/stage175b_source_alignment_scores.csv
reports/stage175b_dual_source_parity_repair/stage175b_archived_parity_trade_diff.csv
reports/stage175b_dual_source_parity_repair/stage175b_archived_engine_parity_trades.csv
reports/stage175b_dual_source_parity_repair/stage175b_t1_locked_trades.csv
reports/stage175b_dual_source_parity_repair/stage175b_t1_period_metrics.csv
reports/stage175b_dual_source_parity_repair/stage175b_t1_gate_checks.csv
```

## Specialist-report trigger

Do not send another intermediate report. Send the consolidated specialist package immediately after Stage175B produces one of these two valid terminal T1 decisions:

```text
SHADOW_CANDIDATE_LOG_ONLY_NO_ORDER
KILL_T1_LOCKED_HOLDOUT_FAILURE_NO_ML
```

A blocked parity/alignment result is still an engineering blocker and is not suitable for external strategy review.
