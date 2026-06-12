# Stage25A Regime / No-Trade Filter Discovery

## Decision

```text
STAGE25A_HAS_FILTER_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow diagnostic only.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- Filters found here are not operational promotions; they require separate forward-shadow validation.

## Data / loader

- m1_path: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- h1_path: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- stage23c_trades_path: `/Users/vahid/Desktop/xauusd-trader/data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv`
- m1_rows: 1452943
- h1_rows: 24277
- m15_rows: 97018
- source_columns: `{"timestamp": "entry_time", "direction": "direction", "x1": "net_x1", "x4": "net_x4", "x6": "net_x6"}`

## Base Stage23C trade metrics

```json
{
  "events": 468,
  "pf_x1": 5.86384088059708,
  "pf_x4": 2.8795789427487484,
  "pf_x6": 1.6681425688004845,
  "total_x1": 1102.9809300000002,
  "total_x4": 611.58093,
  "total_x6": 283.98093000000017,
  "win_rate_x4": 0.7799145299145299,
  "median_x4": 1.0094300000000005
}
```

## Top filter diagnostics

| decision | filter_name | retained_events | retained_ratio | pf_x1 | pf_x4 | pf_x6 | improvement_pf_x4 | total_x4 | win_rate_x4 | median_x4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | keep_short_only | 204 | 0.4359 | 10.7117 | 5.5659 | 3.3384 | 2.6863 | 473.7086 | 0.8284 | 1.0523 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low30 | 327 | 0.6987 | 10.1321 | 5.4259 | 3.4502 | 2.5463 | 723.7062 | 0.8593 | 1.417 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low30 | 327 | 0.6987 | 8.7209 | 4.7405 | 3.0685 | 1.8609 | 700.2469 | 0.844 | 1.4054 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low30 | 330 | 0.7051 | 8.0541 | 4.4172 | 2.8479 | 1.5376 | 684.4102 | 0.8394 | 1.417 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_range_drop_low20 | 375 | 0.8013 | 8.4011 | 4.3524 | 2.6329 | 1.4728 | 697.9223 | 0.8293 | 1.1886 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | early_ny_range_drop_low20 | 375 | 0.8013 | 7.7697 | 4.1271 | 2.5426 | 1.2475 | 689.2687 | 0.8427 | 1.1886 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | diagnostic_drop_year_2022 | 351 | 0.75 | 7.4946 | 3.8824 | 2.3903 | 1.0028 | 647.3206 | 0.7892 | 1.1787 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low30 | 330 | 0.7051 | 7.1616 | 3.8335 | 2.4569 | 0.954 | 638.9909 | 0.8061 | 1.4054 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | asia_range_drop_low20 | 375 | 0.8013 | 7.2126 | 3.7925 | 2.3721 | 0.9129 | 670.7276 | 0.8133 | 1.1886 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_middle_30_70 | 192 | 0.4103 | 7.0011 | 3.636 | 2.2983 | 0.7564 | 374.2461 | 0.7708 | 1.1886 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | diagnostic_drop_year_2023 | 357 | 0.7628 | 6.7843 | 3.593 | 2.2144 | 0.7134 | 619.9431 | 0.8039 | 1.1496 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | prior_day_range_drop_low20 | 375 | 0.8013 | 6.5651 | 3.3996 | 2.1023 | 0.52 | 628.2329 | 0.7973 | 1.1787 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | drop_prior_day_aligned | 231 | 0.4936 | 6.7373 | 3.1983 | 1.8057 | 0.3187 | 317.4564 | 0.7835 | 0.8483 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low30 | 330 | 0.7051 | 6.3457 | 3.1873 | 1.9258 | 0.3078 | 514.0509 | 0.7697 | 1.1496 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_low20 | 375 | 0.8013 | 6.2932 | 3.1507 | 1.8747 | 0.2711 | 560.4885 | 0.7813 | 1.078 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_middle_20_80 | 285 | 0.609 | 6.0876 | 3.0431 | 1.8153 | 0.1635 | 427.2931 | 0.7614 | 1.087 |
| STAGE25A_FILTER_CANDIDATE_REVIEW_ONLY | london_eff_drop_high30 | 330 | 0.7051 | 6.0589 | 3.0305 | 1.7919 | 0.1509 | 471.7761 | 0.7848 | 1.0313 |
| STAGE25A_REJECT | keep_london_aligned | 468 | 1 | 5.8638 | 2.8796 | 1.6681 | 0 | 611.5809 | 0.7799 | 1.0094 |
| STAGE25A_REJECT | keep_entry_hour_13 | 468 | 1 | 5.8638 | 2.8796 | 1.6681 | 0 | 611.5809 | 0.7799 | 1.0094 |
| STAGE25A_REJECT | diagnostic_drop_year_2024 | 339 | 0.7244 | 5.5182 | 2.8136 | 1.7182 | -0.066 | 493.737 | 0.7522 | 0.8534 |
| STAGE25A_REJECT | london_eff_drop_high20 | 378 | 0.8077 | 5.6238 | 2.7465 | 1.5877 | -0.1331 | 478.3855 | 0.7646 | 0.9229 |
| STAGE25A_REJECT | keep_prior_day_aligned | 237 | 0.5064 | 5.2038 | 2.6253 | 1.5534 | -0.2543 | 294.1245 | 0.7764 | 1.087 |
| STAGE25A_REJECT | diagnostic_drop_year_2025 | 375 | 0.8013 | 5.5937 | 2.4941 | 1.2972 | -0.3855 | 358.9457 | 0.784 | 0.8483 |
| STAGE25A_REJECT | diagnostic_drop_year_2026 | 450 | 0.9615 | 4.5228 | 2.0031 | 1.0268 | -0.8765 | 326.3774 | 0.7711 | 0.9066 |
| STAGE25A_REJECT | asia_range_middle_30_70 | 189 | 0.4038 | 4.6397 | 1.9148 | 0.8124 | -0.9648 | 105.631 | 0.836 | 1.087 |
| STAGE25A_REJECT | early_ny_range_middle_30_70 | 189 | 0.4038 | 4.2069 | 1.8798 | 0.9101 | -0.9998 | 117.5435 | 0.8201 | 1.1496 |
| STAGE25A_REJECT | early_ny_range_middle_20_80 | 282 | 0.6026 | 4.3211 | 1.8382 | 0.8378 | -1.0414 | 158.5074 | 0.8191 | 1.036 |
| STAGE25A_REJECT | london_range_middle_30_70 | 186 | 0.3974 | 4.581 | 1.7761 | 0.6832 | -1.1035 | 86.1738 | 0.8333 | 0.9914 |
| STAGE25A_REJECT | keep_long_only | 264 | 0.5641 | 3.6618 | 1.6221 | 0.8345 | -1.2575 | 137.8724 | 0.7424 | 0.8641 |
| STAGE25A_REJECT | asia_range_middle_20_80 | 282 | 0.6026 | 3.6936 | 1.4814 | 0.6167 | -1.3982 | 99.153 | 0.7872 | 1.0274 |

## Interpretation

- This stage tests whether Stage23C's candidate can be improved by excluding bad regimes.
- A filter candidate here is research-only and must be forward-shadowed separately before any operational use.
- This hotfix specifically handles MT5/AMarkets tab-separated CSV exports so the header is not treated as one broken column.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.json`
- `data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.md`
- `data/reports/stage25a_regime_filter_discovery/stage25a_filter_candidates.csv`
- `data/reports/stage25a_regime_filter_discovery/stage25a_enriched_stage23c_trades.csv`