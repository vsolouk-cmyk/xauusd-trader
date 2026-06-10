# Stage 8A Regime Discovery Lab

Generated UTC: `2026-06-09T13:32:23+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- h1_rows: `24225`
- m1_rows: `1449867`
- horizons: `[3, 6, 12]`
- stride_h1: `3`
- macro_windows: `5`
- probes: `47406`

## Top regime/opportunity map
| Group | Value | Direction | H | Diagnosis | Edge score | Samples | Avg close | MFE med | MAE med | TP15 first | SL15 first |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| year | 2025 | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 3.428442 | 1952 | 2.813689 | 15.59 | -12.035 | 0.441086 | 0.351947 |
| compression_bucket | mid_high | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 3.189388 | 2282 | 2.727949 | 9.29 | -7.375 | 0.284838 | 0.221297 |
| h4_trend | up | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 3.130265 | 3199 | 2.535392 | 10.87 | -8.0 | 0.33573 | 0.250391 |
| session | london_ny_overlap | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 2.799364 | 1397 | 2.468654 | 9.01 | -8.13 | 0.285612 | 0.236936 |
| session | new_york | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 2.501355 | 1698 | 2.266961 | 6.3 | -5.205 | 0.189635 | 0.156655 |
| h1_trend | up | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 2.483327 | 3016 | 2.061575 | 9.955 | -8.105 | 0.307361 | 0.247679 |
| vol_bucket | mid_high | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 2.11118 | 2347 | 1.869165 | 9.54 | -8.65 | 0.295271 | 0.260332 |
| h4_trend | up | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 2.0891 | 3199 | 1.742116 | 7.02 | -5.59 | 0.220694 | 0.170678 |
| session | new_york | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 2.028258 | 1698 | 1.946985 | 3.995 | -3.4 | 0.114252 | 0.104829 |
| session | other | long | 3 | PROMISING_REGIME_RESEARCH_ONLY | 2.027086 | 278 | 1.825647 | 2.94 | -1.33 | 0.079137 | 0.05036 |
| impulse_bucket | shock_impulse | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.928549 | 773 | 1.642652 | 9.12 | -8.15 | 0.278137 | 0.238034 |
| year | 2025 | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.809189 | 1952 | 1.468514 | 10.455 | -8.645 | 0.325307 | 0.27459 |
| vol_bucket | mid_low | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.544965 | 2298 | 1.383956 | 9.075 | -8.09 | 0.271105 | 0.251958 |
| h4_trend | up | long | 3 | PROMISING_REGIME_RESEARCH_ONLY | 1.500245 | 3199 | 1.353951 | 4.66 | -3.71 | 0.129415 | 0.109409 |
| year | 2024 | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.426159 | 1960 | 1.145036 | 9.045 | -7.09 | 0.264286 | 0.221939 |
| h1_trend | up | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.310381 | 3016 | 1.078946 | 6.42 | -5.7 | 0.203581 | 0.170424 |
| impulse_bucket | normal | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.304226 | 5609 | 1.089929 | 9.2 | -7.87 | 0.274737 | 0.245142 |
| session | other | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.299066 | 278 | 1.324245 | 5.425 | -3.08 | 0.129496 | 0.125899 |
| macro_bucket | normal | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.287759 | 7890 | 1.07344 | 9.31 | -8.2 | 0.280608 | 0.250317 |
| compression_bucket | mid_low | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.210814 | 2304 | 1.154826 | 8.77 | -8.295 | 0.267361 | 0.259983 |
| impulse_bucket | shock_impulse | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.195098 | 773 | 0.977762 | 7.61 | -6.81 | 0.223803 | 0.192755 |
| session | other | long | 12 | PROMISING_REGIME_RESEARCH_ONLY | 1.158707 | 278 | 1.007626 | 8.54 | -5.765 | 0.201439 | 0.172662 |
| compression_bucket | mid_high | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.138865 | 2282 | 1.00784 | 5.71 | -4.95 | 0.173532 | 0.154689 |
| vol_bucket | mid_low | long | 6 | PROMISING_REGIME_RESEARCH_ONLY | 1.010654 | 2298 | 0.958869 | 5.53 | -5.38 | 0.167972 | 0.163185 |
| macro_bucket | macro_high | short | 6 | IGNORE_TOO_FEW_SAMPLES | 52.815 | 2 | 45.815 | 57.29 | -13.235 | 1.0 | 0.0 |
| macro_bucket | macro_high | short | 12 | IGNORE_TOO_FEW_SAMPLES | 50.115 | 2 | 43.115 | 59.045 | -13.235 | 1.0 | 0.0 |
| macro_bucket | macro_high | short | 3 | IGNORE_TOO_FEW_SAMPLES | 48.93 | 2 | 41.93 | 46.185 | -13.235 | 1.0 | 0.0 |
| macro_bucket | shock | long | 12 | IGNORE_TOO_FEW_SAMPLES | 8.850001 | 11 | 8.304545 | 20.91 | -14.75 | 0.454545 | 0.454545 |
| macro_bucket | shock | long | 6 | IGNORE_TOO_FEW_SAMPLES | 2.735455 | 11 | 3.19 | 11.47 | -14.75 | 0.363636 | 0.454545 |
| h4_trend | down | short | 3 | WATCHLIST_REGIME | 0.893138 | 2029 | 0.728034 | 3.98 | -3.46 | 0.116313 | 0.093149 |
| impulse_bucket | expanded | long | 12 | WATCHLIST_REGIME | 0.888479 | 1521 | 0.717541 | 9.77 | -9.41 | 0.304405 | 0.278107 |
| vol_bucket | low | long | 12 | WATCHLIST_REGIME | 0.810551 | 1629 | 0.619632 | 9.23 | -7.58 | 0.259669 | 0.230816 |
| year | 2025 | long | 3 | WATCHLIST_REGIME | 0.795638 | 1951 | 0.743357 | 7.2 | -6.25 | 0.194772 | 0.186571 |
| compression_bucket | mid_low | long | 6 | WATCHLIST_REGIME | 0.756558 | 2304 | 0.737891 | 5.81 | -5.8 | 0.18099 | 0.178819 |
| vol_bucket | mid_high | long | 6 | WATCHLIST_REGIME | 0.753028 | 2347 | 0.679318 | 6.49 | -6.26 | 0.200256 | 0.188752 |
| macro_bucket | shock | long | 3 | IGNORE_TOO_FEW_SAMPLES | 0.733637 | 11 | 1.37 | 9.92 | -11.78 | 0.363636 | 0.454545 |
| h1_trend | neutral | long | 12 | WATCHLIST_REGIME | 0.731549 | 2682 | 0.654739 | 9.06 | -8.715 | 0.272931 | 0.261745 |
| impulse_bucket | normal | long | 6 | WATCHLIST_REGIME | 0.722681 | 5609 | 0.652435 | 5.66 | -5.18 | 0.173828 | 0.1642 |
| year | 2026 | short | 3 | WATCHLIST_REGIME | 0.699082 | 847 | 0.38503 | 15.18 | -13.56 | 0.423849 | 0.376623 |
| macro_bucket | normal | long | 6 | WATCHLIST_REGIME | 0.635355 | 7890 | 0.553984 | 6.07 | -5.69 | 0.186946 | 0.175285 |
| session | london_ny_overlap | long | 6 | WATCHLIST_REGIME | 0.610836 | 1397 | 0.384639 | 7.8 | -7.49 | 0.248389 | 0.21403 |
| h1_trend | neutral | long | 6 | WATCHLIST_REGIME | 0.584499 | 2682 | 0.599787 | 6.025 | -6.1 | 0.185309 | 0.187919 |
| year | 2024 | long | 6 | WATCHLIST_REGIME | 0.582184 | 1960 | 0.54749 | 5.805 | -4.725 | 0.132143 | 0.127041 |
| h1_trend | up | long | 3 | WATCHLIST_REGIME | 0.577937 | 3016 | 0.548757 | 4.16 | -3.805 | 0.117374 | 0.114058 |
| h4_trend | neutral | short | 3 | WATCHLIST_REGIME | 0.560703 | 2669 | 0.416081 | 3.96 | -3.92 | 0.128887 | 0.108655 |
| compression_bucket | low | long | 12 | WATCHLIST_REGIME | 0.534343 | 1663 | 0.43092 | 9.56 | -9.15 | 0.287432 | 0.273001 |
| compression_bucket | mid_high | long | 3 | WATCHLIST_REGIME | 0.512816 | 2282 | 0.497038 | 4.07 | -3.495 | 0.104733 | 0.102103 |
| year | 2023 | long | 12 | WATCHLIST_REGIME | 0.496889 | 1928 | 0.393154 | 5.795 | -5.84 | 0.145747 | 0.131224 |
| vol_bucket | low | long | 6 | WATCHLIST_REGIME | 0.487217 | 1629 | 0.463892 | 5.44 | -4.28 | 0.149171 | 0.145488 |
| compression_bucket | high | short | 12 | WATCHLIST_REGIME | 0.483044 | 1654 | 0.681959 | 8.18 | -9.985 | 0.256348 | 0.287183 |
| session | london | long | 12 | WATCHLIST_REGIME | 0.468105 | 2094 | 0.252727 | 11.255 | -10.625 | 0.341929 | 0.311843 |
| compression_bucket | low | long | 6 | WATCHLIST_REGIME | 0.461627 | 1663 | 0.410517 | 6.77 | -6.88 | 0.20926 | 0.202646 |
| session | new_york | long | 3 | WATCHLIST_REGIME | 0.456225 | 1692 | 0.508824 | 2.815 | -2.66 | 0.070331 | 0.078014 |
| h4_trend | neutral | short | 6 | WATCHLIST_REGIME | 0.389528 | 2672 | 0.251426 | 5.83 | -5.775 | 0.19012 | 0.170284 |
| session | asia | long | 6 | WATCHLIST_REGIME | 0.350313 | 2436 | 0.35688 | 5.745 | -5.265 | 0.156814 | 0.157635 |
| h4_trend | down | short | 6 | WATCHLIST_REGIME | 0.346864 | 2032 | 0.288794 | 5.83 | -5.23 | 0.165354 | 0.156496 |
| impulse_bucket | shock_impulse | long | 3 | WATCHLIST_REGIME | 0.341019 | 773 | 0.419935 | 5.23 | -5.12 | 0.151358 | 0.160414 |
| vol_bucket | mid_high | long | 3 | WATCHLIST_REGIME | 0.329375 | 2347 | 0.323413 | 4.36 | -4.05 | 0.118875 | 0.117171 |
| h1_trend | down | long | 12 | WATCHLIST_REGIME | 0.320109 | 2205 | 0.227138 | 8.88 | -7.81 | 0.253968 | 0.241723 |
| year | 2026 | short | 12 | WATCHLIST_REGIME | 0.311984 | 847 | -0.057556 | 32.15 | -29.81 | 0.5183 | 0.455726 |

## Interpretation
- `PROMISING_REGIME_RESEARCH_ONLY`: regime has favorable forward distribution; it is not yet a strategy.
- `WATCHLIST_REGIME`: worth deeper slicing, but not enough for entry rules.
- `AVOID_OR_REVERSE_CANDIDATE`: forward behavior is negative for that direction.
- This stage helps design the next thesis from distribution, not from losing-trade deletion.

## Decision
- If no promising regimes appear, mechanical price-only strategy should be paused.
- If promising regimes appear, Stage 8B must build one thesis from the strongest regime only.
- No EA or order workflow changes are allowed from Stage 8A alone.
