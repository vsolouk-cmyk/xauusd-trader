# Stage 10B Event Pipeline Update

Generated UTC: `2026-06-10T09:13:30+00:00`
Tool version: `v3_query_intent_classification`

> Hard rule: data/event collection only. This does not authorize demo, paper, or live orders.

## Workflow metadata
- workflow: `XAUUSD Event Pipeline Update`
- run_id: `27266011610`
- run_number: `3`
- run_attempt: `1`
- sha: `2341a75dcc8969b224488bfcd349ffe2b17432c0`

## Status
- status: `ok`
- scheduled_count: `5`
- manual_count: `0`
- shock_count: `10`
- unified_count: `15`
- gdelt_enabled: `True`
- gdelt_query_mode: `rate_safe`
- timespan: `7d`
- query_delay_sec: `20.0`

## GDELT query status
| Query | Status | HTTP | Articles | Kept | Dropped | Error |
|---|---|---|---:|---:|---:|---|
| XAUUSD | rate_limited | 429 | 0 | 0 | 0 | HTTPError: HTTP Error 429: Too Many Requests |
| gold federal reserve | rate_limited | 429 | 0 | 0 | 0 | HTTPError: HTTP Error 429: Too Many Requests |
| gold central bank | ok | ok | 10 | 10 | 0 |  |

## Counts by source kind
| Source kind | Events |
|---|---:|
| gdelt | 10 |
| scheduled | 5 |

## Counts by event class
| Event class | Events |
|---|---:|
| central_bank_gold_demand | 10 |
| fomc_statement | 5 |

## Recent / detected events preview
| Time UTC | Source | Class | Channel | Expected | Title |
|---|---|---|---|---:|---|
| 2026-06-03T16:00:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 世界黄金协会 ： 2026年4月全球央行重启黄金净买入 _ 金市直播 _ 黄金网 _ 中金在线 |
| 2026-06-04T02:00:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 3月大抛售后 ， 全球央行4月重新恢复购金 - CFi . CN 中财网 |
| 2026-06-04T02:30:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 中國和波蘭正在囤黃金 ！ 世界黃金協會揭驚人數據 全球央行動向一次看 |
| 2026-06-04T06:30:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 全球央行扫货黄金 4月净购金17吨 _ 新闻频道 _ 中华网 |
| 2026-06-04T07:45:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 波兰央行单月净购入黄金14吨 全球央行恢复增持态势 _ 新闻频道 _ 中华网 |
| 2026-06-04T08:15:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 净购入黄金17吨 ， 全球央行重启买买买 - CFi . CN 中财网 |
| 2026-06-04T08:15:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 黄金缘何成全球官方储备最大资产 - 金融频道 - 杭州网 |
| 2026-06-04T15:30:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 净购入黄金17吨 ！ 全球央行重启买买买 |
| 2026-06-04T18:45:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 买买买 ！ 全球央行重新 扫货 黄金 |
| 2026-06-05T03:15:00+00:00 | gdelt | central_bank_gold_demand | central_bank_demand | 1 | 金价高位震荡 ， 全球央行重新入场 扫货 能否支撑未来走势 ？- 华龙网 - 重庆市委市政府官方新闻门户 |
| 2026-06-17T18:00:00+00:00 | scheduled | fomc_statement | real_yield_fed_path | 0 | FOMC statement / SEP / press conference |
| 2026-07-29T18:00:00+00:00 | scheduled | fomc_statement | real_yield_fed_path | 0 | FOMC statement |
| 2026-09-16T18:00:00+00:00 | scheduled | fomc_statement | real_yield_fed_path | 0 | FOMC statement / SEP / press conference |
| 2026-10-28T18:00:00+00:00 | scheduled | fomc_statement | real_yield_fed_path | 0 | FOMC statement |
| 2026-12-09T19:00:00+00:00 | scheduled | fomc_statement | real_yield_fed_path | 0 | FOMC statement / SEP / press conference |

## Warnings
- `GDELT fetch failed query=XAUUSD: HTTPError: HTTP Error 429: Too Many Requests`
- `GDELT fetch failed query=gold federal reserve: HTTPError: HTTP Error 429: Too Many Requests`

## Outputs
- unified Stage 10A CSV: `data/config/stage10a_news_events.csv`
- detected shock CSV: `data/macro/events/stage10b_detected_shock_events.csv`
- scheduled normalized CSV: `data/macro/events/stage10b_scheduled_events_normalized.csv`
- unified full CSV: `data/macro/events/stage10b_unified_news_events.csv`
- GDELT query status CSV: `data/reports/stage10b_event_pipeline_update/stage10b_gdelt_query_status.csv`
- workflow metadata JSON: `data/reports/stage10b_event_pipeline_update/workflow_run_metadata.json`
- workflow metadata MD: `data/reports/stage10b_event_pipeline_update/workflow_run_metadata.md`

## Decision
- No EA change.
- No automatic news trading.
- Run Stage 10A/10D after copying the artifact into local repo.
