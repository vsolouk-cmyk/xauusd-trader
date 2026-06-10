# Stage 4H Session Guard Lab

Generated UTC: `2026-06-08T19:40:04Z`
Tool version: `v1`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`

> Hard rule: this is filter research only. It does not authorize demo, paper, or live orders.

## Interpretation
- Stage 4G v2 non-overlap remains the decision basis.
- This lab only tests simple session guards on the non-overlap trade list.
- A promising filter requires deeper replay and live dry-run monitoring before any EA change.

## Input
- path: `data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv`
- delimiter: `,`
- rows_parsed: `961`
- bad_row_count: `0`
- session_col: `session_utc`
- net_col: `net_usd`
- time_col: `entry_utc_time`
- year_col: `None`

## Filter summary

| Filter | Status | Trades | Total | PF | Median | Max DD | Flags |
|---|---:|---:|---:|---:|---:|---:|---|
| base_all | WARN | 961 | 854.85 | 1.122411 | -3.57 | -396.42 | negative_median, cost_x4_not_positive |
| no_asia | WARN | 648 | 1020.58 | 1.242286 | -1.44 | -323.42 | negative_median |
| no_asia_no_new_york | WARN | 443 | 938.75 | 1.333935 | -0.37 | -282.1 | negative_median |
| overlap_newyork_other | WARN | 648 | 1020.58 | 1.242286 | -1.44 | -323.42 | negative_median |
| overlap_other | WARN | 443 | 938.75 | 1.333935 | -0.37 | -282.1 | negative_median |
| london_ny_overlap_only | WARN | 345 | 556.24 | 1.26139 | -0.73 | -205.35 | negative_median |
| new_york_only | WARN | 205 | 81.83 | 1.058403 | -2.86 | -118.95 | pf_below_threshold, negative_median, cost_x3_not_positive, cost_x4_not_positive |
| other_only | PASS | 98 | 382.51 | 1.559905 | 2.33 | -101.23 |  |

## Detailed candidates
### base_all
- guard_lab_status: `WARN`
- trades: `961`
- total_net_usd: `854.85`
- avg_net_usd: `0.889542`
- median_net_usd: `-3.57`
- win_rate: `0.448491`
- profit_factor: `1.122411`
- max_drawdown_usd: `-396.42`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `[]`
- exclude_sessions: `[]`
- flags: `['negative_median', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`854.85`, PF=`1.122411`, median=`-3.57`, maxDD=`-396.42`
- cost_x2: total=`518.5`, PF=`1.072324`, median=`-3.92`, maxDD=`-415.67`
- cost_x3: total=`182.15`, PF=`1.024761`, median=`-4.27`, maxDD=`-475.3`
- cost_x4: total=`-154.2`, PF=`0.979562`, median=`-4.62`, maxDD=`-563.85`

### no_asia
- guard_lab_status: `WARN`
- trades: `648`
- total_net_usd: `1020.58`
- avg_net_usd: `1.574969`
- median_net_usd: `-1.44`
- win_rate: `0.476852`
- profit_factor: `1.242286`
- max_drawdown_usd: `-323.42`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `[]`
- exclude_sessions: `['asia']`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`1020.58`, PF=`1.242286`, median=`-1.44`, maxDD=`-323.42`
- cost_x2: total=`793.78`, PF=`1.183271`, median=`-1.79`, maxDD=`-335.67`
- cost_x3: total=`566.98`, PF=`1.127366`, median=`-2.14`, maxDD=`-347.92`
- cost_x4: total=`340.18`, PF=`1.074389`, median=`-2.49`, maxDD=`-360.17`

### overlap_newyork_other
- guard_lab_status: `WARN`
- trades: `648`
- total_net_usd: `1020.58`
- avg_net_usd: `1.574969`
- median_net_usd: `-1.44`
- win_rate: `0.476852`
- profit_factor: `1.242286`
- max_drawdown_usd: `-323.42`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap', 'new_york', 'other']`
- exclude_sessions: `[]`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`1020.58`, PF=`1.242286`, median=`-1.44`, maxDD=`-323.42`
- cost_x2: total=`793.78`, PF=`1.183271`, median=`-1.79`, maxDD=`-335.67`
- cost_x3: total=`566.98`, PF=`1.127366`, median=`-2.14`, maxDD=`-347.92`
- cost_x4: total=`340.18`, PF=`1.074389`, median=`-2.49`, maxDD=`-360.17`

### overlap_other
- guard_lab_status: `WARN`
- trades: `443`
- total_net_usd: `938.75`
- avg_net_usd: `2.119074`
- median_net_usd: `-0.37`
- win_rate: `0.494357`
- profit_factor: `1.333935`
- max_drawdown_usd: `-282.1`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap', 'other']`
- exclude_sessions: `[]`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`938.75`, PF=`1.333935`, median=`-0.37`, maxDD=`-282.1`
- cost_x2: total=`783.7`, PF=`1.2712`, median=`-0.72`, maxDD=`-291.2`
- cost_x3: total=`628.65`, PF=`1.211703`, median=`-1.07`, maxDD=`-300.3`
- cost_x4: total=`473.6`, PF=`1.155297`, median=`-1.42`, maxDD=`-309.4`

### london_ny_overlap_only
- guard_lab_status: `WARN`
- trades: `345`
- total_net_usd: `556.24`
- avg_net_usd: `1.61229`
- median_net_usd: `-0.73`
- win_rate: `0.489855`
- profit_factor: `1.26139`
- max_drawdown_usd: `-205.35`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap']`
- exclude_sessions: `[]`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`556.24`, PF=`1.26139`, median=`-0.73`, maxDD=`-205.35`
- cost_x2: total=`435.49`, PF=`1.198874`, median=`-1.08`, maxDD=`-212.7`
- cost_x3: total=`314.74`, PF=`1.139716`, median=`-1.43`, maxDD=`-220.05`
- cost_x4: total=`193.99`, PF=`1.083758`, median=`-1.78`, maxDD=`-227.4`

### new_york_only
- guard_lab_status: `WARN`
- trades: `205`
- total_net_usd: `81.83`
- avg_net_usd: `0.399171`
- median_net_usd: `-2.86`
- win_rate: `0.439024`
- profit_factor: `1.058403`
- max_drawdown_usd: `-118.95`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['new_york']`
- exclude_sessions: `[]`
- flags: `['pf_below_threshold', 'negative_median', 'cost_x3_not_positive', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`81.83`, PF=`1.058403`, median=`-2.86`, maxDD=`-118.95`
- cost_x2: total=`10.08`, PF=`1.006993`, median=`-3.21`, maxDD=`-128.4`
- cost_x3: total=`-61.67`, PF=`0.95839`, median=`-3.56`, maxDD=`-147.76`
- cost_x4: total=`-133.42`, PF=`0.912416`, median=`-3.91`, maxDD=`-192.46`

### other_only
- guard_lab_status: `PASS`
- trades: `98`
- total_net_usd: `382.51`
- avg_net_usd: `3.903163`
- median_net_usd: `2.33`
- win_rate: `0.510204`
- profit_factor: `1.559905`
- max_drawdown_usd: `-101.23`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['other']`
- exclude_sessions: `[]`
- flags: `[]`

#### Cost stress
- cost_x1: total=`382.51`, PF=`1.559905`, median=`2.33`, maxDD=`-101.23`
- cost_x2: total=`348.21`, PF=`1.497464`, median=`1.98`, maxDD=`-106.48`
- cost_x3: total=`313.91`, PF=`1.437951`, median=`1.63`, maxDD=`-111.73`
- cost_x4: total=`279.61`, PF=`1.381163`, median=`1.28`, maxDD=`-116.98`

## Decision
No demo-order authorization. Use this report to decide whether to run a deeper replay for a narrower session guard and to define Stage 5C live outcome tracking.
