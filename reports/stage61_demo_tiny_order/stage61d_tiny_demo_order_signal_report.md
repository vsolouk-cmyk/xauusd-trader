# Stage61D Tiny Demo Order Signal

- status: `TINY_DEMO_ORDER_SIGNAL_ARMED_NO_PROMOTION`
- decision: `TINY_DEMO_ORDER_SIGNAL_ARMED_FOR_MT5_DEMO_ONLY_NO_EDGE_PROMOTION`
- next_allowed_step: `COPY_SIGNAL_TO_MT5_FILES_SET_EA_ALLOWTRADING_TRUE_ON_DEMO_ONLY_THEN_OBSERVE_AND_DISABLE`
- promotion: `NO_GO`
- EA: `DEMO_HARNESS_ONLY`
- paper_live: `NO_GO`
- live: `NO_GO`

## Output
- armed: `True`
- exported_demo_signals: `1`
- preview_file: `/Users/vahid/Desktop/xauusd-trader/reports/stage61_demo_tiny_order/stage61d_tiny_demo_signal_preview.csv`
- mt5_signal_file: `/Users/vahid/Desktop/xauusd-trader/reports/stage61_demo_tiny_order/mt5_files/stage61_demo_signals.csv`
- orders_created_by_python: `0`
- broker_connection_by_python: `DISABLED`

## Required MT5 EA settings for the armed run
- `RequireDemoAccount` = `True`
- `AllowTrading` = `True`
- `FixedLot` = `0.01`
- `MaxOpenPositions` = `1`
- `MaxOrdersPerDay` = `1`

## Interpretation
Stage61D only prepares a one-signal CSV for a tiny demo-account order plumbing test. It does not authorize paper-live, live trading, unrestricted order submission, or edge promotion.
