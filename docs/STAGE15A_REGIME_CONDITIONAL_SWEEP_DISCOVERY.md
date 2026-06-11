# Stage 15A Regime-Conditional Liquidity Sweep Discovery

Stage 15A diagnoses why the Stage 14D filtered sweep branch worked in some years and failed in 2026.

It does **not** rescue the filter with another broad search. It asks:

```text
Can a pre-trade observable regime condition explain the 2026 failure?
```

## Branch

```text
prev_day_low_sweep_rejection
LONG
horizon_bars = 4
sweep_depth_ge_q50
```

## Conditions checked

```text
- year cohorts, diagnostic only
- session
- sweep depth zone
- speed of reclaim
- reclaim strength
- wick/rejection quality
- ATR percentile regime
- prior-day range
- prior-day midpoint context
- H4 context
- limited explicit interactions
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage15a_regime_conditional_sweep_discovery
cat data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_regime_conditional_sweep_discovery.md
```

## Possible decisions

```text
REGIME_CONDITION_CANDIDATE_FOUND
CURRENT_REGIME_FAILURE_NOT_EXPLAINED
WEAK_REGIME_IMPROVEMENT_ONLY
NO_REGIME_CONDITION_FOUND
RETROSPECTIVE_ONLY_NOT_TRADABLE
INCONCLUSIVE_NO_REGIME_RESULTS
```

## Hard rule

Research only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
