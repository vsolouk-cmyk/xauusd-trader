# Stage28B ML-lite Meta-Feature Screen

## Decision

```text
STAGE28B_STRICT_HAS_FORWARD_SAFE_META_GATE_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow feature screening only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.
- Market candle sanity is DB-first via the validated Stage25C loader; AMarkets CSV market fallback is disabled.
- Trade artifact is used only as research evidence for meta-label/gate screening.
- Hotfix2 strict mode: only entry-time forward-safe whitelisted features are screened.
- Leak-prone fields such as full-day range/high/low/close, early-NY fields, exit/tp/sl, and absolute price-level columns are excluded.
- This is ML-lite/nonlinear feature screening, not a black-box prediction model.

## DB source of truth

- loader_mode: `reused:app.stage25c_deduped_filter_validation.load_bars_from_db`
- db_path: `data/local/xauusd_local_store.sqlite`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1534149`
- h1_rows: `25607`

## Trade artifact

- selected_artifact: `data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv`
- rows: `100`
- rows_after_event_dedup: `100`
- time_column_used: `entry_time`

## Base metrics

```json
{
  "events": 100,
  "pf_x1": 5.578964,
  "pf_x4": 2.851412,
  "pf_x6": 1.653422,
  "boot_pf_p05_x4": 1.862959,
  "median_x4": 1.02936,
  "total_x4": 127.61561,
  "win_rate_x4": 0.81,
  "years_positive_x4": 4,
  "year_count": 5
}
```

## Counts

- strict_forward_safe: `True`
- feature_count: `9`
- excluded_feature_count: `47`
- single_gate_count: `148`
- pairwise_gate_count: `206`
- gate_candidates_tested: `354`
- gate_candidate_review_count: `86`
- watchlist_only_count: `84`

## Features screened

`year`, `month`, `prior_day_range`, `asia_range`, `asia_eff`, `london_range`, `london_eff`, `prior_day_aligned`, `dow`

## Top meta-gate diagnostics

| decision                            | gate_name                                                         | gate_kind        |   retained_events |   retained_ratio |    pf_x4 |    pf_x6 |   boot_pf_p05_x4 |   median_x4 |   total_x4 |   win_rate_x4 |   years_positive_x4 |   year_count |   improvement_pf_x4 |   improvement_pf_x6 |   improvement_total_x4 |   rank_score |
|:------------------------------------|:------------------------------------------------------------------|:-----------------|------------------:|-----------------:|---------:|---------:|-----------------:|------------:|-----------:|--------------:|--------------------:|-------------:|--------------------:|--------------------:|-----------------------:|-------------:|
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__prior_day_range_keep_ge_q25 | pairwise_combo   |                44 |             0.44 | 30.3197  | 20.4059  |          8.60195 |     2.03436 |    152.441 |      0.977273 |                   5 |            5 |            27.4683  |            18.7524  |               24.825   |     18.8585  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__prior_day_range_keep_ge_q30 | pairwise_combo   |                43 |             0.43 | 30.1214  | 20.353   |          7.16363 |     2.14814 |    151.409 |      0.976744 |                   5 |            5 |            27.27    |            18.6996  |               23.7937  |     18.7529  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__prior_day_range_keep_ge_q25 | pairwise_combo   |                32 |             0.32 | 28.0148  | 20.5394  |          6.82193 |     2.64421 |    140.456 |      0.96875  |                   5 |            5 |            25.1633  |            18.886   |               12.8409  |     17.8553  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__prior_day_range_keep_ge_q30 | pairwise_combo   |                32 |             0.32 | 28.0148  | 20.5394  |          6.82193 |     2.64421 |    140.456 |      0.96875  |                   5 |            5 |            25.1633  |            18.886   |               12.8409  |     17.8553  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__prior_day_range_keep_ge_q35 | pairwise_combo   |                41 |             0.41 | 28.2015  | 19.0716  |          7.56313 |     2.14814 |    141.427 |      0.97561  |                   5 |            5 |            25.35    |            17.4182  |               13.8116  |     17.5035  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__prior_day_range_keep_ge_q40 | pairwise_combo   |                39 |             0.39 | 27.2413  | 18.9787  |          6.1291  |     2.14814 |    136.435 |      0.974359 |                   5 |            5 |            24.3899  |            17.3253  |                8.8193  |     17.0425  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__prior_day_range_keep_ge_q35 | pairwise_combo   |                31 |             0.31 | 26.2236  | 19.114   |          7.57266 |     2.593   |    131.144 |      0.967742 |                   5 |            5 |            23.3722  |            17.4606  |                3.52829 |     16.6212  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | london_range_keep_ge_q70                                          | numeric_quantile |                30 |             0.3  | 12.1921  |  9.41282 |          4.46627 |     2.77129 |    131.996 |      0.933333 |                   5 |            5 |             9.34069 |             7.7594  |                4.38043 |      7.31607 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q35__AND__prior_day_range_keep_ge_q25 | pairwise_combo   |                48 |             0.48 | 11.6967  |  7.97417 |          4.56649 |     1.73672 |    146.03  |      0.9375   |                   5 |            5 |             8.84524 |             6.32074 |               18.4143  |      6.68555 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q35__AND__prior_day_range_keep_ge_q30 | pairwise_combo   |                47 |             0.47 | 11.6211  |  7.95361 |          4.71337 |     1.849   |    144.999 |      0.93617  |                   5 |            5 |             8.7697  |             6.30019 |               17.3831  |      6.66693 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q35__AND__prior_day_range_keep_ge_q35 | pairwise_combo   |                44 |             0.44 | 10.8029  |  7.40303 |          4.62463 |     1.88478 |    133.828 |      0.931818 |                   5 |            5 |             7.95145 |             5.74961 |                6.21234 |      6.11873 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q35__AND__prior_day_range_keep_ge_q40 | pairwise_combo   |                42 |             0.42 | 10.4372  |  7.24481 |          4.94883 |     1.88478 |    128.836 |      0.928571 |                   5 |            5 |             7.58576 |             5.59139 |                1.22005 |      5.95434 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__drop_year_2022              | pairwise_combo   |                50 |             0.5  | 10.1633  |  7.13813 |          4.26311 |     2.07915 |    152.963 |      0.94     |                   4 |            4 |             7.31191 |             5.4847  |               25.3477  |      5.70024 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | london_range_keep_ge_q60                                          | numeric_quantile |                40 |             0.4  |  9.59536 |  7.09865 |          4.2361  |     2.17515 |    143.482 |      0.925    |                   5 |            5 |             6.74395 |             5.44523 |               15.8667  |      5.42376 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__asia_range_keep_ge_q25      | pairwise_combo   |                38 |             0.38 |  9.49739 |  7.13244 |          3.90131 |     2.26129 |    141.847 |      0.921053 |                   5 |            5 |             6.64598 |             5.47902 |               14.2314  |      5.3386  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__drop_year_2022              | pairwise_combo   |                38 |             0.38 |  9.46425 |  7.05701 |          4.03771 |     2.26129 |    141.294 |      0.921053 |                   4 |            4 |             6.61284 |             5.40358 |               13.6781  |      5.32151 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__asia_range_keep_ge_q30      | pairwise_combo   |                37 |             0.37 |  9.41112 |  7.09306 |          3.87058 |     2.33929 |    140.407 |      0.918919 |                   5 |            5 |             6.55971 |             5.43964 |               12.7913  |      5.28285 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__asia_range_keep_ge_q35      | pairwise_combo   |                35 |             0.35 |  9.26248 |  7.03552 |          4.0551  |     2.593   |    137.926 |      0.914286 |                   5 |            5 |             6.41107 |             5.3821  |               10.31    |      5.22538 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q60__AND__asia_range_keep_ge_q40      | pairwise_combo   |                34 |             0.34 |  9.21626 |  7.03171 |          3.78677 |     2.64421 |    137.154 |      0.911765 |                   5 |            5 |             6.36485 |             5.37829 |                9.5384  |      5.16268 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q65__AND__asia_range_keep_ge_q25      | pairwise_combo   |                33 |             0.33 |  8.8658  |  6.75767 |          4.14669 |     2.593   |    131.304 |      0.909091 |                   5 |            5 |             6.01439 |             5.10425 |                3.68825 |      4.97625 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | london_range_keep_ge_q65                                          | numeric_quantile |                35 |             0.35 |  8.96377 |  6.7267  |          3.724   |     2.167   |    132.939 |      0.914286 |                   5 |            5 |             6.11235 |             5.07328 |                5.32354 |      4.94864 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q65__AND__drop_year_2022              | pairwise_combo   |                33 |             0.33 |  8.83266 |  6.68506 |          4.08737 |     2.593   |    130.751 |      0.909091 |                   4 |            4 |             5.98125 |             5.03163 |                3.13497 |      4.93066 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q65__AND__asia_range_keep_ge_q30      | pairwise_combo   |                32 |             0.32 |  8.77953 |  6.71828 |          3.86755 |     2.64421 |    129.864 |      0.90625  |                   5 |            5 |             5.92812 |             5.06486 |                2.24811 |      4.88324 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__asia_range_keep_ge_q60      | pairwise_combo   |                31 |             0.31 |  8.82056 |  6.79198 |          3.36995 |     2.72586 |    130.549 |      0.903226 |                   5 |            5 |             5.96915 |             5.13856 |                2.93305 |      4.84868 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | london_range_keep_ge_q40                                          | numeric_quantile |                60 |             0.6  |  8.51255 |  5.65752 |          3.88328 |     1.51954 |    157.316 |      0.933333 |                   5 |            5 |             5.66114 |             4.0041  |               29.7006  |      4.46123 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__asia_range_keep_ge_q25      | pairwise_combo   |                52 |             0.52 |  8.23096 |  5.79262 |          3.87274 |     1.98143 |    151.42  |      0.923077 |                   5 |            5 |             5.37955 |             4.1392  |               23.8041  |      4.36947 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__asia_range_keep_ge_q30      | pairwise_combo   |                49 |             0.49 |  8.10624 |  5.81715 |          3.95148 |     2.116   |    148.808 |      0.918367 |                   5 |            5 |             5.25483 |             4.16373 |               21.1923  |      4.33101 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__asia_range_keep_ge_q35      | pairwise_combo   |                46 |             0.46 |  7.94724 |  5.76542 |          3.85412 |     2.1535  |    145.478 |      0.913043 |                   5 |            5 |             5.09583 |             4.112   |               17.8627  |      4.22784 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q40__AND__asia_range_keep_ge_q40      | pairwise_combo   |                45 |             0.45 |  7.91039 |  5.76241 |          3.35152 |     2.15886 |    144.707 |      0.911111 |                   5 |            5 |             5.05898 |             4.10899 |               17.0912  |      4.13447 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q20__AND__prior_day_range_keep_ge_q40 | pairwise_combo   |                48 |             0.48 |  8.08325 |  5.37758 |          3.29405 |     1.73672 |    129.795 |      0.916667 |                   5 |            5 |             5.23184 |             3.72416 |                2.17947 |      4.08968 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q25__AND__prior_day_range_keep_ge_q40 | pairwise_combo   |                47 |             0.47 |  7.9761  |  5.32008 |          3.67794 |     1.62443 |    127.832 |      0.914894 |                   5 |            5 |             5.12469 |             3.66666 |                0.21604 |      4.0813  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q30__AND__prior_day_range_keep_ge_q25 | pairwise_combo   |                53 |             0.53 |  7.48147 |  4.98503 |          3.49234 |     1.56186 |    141.101 |      0.90566  |                   5 |            5 |             4.63005 |             3.3316  |               13.485   |      3.73336 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q30__AND__prior_day_range_keep_ge_q30 | pairwise_combo   |                52 |             0.52 |  7.43409 |  4.97233 |          3.34098 |     1.59315 |    140.069 |      0.903846 |                   4 |            5 |             4.58268 |             3.31891 |               12.4537  |      3.68503 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q30__AND__prior_day_range_keep_ge_q25   | pairwise_combo   |                51 |             0.51 |  7.16773 |  4.81457 |          3.54305 |     1.849   |    138.6   |      0.901961 |                   4 |            5 |             4.31632 |             3.16115 |               10.9848  |      3.54765 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q30__AND__prior_day_range_keep_ge_q30   | pairwise_combo   |                51 |             0.51 |  7.16773 |  4.81457 |          3.54305 |     1.849   |    138.6   |      0.901961 |                   4 |            5 |             4.31632 |             3.16115 |               10.9848  |      3.54765 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q35__AND__prior_day_range_keep_ge_q25   | pairwise_combo   |                47 |             0.47 |  7.01615 |  4.83838 |          3.16109 |     1.92057 |    135.194 |      0.893617 |                   4 |            5 |             4.16473 |             3.18496 |                7.57838 |      3.42728 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q35__AND__prior_day_range_keep_ge_q30   | pairwise_combo   |                47 |             0.47 |  7.01615 |  4.83838 |          3.16109 |     1.92057 |    135.194 |      0.893617 |                   4 |            5 |             4.16473 |             3.18496 |                7.57838 |      3.42728 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__london_range_keep_ge_q20__AND__prior_day_range_keep_ge_q35 | pairwise_combo   |                51 |             0.51 |  7.03319 |  4.63827 |          3.45855 |     1.62443 |    131.342 |      0.901961 |                   4 |            5 |             4.18178 |             2.98485 |                3.72612 |      3.42154 |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q40__AND__prior_day_range_keep_ge_q25   | pairwise_combo   |                43 |             0.43 |  6.88889 |  4.89872 |          3.16627 |     2.14814 |    132.334 |      0.883721 |                   4 |            5 |             4.03748 |             3.2453  |                4.71882 |      3.3869  |
| STAGE28B_GATE_CANDIDATE_REVIEW_ONLY | combo__asia_range_keep_ge_q40__AND__prior_day_range_keep_ge_q30   | pairwise_combo   |                43 |             0.43 |  6.88889 |  4.89872 |          3.16627 |     2.14814 |    132.334 |      0.883721 |                   4 |            5 |             4.03748 |             3.2453  |                4.71882 |      3.3869  |

## Top gate split diagnostics

No rows.

## Interpretation

- Stage28B Hotfix2 screens only forward-safe meta-label/gate features around the strongest Stage23/25 lineage.
- The earlier raw Stage28B top day_range gates are treated as leakage diagnostics, not deployable candidates.
- A candidate here remains research-only and requires a dedicated validation stage before any forward tracker.
- If no strict meta-gate survives, the next useful step is adding richer exogenous/macro/news proxy features rather than mutating raw OHLC entries.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage28a_discovery_factory_batch_runner
python3 -m app.stage28b_ml_meta_feature_screen
```

## Output files

- `data/reports/stage28b_ml_meta_feature_screen/stage28b_ml_meta_feature_screen.md`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_ml_meta_feature_screen.json`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_meta_gate_candidates.csv`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_top_gate_splits.csv`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_artifact_manifest.csv`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_normalized_lineage_trades.csv`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_excluded_features.csv`
- `data/reports/stage28b_ml_meta_feature_screen/stage28b_db_schema_diagnostic.json`
