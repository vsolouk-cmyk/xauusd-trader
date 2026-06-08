# XAUUSD Stage Pipeline Runner

This runner executes the allowed research/dry-run validation modules in a reproducible order.

Hard rule:

- It does not authorize demo, paper, or live orders.
- It does not modify MT5 EA files.
- It does not send orders.
- It only runs local validation/research tools.

## Modes

### Full pipeline

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage_pipeline_runner --mode full
cat data/reports/stage_pipeline/stage_pipeline_summary.md
```

Runs:

1. Stage 4G AMarkets non-overlap replay, offset +2.
2. Stage 4G AMarkets non-overlap replay, offset +3.
3. Stage 4H session guard lab, offset +2.
4. Stage 4H session guard lab, offset +3.
5. Stage 4I guard robustness comparator.
6. Stage 4J shock/regime sensitivity lab.
7. Stage 5B live dry-run signal CSV validator.
8. Stage 5C live dry-run outcome tracker.

### Live-only quick check

Use after MT5 has logged new signals or after refreshing the M1 export:

```bash
python3 -m app.stage_pipeline_runner --mode live_only
cat data/reports/stage_pipeline/stage_pipeline_summary.md
```

Runs only Stage 5B and Stage 5C.

### Research-only refresh

Use after refreshing AMarkets H1/M1 exports:

```bash
python3 -m app.stage_pipeline_runner --mode research
cat data/reports/stage_pipeline/stage_pipeline_summary.md
```

## Default inputs

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv
```

## Important workflow

- Keep MT5 EA running for dry-run logging.
- When new signals appear, run `--mode live_only`.
- After the 12-hour horizon of the latest signal, export fresh AMarkets M1 and run `--mode live_only` again to resolve outcomes.
- When the broker export changes materially, run `--mode full`.

No demo/paper/live authorization.
