# Stage 12A Consolidated Forward-Shadow Report

Generated UTC: `2026-06-10T20:16:24+00:00`
Tool version: `v3_signal_file_state`

> Hard rule: consolidated report only. No EA change, no automatic trading, no paper/live authorization.

## Input completeness audit
| Input | Available |
|---|---|
| long_signal_file_found | `True` |
| long_signal_rows_available | `False` |
| macro_available | `True` |
| gdelt_available | `True` |
| event_guard_available | `True` |
| short_watchlist_available | `True` |

## Executive decision
| Item | Status |
|---|---|
| Trade authorization | `False` |
| EA change authorization | `False` |
| Paper order authorization | `False` |
| Live order authorization | `False` |
| Automatic news trading | `False` |
| Automatic short trading | `False` |
| Observe only | `True` |

## Long v2 forward-shadow state
- state: `signal_file_found_zero_rows`
- file_found: `True`
- rows_available: `False`

| Signal file | State | Rows | Size bytes | Encoding | Latest summary |
|---|---|---:|---:|---|---|
| `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv` | `file_exists_bom_only` | 0 | 2 | `utf-16` |  |

- Interpretation: EA signal file exists, but no signal rows have been logged yet. This is not a trade signal and not an error.

## Macro context
- status: `available`
- source: `report_json`

## GDELT / news monitoring
- status: `available`
- events_loaded: `10`
- event_classes: `{'central_bank_gold_demand': 10}`
- query_status_counts: `{'rate_limited': 2, 'ok': 1}`

| Time UTC | Class | Channel | Expected | Title |
|---|---|---|---:|---|
| 2026-06-03T16:00:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 世界黄金协会 ： 2026年4月全球央行重启黄金净买入 _ 金市直播 _ 黄金网 _ 中金在线 |
| 2026-06-04T07:45:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 波兰央行单月净购入黄金14吨 全球央行恢复增持态势 _ 新闻频道 _ 中华网 |
| 2026-06-04T15:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 净购入黄金17吨 ！ 全球央行重启买买买 |
| 2026-06-04T06:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 全球央行扫货黄金 4月净购金17吨 _ 新闻频道 _ 中华网 |
| 2026-06-04T08:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 净购入黄金17吨 ， 全球央行重启买买买 - CFi . CN 中财网 |
| 2026-06-04T02:00:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 3月大抛售后 ， 全球央行4月重新恢复购金 - CFi . CN 中财网 |
| 2026-06-04T18:45:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 买买买 ！ 全球央行重新 扫货 黄金 |
| 2026-06-04T02:30:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 中國和波蘭正在囤黃金 ！ 世界黃金協會揭驚人數據 全球央行動向一次看 |
| 2026-06-04T08:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 黄金缘何成全球官方储备最大资产 - 金融频道 - 杭州网 |
| 2026-06-05T03:15:00+00:00 | central_bank_gold_demand | central_bank_demand | 1 | 金价高位震荡 ， 全球央行重新入场 扫货 能否支撑未来走势 ？- 华龙网 - 重庆市委市政府官方新闻门户 |

## Event/news guard conclusion
- status: `available`
- source: `stage10e_policy`
- decision: `no_event_guard_passed`
- conclusion: `Stage 10E did not justify yield/news guard`

## Short recent-regime watchlist
- status: `available`
- decision: `recent_short_watchlist_seen_report_only`
- latest_active_count: `0`
- recent_signal_candidate_count: `12`

| Status | Verdict | Active now | Recent count | Last signal UTC | Variant |
|---|---|---:|---:|---|---|
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h6_cool1_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h6_cool1_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h3_cool4_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope3_look12_comp6_1.8_rej6_imp1.2_h3_cool1_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h3_cool1_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | RECENT_REGIME_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h3_cool4_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | SHORT_TERM_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h12_cool1_all |
| RECENT_WATCHLIST_SIGNAL_ONLY | SHORT_TERM_WATCHLIST_ONLY | 0 | 6 | 2026-06-09T05:00:00+00:00 | short_rally_rejection_h4sma20_slope2_look12_comp6_1.8_rej6_imp1.2_h12_cool4_all |

## Operational interpretation
- Long-only validated forward-shadow remains the main active research/monitoring path.
- If the long signal file is found with zero rows, the EA has created the file but has not logged a qualifying signal yet.
- Macro/news and central-bank-demand events remain monitoring/report-only.
- Stage 10E/10D does not enable a yield/news guard.
- Stage 11 short-side candidates are recent-regime watchlist only, not EA rules.
- No short, news, paper, or live order escalation is authorized by this report.

## Output files
- json: `data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.json`
- md: `data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md`
