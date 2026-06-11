# Stage 16A Macro Pressure/Reversal Forward-Shadow Monitor

Stage 16A converts the validated research branch into a **research-only shadow monitor**.

It does not place orders and does not modify any EA.

## Research setup

```text
prev_day_low_sweep_rejection
LONG research direction
sweep_depth >= 1.62
reclaim_above_prev_day_low < 1.55
real_yield_10y_chg5 > 0
```

## Interpretation

This macro context is counterintuitive for classic gold macro logic.

Use this interpretation:

```text
rising real yield = pressure on gold
liquidity sweep + controlled reclaim = possible intraday reversal
```

Do **not** interpret it as:

```text
real yield up = bullish gold macro support
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage16a_macro_pressure_reversal_shadow_monitor
cat data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_macro_pressure_reversal_shadow_monitor.md
```

Scan a wider window:

```bash
python3 -m app.stage16a_macro_pressure_reversal_shadow_monitor --scan-days 120
```

## Outputs

```text
data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_macro_pressure_reversal_shadow_monitor.md
data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_macro_pressure_reversal_shadow_monitor.json
data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_shadow_signals.csv
data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_technical_candidates_before_macro.csv
```

## Hard rule

Research shadow only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
