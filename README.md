# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 4A: MT5 M1/H1 execution replay for the fixed XAUUSD candidate.

No ML. No trading bot. No paper order. No live order.

## Fixed candidate

```text
sma10_h12_dist10_cool1
```

## Required MT5 imports

H1:

```bash
python3 -m app.xauusd_second_source_import \
  --csv ~/Downloads/xauusd_1h_mt5.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1h \
  --provider mt5
```

M1:

```bash
python3 -m app.xauusd_second_source_import \
  --csv ~/Downloads/xauusd_1m_mt5.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1min \
  --provider mt5
```

## Local Stage 4A

```bash
python3 -m app.xauusd_stage4a_execution_replay
```

## GitHub workflow

```text
XAUUSD Stage 4A Execution Replay
```

## Hard rule

Stage 4A is diagnostic only.

It does not authorize demo, paper-order, or live trading.
