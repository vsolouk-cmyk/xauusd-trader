# Stage 16B Shadow Signal Outcome Ledger

Stage 16B labels outcomes for Stage 16A research-only shadow signals.

## Purpose

Stage 16A scans a recent history window. Therefore, its signals are **recent-history shadow records**, not true-forward evidence.

Stage 16B:

```text
- reads stage16a_shadow_signals.csv
- uses M1 exact path
- enters theoretically at next M15 bar open
- exits after 60 minutes
- subtracts cost
- creates an outcome ledger
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage16b_shadow_signal_outcome_ledger
cat data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_signal_outcome_ledger.md
```

## Outputs

```text
data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_signal_outcome_ledger.md
data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_signal_outcome_ledger.json
data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_outcome_ledger.csv
data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_closed_recent_history_outcomes.csv
```

## Possible decisions

```text
RECENT_HISTORY_SHADOW_POSITIVE_NOT_FORWARD_PROOF
RECENT_HISTORY_SHADOW_WEAK_OR_NEGATIVE
TOO_FEW_POSITIVE_RECENT_SHADOW_OUTCOMES
TOO_FEW_NEGATIVE_RECENT_SHADOW_OUTCOMES
NO_CLOSED_SHADOW_OUTCOMES
```

## Hard rule

Research outcome ledger only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
