# Stage61D MT5 Tiny Demo Order Checklist

Before arming:

1. Confirm MT5 is connected to AMarkets-Demo.
2. Confirm the chart symbol is XAUUSD.
3. Confirm no unintended open positions.
4. Keep lot at 0.01.
5. Copy the generated `stage61_demo_signals.csv` into `MQL5/Files` only after reviewing the preview.
6. Set EA inputs:
   - `RequireDemoAccount=true`
   - `AllowTrading=true`
   - `FixedLot=0.01`
   - `MaxOpenPositions=1`
   - `MaxOrdersPerDay=1`
7. Watch Experts/Journal and the Trade tab.
8. Immediately set `AllowTrading=false` after the test.
9. Manually close the demo position if the harness does not close it automatically.

This is a demo execution-plumbing test only.
