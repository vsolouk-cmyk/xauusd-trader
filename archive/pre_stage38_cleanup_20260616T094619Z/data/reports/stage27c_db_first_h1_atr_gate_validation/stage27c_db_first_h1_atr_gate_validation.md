# Stage27C DB-First H1 ATR Gate Validation

Generated UTC: `2026-06-14T17:58:59.730311+00:00`

## Decision

```text
STAGE27C_H1_ATR_GATE_VALIDATED_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow validation only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles/regime features are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.
- Prior trade CSV is used only as a research artifact, not as market-data fallback.
- H1 ATR gate is anti-leakage validated: H1 bar_end must be <= entry_time.

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1534217` | span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_rows: `25608` | span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`

## Trade artifact

- selected_artifact: `data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv`
- requested_candidate: `S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65`
- rows_after_event_dedup: `100`

| path | exists | rows | status |
| --- | --- | --- | --- |
| data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv | True | 100 | loaded |

## Base lineage metrics before strict H1 ATR gate

```json
{
  "events": 100,
  "pf_x1": 5.578963613461408,
  "pf_x4": 2.851412305366161,
  "pf_x6": 1.653421789024173,
  "boot_pf_p05_x4": 1.72574332566553,
  "median_x4": 1.0293600000000005,
  "total_x4": 127.61561,
  "win_rate_x4": 0.81,
  "years_positive_x4": 4,
  "year_count": 5
}
```

## Anti-leakage diagnostics

```json
{
  "strict_completed_h1_rows_missing": 0,
  "strict_completed_h1_not_complete_count": 0,
  "strict_vs_loose_gate_mismatch_count": 5,
  "strict_kept_events_q30": 62,
  "loose_kept_events_q30": 59,
  "min_completed_h1_age_minutes": 1.0,
  "median_completed_h1_age_minutes": 1.0,
  "max_completed_h1_age_minutes": 1.0
}
```

## H1 ATR gate validation diagnostics
| decision | gate_name | retained_events | retained_ratio | pf_x1 | pf_x4 | pf_x6 | boot_pf_p05_x4 | median_x4 | total_x4 | win_rate_x4 | years_positive_x4 | year_count | improvement_pf_x4 | improvement_pf_x6 | improvement_total_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE27C_GATE_VALIDATED_REVIEW_ONLY | h1_atr_drop_low30_strict_completed | 62 | 0.62 | 8.2873 | 4.8293 | 3.2792 | 2.5624 | 1.3735 | 139.8745 | 0.871 | 4 | 5 | 1.9779 | 1.6257 | 12.2588 |
| STAGE27C_GATE_VALIDATED_REVIEW_ONLY | h1_atr_drop_low35_strict_completed | 59 | 0.59 | 8.1016 | 4.7725 | 3.2891 | 2.6881 | 1.4401 | 137.801 | 0.8644 | 4 | 5 | 1.9211 | 1.6357 | 10.1854 |
| STAGE27C_GATE_VALIDATED_REVIEW_ONLY | h1_atr_drop_low40_strict_completed | 58 | 0.58 | 8.0314 | 4.7472 | 3.2839 | 2.7713 | 1.501 | 136.8782 | 0.8621 | 4 | 5 | 1.8958 | 1.6304 | 9.2625 |
| STAGE27C_GATE_VALIDATED_REVIEW_ONLY | h1_atr_drop_low20_strict_completed | 68 | 0.68 | 7.6666 | 4.4224 | 2.965 | 2.5061 | 1.2912 | 141.7781 | 0.8676 | 4 | 5 | 1.5709 | 1.3116 | 14.1625 |
| STAGE27C_GATE_VALIDATED_REVIEW_ONLY | h1_atr_drop_low25_strict_completed | 66 | 0.66 | 7.5085 | 4.351 | 2.9325 | 2.587 | 1.2912 | 138.8233 | 0.8636 | 4 | 5 | 1.4996 | 1.2791 | 11.2077 |

## Primary gate split diagnostics
| gate_name | split | bucket | events | pf_x4 | pf_x6 | total_x4 | win_rate_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| h1_atr_drop_low30_strict_completed | year | 2022 | 6 | 0.5883 | 0.2019 | -3.2847 | 0.6667 |
| h1_atr_drop_low30_strict_completed | year | 2023 | 15 | 2.1633 | 0.7677 | 8.471 | 0.8667 |
| h1_atr_drop_low30_strict_completed | year | 2024 | 23 | 3.3418 | 1.6339 | 23.4206 | 0.913 |
| h1_atr_drop_low30_strict_completed | year | 2025 | 14 | 5.6816 | 4.3905 | 52.746 | 0.8571 |
| h1_atr_drop_low30_strict_completed | year | 2026 | 4 | inf | inf | 58.5216 | 1 |
| h1_atr_drop_low30_strict_completed | direction | -1 | 27 | 6.3216 | 4.594 | 89.2715 | 0.8519 |
| h1_atr_drop_low30_strict_completed | direction | 1 | 35 | 3.5619 | 2.1474 | 50.6029 | 0.8857 |
| h1_atr_drop_low30_strict_completed | entry_hour | 13 | 62 | 4.8293 | 3.2792 | 139.8745 | 0.871 |
| h1_atr_drop_low30_strict_completed | dow | 0 | 14 | 2.2656 | 1.5184 | 18.4427 | 0.7857 |
| h1_atr_drop_low30_strict_completed | dow | 1 | 9 | 11.2328 | 8.7268 | 47.8104 | 0.8889 |
| h1_atr_drop_low30_strict_completed | dow | 2 | 10 | 6.5105 | 4.046 | 20.4508 | 0.9 |
| h1_atr_drop_low30_strict_completed | dow | 3 | 14 | 2.1813 | 1.054 | 10.3599 | 0.8571 |
| h1_atr_drop_low30_strict_completed | dow | 4 | 15 | 9.9155 | 6.8727 | 42.8106 | 0.9333 |
| h1_atr_drop_low30_strict_completed | year_direction | 2022/-1 | 4 | 0.9827 | 0.3534 | -0.0647 | 0.75 |
| h1_atr_drop_low30_strict_completed | year_direction | 2022/1 | 2 | 0.2419 | 0.0662 | -3.22 | 0.5 |
| h1_atr_drop_low30_strict_completed | year_direction | 2023/-1 | 7 | 2.1376 | 0.8037 | 4.0619 | 0.8571 |
| h1_atr_drop_low30_strict_completed | year_direction | 2023/1 | 8 | 2.188 | 0.7333 | 4.4091 | 0.875 |
| h1_atr_drop_low30_strict_completed | year_direction | 2024/-1 | 8 | 2.9042 | 1.6435 | 9.1436 | 0.875 |
| h1_atr_drop_low30_strict_completed | year_direction | 2024/1 | 15 | 3.746 | 1.6251 | 14.277 | 0.9333 |
| h1_atr_drop_low30_strict_completed | year_direction | 2025/-1 | 5 | 6.8257 | 5.4151 | 27.2191 | 0.8 |
| h1_atr_drop_low30_strict_completed | year_direction | 2025/1 | 9 | 4.871 | 3.6358 | 25.5269 | 0.8889 |
| h1_atr_drop_low30_strict_completed | year_direction | 2026/-1 | 3 | inf | inf | 48.9116 | 1 |
| h1_atr_drop_low30_strict_completed | year_direction | 2026/1 | 1 | inf | inf | 9.61 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2022/0 | 4 | 0.2788 | 0.0879 | -5.754 | 0.5 |
| h1_atr_drop_low30_strict_completed | year_dow | 2022/2 | 1 | inf | inf | 1.0523 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2022/3 | 1 | inf | inf | 1.417 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2023/0 | 3 | inf | inf | 5.0812 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2023/1 | 2 | inf | inf | 2.5147 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2023/2 | 3 | 0.526 | 0.1251 | -1.7592 | 0.6667 |
| h1_atr_drop_low30_strict_completed | year_dow | 2023/3 | 5 | 1.2043 | 0.3593 | 0.7295 | 0.8 |
| h1_atr_drop_low30_strict_completed | year_dow | 2023/4 | 2 | inf | inf | 1.9049 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2024/0 | 2 | inf | inf | 2.0253 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2024/1 | 2 | inf | inf | 2.0369 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2024/2 | 4 | inf | 770.6093 | 6.4249 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2024/3 | 6 | 1.3274 | 0.5866 | 1.7023 | 0.8333 |
| h1_atr_drop_low30_strict_completed | year_dow | 2024/4 | 9 | 3.339 | 1.8963 | 11.2313 | 0.8889 |
| h1_atr_drop_low30_strict_completed | year_dow | 2025/0 | 4 | 2.1794 | 1.6824 | 7.7777 | 0.75 |
| h1_atr_drop_low30_strict_completed | year_dow | 2025/1 | 4 | 4.4298 | 3.4617 | 16.0251 | 0.75 |
| h1_atr_drop_low30_strict_completed | year_dow | 2025/2 | 1 | inf | inf | 5.1229 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2025/3 | 2 | inf | inf | 6.5111 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2025/4 | 3 | inf | inf | 17.3092 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2026/0 | 1 | inf | inf | 9.3126 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2026/1 | 1 | inf | inf | 27.2337 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2026/2 | 1 | inf | inf | 9.61 | 1 |
| h1_atr_drop_low30_strict_completed | year_dow | 2026/4 | 1 | inf | inf | 12.3653 | 1 |

## Interpretation

- Stage27C validates Stage27B's strongest gate with strict completed-H1 anti-leakage logic.
- The primary gate is `h1_atr_drop_low30_strict_completed`, which keeps trades only when completed H1 ATR is above its prior rolling q30 threshold.
- A validated result remains research-only and requires a separate filtered forward-shadow tracker before any operational consideration.
- If strict completed-H1 validation materially degrades Stage27B's gate, the gate should stay review-only and not be added to any tracker.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files

- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_first_h1_atr_gate_validation.json`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_first_h1_atr_gate_validation.md`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_artifact_manifest.csv`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_enriched_h1_atr_trades.csv`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_gate_validation.csv`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_h1_atr_gate_splits.csv`
- `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_schema_diagnostic.csv`