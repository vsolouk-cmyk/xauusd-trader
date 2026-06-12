# Stage 7D Exit Geometry Lab

Stage 7D tests whether Stage 7B entries failed because of bad exit geometry rather than completely weak entry logic.

It uses candidate entries from Stage 7B and applies a small predefined set of TP/SL/horizon geometries.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage7d_exit_geometry_lab
cat data/reports/stage7d_exit_geometry_lab/stage7d_exit_geometry_lab.md
```

## Inputs

```text
data/local/xauusd_local_store.sqlite
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv
```

## Outputs

```text
data/reports/stage7d_exit_geometry_lab/stage7d_exit_geometry_lab.md
data/reports/stage7d_exit_geometry_lab/stage7d_exit_geometry_summaries.csv
data/reports/stage7d_exit_geometry_lab/stage7d_exit_geometry_trades.csv
data/reports/stage7d_exit_geometry_lab/stage7d_exit_geometry_lab.json
```

## Predefined geometries

```text
tp10_sl8_h3
tp12_sl8_h3
tp12_sl10_h6
tp15_sl10_h6
tp15_sl12_h6
tp18_sl12_h12
tp18_sl15_h12
tp24_sl15_h12_control
```

## Hard rule

Research only. No EA change, no demo, no paper, no live authorization.
