# Stage 22A Trend Pullback Short Targeted Exact Refinement

Generated UTC: `2026-06-11T13:16:21+00:00`
Tool version: `v1`

> Hard rule: research refinement only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Stage21B was positive but not robust enough for forward-shadow design.
- Run a limited exact-M1 refinement of the same trend-pullback short family.
- Do not perform a broad exhaustive grid.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- h1_rows: `25769`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`
- cost_usd: `0.35`
- bootstrap_n: `200`
- variants_tested: `576`
- fast: `False`

## Final decision
- final_decision: `REFINED_TREND_PULLBACK_WATCHLIST_ONLY`

## Counts
- promoted: `0`
- refined_watchlist: `18`

## Top variants
| Rank | Variant | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `trend_pullback_short_td7.5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 165 | 3.4375 | 1.287162 | 1.19 | 341.57 | 1.23319 | 1.132222 | 33 | 11.71 | 1.025025 | 109.77 | 1.191011 | 0.859331 | 10.021567 |
| 2 | `trend_pullback_short_td7.5_pb0.5_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 134 | 3.35 | 1.305461 | 1.41 | 337.43 | 1.257916 | 1.167903 | 27 | 79.36 | 1.203581 | 49.05 | 1.078489 | 0.784848 | 9.553699 |
| 3 | `trend_pullback_short_td12.5_pb2_slope2_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 117 | 3.441176 | 1.352199 | 0.24 | 283.76 | 1.29392 | 1.185357 | 24 | 51.3 | 1.208545 | 107.3 | 1.210301 | 0.934953 | 9.401315 |
| 4 | `trend_pullback_short_td5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 199 | 4.061224 | 1.267759 | 0.84 | 347.76 | 1.208713 | 1.099061 | 40 | 136.37 | 1.246641 | 96.95 | 1.163444 | 0.820286 | 9.250334 |
| 5 | `trend_pullback_short_td12.5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 105 | 2.916667 | 1.291214 | 0.84 | 256.83 | 1.244593 | 1.156547 | 21 | 107.5 | 1.633658 | 47.83 | 1.092547 | 0.758197 | 9.233147 |
| 6 | `trend_pullback_short_td12.5_pb2_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 128 | 3.555556 | 1.340116 | 0.15 | 284.0 | 1.278957 | 1.165511 | 26 | 37.62 | 1.148479 | 97.84 | 1.19176 | 0.936628 | 9.034759 |
| 7 | `trend_pullback_short_td12.5_pb2_slope0_sma505_ny_h8` | `KEEP_REFINED_WATCHLIST` | 122 | 3.388889 | 1.33874 | 0.285 | 277.14 | 1.279335 | 1.168813 | 25 | 45.0 | 1.182934 | 97.84 | 1.19176 | 0.819461 | 8.965001 |
| 8 | `trend_pullback_short_td12.5_pb2_slope5_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 90 | 3.103448 | 1.294774 | 1.365 | 214.79 | 1.246454 | 1.155452 | 18 | 22.82 | 1.107333 | 48.15 | 1.095469 | 0.683075 | 8.94676 |
| 9 | `trend_pullback_short_td12.5_pb2_slope2_sma505_ny_h8` | `KEEP_REFINED_WATCHLIST` | 113 | 3.323529 | 1.326358 | 0.24 | 259.99 | 1.270025 | 1.16493 | 23 | 40.98 | 1.166592 | 96.98 | 1.190075 | 0.765166 | 8.764783 |
| 10 | `trend_pullback_short_td7.5_pb2_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 236 | 4.72 | 1.228385 | 0.355 | 306.31 | 1.161876 | 1.039864 | 48 | 105.65 | 1.17833 | 93.19 | 1.150583 | 0.87608 | 8.579833 |
| 11 | `trend_pullback_short_td12.5_pb2_slope0_sma5010_ny_h8` | `KEEP_REFINED_WATCHLIST` | 114 | 3.166667 | 1.318616 | 0.15 | 250.84 | 1.261307 | 1.154639 | 23 | 9.05 | 1.038027 | 56.29 | 1.113754 | 0.774708 | 8.113855 |
| 12 | `trend_pullback_short_td10_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 137 | 3.186047 | 1.232034 | 1.19 | 247.94 | 1.1832 | 1.091411 | 28 | 12.17 | 1.033906 | 8.32 | 1.014659 | 0.770499 | 7.967944 |
| 13 | `trend_pullback_short_td7.5_pb2_slope0_sma505_ny_h12` | `KEEP_REFINED_WATCHLIST` | 195 | 3.9 | 1.18349 | 0.65 | 248.2 | 1.129777 | 1.029845 | 39 | 14.6 | 1.026723 | 42.36 | 1.069371 | 0.788797 | 7.814759 |
| 14 | `trend_pullback_short_td12.5_pb2_slope2_sma5010_ny_h8` | `KEEP_REFINED_WATCHLIST` | 107 | 3.147059 | 1.279292 | -0.1 | 218.2 | 1.225788 | 1.126052 | 22 | 8.19 | 1.034413 | 55.43 | 1.112016 | 0.758416 | 7.559374 |
| 15 | `trend_pullback_short_td5_pb0.5_slope0_sma500_ny_h12` | `KEEP_REFINED_WATCHLIST` | 237 | 4.74 | 1.180827 | 0.26 | 276.86 | 1.123334 | 1.01689 | 48 | 74.37 | 1.104582 | 10.08 | 1.015813 | 0.860097 | 7.066941 |
| 16 | `trend_pullback_short_td10_pb0.5_slope0_sma505_ny_h12` | `KEEP_REFINED_WATCHLIST` | 120 | 3.333333 | 1.232575 | 0.335 | 248.79 | 1.189636 | 1.108346 | 24 | 3.74 | 1.014161 | -120.46 | 0.815748 | 0.79819 | 6.763679 |
| 17 | `trend_pullback_short_td7.5_pb1_slope0_sma500_ny_h12` | `KEEP_REFINED_WATCHLIST` | 188 | 3.836735 | 1.192092 | -0.085 | 271.18 | 1.142134 | 1.048751 | 38 | 22.76 | 1.036812 | -24.97 | 0.962555 | 0.757655 | 6.525648 |
| 18 | `trend_pullback_short_td5_pb0_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 212 | 4.24 | 1.199112 | -0.1 | 254.37 | 1.13686 | 1.02275 | 43 | 9.78 | 1.016109 | -2.68 | 0.99577 | 0.819902 | 5.995693 |
| 19 | `trend_pullback_short_td5_pb0.5_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 165 | 3.510638 | 1.275963 | 1.08 | 338.88 | 1.223981 | 1.126282 | 33 | -21.28 | 0.960992 | 78.14 | 1.129906 | 0.842041 | 9.163695 |
| 20 | `trend_pullback_short_td10_pb0.5_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 110 | 3.055556 | 1.246163 | 1.865 | 247.81 | 1.204279 | 1.1246 | 22 | 63.49 | 1.268502 | -52.4 | 0.915187 | 0.709405 | 8.814711 |
| 21 | `trend_pullback_short_td10_pb1_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 120 | 3.0 | 1.214076 | 1.865 | 231.48 | 1.172059 | 1.092364 | 24 | -24.44 | 0.936531 | -58.36 | 0.906443 | 0.757036 | 8.186737 |
| 22 | `trend_pullback_short_td7.5_pb2_slope0_sma505_ny_h8` | `REJECT_REFINED_WEAK` | 218 | 4.36 | 1.230509 | 0.4 | 297.02 | 1.166471 | 1.048496 | 44 | -101.5 | 0.827287 | 93.19 | 1.150583 | 0.896834 | 8.152578 |
| 23 | `trend_pullback_short_td7.5_pb1_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 148 | 3.288889 | 1.255597 | 0.755 | 306.65 | 1.208051 | 1.118482 | 30 | -26.04 | 0.947417 | 43.09 | 1.0683 | 0.822509 | 8.034493 |
| 24 | `trend_pullback_short_td7.5_pb2_slope2_sma505_ny_h8` | `REJECT_REFINED_WEAK` | 177 | 3.847826 | 1.196622 | 0.38 | 227.44 | 1.139409 | 1.03323 | 36 | -77.69 | 0.846256 | 92.33 | 1.149194 | 0.804168 | 7.881564 |
| 25 | `trend_pullback_short_td7.5_pb2_slope0_sma5010_ny_h8` | `REJECT_REFINED_WEAK` | 186 | 3.875 | 1.244428 | 0.59 | 284.94 | 1.183693 | 1.070981 | 38 | -104.95 | 0.805425 | 51.64 | 1.08557 | 0.868912 | 7.860107 |
| 26 | `trend_pullback_short_td5_pb2_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 169 | 3.673913 | 1.181599 | 0.67 | 223.47 | 1.13044 | 1.034879 | 34 | 30.29 | 1.06227 | 73.28 | 1.12354 | 0.769846 | 7.858503 |
| 27 | `trend_pullback_short_td12.5_pb2_slope5_sma505_ny_h8` | `REJECT_REFINED_WEAK` | 89 | 3.068966 | 1.255579 | 1.32 | 186.23 | 1.208522 | 1.1199 | 18 | -38.01 | 0.844781 | 19.59 | 1.038842 | 0.71077 | 7.803944 |
| 28 | `trend_pullback_short_td7.5_pb2_slope2_sma500_ny_h8` | `REJECT_REFINED_WEAK` | 187 | 3.978723 | 1.191765 | 0.13 | 228.57 | 1.13319 | 1.024897 | 38 | -59.57 | 0.882114 | 102.65 | 1.16587 | 0.808733 | 7.692208 |
| 29 | `trend_pullback_short_td7.5_pb0.5_slope0_sma5010_ny_h16` | `REJECT_REFINED_WEAK` | 127 | 3.175 | 1.19937 | 1.81 | 253.01 | 1.161589 | 1.089695 | 26 | -66.71 | 0.887169 | -59.61 | 0.923543 | 0.758196 | 7.482378 |
| 30 | `trend_pullback_short_td7.5_pb2_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 145 | 3.372093 | 1.136049 | -0.26 | 161.43 | 1.091285 | 1.007258 | 29 | 95.62 | 1.261235 | 91.77 | 1.159689 | 0.673339 | 7.4051 |

## Promoted refined candidates
- none

## Interpretation
- Stage22A is targeted exact historical refinement, not forward proof.
- Promoted variants may go to a later forward-shadow collector design.
- Watchlist-only variants must not be added to Stage18A.
- If no promotion appears, this trend-pullback short family should be frozen as watchlist-only.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refinement_summary.csv`
- promoted_csv: `data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refined_promoted.csv`
- trades_csv: `data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refinement_trades.csv`
- json: `data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refinement.json`
- md: `data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refinement.md`
