# Stage56 Parallel Alternative Megascan Design

Stage56 runs the three Stage55 alternative thesis families in one bounded broker-real scan and applies one shared hard-audit policy. It is deliberately a historical scanner and audit tool only.

Families:

- `ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE`: failed squeeze breakout pullback/reversal.
- `ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA`: trend-confirmed pullback to an M15 value area after impulse.
- `ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION`: session range extension and exhaustion reversion.

Key constraints:

- Reads only local AMarkets broker-real multitf SQLite data.
- Uses Stage48F stress/extreme cost model where available.
- Does not use Stage52 true-forward evidence as historical training data.
- Does not place orders.
- Does not authorize promotion, EA, paper-live, or live trading.

The default run is single-process for older Mac stability. It still scans all three families in one execution and ranks them under a shared audit model. `--max-workers` may be increased only if memory is acceptable.
