# Stage61C2 Demo Parse Telemetry Design

Purpose: verify that the MT5 EA can read `stage61_demo_signals.csv` from `MQL5/Files` and write an auditable telemetry file `stage61_ea_status.csv` without sending orders.

This is a no-order parse telemetry stage only. It does not authorize paper-live, live trading, or unrestricted demo order submission.
