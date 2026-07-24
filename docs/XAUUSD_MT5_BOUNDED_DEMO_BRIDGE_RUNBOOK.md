# XAUUSD MT5 bounded-demo bridge runbook — V1.1

## Current mode

The bridge is diagnostic-only and disabled by default. No arming permit is included.

## Inputs

- `InpArmed=false`
- `InpAllowedDemoLogin=0`
- `InpDiagnosticLogSeconds=30`
- `InpShowChartStatus=true`

## Runtime observability

After attachment, the EA must immediately write one line to the MT5 Experts log and update the chart comment. It repeats a diagnostic line every configured interval.

It also writes:

- `XAUUSD_DEMO_BRIDGE/bridge_heartbeat.txt`
- `XAUUSD_DEMO_BRIDGE/bridge_runtime.log`

## Volume contract

The bridge never increases risk to satisfy minimum lot. If the minimum broker volume exceeds either the initial exposure or the validated ceiling, arming remains blocked.

The runtime report distinguishes:

- healthy disabled installation;
- arming readiness;
- order authorization (always false in this package).

## Resolution paths for a minimum-lot block

Use one of these without changing the locked risk limits:

1. Create a demo account with sufficient virtual equity.
2. Use a broker account/symbol whose XAUUSD minimum volume is smaller, such as `0.001` lot where available.
3. Do not arm the bridge on the current account.

Do not lower the safety check or round the target volume upward.
