# Stage61D Tiny Demo Order Test Design

Stage61D prepares a one-row CSV for the already compiled Stage61 demo execution harness. It is an execution-plumbing test only. It does not prove statistical edge and does not authorize paper-live or live trading.

Default mode is preview-only. The MT5-ready armed signal file is created only when both CLI flags are passed:

```bash
--arm-demo-order --i-understand-demo-order
```

Required MT5 constraints for the armed run:

- demo account only
- `RequireDemoAccount=true`
- `AllowTrading=true` only during the short test window
- `FixedLot=0.01`
- `MaxOpenPositions=1`
- `MaxOrdersPerDay=1`
- disable `AllowTrading` immediately after the test

The Python script does not connect to a broker and never sends orders.
