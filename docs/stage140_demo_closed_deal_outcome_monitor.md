# Stage140 Demo Closed Deal Outcome Monitor

Stage139 showed:
- Stage134 demo order accepted
- no open XAUUSD position remains

Stage140 reads MT5 deal history to determine whether the demo order closed by SL/TP/manual/other and what the realized PnL was.

It is read-only:
- no order send
- no position modification
- no duplicate order logic

Install/compile the indicator:
- `Stage140_DemoClosedDealOutcomeMonitor.mq5`

Then run:
- `app/stage140_demo_closed_deal_outcome_collector.py`

The collector classifies:
- `STAGE140_CLOSED_DEMO_DEAL_PROFIT`
- `STAGE140_CLOSED_DEMO_DEAL_LOSS`
- `STAGE140_CLOSED_DEMO_DEAL_FLAT`
- `STAGE140_ENTRY_DEAL_FOUND_BUT_NO_EXIT_DEAL`
- `STAGE140_ACCEPTED_ORDER_BUT_NO_SYMBOL_DEAL_FOUND_CHECK_HISTORY_WINDOW`
