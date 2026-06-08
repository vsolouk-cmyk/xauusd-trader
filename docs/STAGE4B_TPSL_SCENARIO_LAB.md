# Stage 4B TP/SL and Side-Filter Scenario Lab

## Purpose

Stage 4A showed that the original both-side time-exit candidate is only moderately positive under M1 execution replay.

Stage 4B tests a limited set of side and TP/SL scenarios.

## What it tests

- long-only
- short-only
- both-side
- no TP / no SL baseline
- limited TP values
- limited SL values

## Conservative intrabar rule

If TP and SL are both touched inside the same M1 candle, Stage 4B assumes SL first.

This avoids optimistic intrabar assumptions.

## Local command

```bash
python3 -m app.xauusd_stage4b_tpsl_scenario_lab
```

## Outputs

```text
data/reports/stage4b_tpsl_scenario_summary_*.json
data/reports/stage4b_tpsl_scenario_summary_*.md
data/reports/stage4b_tpsl_scenarios_*.csv
data/reports/stage4b_best_scenario_trades_*.csv
```

## Hard rule

Stage 4B is diagnostic only.

It does not finalize TP/SL and does not authorize demo, paper-order, or live trading.
