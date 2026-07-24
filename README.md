# XAUUSD MT5 Bounded Demo Bridge — Volume Diagnostic & Logging Repair

This repair keeps the bridge disabled and order-forbidden while fixing two issues:

1. A broker minimum-lot mismatch is reported as an **arming blocker**, not as an EA installation failure.
2. The EA now publishes periodic diagnostics to the MT5 Experts log, chart comment, heartbeat, and `bridge_runtime.log`.

## Safety state

- `InpArmed=false`
- no arming permit is included
- demo orders remain forbidden
- live orders remain forbidden
- minimum lot is never rounded upward to force execution

## Runtime decisions

- `PASS_MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_DISABLED_NO_ORDER`
  - disabled runtime is healthy and volume is arming-ready.
- `PASS_MT5_DEMO_BRIDGE_RUNTIME_DISABLED_ARMING_BLOCKED_VOLUME_CONTRACT`
  - disabled runtime is healthy, but arming is blocked by minimum lot / equity.
- `MT5_DEMO_BRIDGE_RUNTIME_PREFLIGHT_FAIL_CLOSED`
  - EA installation, account mode, symbol, heartbeat, or locked contract is invalid.

## New diagnostics

The heartbeat and log expose:

- account equity
- bid / ask / midpoint
- contract size
- minimum / maximum / step volume
- minimum-lot notional and notional/equity ratio
- raw and floored target volume
- required equity for the validated ceiling
- required equity for the initial target exposure
- exact equity multipliers
- volume contract decision

## Log locations

- MT5 `Experts` tab: init and periodic status lines
- chart comment: current disabled status and volume decision
- file:
  `MQL5/Files/XAUUSD_DEMO_BRIDGE/bridge_runtime.log`
- heartbeat:
  `MQL5/Files/XAUUSD_DEMO_BRIDGE/bridge_heartbeat.txt`

## Required post-install action

Re-copy the `.mq5`, compile it in MetaEditor, remove the old EA instance from the chart, and attach the newly compiled EA with `InpArmed=false`.
