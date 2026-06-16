# Stage 22A v2 Trend Pullback Short Hybrid Refinement

Generated UTC: `2026-06-11T13:57:53+00:00`
Tool version: `v2_hybrid_proxy_then_exact`

> Hard rule: research refinement only. No EA change, no automatic trading, no paper/live authorization.

## Why v2
- The old full exact grid is too slow.
- v2 first ranks all variants with fast M15 proxy replay.
- v2 exact-replays only top proxy candidates with M1 path.
- Bootstrap runs only on exact finalists.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- h1_rows: `25769`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`
- cost_usd: `0.35`
- bootstrap_n: `100`
- exact_top_n: `30`
- fast: `False`
- variants_total: `576`
- variants_exact_replayed: `30`

## Final decision
- final_decision: `REFINED_TREND_PULLBACK_WATCHLIST_ONLY`

## Counts
- proxy_exact_candidates: `55`
- exact_replayed: `30`
- promoted: `0`
- watchlist: `18`

## Exact replay ranking
| Rank | Variant | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `trend_pullback_short_td7.5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 165 | 3.4375 | 1.287162 | 1.19 | 341.57 | 1.23319 | 1.132222 | 33 | 11.71 | 1.025025 | 109.77 | 1.191011 | 0.908652 | 10.081568 |
| 2 | `trend_pullback_short_td7.5_pb0.5_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 134 | 3.35 | 1.305461 | 1.41 | 337.43 | 1.257916 | 1.167903 | 27 | 79.36 | 1.203581 | 49.05 | 1.078489 | 0.836231 | 9.393699 |
| 3 | `trend_pullback_short_td5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 199 | 4.061224 | 1.267759 | 0.84 | 347.76 | 1.208713 | 1.099061 | 40 | 136.37 | 1.246641 | 96.95 | 1.163444 | 0.821494 | 9.170334 |
| 4 | `trend_pullback_short_td12.5_pb2_slope2_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 117 | 3.441176 | 1.352199 | 0.24 | 283.76 | 1.29392 | 1.185357 | 24 | 51.3 | 1.208545 | 107.3 | 1.210301 | 0.867171 | 9.161315 |
| 5 | `trend_pullback_short_td12.5_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 105 | 2.916667 | 1.291214 | 0.84 | 256.83 | 1.244593 | 1.156547 | 21 | 107.5 | 1.633658 | 47.83 | 1.092547 | 0.754947 | 9.033147 |
| 6 | `trend_pullback_short_td12.5_pb2_slope0_sma505_ny_h8` | `KEEP_REFINED_WATCHLIST` | 122 | 3.388889 | 1.33874 | 0.285 | 277.14 | 1.279335 | 1.168813 | 25 | 45.0 | 1.182934 | 97.84 | 1.19176 | 0.82378 | 8.865001 |
| 7 | `trend_pullback_short_td7.5_pb2_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 236 | 4.72 | 1.228385 | 0.355 | 306.31 | 1.161876 | 1.039864 | 48 | 105.65 | 1.17833 | 93.19 | 1.150583 | 0.857455 | 8.679833 |
| 8 | `trend_pullback_short_td12.5_pb2_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 128 | 3.555556 | 1.340116 | 0.15 | 284.0 | 1.278957 | 1.165511 | 26 | 37.62 | 1.148479 | 97.84 | 1.19176 | 0.780464 | 8.574758 |
| 9 | `trend_pullback_short_td12.5_pb2_slope2_sma505_ny_h8` | `KEEP_REFINED_WATCHLIST` | 113 | 3.323529 | 1.326358 | 0.24 | 259.99 | 1.270025 | 1.16493 | 23 | 40.98 | 1.166592 | 96.98 | 1.190075 | 0.744607 | 8.544783 |
| 10 | `trend_pullback_short_td10_pb2_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 137 | 3.186047 | 1.232034 | 1.19 | 247.94 | 1.1832 | 1.091411 | 28 | 12.17 | 1.033906 | 8.32 | 1.014659 | 0.75897 | 7.927944 |
| 11 | `trend_pullback_short_td12.5_pb2_slope0_sma5010_ny_h8` | `KEEP_REFINED_WATCHLIST` | 114 | 3.166667 | 1.318616 | 0.15 | 250.84 | 1.261307 | 1.154639 | 23 | 9.05 | 1.038027 | 56.29 | 1.113754 | 0.735432 | 7.873856 |
| 12 | `trend_pullback_short_td12.5_pb2_slope2_sma5010_ny_h8` | `KEEP_REFINED_WATCHLIST` | 107 | 3.147059 | 1.279292 | -0.1 | 218.2 | 1.225788 | 1.126052 | 22 | 8.19 | 1.034413 | 55.43 | 1.112016 | 0.720767 | 7.539375 |
| 13 | `trend_pullback_short_td7.5_pb2_slope0_sma500_ny_h12` | `KEEP_REFINED_WATCHLIST` | 211 | 4.22 | 1.141603 | 0.36 | 205.9 | 1.088575 | 0.990009 | 43 | 50.67 | 1.084125 | 42.36 | 1.069371 | 0.823668 | 7.443545 |
| 14 | `trend_pullback_short_td5_pb0.5_slope0_sma500_ny_h12` | `KEEP_REFINED_WATCHLIST` | 237 | 4.74 | 1.180827 | 0.26 | 276.86 | 1.123334 | 1.01689 | 48 | 74.37 | 1.104582 | 10.08 | 1.015813 | 0.824378 | 6.886941 |
| 15 | `trend_pullback_short_td12.5_pb0.5_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 93 | 2.818182 | 1.21856 | 0.26 | 199.37 | 1.179687 | 1.105723 | 19 | 46.78 | 1.212733 | -12.89 | 0.977269 | 0.712594 | 6.779799 |
| 16 | `trend_pullback_short_td5_pb1_slope0_sma5010_ny_h12` | `KEEP_REFINED_WATCHLIST` | 179 | 3.729167 | 1.175326 | -0.02 | 237.73 | 1.126179 | 1.034272 | 36 | 79.74 | 1.134378 | 30.27 | 1.046614 | 0.752483 | 6.513107 |
| 17 | `trend_pullback_short_td7.5_pb0.5_slope2_sma500_ny_h12` | `KEEP_REFINED_WATCHLIST` | 143 | 3.404762 | 1.151142 | -0.07 | 183.97 | 1.107784 | 1.026121 | 29 | 26.89 | 1.064413 | -11.73 | 0.982251 | 0.782197 | 6.414475 |
| 18 | `trend_pullback_short_td5_pb0_slope0_sma500_ny_h8` | `KEEP_REFINED_WATCHLIST` | 212 | 4.24 | 1.199112 | -0.1 | 254.37 | 1.13686 | 1.02275 | 43 | 9.78 | 1.016109 | -2.68 | 0.99577 | 0.866428 | 6.035693 |
| 19 | `trend_pullback_short_td5_pb0.5_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 165 | 3.510638 | 1.275963 | 1.08 | 338.88 | 1.223981 | 1.126282 | 33 | -21.28 | 0.960992 | 78.14 | 1.129906 | 0.873408 | 9.103696 |
| 20 | `trend_pullback_short_td12.5_pb2_slope5_sma500_ny_h8` | `REJECT_REFINED_WEAK` | 90 | 3.103448 | 1.294774 | 1.365 | 214.79 | 1.246454 | 1.155452 | 18 | 22.82 | 1.107333 | 48.15 | 1.095469 | 0.698288 | 8.84676 |
| 21 | `trend_pullback_short_td7.5_pb2_slope0_sma505_ny_h12` | `REJECT_REFINED_WEAK` | 195 | 3.9 | 1.18349 | 0.65 | 248.2 | 1.129777 | 1.029845 | 39 | 14.6 | 1.026723 | 42.36 | 1.069371 | 0.801023 | 7.734759 |
| 22 | `trend_pullback_short_td7.5_pb2_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 145 | 3.372093 | 1.136049 | -0.26 | 161.43 | 1.091285 | 1.007258 | 29 | 95.62 | 1.261235 | 91.77 | 1.159689 | 0.742221 | 7.4851 |
| 23 | `trend_pullback_short_td12.5_pb2_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 99 | 2.911765 | 1.190717 | -0.14 | 170.69 | 1.149087 | 1.070376 | 20 | 89.5 | 1.527557 | 29.83 | 1.057718 | 0.594699 | 7.109753 |
| 24 | `trend_pullback_short_td5_pb0.5_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 148 | 3.363636 | 1.149841 | 0.245 | 182.74 | 1.105146 | 1.021048 | 30 | -43.59 | 0.911898 | 54.47 | 1.090555 | 0.788594 | 7.096875 |
| 25 | `trend_pullback_short_td7.5_pb0.5_slope2_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 124 | 3.179487 | 1.159826 | 0.095 | 179.8 | 1.118944 | 1.041611 | 25 | 64.97 | 1.168225 | 31.05 | 1.049686 | 0.75399 | 7.013577 |
| 26 | `trend_pullback_short_td5_pb2_slope2_sma500_ny_h12` | `REJECT_REFINED_WEAK` | 212 | 4.24 | 1.117676 | -0.06 | 166.9 | 1.063673 | 0.963673 | 43 | 102.68 | 1.176867 | 54.95 | 1.087344 | 0.790823 | 6.796915 |
| 27 | `trend_pullback_short_td10_pb0_slope0_sma5010_ny_h12` | `REJECT_REFINED_WEAK` | 98 | 2.882353 | 1.080639 | 1.415 | 78.19 | 1.044506 | 0.975774 | 20 | 33.72 | 1.153342 | -186.71 | 0.697797 | 0.6365 | 6.63326 |
| 28 | `trend_pullback_short_td5_pb2_slope0_sma505_ny_h12` | `REJECT_REFINED_WEAK` | 251 | 5.02 | 1.12578 | -0.26 | 195.55 | 1.067328 | 0.959829 | 51 | 117.31 | 1.171546 | 29.54 | 1.046954 | 0.785693 | 6.212569 |
| 29 | `trend_pullback_short_td5_pb0.5_slope2_sma500_ny_h12` | `REJECT_REFINED_WEAK` | 185 | 3.77551 | 1.132826 | -0.07 | 179.69 | 1.082913 | 0.989999 | 37 | 75.14 | 1.131095 | 11.69 | 1.018338 | 0.799012 | 6.034832 |
| 30 | `trend_pullback_short_td10_pb0.5_slope2_sma500_ny_h12` | `REJECT_REFINED_WEAK` | 116 | 3.314286 | 1.165747 | 0.335 | 177.21 | 1.125422 | 1.049007 | 24 | 11.02 | 1.041727 | -113.18 | 0.826884 | 0.738186 | 5.937958 |

## Promoted refined candidates
- none

## Interpretation
- Stage22A v2 is targeted exact historical refinement, not forward proof.
- Promoted variants may go to a later forward-shadow collector design.
- Watchlist-only variants must not be added to Stage18A.
- If no promotion appears, this trend-pullback short family should be frozen as watchlist-only.
- No paper/live/order escalation is authorized.

## Output files
- proxy_csv: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_proxy_summary.csv`
- exact_csv: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_exact_summary.csv`
- promoted_csv: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_promoted.csv`
- trades_csv: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_exact_trades.csv`
- json: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_trend_pullback_short_refinement.json`
- md: `data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_trend_pullback_short_refinement.md`
