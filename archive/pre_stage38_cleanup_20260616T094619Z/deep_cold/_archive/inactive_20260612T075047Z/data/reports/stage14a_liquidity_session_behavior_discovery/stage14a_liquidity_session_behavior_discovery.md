# Stage 14A Liquidity / Session / Sweep Behavior Discovery

Generated UTC: `2026-06-10T22:26:33+00:00`
Tool version: `v2_fast`

> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- intraday_source: `m1_to_m15`
- intraday_rows: `97633`
- days: `1279`
- h4_rows: `6482`
- events_path: `data/config/stage10a_news_events.csv`
- buffer_usd: `0.2`
- max_days: `0`

## Decision
- decision: `MECHANISM_CANDIDATE_FOUND`
- candidate_count: `1`

## Mechanism event counts
| Mechanism group | Events |
|---|---:|
| asia_london | 739 |
| london_ny | 860 |
| prev_day_sweep | 744 |
| news_spike_failure | 220 |
| failed_h4_breakout | 4063 |

## Top mechanism summaries
| Rank | Mechanism | Side | Horizon bars | Events | Total | Avg | Median | WR | PF | DD | Pos years | Candidate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | prev_day_low_sweep_rejection | LONG | 4 | 377 | 240.56 | 0.63809 | 0.33 | 0.522546 | 1.276455 | -112.49 | 4/5 | True |
| 2 | prev_day_low_sweep_rejection | LONG | 24 | 377 | 168.66 | 0.447374 | 0.63 | 0.527851 | 1.083724 | -348.13 | 3/5 | False |
| 3 | asia_low_sweep_london_rejection | LONG | 4 | 341 | 56.03 | 0.164311 | 0.41 | 0.533724 | 1.0699 | -102.85 | 3/5 | False |
| 4 | london_high_sweep_ny_rejection | SHORT | 12 | 445 | 142.82 | 0.320944 | -0.5 | 0.485393 | 1.054175 | -259.53 | 3/5 | False |
| 5 | asia_high_sweep_london_rejection | SHORT | 12 | 398 | 11.09 | 0.027864 | 0.33 | 0.530151 | 1.009771 | -282.69 | 3/5 | False |
| 6 | failed_break_below_prior_h4_low | LONG | 24 | 1973 | 56.65 | 0.028713 | 0.58 | 0.524582 | 1.004922 | -682.29 | 3/5 | False |
| 7 | asia_high_sweep_london_rejection | SHORT | 4 | 398 | 1.38 | 0.003467 | -0.165 | 0.484925 | 1.001783 | -107.22 | 2/5 | False |
| 8 | london_high_sweep_ny_rejection | SHORT | 24 | 445 | -5.29 | -0.011888 | 0.19 | 0.503371 | 0.998292 | -429.49 | 1/5 | False |
| 9 | prev_day_low_sweep_rejection | LONG | 12 | 377 | -27.83 | -0.07382 | 0.44 | 0.525199 | 0.983769 | -427.64 | 2/5 | False |
| 10 | failed_break_below_prior_h4_low | LONG | 4 | 1973 | -261.01 | -0.132291 | 0.01 | 0.50076 | 0.950796 | -544.51 | 3/5 | False |
| 11 | news_first_spike_up_failure | SHORT | 12 | 106 | -50.37 | -0.475189 | 0.505 | 0.528302 | 0.932902 | -346.26 | 3/5 | False |
| 12 | failed_break_below_prior_h4_low | LONG | 12 | 1973 | -621.3 | -0.314901 | 0.06 | 0.504308 | 0.927666 | -630.45 | 1/5 | False |
| 13 | london_low_sweep_ny_rejection | LONG | 24 | 415 | -222.29 | -0.535639 | -0.4 | 0.484337 | 0.9193 | -340.52 | 2/5 | False |
| 14 | news_first_spike_up_failure | SHORT | 4 | 106 | -48.05 | -0.453302 | -0.95 | 0.443396 | 0.916983 | -162.65 | 1/5 | False |
| 15 | failed_break_above_prior_h4_high | SHORT | 4 | 2090 | -501.15 | -0.239785 | -0.13 | 0.482297 | 0.912544 | -618.84 | 0/5 | False |

## Interpretation rules
- `MECHANISM_CANDIDATE_FOUND` means a behavior deserves focused robustness/replay study.
- `NO_MECHANISM_FOUND_FOR_TESTED_HYPOTHESES` does not mean XAUUSD has no behavior; it means these tested hypotheses did not capture one.
- `INCONCLUSIVE_*` means event extraction or sample size is insufficient.
- Do not convert any candidate directly to EA/paper/live.

## Output files
- events_csv: `data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_events.csv`
- outcomes_csv: `data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_outcomes.csv`
- summary_csv: `data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_summary.csv`
- json: `data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.json`
- md: `data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_liquidity_session_behavior_discovery.md`
