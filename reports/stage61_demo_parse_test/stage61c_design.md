# Stage61C Demo Signal Parse Test Design

Stage61C creates one synthetic MT5 signal CSV row for the compiled Stage61 demo execution harness.

Purpose:
- verify full signal CSV parsing in MT5,
- keep `AllowTrading=false`,
- create zero orders,
- keep demo-only execution sandbox separate from statistical edge validation.

This stage does not authorize promotion, paper-live, live trading, or order submission.
