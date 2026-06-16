# Stage 4A MT5 M1/H1 Execution Replay

## Purpose

Replay the fixed H1 candidate using MT5 M1 path data.

This stage moves from simple close-to-close validation toward execution-realistic diagnostics.

## What it does

- Reads H1 bars from MT5 SQLite.
- Reads M1 bars from the same MT5 SQLite.
- Detects the fixed H1 candidate.
- Enters at the next H1 open using the first M1 bar at/after that time.
- Exits after 12 H1 candles using M1 close near the target exit time.
- Computes MAE and MFE for each trade.

## Key definitions

- MAE: maximum adverse excursion, the worst movement against the trade before exit.
- MFE: maximum favorable excursion, the best movement in favor of the trade before exit.
- Execution replay: replaying entries/exits with lower-timeframe path data.

## Import M1 from MT5

If the exported file is:

```text
~/Downloads/xauusd_1m_mt5.csv
```

Run:

```bash
python3 -m app.xauusd_second_source_import \
  --csv ~/Downloads/xauusd_1m_mt5.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1min \
  --provider mt5
```

Then run:

```bash
python3 -m app.xauusd_stage4a_execution_replay
```

## Important

Stage 4A does not finalize TP/SL.

It only measures MAE/MFE so TP/SL can be designed from evidence instead of guessing.
