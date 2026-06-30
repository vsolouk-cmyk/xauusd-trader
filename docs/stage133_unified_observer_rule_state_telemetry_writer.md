# Stage133 Unified Observer rule-state telemetry writer

Stage132 confirmed the Unified Observer EA runtime is alive. Stage133 adds rule-state telemetry inside the existing `DisplaySignal()` flow after the signal CSV has been read.

This package does not:
- add order functions
- add trade-class usage
- change signal rules
- change selected-rule logic
- change chart UI
- open paper/live/live paths

The injected MQL5 code writes:
- `xauusd_stage133_unified_observer_rule_state_kv.csv`
- `xauusd_stage133_unified_observer_rule_state_latest.csv`
- `xauusd_stage133_unified_observer_rule_state_history.csv`

The telemetry records the seven current observer rules:
- K06
- K03
- K07
- S83_14
- S83_13
- C96_07
- S105_03

Compile the patched EA and reload it on XAUUSD,H1. Then run Stage133 without `--patch-source` to verify fresh telemetry.
