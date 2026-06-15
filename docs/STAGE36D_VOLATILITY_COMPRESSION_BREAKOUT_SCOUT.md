# Stage36D — Volatility Compression Breakout Scout

Purpose: start the third Stage36 thesis branch while Stage35C continues in the background.

This branch tests whether XAUUSD has a usable edge after low-range/ATR compression when price either breaks out of the prior range or expands from compression.

This is research-only:

- no EA change
- no paper-live
- no order authorization

## Inputs

- `data/local/xauusd_local_store.sqlite`
- OHLC table auto-detected, normally `bars`
- H1 bars resampled/selected from local AMarkets history
- Stage36C summary is read only for context

## Tested concepts

- compression q20/q30 using rolling 250-bar range quantiles
- breakout follow/fade after compressed state
- range expansion follow/fade after compressed state
- horizons 4h, 8h, and selected 12h expansion variants
- strict cost-stressed metrics

## Outputs

- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_volatility_compression_breakout_scout.md`
- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_summary.json`
- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_candidate_summary.csv`
- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_strict_review_queue.csv`
- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_background_queue.csv`
- `data/reports/stage36d_volatility_compression_breakout_scout/stage36d_kill_or_repair_queue.csv`

## Decision logic

- strict review candidate: enough events and passes PF, avg, WR, tail, recent, cost stress, and drawdown gates
- background only: positive but not strict enough
- kill/repair: weak or unstable branch; do not wait for N40 by default
