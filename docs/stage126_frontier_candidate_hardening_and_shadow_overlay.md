# Stage126 frontier candidate hardening and shadow overlay

Stage126 validates candidate(s) selected by Stage125, especially `F125_04_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP`, in one consolidated pass.

It is report/status only. It does not open any order, paper/live, broker, CTrade, or OrderSend surface.

## Inputs

- `reports/stage125_market_open_shadow_telemetry_and_frontier_discovery/stage125_selected_for_stage126.csv`
- `data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv`

## Main checks

- Required feature availability
- Full-period, selection, validation, and tail metrics
- 10 bps cost stress
- 120-hour event-spacing non-overlap count
- Year concentration
- Stage127 queue decision

## MT5 status output

Optional flag:

```bash
--write-mt5-status-kv --write-mql5-indicator
```

This writes a two-column key/value CSV and an optional indicator source for chart display only.

## No-order governance

Stage126 keeps all order surfaces blocked:

- no automated order
- no paper order
- no broker connection
- no CTrade
- no OrderSend
- no live
