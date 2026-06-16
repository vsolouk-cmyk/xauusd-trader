# Stage 8D Forward Shadow v2

Stage 8D starts live forward-shadow logging for the first robust regime-driven candidate.

## Candidate

```text
strategy_id = xauusd_h4_up_compression_liquidity_long_v1
definition = liquidity_session
execution basis = nonoverlap
exit model = time_exit_12h_with_emergency_stop
emergency_stop_usd = 30
direction = long only
```

## Why this candidate

Stage 8C passed this candidate under non-overlap execution with emergency stop 30:

```text
liquidity_session / nonoverlap / time_exit_12h / emergency_stop_30
Total x4 = 1090.16
Total x6 = 906.76
PF x4 = 1.862694
Median x4 = 1.96
DD x1 = -155.76
Positive years = 4/5
Positive quarters = 13/17
Worst month = -58.98
```

## Hard rule

This is still forward-shadow only.

No demo, no paper, no live, no order sending.

## EA file

```text
mql5/Experts/XAUUSD/XAUUSD_DryRun_v2_RegimeShadow.mq5
```

Copy it into MT5 Experts/Advisors/XAUUSD, compile it, and attach it to XAUUSD chart.

It writes this Common Files CSV:

```text
XAUUSD_DryRun_v2_regime_shadow_signals.csv
```

## EA logic

A dry-run signal is logged only when all are true:

```text
H4 close > EMA20 > EMA50
H4 EMA20 slope over 5 H4 bars > 0
H1 range16 percentile over prior 240 H1 bars > 0.50 and <= 0.80
planned entry UTC session is london_ny_overlap or new_york
```

Exit model for outcome tracking:

```text
entry = next H1 open after signal close
exit = emergency stop 30 USD OR time exit after 12 hours
```

## Outcome tracker

Run after exporting/refreshing latest M1 data into local SQLite:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage8d_forward_shadow_outcome_tracker
cat data/reports/stage8d_forward_shadow_outcomes/stage8d_forward_shadow_outcomes.md
```

## Important

- The EA contains no order code.
- The tracker contains no order code.
- This is not paper-order.
- This is not demo-order.
- This is not live.
