# Stage 4G AMarkets Backfill Validation

Generated UTC: `2026-06-08T13:32:24Z`
Tool version: `v1`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`
Overall status: **PASS_WITH_WARNINGS**

> Hard rule: this is broker-feed backfill validation only. It does not authorize demo, paper, or live orders.

## Inputs
- h1: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- m1: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- server_utc_offset_hours: `2.0`
- roundtrip_cost_usd: `0.35`
- min_trades: `20`

## Data quality
### H1
- rows_parsed: `24166`
- bad_row_count: `0`
- start_server: `2022-05-02T01:00:00`
- end_server: `2026-06-04T23:00:00`
- start_utc: `2022-05-01T23:00:00`
- end_utc: `2026-06-04T21:00:00`
- delimiter: `TAB`
- has_header: `True`

### M1
- rows_parsed: `1446351`
- bad_row_count: `0`
- start_server: `2022-05-02T01:01:00`
- end_server: `2026-06-04T23:58:00`
- start_utc: `2022-05-01T23:01:00`
- end_utc: `2026-06-04T21:58:00`
- delimiter: `TAB`
- has_header: `True`

## Signal/replay stats
- h1_rows: `24166`
- m1_rows: `1446351`
- signals: `2375`
- replayed_trades: `2375`
- skipped_replay: `0`
- ambiguous_exit_count: `0`
- exit_reasons: `{'time_exit': 883, 'stop_loss': 904, 'take_profit': 588}`
- trades_csv: `/Users/vahid/Desktop/xauusd-trader/data/reports/stage4g_amarkets_backfill_trades.csv`

## Main metrics, cost x1
- trades: `2375`
- total_net_usd: `2237.18`
- avg_net_usd: `0.941971`
- median_net_usd: `-1.85`
- win_rate: `0.469053`
- profit_factor: `1.143797`
- max_drawdown_usd: `-721.24`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

## Cost stress
### cost_x1
- trades: `2375`
- total_net_usd: `2237.18`
- avg_net_usd: `0.941971`
- median_net_usd: `-1.85`
- win_rate: `0.469053`
- profit_factor: `1.143797`
- max_drawdown_usd: `-721.24`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### cost_x2
- trades: `2375`
- total_net_usd: `1405.93`
- avg_net_usd: `0.591971`
- median_net_usd: `-2.2`
- win_rate: `0.461474`
- profit_factor: `1.087858`
- max_drawdown_usd: `-766.74`
- best_net_usd: `23.3`
- worst_net_usd: `-15.7`

### cost_x3
- trades: `2375`
- total_net_usd: `574.68`
- avg_net_usd: `0.241971`
- median_net_usd: `-2.55`
- win_rate: `0.454316`
- profit_factor: `1.03493`
- max_drawdown_usd: `-821.3`
- best_net_usd: `22.95`
- worst_net_usd: `-16.05`

### cost_x4
- trades: `2375`
- total_net_usd: `-256.57`
- avg_net_usd: `-0.108029`
- median_net_usd: `-2.9`
- win_rate: `0.447579`
- profit_factor: `0.984827`
- max_drawdown_usd: `-978.8`
- best_net_usd: `22.6`
- worst_net_usd: `-16.4`

## Session breakdown
### asia
- trades: `801`
- total_net_usd: `67.41`
- avg_net_usd: `0.084157`
- median_net_usd: `-15.35`
- win_rate: `0.420724`
- profit_factor: `1.010101`
- max_drawdown_usd: `-539.77`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### london_ny_overlap
- trades: `528`
- total_net_usd: `642.27`
- avg_net_usd: `1.21642`
- median_net_usd: `-0.92`
- win_rate: `0.484848`
- profit_factor: `1.202705`
- max_drawdown_usd: `-273.8`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### new_york
- trades: `823`
- total_net_usd: `1092.37`
- avg_net_usd: `1.327303`
- median_net_usd: `0.0`
- win_rate: `0.499392`
- profit_factor: `1.264664`
- max_drawdown_usd: `-263.54`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### other
- trades: `223`
- total_net_usd: `435.13`
- avg_net_usd: `1.951256`
- median_net_usd: `-1.57`
- win_rate: `0.493274`
- profit_factor: `1.273904`
- max_drawdown_usd: `-174.65`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

## Year breakdown
### 2022
- trades: `143`
- total_net_usd: `-47.3`
- avg_net_usd: `-0.330769`
- median_net_usd: `0.05`
- win_rate: `0.503497`
- profit_factor: `0.915416`
- max_drawdown_usd: `-194.48`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### 2023
- trades: `239`
- total_net_usd: `16.27`
- avg_net_usd: `0.068075`
- median_net_usd: `0.29`
- win_rate: `0.539749`
- profit_factor: `1.020408`
- max_drawdown_usd: `-220.48`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### 2024
- trades: `367`
- total_net_usd: `126.77`
- avg_net_usd: `0.345422`
- median_net_usd: `-0.75`
- win_rate: `0.479564`
- profit_factor: `1.073964`
- max_drawdown_usd: `-260.37`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### 2025
- trades: `969`
- total_net_usd: `1584.15`
- avg_net_usd: `1.63483`
- median_net_usd: `-2.2`
- win_rate: `0.469556`
- profit_factor: `1.234392`
- max_drawdown_usd: `-703.61`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

### 2026
- trades: `657`
- total_net_usd: `557.29`
- avg_net_usd: `0.848234`
- median_net_usd: `-15.35`
- win_rate: `0.429224`
- profit_factor: `1.097275`
- max_drawdown_usd: `-721.24`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`

## Checks

| Status | Check | Detail |
|---|---|---|
| PASS | Trades produced | trades=2375 |
| PASS | Minimum trades | trades=2375, min_trades=20 |
| PASS | Positive total net | total_net_usd=2237.18 |
| PASS | Profit factor | profit_factor=1.143797, threshold=1.05 |
| WARN | Median nonnegative | median_net_usd=-1.85 |
| PASS | Ambiguous exit ratio | ambiguous=0, ratio=0.0000 |

Decision: **Backfill is usable but not sufficient alone for demo-order. Continue live dry-run and inspect warnings.**
