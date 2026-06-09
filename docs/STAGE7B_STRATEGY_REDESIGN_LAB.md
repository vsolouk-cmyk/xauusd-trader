# Stage 7B Strategy Redesign Lab

Stage 7B is a thesis-redesign lab, not a filter-mining lab.

It tests a small set of predefined strategy designs using the local SQLite store:

1. `h4_trend_h1_pullback_continuation`
2. `asia_range_breakout_retest`
3. `compression_expansion_confirmed`
4. `regime_reversal_after_failed_break`
5. `baseline_sma_distance_v1_control`

Each design is tested as:

- `unguarded`
- `macro_blocked`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage7b_strategy_redesign_lab
cat data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_redesign_lab.md
```

## Run with current shock window

```bash
python3 -m app.stage7b_strategy_redesign_lab \
  --shock-window 2026-06-08T00:00:00Z,2026-06-10T23:59:00Z,iran_israel_shock

cat data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_redesign_lab.md
```

## Outputs

```text
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_redesign_lab.md
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_summaries.csv
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv
data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_redesign_lab.json
```

## Decision labels

- `PROMISING_FOR_STAGE7C_RESEARCH_ONLY`: deeper validation candidate only.
- `WATCHLIST_REDESIGN_NEEDED`: not dead, but not robust enough.
- `KILL_*`: do not rescue by adding filters.

## Hard rule

No EA change, no demo, no paper, no live authorization from this report.
