# XAUUSD Project Transfer Pack — Stage65 Forward Shadow Active

Generated: 2026-06-25

## Standing response/process rules
- Start each project response with: `چپ‌چین ادامه می‌دهم.`
- Persian, left-aligned/plain markdown; no HTML/RTL wrappers.
- Code blocks only for terminal commands, exact paths, raw logs.
- Always include a clear `گام بعدی` in operational replies.
- Repo path: `/Users/vahid/Desktop/xauusd-trader`
- Downloads path: `~/Downloads`
- Use `python3`; no `gh`; no Homebrew.
- For patches: provide zip + docs, `mv` from Downloads, unzip to `_incoming...`, move files, remove `_incoming...`, then safe git commands.
- No order, broker connection, paper-live/live, EA promotion unless later explicitly authorized by passed governance gates.

## Current strategic state
- Intraday/candidate-first research is frozen/archived.
- Stage58B remains passive telemetry/reference only.
- Main path: Stage64 macro-regime daily/weekly gold thesis.
- The locked survivor is:
  - `H64L_H1_FULL_MACRO_TAILWIND_LONG`
  - horizon: `120` trading days
  - benchmark: external/spot B1 trend-only reference
- Historical event-calendar filtering is forbidden; event calendar may only be used forward-only as future annotation/blackout governance after later gates.

## Key validation history
- Stage64M: full-scope walk-forward found corrected survivor H1/h120.
- Stage64N1/N1B: corrected robustness and A2 reconciliation passed.
- Stage64N4: independent replication matched expected metrics.
- Stage64O/P: AMarkets-derived broker/reference alignment failed; broker-specific execution claim blocked.
- Stage64Q: AMarkets broker transfer was statistically positive but failed concentration gates; not enough for broker claim.
- Stage64R: external spot D1 transfer passed all declared gates using Investing-normalized D1 data.
- Stage64S: governance confirmed research survivor and allowed Stage65 forward-shadow design only; no order path.

## Stage64R external transfer headline
- joined_return_days: 3578
- candidate_active_days: 336
- candidate_mean_bps: 1059.5781768455959
- external_B1_active_days: 1296
- external_B1_mean_bps: 672.7337370199871
- mean_excess_vs_external_B1_bps: 386.8444398256088
- one_sided_p_uncorrected_z_approx: 7.937411793850522e-07
- positive_excess_splits_vs_external_B1: 3
- max_split_share_of_candidate_active_days: 0.3898809523809524
- max_year_share_of_candidate_active_days: 0.2916666666666667

## Stage65 current status
Stage65 forward-shadow signal ledger is active.

Latest Stage65 run:
- status: `FORWARD_SHADOW_SIGNAL_LEDGER_FASTLANE_COMPLETE_NO_PROMOTION`
- decision: `STAGE65_FORWARD_LEDGER_ACTIVE_CONTINUE_DAILY_NO_ORDER`
- latest_feature_date: `2026-06-24`
- signal_active: `False`
- benchmark_active: `False`
- signal_row_appended: `True`
- observation_row_appended: `False`
- observations_matured_this_run: `0`
- signal_ledger_rows: `1`
- observation_ledger_rows: `0`
- forward_governance_ready: `False`

Latest rule failures:
- `gold_sma20_over_50` was not > 0
- `dxy_ret_20d` was not < 0
- `real_yield_change_20d` was not < 0
- `etf_flow_tonnes_3m` was not > 0

Forward governance minimums:
- observed_new_signals_min: 5
- calendar_span_min_days: 180
- asof_lag_safe must remain true
- no manual override/backfill

## Important files
- Stage64K dataset:
  - `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- External spot D1:
  - `data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv`
- Stage65 app/config:
  - `app/stage65_forward_shadow_signal_ledger_fastlane.py`
  - `configs/stage65_forward_shadow_signal_ledger_fastlane.json`
- Stage65 ledgers:
  - `data/forward_shadow/stage65_macro_signal_ledger.csv`
  - `data/forward_shadow/stage65_observation_ledger.csv`
  - `data/forward_shadow/stage65_forward_shadow_state.json`
- Stage65 reports:
  - `reports/stage65_forward_shadow_signal_ledger_fastlane/stage65_forward_shadow_signal_ledger_summary.json`
  - `reports/stage65_forward_shadow_signal_ledger_fastlane/stage65_forward_shadow_signal_ledger_report.md`

## Daily run command
Run only after the dataset and external D1 file are refreshed/confirmed current:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage65_forward_shadow_signal_ledger_fastlane.py \
  --root . \
  --config configs/stage65_forward_shadow_signal_ledger_fastlane.json \
  --out reports/stage65_forward_shadow_signal_ledger_fastlane
```

## Current hard blocks
- `NO_PAPER_ORDER`
- `NO_EA_PROMOTION`
- `NO_PAPER_LIVE`
- `NO_LIVE`
- `NO_BROKER_CONNECTION`
- `NO_ORDER_AUTHORIZATION_FROM_STAGE65`
- `NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE`
- `NO_POST_HOC_EVENT_EXCLUSION`
- `NO_REDUCED_SCOPE_RETEST`
- `NO_RESCUE_FILTERING`
- `NO_NEW_INTRADAY_SCAN`
- `NO_THRESHOLD_TUNING`
- `NO_COMMERCIALIZATION_WITHOUT_LATER_FORWARD_AND_BROKER_GOVERNANCE`

## Next step in new session
Continue from Stage65 forward-shadow daily ledger. First check whether data-refresh pipeline exists for Stage64K/external D1. If not, create a single operational Stage65B/Stage66 fastlane package that refreshes/validates the latest macro + external spot D1 data and then runs Stage65, without order/broker connection.
