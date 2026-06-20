# Stage61 LoaderFix1 - MQL5 Compile-Safe EA

Fixes:
- Renamed input `SymbolName` to `TradeSymbol` to avoid collision with built-in `SymbolName`.
- Replaced ambiguous direct string comparisons with `StringCompare` helper.
- Reworked runtime gate functions into smaller compile-safe MQL5 functions.
- Kept demo-only and `AllowTrading=false` defaults.

No live trading is authorized.
