# Stage31E Exogenous Forward-Shadow Tracker

Generated UTC: `2026-06-13T22:55:11.139245+00:00`

## Decision

```text
STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow tracker only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage31A enriched dataset and Stage31D confirmed candidates only.
- Gate thresholds are applied with expanding prior-year calibration only.
- Recent signals are review-only observations, not executable instructions.

## Counts

- dataset_rows: `17124`
- gate_defs_loaded: `8`
- gate_defs_tracked: `8`
- tracker_results: `8`
- recent_signal_rows: `4`
- recent_signal_gate_count: `8`
- lookback_hours: `4320`

## Tracker summary

| tracker_decision | scope_type | scope_value | macro_gate | overlay_name | confirmed_recalc_events | confirmed_recalc_pf_x4 | confirmed_recalc_total_x4 | recent_events | recent_last_entry_ts | rank_score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250_le_q20 | london_q40_prior_q30 | 50 | 22.7856 | 209.2207 | 4 | 2026-03-06T13:01:00+00:00 | 248.6655 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60_le_q20 | london_q40_prior_q30 | 56 | 23.3726 | 159.7644 | 2 | 2026-03-03T13:01:00+00:00 | 225.9549 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_rank250_le_q20 | macro_only | 56 | 13.2074 | 207.8443 | 4 | 2026-03-06T13:01:00+00:00 | 202.0691 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | real_yield_z60_le_q20 | macro_only | 66 | 12.1744 | 162.7386 | 2 | 2026-03-03T13:01:00+00:00 | 171.4248 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | candidate_name | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | us10y_rank250_le_q30 | macro_only | 50 | 7.0067 | 179.0047 | 4 | 2026-03-06T13:01:00+00:00 | 145.1137 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | family | london_oneway_continuation | real_yield_rank250_le_q20 | london_q40_prior_q30 | 50 | 22.7856 | 209.2207 | 4 | 2026-03-06T13:01:00+00:00 | 248.3576 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | family | london_oneway_continuation | real_yield_z60_le_q20 | london_q40_prior_q30 | 56 | 23.3726 | 159.7644 | 2 | 2026-03-03T13:01:00+00:00 | 226.1224 |
| STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | family | london_oneway_continuation | real_yield_rank250_le_q20 | macro_only | 56 | 13.2074 | 207.8443 | 4 | 2026-03-06T13:01:00+00:00 | 199.2434 |

## Recent signal sample

| entry_ts_norm | event_key | candidate_name | family | net_x4 | net_x6 | stage31e_gate_key | real_yield_rank250 | real_yield_z60 | us10y_rank250 | dxy_ret_5 | london_range | prior_day_range | h1_atr20_pct_rank_250 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-03-06 13:01:00+00:00 | 2026-03-06 13:01:00+00:00\|0.0\|S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | london_oneway_continuation | 12.3653 | 11.6653 | candidate_name:S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65\|real_yield_rank250_le_q20\|london_q40_prior_q30 | 0.2060 | -1.1825 | 0.3300 | 0.0142 | 54.2500 | 143.6900 | 0.5720 |
| 2026-03-06 13:01:00+00:00 | 2026-03-06 13:01:00+00:00\|-1.0\|S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | london_oneway_continuation | 12.3653 | 11.6653 | family:london_oneway_continuation\|real_yield_rank250_le_q20\|macro_only | 0.2060 | -1.1825 | 0.3300 | 0.0142 | 54.2500 | 143.6900 | 0.5720 |
| 2026-03-03 13:01:00+00:00 | 2026-03-03 13:01:00+00:00\|0.0\|S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | london_oneway_continuation | 27.2337 | 26.5337 | candidate_name:S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65\|real_yield_z60_le_q20\|london_q40_prior_q30 | 0.1260 | -1.7764 | 0.1340 | 0.0126 | 140.1000 | 158.2600 | 0.9720 |
| 2026-03-03 13:01:00+00:00 | 2026-03-03 13:01:00+00:00\|-1.0\|S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65 | london_oneway_continuation | 27.2337 | 26.5337 | candidate_name:S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65\|real_yield_rank250_le_q20\|london_q40_prior_q30 | 0.1260 | -1.7764 | 0.1340 | 0.0126 | 140.1000 | 158.2600 | 0.9720 |

## Interpretation

- A recent signal only means a historically confirmed research gate matched a recent candidate-pool row.
- This stage cannot authorize EA, paper/live, or orders.
- The next promotion step, if warranted, is sustained forward-shadow observation and active-suite integration, not live execution.

## Output files

- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.json`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.md`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_tracker_summary.csv`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_recent_signals.csv`
