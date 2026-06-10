# Stage 4H Session Guard Lab

Generated UTC: `2026-06-08T19:40:05Z`
Tool version: `v1`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`

> Hard rule: this is filter research only. It does not authorize demo, paper, or live orders.

## Interpretation
- Stage 4G v2 non-overlap remains the decision basis.
- This lab only tests simple session guards on the non-overlap trade list.
- A promising filter requires deeper replay and live dry-run monitoring before any EA change.

## Input
- path: `data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv`
- delimiter: `,`
- rows_parsed: `941`
- bad_row_count: `0`
- session_col: `session_utc`
- net_col: `net_usd`
- time_col: `entry_utc_time`
- year_col: `None`

## Filter summary

| Filter | Status | Trades | Total | PF | Median | Max DD | Flags |
|---|---:|---:|---:|---:|---:|---:|---|
| base_all | WARN | 941 | 746.29 | 1.10945 | -3.57 | -440.9 | negative_median, cost_x4_not_positive |
| no_asia | WARN | 631 | 782.29 | 1.187423 | -2.24 | -299.77 | negative_median |
| no_asia_no_new_york | WARN | 454 | 338.31 | 1.110427 | -2.645 | -271.3 | negative_median, cost_x4_not_positive |
| overlap_newyork_other | WARN | 631 | 782.29 | 1.187423 | -2.24 | -299.77 | negative_median |
| overlap_other | WARN | 454 | 338.31 | 1.110427 | -2.645 | -271.3 | negative_median, cost_x4_not_positive |
| london_ny_overlap_only | WARN | 350 | 291.0 | 1.13414 | -1.89 | -273.19 | negative_median, cost_x4_not_positive |
| new_york_only | PASS | 177 | 443.98 | 1.399885 | 0.3 | -99.15 |  |
| other_only | WARN | 104 | 47.31 | 1.052903 | -15.35 | -158.22 | pf_below_threshold, negative_median, cost_x3_not_positive, cost_x4_not_positive |

## Detailed candidates
### base_all
- guard_lab_status: `WARN`
- trades: `941`
- total_net_usd: `746.29`
- avg_net_usd: `0.793082`
- median_net_usd: `-3.57`
- win_rate: `0.44102`
- profit_factor: `1.10945`
- max_drawdown_usd: `-440.9`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `[]`
- exclude_sessions: `[]`
- flags: `['negative_median', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`746.29`, PF=`1.10945`, median=`-3.57`, maxDD=`-440.9`
- cost_x2: total=`416.94`, PF=`1.059539`, median=`-3.92`, maxDD=`-537.15`
- cost_x3: total=`87.59`, PF=`1.012184`, median=`-4.27`, maxDD=`-633.4`
- cost_x4: total=`-241.76`, PF=`0.967226`, median=`-4.62`, maxDD=`-729.65`

### no_asia
- guard_lab_status: `WARN`
- trades: `631`
- total_net_usd: `782.29`
- avg_net_usd: `1.239762`
- median_net_usd: `-2.24`
- win_rate: `0.462758`
- profit_factor: `1.187423`
- max_drawdown_usd: `-299.77`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `[]`
- exclude_sessions: `['asia']`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`782.29`, PF=`1.187423`, median=`-2.24`, maxDD=`-299.77`
- cost_x2: total=`561.44`, PF=`1.130786`, median=`-2.59`, maxDD=`-312.37`
- cost_x3: total=`340.59`, PF=`1.077171`, median=`-2.94`, maxDD=`-324.97`
- cost_x4: total=`119.74`, PF=`1.026401`, median=`-3.29`, maxDD=`-337.57`

### overlap_newyork_other
- guard_lab_status: `WARN`
- trades: `631`
- total_net_usd: `782.29`
- avg_net_usd: `1.239762`
- median_net_usd: `-2.24`
- win_rate: `0.462758`
- profit_factor: `1.187423`
- max_drawdown_usd: `-299.77`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap', 'new_york', 'other']`
- exclude_sessions: `[]`
- flags: `['negative_median']`

#### Cost stress
- cost_x1: total=`782.29`, PF=`1.187423`, median=`-2.24`, maxDD=`-299.77`
- cost_x2: total=`561.44`, PF=`1.130786`, median=`-2.59`, maxDD=`-312.37`
- cost_x3: total=`340.59`, PF=`1.077171`, median=`-2.94`, maxDD=`-324.97`
- cost_x4: total=`119.74`, PF=`1.026401`, median=`-3.29`, maxDD=`-337.57`

### overlap_other
- guard_lab_status: `WARN`
- trades: `454`
- total_net_usd: `338.31`
- avg_net_usd: `0.745176`
- median_net_usd: `-2.645`
- win_rate: `0.447137`
- profit_factor: `1.110427`
- max_drawdown_usd: `-271.3`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap', 'other']`
- exclude_sessions: `[]`
- flags: `['negative_median', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`338.31`, PF=`1.110427`, median=`-2.645`, maxDD=`-271.3`
- cost_x2: total=`179.41`, PF=`1.056925`, median=`-2.995`, maxDD=`-284.6`
- cost_x3: total=`20.51`, PF=`1.006328`, median=`-3.345`, maxDD=`-297.9`
- cost_x4: total=`-138.39`, PF=`0.958468`, median=`-3.695`, maxDD=`-311.2`

### london_ny_overlap_only
- guard_lab_status: `WARN`
- trades: `350`
- total_net_usd: `291.0`
- avg_net_usd: `0.831429`
- median_net_usd: `-1.89`
- win_rate: `0.457143`
- profit_factor: `1.13414`
- max_drawdown_usd: `-273.19`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['london_ny_overlap']`
- exclude_sessions: `[]`
- flags: `['negative_median', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`291.0`, PF=`1.13414`, median=`-1.89`, maxDD=`-273.19`
- cost_x2: total=`168.5`, PF=`1.075356`, median=`-2.24`, maxDD=`-306.79`
- cost_x3: total=`46.0`, PF=`1.019964`, median=`-2.59`, maxDD=`-340.39`
- cost_x4: total=`-76.5`, PF=`0.967773`, median=`-2.94`, maxDD=`-373.99`

### new_york_only
- guard_lab_status: `PASS`
- trades: `177`
- total_net_usd: `443.98`
- avg_net_usd: `2.508362`
- median_net_usd: `0.3`
- win_rate: `0.502825`
- profit_factor: `1.399885`
- max_drawdown_usd: `-99.15`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['new_york']`
- exclude_sessions: `[]`
- flags: `[]`

#### Cost stress
- cost_x1: total=`443.98`, PF=`1.399885`, median=`0.3`, maxDD=`-99.15`
- cost_x2: total=`382.03`, PF=`1.334785`, median=`-0.05`, maxDD=`-102.3`
- cost_x3: total=`320.08`, PF=`1.273043`, median=`-0.4`, maxDD=`-105.45`
- cost_x4: total=`258.13`, PF=`1.214497`, median=`-0.75`, maxDD=`-108.6`

### other_only
- guard_lab_status: `WARN`
- trades: `104`
- total_net_usd: `47.31`
- avg_net_usd: `0.454904`
- median_net_usd: `-15.35`
- win_rate: `0.413462`
- profit_factor: `1.052903`
- max_drawdown_usd: `-158.22`
- best_net_usd: `23.65`
- worst_net_usd: `-15.35`
- include_sessions: `['other']`
- exclude_sessions: `[]`
- flags: `['pf_below_threshold', 'negative_median', 'cost_x3_not_positive', 'cost_x4_not_positive']`

#### Cost stress
- cost_x1: total=`47.31`, PF=`1.052903`, median=`-15.35`, maxDD=`-158.22`
- cost_x2: total=`10.91`, PF=`1.011915`, median=`-15.7`, maxDD=`-167.32`
- cost_x3: total=`-25.49`, PF=`0.972796`, median=`-16.05`, maxDD=`-180.22`
- cost_x4: total=`-61.89`, PF=`0.935419`, median=`-16.4`, maxDD=`-194.92`

## Decision
No demo-order authorization. Use this report to decide whether to run a deeper replay for a narrower session guard and to define Stage 5C live outcome tracking.
