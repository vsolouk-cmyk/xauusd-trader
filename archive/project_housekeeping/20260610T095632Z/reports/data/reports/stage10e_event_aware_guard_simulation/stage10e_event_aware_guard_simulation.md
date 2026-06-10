# Stage 10E Event-Aware Guard / Report Simulation

Generated UTC: `2026-06-10T09:34:23+00:00`
Tool version: `v2_input_audit`

> Hard rule: simulation only. This does not authorize demo, paper, or live orders.

## Input audit
- numeric_events_path_exists: `True`
- numeric_events_loaded: `500`
- gdelt_events_loaded: `10`
- all_events_loaded: `510`
- guard_rules_loaded: `2`
- guard_events_loaded: `85`
- numeric_guard_events_loaded: `85`

## Inputs
- stage8b_trades: `data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv`
- numeric_events: `data/macro/events/stage10c_numeric_shock_events.csv`
- gdelt_events: `data/macro/events/stage10b_detected_shock_events.csv`
- rules_config: `data/config/stage10e_validated_event_classes.csv`
- raw_stage8b_trades_loaded: `64474`
- candidate_trades_loaded: `524`
- rules_loaded: `3`

## Guard policy simulation
| Policy | Trades | Blocked | Blocked % | Total x4 | Median x4 | PF x4 | WR x4 | DD x4 | ΔTotal | ΔPF | ΔDD | Decision hint |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline_all_trades | 524 | 0 | 0.0 | 2410.28 | 2.06 | 1.920727 | 0.580153 | -202.67 | 0.0 | 0.0 | 0.0 | baseline |
| block_any_validated_yield_event_window | 502 | 22 | 0.041985 | 2266.92 | 2.14 | 1.891183 | 0.589641 | -202.67 | -143.36 | -0.029544 | 0.0 | reject_as_guard_or_report_only |
| block_hostile_yield_event_window_only | 514 | 10 | 0.019084 | 2289.5 | 2.07 | 1.878058 | 0.583658 | -202.67 | -120.78 | -0.042669 | 0.0 | reject_as_guard_or_report_only |
| take_only_supportive_yield_event_window | 12 | 512 | 0.977099 | 22.58 | -5.305 | 1.354252 | 0.333333 | -21.26 | -2387.7 | -0.566475 | 181.41 | insufficient_remaining_sample |
| take_only_no_validated_event_window | 502 | 22 | 0.041985 | 2266.92 | 2.14 | 1.891183 | 0.589641 | -202.67 | -143.36 | -0.029544 | 0.0 | reject_as_guard_or_report_only |

## Recent event dashboard
| Time UTC | Class | Channel | Expected | Source | Role | Title |
|---|---|---|---:|---|---|---|
| 2026-06-08T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | numeric | unvalidated_or_monitoring | DFII10 real_yield_shock hostile on 2026-06-08 |
| 2026-06-05T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | numeric | unvalidated_or_monitoring | DFII10 real_yield_shock hostile on 2026-06-05 |
| 2026-06-05T03:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 金价高位震荡 ， 全球央行重新入场 扫货 能否支撑未来走势 ？- 华龙网 - 重庆市委市政府官方新闻门户 |
| 2026-06-04T18:45:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 买买买 ！ 全球央行重新 扫货 黄金 |
| 2026-06-04T15:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 净购入黄金17吨 ！ 全球央行重启买买买 |
| 2026-06-04T08:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 净购入黄金17吨 ， 全球央行重启买买买 - CFi . CN 中财网 |
| 2026-06-04T08:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 黄金缘何成全球官方储备最大资产 - 金融频道 - 杭州网 |
| 2026-06-04T07:45:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 波兰央行单月净购入黄金14吨 全球央行恢复增持态势 _ 新闻频道 _ 中华网 |
| 2026-06-04T06:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 全球央行扫货黄金 4月净购金17吨 _ 新闻频道 _ 中华网 |
| 2026-06-04T02:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 中國和波蘭正在囤黃金 ！ 世界黃金協會揭驚人數據 全球央行動向一次看 |
| 2026-06-04T02:00:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 3月大抛售后 ， 全球央行4月重新恢复购金 - CFi . CN 中财网 |
| 2026-06-03T16:00:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | gdelt | monitoring_only | 世界黄金协会 ： 2026年4月全球央行重启黄金净买入 _ 金市直播 _ 黄金网 _ 中金在线 |
| 2026-06-01T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILBRENTEU oil_supply_shock mixed on 2026-06-01 |
| 2026-05-29T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILBRENTEU oil_supply_shock mixed on 2026-05-29 |
| 2026-05-28T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILBRENTEU oil_supply_shock mixed on 2026-05-28 |
| 2026-05-27T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILBRENTEU oil_supply_shock mixed on 2026-05-27 |
| 2026-05-26T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILBRENTEU oil_supply_shock mixed on 2026-05-26 |
| 2026-05-22T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILWTICO oil_supply_shock mixed on 2026-05-22 |
| 2026-05-21T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILWTICO oil_supply_shock mixed on 2026-05-21 |
| 2026-05-21T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | numeric | unvalidated_or_monitoring | DFII10 real_yield_shock hostile on 2026-05-21 |
| 2026-05-20T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | numeric | unvalidated_or_monitoring | DCOILWTICO oil_supply_shock mixed on 2026-05-20 |
| 2026-05-20T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | numeric | unvalidated_or_monitoring | DFII10 real_yield_shock hostile on 2026-05-20 |

## Interpretation
- If `numeric_guard_events_loaded` is zero, yield-guard simulation is invalid and Stage 10C must be rerun.
- A policy is useful only if it improves PF/drawdown without destroying trade count.
- GDELT central-bank demand is monitoring-only until it has enough independent clusters.

## Decision
- No EA change.
- No automatic news trading.
- If a guard policy passes here, the next step is forward-shadow reporting only.
