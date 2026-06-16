# Stage31C Exogenous Fragile-Edge Audit

Generated UTC: `2026-06-13T22:40:48.016212+00:00`

## Decision

```text
STAGE31C_HAS_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow audit only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage31A enriched dataset and Stage31B gate diagnostics only.
- All gates use expanding prior-year thresholds; no future thresholds are used.
- Combo overlays are diagnostic intersections, not executable strategy rules.

## Inputs

```json
{
  "stage31a_dataset": {
    "path": "data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv",
    "exists": true,
    "loaded": true,
    "rows": 17124,
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
    ]
  },
  "stage31b_results": {
    "path": "data/reports/stage31b_exogenous_gate_validation/stage31b_gate_results.csv",
    "exists": true,
    "loaded": true,
    "rows": 5275,
    "columns": [
      "scope_type",
      "scope_value",
      "feature",
      "gate",
      "direction",
      "quantile",
      "wf_events",
      "wf_retained_ratio",
      "threshold_avg",
      "threshold_min",
      "threshold_max",
      "base_events",
      "base_pf_x4",
      "base_total_x4",
      "wf_pf_x4",
      "wf_pf_x6",
      "wf_total_x4",
      "wf_total_x6",
      "wf_win_rate_x4",
      "wf_median_x4",
      "wf_avg_x4",
      "years_tested",
      "years_positive_x4",
      "min_year_events",
      "lift_pf_x4",
      "lift_total_x4",
      "boot_p05_total_x4",
      "decision",
      "rank_score"
    ]
  }
}
```

## Counts

- rows_after_parse: `17124`
- gate_defs: `272`
- overlay_defs: `5`
- audit_results: `1360`
- candidate_review_count: `120`
- strong_candidate_count: `94`
- fragile_positive_count: `26`
- weak_watchlist_count: `0`

## Candidate / watchlist rows

| decision                                       | scope_type     | scope_value                            | macro_feature      | macro_gate                | overlay_name         |   wf_events |   wf_pf_x4 |   wf_pf_x6 |   wf_total_x4 |   boot_p05_total_x4 |   years_positive_x4 |   years_tested |   rank_score |
|:-----------------------------------------------|:---------------|:---------------------------------------|:-------------------|:--------------------------|:---------------------|------------:|-----------:|-----------:|--------------:|--------------------:|--------------------:|---------------:|-------------:|
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |         112 |   13.2074  |    9.46011 |       415.689 |             316.995 |                   4 |              4 |      145.419 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |         112 |   13.2074  |    9.46011 |       415.689 |             307.764 |                   4 |              4 |      144.957 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |          92 |   21.9196  |   16.1826  |       401.808 |             306.081 |                   4 |              4 |      142.685 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |          92 |   21.9196  |   16.1826  |       401.808 |             303.202 |                   4 |              4 |      142.541 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |          88 |   19.8517  |   14.6629  |       392.06  |             300.294 |                   3 |              3 |      139.021 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |          88 |   19.8517  |   14.6629  |       392.06  |             288.497 |                   3 |              3 |      138.431 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |          96 |   10.4392  |    7.71964 |       377.607 |             288.167 |                   3 |              3 |      137.769 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |          96 |   10.4392  |    7.71964 |       377.607 |             281.063 |                   3 |              3 |      137.414 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |          76 |   20.6431  |   15.7265  |       377.29  |             288.078 |                   3 |              3 |      135.733 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |          76 |   20.6431  |   15.7265  |       377.29  |             285.506 |                   3 |              3 |      135.604 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |          76 |   20.6431  |   15.7265  |       377.29  |             282.973 |                   3 |              3 |      135.478 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |          76 |   20.6431  |   15.7265  |       377.29  |             272.429 |                   3 |              3 |      134.95  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |         100 |    7.00671 |    5.19892 |       358.009 |             255.71  |                   3 |              3 |      134.586 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |         100 |    7.00671 |    5.19892 |       358.009 |             254.465 |                   3 |              3 |      134.524 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |         132 |   12.1744  |    7.39838 |       325.477 |             238.009 |                   4 |              4 |      132.448 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |         132 |   12.1744  |    7.39838 |       325.477 |             234.136 |                   4 |              4 |      132.255 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |         108 |   22.8006  |   13.552   |       311.36  |             223.273 |                   4 |              4 |      130.3   |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |         108 |   22.8006  |   13.552   |       311.36  |             221.672 |                   4 |              4 |      130.22  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | oil_rank250        | oil_rank250_le_q30        | macro_only           |          68 |    7.35299 |    5.06283 |       209.785 |             152.041 |                   3 |              3 |      111.381 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | oil_rank250        | oil_rank250_le_q30        | macro_only           |          68 |    7.35299 |    5.06283 |       209.785 |             148.353 |                   3 |              3 |      111.196 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |          56 |   10.2984  |    6.91663 |       193.38  |             137.831 |                   4 |              4 |      109.83  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |          56 |   10.2984  |    6.91663 |       193.38  |             125.988 |                   4 |              4 |      109.237 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |             143.716 |                   3 |              3 |      108.658 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |             143.355 |                   3 |              3 |      108.64  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |             141.722 |                   3 |              3 |      108.558 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |             140.421 |                   3 |              3 |      108.493 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | london_q60_prior_q25 |          44 |    9.59771 |    7.11934 |       178.807 |             123.302 |                   3 |              4 |      104.446 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |          60 |    8.9514  |    6.22801 |       165.365 |             114.188 |                   3 |              3 |      104.246 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |          60 |    8.9514  |    6.22801 |       165.365 |             114.12  |                   3 |              3 |      104.243 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_chg_5        | us10y_chg_5_le_q30        | london_q60_prior_q25 |          60 |    8.89708 |    6.18013 |       164.236 |             114.177 |                   3 |              3 |      104.132 |

## Top diagnostics

| decision                                       | scope_type     | scope_value                            | macro_feature      | macro_gate                | overlay_name         |   wf_events |   wf_pf_x4 |   wf_pf_x6 |   wf_total_x4 |   boot_p05_total_x4 |   years_positive_x4 |   years_tested |   rank_score |
|:-----------------------------------------------|:---------------|:---------------------------------------|:-------------------|:--------------------------|:---------------------|------------:|-----------:|-----------:|--------------:|--------------------:|--------------------:|---------------:|-------------:|
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |         112 |   13.2074  |    9.46011 |       415.689 |            316.995  |                   4 |              4 |      145.419 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | macro_only           |         112 |   13.2074  |    9.46011 |       415.689 |            307.764  |                   4 |              4 |      144.957 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |          92 |   21.9196  |   16.1826  |       401.808 |            306.081  |                   4 |              4 |      142.685 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250 | real_yield_rank250_le_q20 | london_q40_prior_q30 |          92 |   21.9196  |   16.1826  |       401.808 |            303.202  |                   4 |              4 |      142.541 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |          88 |   19.8517  |   14.6629  |       392.06  |            300.294  |                   3 |              3 |      139.021 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q60_prior_q25 |          88 |   19.8517  |   14.6629  |       392.06  |            288.497  |                   3 |              3 |      138.431 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |          96 |   10.4392  |    7.71964 |       377.607 |            288.167  |                   3 |              3 |      137.769 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | london_q40_prior_q30 |          96 |   10.4392  |    7.71964 |       377.607 |            281.063  |                   3 |              3 |      137.414 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |          76 |   20.6431  |   15.7265  |       377.29  |            288.078  |                   3 |              3 |      135.733 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |          76 |   20.6431  |   15.7265  |       377.29  |            285.506  |                   3 |              3 |      135.604 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | london_q40_prior_q30 |          76 |   20.6431  |   15.7265  |       377.29  |            282.973  |                   3 |              3 |      135.478 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q20      | macro_only           |          76 |   20.6431  |   15.7265  |       377.29  |            272.429  |                   3 |              3 |      134.95  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |         100 |    7.00671 |    5.19892 |       358.009 |            255.71   |                   3 |              3 |      134.586 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250      | us10y_rank250_le_q30      | macro_only           |         100 |    7.00671 |    5.19892 |       358.009 |            254.465  |                   3 |              3 |      134.524 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |         132 |   12.1744  |    7.39838 |       325.477 |            238.009  |                   4 |              4 |      132.448 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | macro_only           |         132 |   12.1744  |    7.39838 |       325.477 |            234.136  |                   4 |              4 |      132.255 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |         108 |   22.8006  |   13.552   |       311.36  |            223.273  |                   4 |              4 |      130.3   |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_z60     | real_yield_z60_le_q20     | london_q40_prior_q30 |         108 |   22.8006  |   13.552   |       311.36  |            221.672  |                   4 |              4 |      130.22  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | oil_rank250        | oil_rank250_le_q30        | macro_only           |          68 |    7.35299 |    5.06283 |       209.785 |            152.041  |                   3 |              3 |      111.381 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | oil_rank250        | oil_rank250_le_q30        | macro_only           |          68 |    7.35299 |    5.06283 |       209.785 |            148.353  |                   3 |              3 |      111.196 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |          56 |   10.2984  |    6.91663 |       193.38  |            137.831  |                   4 |              4 |      109.83  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | macro_only           |          56 |   10.2984  |    6.91663 |       193.38  |            125.988  |                   4 |              4 |      109.237 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |            143.716  |                   3 |              3 |      108.658 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_ret_5          | dxy_ret_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |            143.355  |                   3 |              3 |      108.64  |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |            141.722  |                   3 |              3 |      108.558 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | dxy_chg_5          | dxy_chg_5_le_q30          | london_q40_prior_q30 |          60 |   14.6338  |    9.82866 |       194.72  |            140.421  |                   3 |              3 |      108.493 |
| STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY      | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |          60 |    9.54992 |    6.75551 |       177.813 |            134.24   |                   2 |              3 |      104.493 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | real_yield_ret_1   | real_yield_ret_1_le_q30   | london_q60_prior_q25 |          44 |    9.59771 |    7.11934 |       178.807 |            123.302  |                   3 |              4 |      104.446 |
| STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY      | family         | london_oneway_continuation             | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q40_prior_q30 |          60 |    9.54992 |    6.75551 |       177.813 |            131.918  |                   2 |              3 |      104.377 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |          60 |    8.9514  |    6.22801 |       165.365 |            114.188  |                   3 |              3 |      104.246 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q40_prior_q30 |          60 |    8.9514  |    6.22801 |       165.365 |            114.12   |                   3 |              3 |      104.243 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_chg_5        | us10y_chg_5_le_q30        | london_q60_prior_q25 |          60 |    8.89708 |    6.18013 |       164.236 |            114.177  |                   3 |              3 |      104.132 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_ret_1   | real_yield_ret_1_le_q30   | london_q60_prior_q25 |          44 |    9.59771 |    7.11934 |       178.807 |            115.45   |                   3 |              4 |      104.053 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_chg_5        | us10y_chg_5_le_q30        | london_q60_prior_q25 |          60 |    8.89708 |    6.18013 |       164.236 |            112.079  |                   3 |              3 |      104.027 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | us10y_ret_5        | us10y_ret_5_le_q30        | london_q60_prior_q25 |          56 |    8.58465 |    6.02343 |       157.738 |            113.293  |                   3 |              3 |      103.038 |
| STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY      | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q60_prior_q25 |          56 |    9.18317 |    6.55093 |       170.185 |            126.579  |                   2 |              3 |      102.947 |
| STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY      | family         | london_oneway_continuation             | real_yield_chg_5   | real_yield_chg_5_le_q30   | london_q60_prior_q25 |          56 |    9.18317 |    6.55093 |       170.185 |            123.507  |                   2 |              3 |      102.794 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_ret_5        | us10y_ret_5_le_q30        | london_q60_prior_q25 |          56 |    8.58465 |    6.02343 |       157.738 |            107.976  |                   3 |              3 |      102.773 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | spx_chg_5          | spx_chg_5_ge_q70          | london_q40_prior_q30 |          60 |    7.85501 |    5.22305 |       142.564 |             99.9447 |                   3 |              3 |      101.254 |
| STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY | family         | london_oneway_continuation             | spx_chg_5          | spx_chg_5_ge_q70          | london_q60_prior_q25 |          60 |    7.85501 |    5.22305 |       142.564 |             95.9871 |                   3 |              3 |      101.056 |

## Interpretation

- A fragile positive means the filter improved a weak lineage but still lacks robust bootstrap/year evidence.
- Promotion requires a later forward-shadow tracker; this stage cannot authorize execution.
- If no robust candidate survives, the next useful route is calendar-event enrichment or returning to the validated Stage28C/Stage27C lineage, not broader ML.

## Output files

- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.md`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.json`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.csv`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_year_diagnostics.csv`