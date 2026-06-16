# Stage31D Exogenous Candidate Confirmation

Generated UTC: `2026-06-13T22:47:56.808421+00:00`

## Decision

```text
STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow confirmation only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage31A enriched dataset and Stage31C audit outputs only.
- Gate thresholds are recalibrated with expanding prior-year data only.
- Event-level deduplication is applied to reduce artifact duplication risk.

## Inputs

```json
{
  "stage31a_dataset": {
    "path": "/Users/vahid/Desktop/xauusd-trader/data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv",
    "exists": true,
    "loaded": true,
    "rows_raw": 17124,
    "columns": [
      "event_key",
      "entry_ts_norm",
      "source_stage",
      "source_file",
      "family",
      "candidate_name",
      "net_x1",
      "net_x4",
      "net_x6",
      "label_win_x4",
      "label_win_x6",
      "label_strong_win_x4",
      "label_bad_loss_x4",
      "sample_weight_abs_net_x4",
      "prior_day_range",
      "asia_range",
      "asia_eff",
      "london_range",
      "london_eff",
      "h1_range",
      "h1_atr20",
      "h1_atr20_pct_rank_250",
      "direction_num",
      "prior_day_aligned",
      "london_aligned",
      "entry_hour",
      "dow",
      "month",
      "year",
      "dxy_asof_ts",
      "dxy_value",
      "dxy_ret_1",
      "dxy_ret_5",
      "dxy_chg_1",
      "dxy_chg_5",
      "dxy_z60",
      "dxy_rank250",
      "dxy_age_hours",
      "us10y_asof_ts",
      "us10y_value",
      "us10y_ret_1",
      "us10y_ret_5",
      "us10y_chg_1",
      "us10y_chg_5",
      "us10y_z60",
      "us10y_rank250",
      "us10y_age_hours",
      "real_yield_asof_ts",
      "real_yield_value",
      "real_yield_ret_1",
      "real_yield_ret_5",
      "real_yield_chg_1",
      "real_yield_chg_5",
      "real_yield_z60",
      "real_yield_rank250",
      "real_yield_age_hours",
      "vix_asof_ts",
      "vix_value",
      "vix_ret_1",
      "vix_ret_5",
      "vix_chg_1",
      "vix_chg_5",
      "vix_z60",
      "vix_rank250",
      "vix_age_hours",
      "spx_asof_ts",
      "spx_value",
      "spx_ret_1",
      "spx_ret_5",
      "spx_chg_1",
      "spx_chg_5",
      "spx_z60",
      "spx_rank250",
      "spx_age_hours",
      "oil_asof_ts",
      "oil_value",
      "oil_ret_1",
      "oil_ret_5",
      "oil_chg_1",
      "oil_chg_5",
      "oil_z60",
      "oil_rank250",
      "oil_age_hours",
      "macro_event_within_2h",
      "macro_event_within_6h",
      "macro_event_within_24h"
    ],
    "rows_after_parse": 17124
  },
  "stage31c_candidates": {
    "candidate_path": "/Users/vahid/Desktop/xauusd-trader/data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv",
    "candidate_exists": true,
    "audit_path": "/Users/vahid/Desktop/xauusd-trader/data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.csv",
    "audit_exists": true,
    "loaded": true,
    "used_path": "/Users/vahid/Desktop/xauusd-trader/data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv",
    "rows_raw": 120,
    "columns": [
      "source",
      "scope_type",
      "scope_value",
      "macro_feature",
      "macro_gate",
      "macro_side",
      "macro_q",
      "overlay_name",
      "overlay_features_json",
      "scope_rows",
      "stage31b_decision",
      "stage31b_wf_pf_x4",
      "stage31b_wf_total_x4",
      "wf_events",
      "wf_pf_x1",
      "wf_pf_x4",
      "wf_pf_x6",
      "wf_total_x1",
      "wf_total_x4",
      "wf_total_x6",
      "win_rate_x4",
      "median_x4",
      "boot_p05_total_x4",
      "years_positive_x4",
      "years_tested",
      "decision",
      "rank_score"
    ],
    "rows_after_filter": 40
  }
}
```

## Counts

- dataset_rows: `17124`
- stage31c_gate_defs_loaded: `40`
- confirmation_results: `40`
- confirmed_candidate_count: `10`
- fragile_confirmation_count: `20`
- rejected_count: `10`
- year_diagnostic_rows: `160`

## Candidate review

| decision                                               | scope_type     | scope_value                            | macro_feature      | macro_gate                | overlay_name         |   confirmed_events |   confirmed_pf_x4 |   confirmed_pf_x6 |   confirmed_total_x4 |   boot_p05_total_x4 |   stress_0.20_total_x4 |   years_positive_x4 |   years_tested |   rank_score |
|:-------------------------------------------------------|:---------------|:---------------------------------------|:-------------------|:--------------------------|:---------------------|-------------------:|------------------:|------------------:|---------------------:|--------------------:|-----------------------:|--------------------:|---------------:|-------------:|
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |                 50 |          22.7856  |          16.6791  |             209.221  |            143.886  |               199.221  |                   4 |              4 |     248.666  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |                 50 |          22.7856  |          16.6791  |             209.221  |            142.654  |               199.221  |                   4 |              4 |     248.358  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |                 56 |          23.3726  |          13.8378  |             159.764  |             99.4008 |               148.564  |                   4 |              4 |     226.122  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |                 56 |          23.3726  |          13.8378  |             159.764  |             98.7305 |               148.564  |                   4 |              4 |     225.955  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |                 44 |          19.8517  |          14.6629  |             196.03   |            132.521  |               187.23   |                   3 |              3 |     218.718  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |                 44 |          19.8517  |          14.6629  |             196.03   |            132.305  |               187.23   |                   3 |              3 |     218.664  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |                 38 |          20.6431  |          15.7265  |             188.645  |            127.036  |               181.045  |                   3 |              3 |     218.608  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |                 38 |          20.6431  |          15.7265  |             188.645  |            124.146  |               181.045  |                   3 |              3 |     217.885  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |                 38 |          20.6431  |          15.7265  |             188.645  |            122.583  |               181.045  |                   3 |              3 |     217.495  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |                 38 |          20.6431  |          15.7265  |             188.645  |            121.668  |               181.045  |                   3 |              3 |     217.266  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |                 56 |          13.2074  |           9.46011 |             207.844  |            148.795  |               196.644  |                   4 |              4 |     202.069  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |                 56 |          13.2074  |           9.46011 |             207.844  |            137.492  |               196.644  |                   4 |              4 |     199.243  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |                 66 |          12.1744  |           7.39838 |             162.739  |             97.8047 |               149.539  |                   4 |              4 |     171.425  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |                 66 |          12.1744  |           7.39838 |             162.739  |             96.1216 |               149.539  |                   4 |              4 |     171.004  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |                 48 |          10.4392  |           7.71964 |             188.803  |            119.75   |               179.203  |                   3 |              3 |     166.614  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |                 48 |          10.4392  |           7.71964 |             188.803  |            119.144  |               179.203  |                   3 |              3 |     166.463  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |                 50 |           7.00671 |           5.19892 |             179.005  |            113.515  |               169.005  |                   3 |              3 |     145.114  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             62.4991 |                91.3598 |                   3 |              3 |     144.402  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             62.1392 |                91.3598 |                   3 |              3 |     144.312  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             60.4778 |                91.3598 |                   3 |              3 |     143.896  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             60.234  |                91.3598 |                   3 |              3 |     143.835  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |                 50 |           7.00671 |           5.19892 |             179.005  |            101.067  |               169.005  |                   3 |              3 |     142.002  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |                 30 |           8.9514  |           6.22801 |              82.6827 |             52.8054 |                76.6827 |                   3 |              3 |     109.163  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |                 30 |           8.9514  |           6.22801 |              82.6827 |             48.6107 |                76.6827 |                   3 |              3 |     108.114  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |                 30 |           9.54992 |           6.75551 |              88.9064 |             59.4302 |                82.9064 |                   2 |              3 |     107.679  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |                 30 |           9.54992 |           6.75551 |              88.9064 |             59.0738 |                82.9064 |                   2 |              3 |     107.59   |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | spx_chg_5          | spx_chg_5_ge_q70          | london_q60_prior_q25 |                 30 |           7.85501 |           5.22305 |              71.2818 |             37.2223 |                65.2818 |                   3 |              3 |      96.3651 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | spx_chg_5          | spx_chg_5_ge_q70          | london_q40_prior_q30 |                 30 |           7.85501 |           5.22305 |              71.2818 |             36.8286 |                65.2818 |                   3 |              3 |      96.2667 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | oil_rank250        | oil_rank250_le_q30        | macro_only           |                 36 |           4.51158 |           3.18193 |              94.494  |             55.3684 |                87.294  |                   2 |              3 |      83.6282 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | oil_rank250        | oil_rank250_le_q30        | macro_only           |                 36 |           4.51158 |           3.18193 |              94.494  |             52.1611 |                87.294  |                   2 |              3 |      82.8264 |

## Top diagnostics

| decision                                               | scope_type     | scope_value                            | macro_feature      | macro_gate                | overlay_name         |   confirmed_events |   confirmed_pf_x4 |   confirmed_pf_x6 |   confirmed_total_x4 |   boot_p05_total_x4 |   stress_0.20_total_x4 |   years_positive_x4 |   years_tested |   rank_score |
|:-------------------------------------------------------|:---------------|:---------------------------------------|:-------------------|:--------------------------|:---------------------|-------------------:|------------------:|------------------:|---------------------:|--------------------:|-----------------------:|--------------------:|---------------:|-------------:|
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |                 50 |          22.7856  |          16.6791  |             209.221  |            143.886  |               199.221  |                   4 |              4 |     248.666  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |                 50 |          22.7856  |          16.6791  |             209.221  |            142.654  |               199.221  |                   4 |              4 |     248.358  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |                 56 |          23.3726  |          13.8378  |             159.764  |             99.4008 |               148.564  |                   4 |              4 |     226.122  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |                 56 |          23.3726  |          13.8378  |             159.764  |             98.7305 |               148.564  |                   4 |              4 |     225.955  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |                 44 |          19.8517  |          14.6629  |             196.03   |            132.521  |               187.23   |                   3 |              3 |     218.718  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |                 44 |          19.8517  |          14.6629  |             196.03   |            132.305  |               187.23   |                   3 |              3 |     218.664  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |                 38 |          20.6431  |          15.7265  |             188.645  |            127.036  |               181.045  |                   3 |              3 |     218.608  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |                 38 |          20.6431  |          15.7265  |             188.645  |            124.146  |               181.045  |                   3 |              3 |     217.885  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |                 38 |          20.6431  |          15.7265  |             188.645  |            122.583  |               181.045  |                   3 |              3 |     217.495  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |                 38 |          20.6431  |          15.7265  |             188.645  |            121.668  |               181.045  |                   3 |              3 |     217.266  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |                 56 |          13.2074  |           9.46011 |             207.844  |            148.795  |               196.644  |                   4 |              4 |     202.069  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |                 56 |          13.2074  |           9.46011 |             207.844  |            137.492  |               196.644  |                   4 |              4 |     199.243  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |                 66 |          12.1744  |           7.39838 |             162.739  |             97.8047 |               149.539  |                   4 |              4 |     171.425  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |                 66 |          12.1744  |           7.39838 |             162.739  |             96.1216 |               149.539  |                   4 |              4 |     171.004  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |                 48 |          10.4392  |           7.71964 |             188.803  |            119.75   |               179.203  |                   3 |              3 |     166.614  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |                 48 |          10.4392  |           7.71964 |             188.803  |            119.144  |               179.203  |                   3 |              3 |     166.463  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |                 50 |           7.00671 |           5.19892 |             179.005  |            113.515  |               169.005  |                   3 |              3 |     145.114  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             62.4991 |                91.3598 |                   3 |              3 |     144.402  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             62.1392 |                91.3598 |                   3 |              3 |     144.312  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             60.4778 |                91.3598 |                   3 |              3 |     143.896  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |                 30 |          14.6338  |           9.82866 |              97.3598 |             60.234  |                91.3598 |                   3 |              3 |     143.835  |
| STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |                 50 |           7.00671 |           5.19892 |             179.005  |            101.067  |               169.005  |                   3 |              3 |     142.002  |
| STAGE31D_REJECT_CONFIRMATION                           | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |                 28 |          10.2984  |           6.91663 |              96.6898 |             56.6449 |                91.0898 |                   4 |              4 |     128.9    |
| STAGE31D_REJECT_CONFIRMATION                           | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |                 28 |          10.2984  |           6.91663 |              96.6898 |             55.4455 |                91.0898 |                   4 |              4 |     128.601  |
| STAGE31D_REJECT_CONFIRMATION                           | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_ret_1   | real_yield_ret_1_le_q30   | london_q60_prior_q25 |                 22 |           9.59771 |           7.11934 |              89.4033 |             44.9258 |                85.0033 |                   3 |              4 |     111.801  |
| STAGE31D_REJECT_CONFIRMATION                           | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | london_q60_prior_q25 |                 22 |           9.59771 |           7.11934 |              89.4033 |             44.8974 |                85.0033 |                   3 |              4 |     111.794  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |                 30 |           8.9514  |           6.22801 |              82.6827 |             52.8054 |                76.6827 |                   3 |              3 |     109.163  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |                 30 |           8.9514  |           6.22801 |              82.6827 |             48.6107 |                76.6827 |                   3 |              3 |     108.114  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |                 30 |           9.54992 |           6.75551 |              88.9064 |             59.4302 |                82.9064 |                   2 |              3 |     107.679  |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |                 30 |           9.54992 |           6.75551 |              88.9064 |             59.0738 |                82.9064 |                   2 |              3 |     107.59   |
| STAGE31D_REJECT_CONFIRMATION                           | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_chg_5        | us10y_chg_5_le_q30        | london_q60_prior_q25 |                 28 |           8.66848 |           6.09731 |              79.7407 |             46.9083 |                74.1407 |                   3 |              3 |     105.232  |
| STAGE31D_REJECT_CONFIRMATION                           | family         | london_oneway_continuation             | us10y_chg_5        | us10y_chg_5_le_q30        | london_q60_prior_q25 |                 28 |           8.66848 |           6.09731 |              79.7407 |             45.8227 |                74.1407 |                   3 |              3 |     104.96   |
| STAGE31D_REJECT_CONFIRMATION                           | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q60_prior_q25 |                 26 |           8.35604 |           5.94061 |              76.4918 |             46.2967 |                71.2918 |                   3 |              3 |     102.382  |
| STAGE31D_REJECT_CONFIRMATION                           | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q60_prior_q25 |                 26 |           8.35604 |           5.94061 |              76.4918 |             43.6829 |                71.2918 |                   3 |              3 |     101.728  |
| STAGE31D_REJECT_CONFIRMATION                           | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q60_prior_q25 |                 26 |           8.95456 |           6.46811 |              82.7155 |             47.9151 |                77.5155 |                   2 |              3 |      99.6463 |
| STAGE31D_REJECT_CONFIRMATION                           | family         | london_oneway_continuation             | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q60_prior_q25 |                 26 |           8.95456 |           6.46811 |              82.7155 |             47.7334 |                77.5155 |                   2 |              3 |      99.6008 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | spx_chg_5          | spx_chg_5_ge_q70          | london_q60_prior_q25 |                 30 |           7.85501 |           5.22305 |              71.2818 |             37.2223 |                65.2818 |                   3 |              3 |      96.3651 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | spx_chg_5          | spx_chg_5_ge_q70          | london_q40_prior_q30 |                 30 |           7.85501 |           5.22305 |              71.2818 |             36.8286 |                65.2818 |                   3 |              3 |      96.2667 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | family         | london_oneway_continuation             | oil_rank250        | oil_rank250_le_q30        | macro_only           |                 36 |           4.51158 |           3.18193 |              94.494  |             55.3684 |                87.294  |                   2 |              3 |      83.6282 |
| STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY             | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | oil_rank250        | oil_rank250_le_q30        | macro_only           |                 36 |           4.51158 |           3.18193 |              94.494  |             52.1611 |                87.294  |                   2 |              3 |      82.8264 |

## Interpretation

- A confirmed candidate is still review-only; it is not an execution authorization.
- The next step after a confirmed candidate is a dedicated forward-shadow tracker, not EA/paper/live promotion.
- If confirmation fails, the Stage31C positives should be treated as selection artifacts or overfit intersections.

## Output files

- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.json`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.md`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_year_diagnostics.csv`
