# Stage 15D Macro Context Robustness

Stage 15D validates the top Stage 15C macro context:

```text
macro_daily_regime_real_yield_10y_chg5_up
```

## Why this is needed

The result is statistically strong but economically counterintuitive:

```text
real yield up
```

is normally not a bullish gold macro condition. It may instead represent a pressure/reversal environment where gold is sold under yield pressure, sweeps liquidity, and then mean-reverts intraday.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage15d_macro_context_robustness
cat data/reports/stage15d_macro_context_robustness/stage15d_macro_context_robustness.md
```

Optional manual context:

```bash
python3 -m app.stage15d_macro_context_robustness --top-context macro_daily_regime_real_yield_10y_chg5_up
```

## Checks

```text
- selected macro direction vs opposite direction
- split stability
- year distribution
- bootstrap lower tail
- sample size
- counterintuitive macro interpretation warning
```

## Possible decisions

```text
MACRO_CONTEXT_ROBUST_BUT_COUNTERINTUITIVE
MACRO_CONTEXT_ROBUST_FOR_FORWARD_SHADOW_RESEARCH
MACRO_CONTEXT_SAMPLE_TOO_SMALL
MACRO_CONTEXT_NOT_ROBUST
MACRO_CONTEXT_DIRECTION_NOT_DISTINCT
MACRO_CONTEXT_SPLIT_FRAGILE
MACRO_CONTEXT_YEAR_FRAGILE
MACRO_CONTEXT_BOOTSTRAP_FRAGILE
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
