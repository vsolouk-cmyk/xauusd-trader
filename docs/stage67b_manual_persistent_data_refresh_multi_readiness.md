# Stage67B Manual Persistent Data Refresh + Multi-Readiness Runner

Purpose: local-only refresh stage for XAUUSD macro readiness. Stage67B never downloads internet data. The operator manually places source files in `~/Downloads`; Stage67B persistently merges them into local canonical datasets, rebuilds the macro feature dataset, then runs Stage66J2 if new data was imported.

Key fixes versus Stage67:

- Parses AMarkets/MT5 CSV headers such as `<DATE>`, `<TIME>`, `<OPEN>`, `<HIGH>`, `<LOW>`, `<CLOSE>`, `<TICKVOL>`, `<VOL>`, `<SPREAD>`.
- Persistent merge/upsert by date; daily incremental files are appended, not used to overwrite history.
- Anti-truncation guard for canonical datasets.
- No GitHub workflow included because this stage depends on local Downloads and local datasets.

Expected manual files:

- `~/Downloads/amarkets_xauusd_5m.csv`
- `~/Downloads/dxy.csv`
- `~/Downloads/real_yield.csv`
- `~/Downloads/vix.csv`
- `~/Downloads/etf_flow.csv` optional / periodic
- `~/Downloads/central_bank_demand.csv` optional / periodic

Canonical outputs:

- `data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv`
- `data/exogenous/dxy.csv`
- `data/exogenous/real_yield.csv`
- `data/exogenous/vix.csv`
- `data/exogenous/etf_flow.csv`
- `data/exogenous/central_bank_demand.csv`
- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- `data/forward_shadow/stage67b_manual_persistent_data_refresh_ledger.csv`

Decision meanings:

- `STAGE67B_REFRESH_COMPLETE_STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER`: data refreshed and all readiness paths remain inactive.
- `STAGE67B_REFRESH_COMPLETE_STAGE66J2_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER`: a backup path became active; Stage66L is required before any dry-run ticket review.
- `STAGE67B_NO_NEW_MANUAL_DATA_IMPORTED_NO_FORWARD_READINESS_RUN`: no new manual data was detected; no forward readiness run was counted.
- `STAGE67B_STOP_INPUT_OR_REFRESH_FAILURE_NO_ORDER`: input or refresh failed.

Hard blocks remain: no automated order, no broker, no EA promotion, no paper-live, no live, no threshold tuning.
