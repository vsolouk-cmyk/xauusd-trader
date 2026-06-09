# Stage 7C Edge Diagnostics Lab

Stage 7C diagnoses why Stage 7B strategy families failed.

It separates:

- weak entry thesis
- poor stop/target geometry
- target too far
- exit design weakness

## Key concepts

- MFE = Maximum Favorable Excursion: how far price moved in our favor after entry.
- MAE = Maximum Adverse Excursion: how far price moved against us after entry.
- First-hit test = whether TP or SL would be hit first for a symmetric threshold.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage7c_edge_diagnostics_lab
cat data/reports/stage7c_edge_diagnostics_lab/stage7c_edge_diagnostics_lab.md
```

## Inputs

Default trades CSV:

```text
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv
```

Default DB:

```text
data/local/xauusd_local_store.sqlite
```

## Outputs

```text
data/reports/stage7c_edge_diagnostics_lab/stage7c_edge_diagnostics_lab.md
data/reports/stage7c_edge_diagnostics_lab/stage7c_edge_summaries.csv
data/reports/stage7c_edge_diagnostics_lab/stage7c_trade_diagnostics.csv
data/reports/stage7c_edge_diagnostics_lab/stage7c_edge_diagnostics_lab.json
```

## Hard rule

Research only. No EA change, no demo, no paper, no live authorization.
