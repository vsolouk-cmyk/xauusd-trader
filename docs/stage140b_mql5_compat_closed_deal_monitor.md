# Stage140B MQL5 Compat Closed Deal Monitor

Stage140 indicator may fail to compile on some MT5 builds due to named enum constants used for deal type/reason formatting.

Stage140B keeps the same operational goal but makes the MQL5 indicator more conservative:

- no order send
- no position modification
- no fragile `DEAL_REASON_TP`, `DEAL_REASON_SL`, `DEAL_TYPE_BALANCE`, etc. references
- writes numeric:
  - `latest_entry_type_code`
  - `latest_exit_type_code`
  - `latest_exit_reason_code`
- Python collector maps common reason codes to a label where possible

Compile:
- `MQL5/Indicators/XAUUSD/Stage140_DemoClosedDealOutcomeMonitor.mq5`

Then run:
- `app/stage140_demo_closed_deal_outcome_collector.py`
