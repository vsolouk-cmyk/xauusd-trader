# Stage149 ATR Stops and Stage143 Timezone Audit

Stage149 implements two external-review P1 items.

## Stage134E ATR-based SL/TP

The demo executor now supports optional ATR-based stop/take-profit sizing.

Defaults:
- `InpUseAtrStops=true`
- `InpAtrTimeframe=PERIOD_H1`
- `InpAtrPeriod=14`
- `InpAtrStopLossMult=1.5`
- `InpAtrTakeProfitMult=2.0`
- fallback fixed points remain available if ATR cannot be calculated.

This keeps demo execution adaptive to XAUUSD volatility while preserving demo-only, max-position, spread, duplicate, and retcode hardening guards.

## Stage149 timestamp/bar audit

`app/stage149_stage143_timezone_and_bar_audit.py` reads Stage143 H1 bars and checks:

- parseable timestamps
- monotonic order
- H1 gap count
- whether the last bar is too far in the future versus local UTC

This is not a replacement for external vendor timestamp validation, but it catches the hidden timestamp/signal-freshness failure modes before using the feed for promotion decisions.
