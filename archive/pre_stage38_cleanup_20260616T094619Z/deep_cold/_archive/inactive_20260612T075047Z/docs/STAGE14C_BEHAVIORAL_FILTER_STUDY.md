# Stage 14C Behavioral Filter Study

Stage 14C tries to rescue the cost-fragile Stage 14B candidate using behavior-based filters only.

Candidate:

```text
prev_day_low_sweep_rejection
LONG
horizon_bars = 4
```

## Filters tested

Small, behavior-based set:

```text
1. Session of reclaim
2. Sweep depth
3. Reclaim strength
4. Lower-wick rejection quality
5. Speed of reclaim
6. ATR/volatility regime
7. Previous-day midpoint context
8. H4 context
9. A few explicit logical combinations
```

This is not a classic indicator grid.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage14c_behavioral_filter_study
cat data/reports/stage14c_behavioral_filter_study/stage14c_behavioral_filter_study.md
```

Optional sensitivity:

```bash
python3 -m app.stage14c_behavioral_filter_study --cost-usd 0.25
python3 -m app.stage14c_behavioral_filter_study --cost-usd 0.50
python3 -m app.stage14c_behavioral_filter_study --min-events 120
```

## Decisions

```text
FILTER_CANDIDATE_FOUND
WEAK_FILTER_IMPROVEMENT_ONLY
NO_FILTER_IMPROVEMENT
INCONCLUSIVE_NO_FILTER_RESULTS
```

## Hard rule

Research only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
