# Stage72 Historical Daily Replay

Stage72 replaces unnecessary waiting for real future data with a historical daily replay.

It treats every historical row in the configured replay window as a daily refresh snapshot. K06 is evaluated using only same-row lag-safe features. No future row can trigger a signal. Future prices are used only after the 120-trading-day horizon has matured, exactly as a real forward ledger would be scored after time passes.

## Purpose

- Prove operational daily-refresh behavior from existing historical data.
- Avoid making real forward data the primary statistical proof mechanism.
- Keep real forward only for pipeline, latency, and source-freshness sanity.
- Keep K06 on the mainline without opening a new thesis search.

## Default replay window

- Replay starts on 2019-01-01.
- 2019-2022 behaves like locked historical forward.
- 2023 onward behaves like final statistical holdout.

## K06 rule

`gold_sma20_over_50 > 0 ; dxy_ret_20d > 0 ; real_yield_change_20d < 0`

Horizon: 120 trading days.

Cooldown: 120 trading days.

Cost reference: 50 bps.

## Outputs

- `stage72_historical_daily_replay_summary.json`
- `stage72_historical_daily_replay_report.md`
- `stage72_k06_historical_daily_ledger.csv`
- `stage72_k06_activation_events.csv`
- `stage72_k06_matured_outcomes.csv`
- `stage72_k06_monthly_replay_metrics.csv`
- `stage72_historical_replay_audit.csv`

## Hard blocks

Stage72 is no-order only. It cannot authorize broker connection, paper orders, EA promotion, paper-live, or live trading.
