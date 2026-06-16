# Stage 5A.1 — EA Safety Audit

Purpose: statically audit the Stage 5A MT5 EA and confirm it remains dry-run/log-only.

This does **not** authorize demo-order, paper-order, or live trading.

## Run

From the repo root:

```bash
python3 -m app.stage5a_ea_safety_audit
```

Explicit EA path if needed:

```bash
python3 -m app.stage5a_ea_safety_audit --ea mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5
```

## Output

Reports are written to:

```text
data/reports/stage5a1_ea_safety_audit.json
data/reports/stage5a1_ea_safety_audit.md
```

`data/reports/` is local evidence and should not be committed.

## Hard blocker

Any executable order-placement or position-management code is a blocker, including:

```text
OrderSend
CTrade
Buy/Sell calls
PositionOpen
PositionClose
MqlTradeRequest
TRADE_ACTION_DEAL
TRADE_ACTION_PENDING
```

If the audit returns `FAIL`, do not run that EA in MT5 until fixed.
