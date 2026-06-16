# Stage31B Exogenous/Macro Gate Validation

Generated UTC: `2026-06-13T22:27:27.077685+00:00`

## Decision

```text
STAGE31B_HAS_WEAK_EXOGENOUS_GATE_IMPROVEMENT_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow validation only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes the Stage31A enriched dataset only; no internet fetch is performed.
- Gate thresholds are calibrated with expanding prior-year data only.
- Results are review-only even if a candidate is strong.

## Dataset

```json
{
  "dataset_path": "data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv",
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
  "rows_after_required_parse": 17124
}
```

## Counts

- feature_count: `42`
- scope_count: `49`
- gate_result_count: `5275`
- candidate_review_count: `4`
- strong_candidate_count: `0`
- weak_improvement_count: `4`

## Candidate review sample

| decision                     | scope_type     | scope_value                                     | feature          | gate                    |   wf_events |   wf_pf_x4 |   wf_pf_x6 |   wf_total_x4 |   boot_p05_total_x4 |   years_positive_x4 |   years_tested |   rank_score |
|:-----------------------------|:---------------|:------------------------------------------------|:-----------------|:------------------------|------------:|-----------:|-----------:|--------------:|--------------------:|--------------------:|---------------:|-------------:|
| REVIEW_WEAK_IMPROVEMENT_ONLY | candidate_name | calendar_drop_monday_h13_tp06_sl065             | dxy_chg_1        | dxy_chg_1_ge_q80        |          82 |   0.969794 |   0.656959 |      -4.5015  |            -88.197  |                   2 |              3 |      25.0813 |
| REVIEW_WEAK_IMPROVEMENT_ONLY | candidate_name | calendar_drop_monday_h13_tp06_sl065             | dxy_ret_1        | dxy_ret_1_ge_q80        |          83 |   0.896297 |   0.613063 |     -16.7217  |            -96.5769 |                   2 |              3 |      23.0982 |
| REVIEW_WEAK_IMPROVEMENT_ONLY | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | real_yield_chg_5 | real_yield_chg_5_ge_q70 |          42 |   0.8047   |   0.394468 |      -8.39103 |            -37.59   |                   2 |              3 |      22.3699 |
| REVIEW_WEAK_IMPROVEMENT_ONLY | candidate_name | calendar_drop_friday_h13_tp06_sl065             | real_yield_ret_5 | real_yield_ret_5_ge_q70 |          61 |   0.827198 |   0.585745 |     -23.1088  |           -102.068  |                   2 |              3 |      21.0531 |

## Top rejected / diagnostic gates

| decision               | scope_type     | scope_value                                     | feature            | gate                      |   wf_events |   wf_pf_x4 |   wf_total_x4 |   base_pf_x4 |   base_total_x4 |   rank_score |
|:-----------------------|:---------------|:------------------------------------------------|:-------------------|:--------------------------|------------:|-----------:|--------------:|-------------:|----------------:|-------------:|
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_chg_5          | oil_chg_5_le_q20          |          42 |   1.32708  |     15.9262   |     0.237335 |        -654.586 |      31.7431 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | real_yield_chg_1   | real_yield_chg_1_ge_q70   |          53 |   1.07418  |      4.0953   |     0.237335 |        -654.586 |      25.3759 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | real_yield_ret_1   | real_yield_ret_1_ge_q70   |          37 |   1.0669   |      2.88742  |     0.237335 |        -654.586 |      25.0277 |
| REJECT_NO_FORWARD_EDGE | candidate_name | calendar_drop_friday_h9_tp06_sl065              | real_yield_rank250 | real_yield_rank250_ge_q80 |          34 |   1.04765  |      2.859    |     0.231633 |       -1575.78  |      24.6214 |
| REJECT_NO_FORWARD_EDGE | candidate_name | calendar_drop_monday_h9_tp06_sl065              | real_yield_rank250 | real_yield_rank250_ge_q80 |          37 |   1.02732  |      1.81187  |     0.216323 |       -1630.97  |      24.508  |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_chg_1          | oil_chg_1_le_q20          |          39 |   1.01785  |      0.943025 |     0.237335 |        -654.586 |      23.7969 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_ret_5          | oil_ret_5_le_q20          |          45 |   1.01633  |      0.91695  |     0.237335 |        -654.586 |      23.7941 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | us10y_rank250      | us10y_rank250_ge_q70      |          48 |   0.977194 |     -1.9352   |     0.237335 |        -654.586 |      22.7708 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_chg_1          | oil_chg_1_ge_q80          |          41 |   0.970444 |     -1.6693   |     0.237335 |        -654.586 |      22.5489 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_rank250        | oil_rank250_ge_q80        |          83 |   0.948015 |     -7.00962  |     0.237335 |        -654.586 |      22.2882 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | vix_z60            | vix_z60_le_q30            |          61 |   0.944469 |     -5.2073   |     0.237335 |        -654.586 |      22.0379 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | dxy_value          | dxy_value_le_q30          |          90 |   0.913506 |    -14.6648   |     0.237335 |        -654.586 |      21.3692 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_chg_5          | spx_chg_5_ge_q80          |          69 |   0.900248 |     -8.95172  |     0.237335 |        -654.586 |      20.9568 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_ret_5          | oil_ret_5_ge_q80          |          58 |   0.896433 |     -7.82107  |     0.237335 |        -654.586 |      20.7917 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_ret_5          | spx_ret_5_ge_q80          |          40 |   0.889587 |     -5.94272  |     0.237335 |        -654.586 |      20.492  |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_z60            | oil_z60_ge_q80            |          61 |   0.854108 |    -10.5444   |     0.237335 |        -654.586 |      19.7247 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_fade_h1_high_cooling_h12_tp06_sl065   | real_yield_z60     | real_yield_z60_ge_q80     |          35 |   0.758139 |    -12.4033   |     0.138281 |        -837.561 |      19.5596 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | us10y_z60          | us10y_z60_ge_q70          |          45 |   0.850409 |    -10.4634   |     0.237335 |        -654.586 |      19.4738 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h12_tp06_sl065 | spx_ret_5          | spx_ret_5_ge_q80          |          38 |   0.800394 |    -11.6209   |     0.184773 |        -715.542 |      19.4559 |
| REJECT_NO_FORWARD_EDGE | family         | high_range_broad_pullback_continuation_v1       | vix_z60            | vix_z60_le_q20            |          88 |   0.778434 |    -34.0058   |     0.169397 |       -2857.61  |      19.4174 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_chg_5          | oil_chg_5_le_q30          |          60 |   0.836181 |    -13.6768   |     0.237335 |        -654.586 |      19.2166 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_chg_5          | oil_chg_5_ge_q80          |          52 |   0.834009 |    -12.7562   |     0.237335 |        -654.586 |      19.0934 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_z60            | spx_z60_ge_q80            |          71 |   0.798331 |    -16.1849   |     0.237335 |        -654.586 |      18.3602 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_rank250        | oil_rank250_ge_q70        |         114 |   0.784687 |    -36.3696   |     0.237335 |        -654.586 |      18.0885 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | dxy_chg_5          | dxy_chg_5_le_q30          |          62 |   0.785712 |    -17.3733   |     0.237335 |        -654.586 |      17.9302 |
| REJECT_NO_FORWARD_EDGE | family         | session_handoff_imbalance_v1                    | real_yield_ret_5   | real_yield_ret_5_ge_q80   |          51 |   0.862937 |    -26.4242   |     0.305412 |       -3729.26  |      17.6023 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | us10y_ret_5        | us10y_ret_5_ge_q70        |          40 |   0.770019 |    -10.0932   |     0.237335 |        -654.586 |      17.4725 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_ret_1          | spx_ret_1_ge_q80          |          44 |   0.762638 |    -14.9739   |     0.237335 |        -654.586 |      17.245  |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_ret_1          | spx_ret_1_le_q20          |          33 |   0.754477 |    -11.5394   |     0.237335 |        -654.586 |      16.9699 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_fade_h1_high_cooling_h12_tp06_sl065   | us10y_z60          | us10y_z60_ge_q80          |          30 |   0.654136 |    -16.172    |     0.138281 |        -837.561 |      16.8515 |
| REJECT_NO_FORWARD_EDGE | candidate_name | calendar_drop_monday_h9_tp06_sl065              | dxy_chg_1          | dxy_chg_1_ge_q80          |          82 |   0.719963 |    -46.6553   |     0.216323 |       -1630.97  |      16.4608 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | dxy_ret_5          | dxy_ret_5_le_q30          |          65 |   0.728549 |    -23.9196   |     0.237335 |        -654.586 |      16.4237 |
| REJECT_NO_FORWARD_EDGE | candidate_name | calendar_drop_friday_h13_tp06_sl065             | real_yield_ret_1   | real_yield_ret_1_le_q20   |          33 |   0.799763 |    -11.4257   |     0.303899 |       -1331.68  |      16.4049 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | oil_ret_1          | oil_ret_1_le_q20          |          40 |   0.725683 |    -16.3594   |     0.237335 |        -654.586 |      16.2564 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_fade_h1_high_cooling_h12_tp06_sl065   | us10y_z60          | us10y_z60_ge_q70          |          46 |   0.626929 |    -29.9555   |     0.138281 |        -837.561 |      16.1091 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h12_tp06_sl065 | dxy_ret_5          | dxy_ret_5_le_q20          |          43 |   0.662826 |    -19.7195   |     0.184773 |        -715.542 |      15.9911 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h12_tp06_sl065 | dxy_chg_5          | dxy_chg_5_le_q20          |          43 |   0.662826 |    -19.7195   |     0.184773 |        -715.542 |      15.9911 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 | spx_z60            | spx_z60_ge_q70            |         132 |   0.69468  |    -50.8714   |     0.237335 |        -654.586 |      15.8413 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_fade_h1_high_cooling_h12_tp06_sl065   | real_yield_chg_5   | real_yield_chg_5_ge_q70   |          42 |   0.605531 |    -20.3749   |     0.138281 |        -837.561 |      15.7063 |
| REJECT_NO_FORWARD_EDGE | candidate_name | vol_trans_follow_h1_high_cooling_h12_tp06_sl065 | dxy_ret_5          | dxy_ret_5_le_q30          |          65 |   0.647227 |    -33.2502   |     0.184773 |        -715.542 |      15.5866 |

## Interpretation

- A rejected result does not mean macro data is useless; it means these simple forward-safe quantile gates did not validate on the current candidate pool/scope.
- Candidate-pool quality still matters: Stage30A included weak families, so lineage-specific results should be read before global results.
- Promotion requires a separate forward-shadow tracker; this stage cannot authorize execution.

## Output files

- `data/reports/stage31b_exogenous_gate_validation/stage31b_exogenous_gate_validation.json`
- `data/reports/stage31b_exogenous_gate_validation/stage31b_exogenous_gate_validation.md`
- `data/reports/stage31b_exogenous_gate_validation/stage31b_gate_results.csv`
- `data/reports/stage31b_exogenous_gate_validation/stage31b_candidate_review.csv`
