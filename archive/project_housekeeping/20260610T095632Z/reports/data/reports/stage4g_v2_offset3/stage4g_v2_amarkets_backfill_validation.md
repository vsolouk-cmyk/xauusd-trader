# Stage 4G AMarkets Backfill Validation v2

Generated UTC: `2026-06-08T13:40:31Z`
Tool version: `v2_non_overlap`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`
Overall status: **PASS_WITH_WARNINGS**

> Hard rule: this is broker-feed backfill validation only. It does not authorize demo, paper, or live orders.

## Critical interpretation

- `overlap_every_signal` is diagnostic only: it opens a replay trade for every qualifying H1 signal.
- `non_overlap` is the decision basis: it allows only one active dry-run trade at a time until TP, SL, or 12 H1-bar time-exit resolves.
- Demo-order remains forbidden unless non-overlap replay, live dry-run outcomes, spread guard, and risk guards pass.

## Inputs
- h1: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- m1: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- server_utc_offset_hours: `3.0`
- roundtrip_cost_usd: `0.35`
- decision_basis: `non_overlap`

## Data quality
### H1
- path: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- delimiter: `TAB`
- has_header: `True`
- rows_parsed: `24166`
- bad_row_count: `0`
- start_server: `2022-05-02T01:00:00`
- end_server: `2026-06-04T23:00:00`
- start_utc: `2022-05-01T22:00:00`
- end_utc: `2026-06-04T20:00:00`

### M1
- path: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- delimiter: `TAB`
- has_header: `True`
- rows_parsed: `1446351`
- bad_row_count: `0`
- start_server: `2022-05-02T01:01:00`
- end_server: `2026-06-04T23:58:00`
- start_utc: `2022-05-01T22:01:00`
- end_utc: `2026-06-04T20:58:00`

## Signal counts
- h1_rows: `24166`
- m1_rows: `1446351`
- raw_signals: `2336`
- overlap_replayed_trades: `2336`
- non_overlap_replayed_trades: `941`
- non_overlap_skipped_by_open_position: `1395`
- overlap_skipped: `0`

## Replay comparison
### overlap_every_signal
- trades: `2336`
- total_net_usd: `2011.66`
- avg_net_usd: `0.861156`
- median_net_usd: `-1.855`
- win_rate: `0.462329`
- profit_factor: `1.129984`
- max_drawdown_usd: `-731.36`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### non_overlap
- trades: `941`
- total_net_usd: `746.29`
- avg_net_usd: `0.793082`
- median_net_usd: `-3.57`
- win_rate: `0.44102`
- profit_factor: `1.10945`
- max_drawdown_usd: `-440.9`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

## Non-overlap cost stress
### cost_x1
- trades: `941`
- total_net_usd: `746.29`
- avg_net_usd: `0.793082`
- median_net_usd: `-3.57`
- win_rate: `0.44102`
- profit_factor: `1.10945`
- max_drawdown_usd: `-440.9`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### cost_x2
- trades: `941`
- total_net_usd: `416.94`
- avg_net_usd: `0.443082`
- median_net_usd: `-3.92`
- win_rate: `0.437832`
- profit_factor: `1.059539`
- max_drawdown_usd: `-537.15`
- best_net_usd: `23.3`
- worst_net_usd: `-15.7`
- ambiguous_exit_count: `0`

### cost_x3
- trades: `941`
- total_net_usd: `87.59`
- avg_net_usd: `0.093082`
- median_net_usd: `-4.27`
- win_rate: `0.431456`
- profit_factor: `1.012184`
- max_drawdown_usd: `-633.4`
- best_net_usd: `22.95`
- worst_net_usd: `-16.05`
- ambiguous_exit_count: `0`

### cost_x4
- trades: `941`
- total_net_usd: `-241.76`
- avg_net_usd: `-0.256918`
- median_net_usd: `-4.62`
- win_rate: `0.430393`
- profit_factor: `0.967226`
- max_drawdown_usd: `-729.65`
- best_net_usd: `22.6`
- worst_net_usd: `-16.4`
- ambiguous_exit_count: `0`

## Non-overlap session breakdown
### asia
- trades: `310`
- total_net_usd: `-36.0`
- avg_net_usd: `-0.116129`
- median_net_usd: `-15.35`
- win_rate: `0.396774`
- profit_factor: `0.986387`
- max_drawdown_usd: `-380.35`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### london_ny_overlap
- trades: `350`
- total_net_usd: `291.0`
- avg_net_usd: `0.831429`
- median_net_usd: `-1.89`
- win_rate: `0.457143`
- profit_factor: `1.13414`
- max_drawdown_usd: `-273.19`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### new_york
- trades: `177`
- total_net_usd: `443.98`
- avg_net_usd: `2.508362`
- median_net_usd: `0.3`
- win_rate: `0.502825`
- profit_factor: `1.399885`
- max_drawdown_usd: `-99.15`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### other
- trades: `104`
- total_net_usd: `47.31`
- avg_net_usd: `0.454904`
- median_net_usd: `-15.35`
- win_rate: `0.413462`
- profit_factor: `1.052903`
- max_drawdown_usd: `-158.22`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

## Non-overlap year breakdown
### 2022
- trades: `43`
- total_net_usd: `-91.9`
- avg_net_usd: `-2.137209`
- median_net_usd: `-3.26`
- win_rate: `0.372093`
- profit_factor: `0.594583`
- max_drawdown_usd: `-121.53`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### 2023
- trades: `81`
- total_net_usd: `-25.95`
- avg_net_usd: `-0.32037`
- median_net_usd: `-1.27`
- win_rate: `0.45679`
- profit_factor: `0.927925`
- max_drawdown_usd: `-125.86`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### 2024
- trades: `114`
- total_net_usd: `121.83`
- avg_net_usd: `1.068684`
- median_net_usd: `-0.57`
- win_rate: `0.491228`
- profit_factor: `1.230268`
- max_drawdown_usd: `-94.79`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### 2025
- trades: `347`
- total_net_usd: `651.41`
- avg_net_usd: `1.877262`
- median_net_usd: `-2.96`
- win_rate: `0.461095`
- profit_factor: `1.262746`
- max_drawdown_usd: `-170.66`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

### 2026
- trades: `356`
- total_net_usd: `90.9`
- avg_net_usd: `0.255337`
- median_net_usd: `-15.35`
- win_rate: `0.410112`
- profit_factor: `1.028199`
- max_drawdown_usd: `-440.9`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- ambiguous_exit_count: `0`

## Checks — decision basis: non_overlap

| Status | Check | Detail |
|---|---|---|
| PASS | Minimum non-overlap trades | trades=941, min=20 |
| PASS | Positive total net | total_net_usd=746.29 |
| PASS | Profit factor | profit_factor=1.10945, threshold=1.05 |
| WARN | Median nonnegative | median_net_usd=-3.57 |
| PASS | Ambiguous exits | ambiguous=0 |

Decision: **Non-overlap AMarkets backfill is usable with warnings. Continue live dry-run and inspect weak segments before demo-order.**
