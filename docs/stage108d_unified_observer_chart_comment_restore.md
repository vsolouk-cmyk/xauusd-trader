# Stage108D Unified Observer Chart Comment Restore

## Purpose
Restore the on-chart `Comment()` overlay for the Stage108 unified observer EA while preserving the existing journal `Print()` output and observer-only hard blocks.

## Scope
- Updates `mt5/Unified_ObserverOnly_EA.mq5` only.
- No Python observer logic changes.
- No rule, threshold, broker, order, paper-live, or live change.

## Expected chart overlay
The chart should show:
- feature date
- observer-only mode
- any signal active
- selected rule
- execution/order flags
- 7 rule status lines: K06, K03, K07, S83_14, S83_13, C96_07, S105_03

## Hard blocks
- No automated order
- No paper order
- No broker connection
- No OrderSend or CTrade usage
- Observer-only EA
