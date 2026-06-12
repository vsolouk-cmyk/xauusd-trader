# Stage 7A Strategy Thesis Lab from SQLite

Stage 7A stops pure filter-mining and tests a small number of thesis-driven XAUUSD strategy families.

## Strategy families

1. `baseline_sma_distance_v1_control`
2. `trend_pullback_continuation`
3. `asia_range_breakout`
4. `volatility_compression_breakout`
5. `range_mean_reversion`

Each family is evaluated twice:

- `unguarded`
- `macro_blocked`

## Macro/event guard

By default, Stage 7A reads this file if it exists:

```text
data/config/macro_events.csv
```

Required columns:

```text
event_time_utc,label,impact,guard_before_min,guard_after_min,mode
```

Example:

```csv
event_time_utc,label,impact,guard_before_min,guard_after_min,mode
2026-06-10T12:30:00Z,US CPI,high,120,240,block
2026-06-17T18:00:00Z,FOMC,high,180,360,block
```

You can also add geopolitical shock windows from CLI:

```bash
python3 -m app.stage7a_strategy_thesis_lab \
  --shock-window 2026-06-08T00:00:00Z,2026-06-10T23:59:00Z,iran_israel_shock
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage7a_strategy_thesis_lab
cat data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_thesis_lab.md
```

## Run with shock window

```bash
python3 -m app.stage7a_strategy_thesis_lab \
  --shock-window 2026-06-08T00:00:00Z,2026-06-10T23:59:00Z,iran_israel_shock

cat data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_thesis_lab.md
```

## Outputs

```text
data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_thesis_lab.md
data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_summaries.csv
data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_trades.csv
data/reports/stage7a_strategy_thesis_lab/stage7a_strategy_thesis_lab.json
```

## Important

- Research only.
- No EA modification.
- No order authorization.
- `PROMISING_RESEARCH_ONLY` means candidate for deeper validation, not tradable.
- `KILL_*` means do not keep tuning filters around that version.
