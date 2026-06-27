# Stage76 K06 MT5 Observer Bridge

## Purpose

Stage76 converts the validated K06 thesis into an MT5 observer-only bridge.
It writes a CSV signal row that can be copied into `MQL5/Files` and read by
`K06_ObserverOnly_EA.mq5`.

This stage is not an order generator. The EA is intentionally observer-only.

## Required locks

Stage76 requires these prior dispositions:

- Stage70B: `PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE`
- Stage71: `K06_PASSES_LOCKED_HISTORICAL_FORWARD`
- Stage72: `K06_PASSES_HISTORICAL_DAILY_REPLAY`
- Stage73B: `K06_PASSES_CORRECTED_ASOF_VALIDATION`
- Stage75: `K06_PASSES_HISTORICAL_ACTIVATION_DRILL`

## Outputs

- `reports/stage76_k06_mt5_observer_bridge/stage76_k06_mt5_observer_bridge_summary.json`
- `reports/stage76_k06_mt5_observer_bridge/stage76_k06_mt5_observer_bridge_report.md`
- `data/mt5_bridge/k06_observer_signal.csv`
- `mt5/K06_ObserverOnly_EA.mq5`

## MT5 observer-only setup

1. Compile `mt5/K06_ObserverOnly_EA.mq5` in MetaEditor.
2. Copy `data/mt5_bridge/k06_observer_signal.csv` to the terminal's `MQL5/Files` folder.
3. Attach the EA to an XAUUSD chart.
4. Keep `InpAllowTrading=false`.

The EA refuses to initialize if `InpAllowTrading=true`.

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No order send in EA
- Observer-only EA
- No paper-live
- No live
- No order authorization from Stage76
- No threshold tuning from MT5 bridge

## Design note

Building this observer EA is the correct next step after Stage75. It proves the
MT5 handoff and operator display path without waiting for a live active signal
and without sending any order.
