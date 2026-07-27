# XAUUSD bounded-demo activation runbook

## Scope

This package completes the operational activation path for the frozen
`logistic__direction_24h` candidate on AMarkets demo login `7907958`.

It does **not** authorize a live account. Python never sends an order. The only
order boundary remains inside the existing MT5 EA and requires all of these:

- `ACCOUNT_TRADE_MODE_DEMO`;
- exact login `7907958`;
- `InpArmed=true`;
- active unexpired permit linked to the current bounded-preflight hash;
- exact XAUUSD symbol and magic `1782401`;
- live spread at or below `3.0764778059487488` bps;
- executable volume without increasing the locked risk;
- no weekly pause or hard-drawdown kill;
- at most one concurrent position and one new position per day;
- an unexpired, event-cleared, idempotent candidate;
- qualification below 30 calendar days and below 10 resolved positions.

## Why the exporter is required

The bridge EA consumes `demo_candidate.txt`; it does not calculate Stage180
features. The recent-bar exporter keeps completed broker M5/H1 bars available to
the local Python cycle. The cycle merges those bars into the persistent AMarkets
CSVs, runs the frozen model and controlled-paper logger, and only then asks the
existing bridge emitter to create a candidate.

## Arming sequence

1. Compile and attach `AMarkets_Recent_Bar_Exporter_EA.mq5` to an XAUUSD M5
   chart. Leave the exact default login `7907958` unchanged.
2. Run the explicit `arm` command. It reruns runtime-preflight and the complete
   fresh dry-cycle before creating `arming_permit.txt`.
3. Reload the existing `XAUUSD_BoundedDemoBridge` on an XAUUSD H1 chart with
   the generated `...ARMED_INPUTS.txt` values.
4. Run `verify`; require
   `PASS_DEMO_BRIDGE_ARMED_RUNTIME_GUARDS_ACTIVE`.
5. Run one operational cycle manually; require
   `PASS_BOUNDED_DEMO_OPERATIONAL_CYCLE`.
6. Load the LaunchAgent for a five-minute cycle.

A neutral model output is normal: the bridge remains armed but no candidate or
order is created until probability reaches a frozen tail (`>=0.60` or `<=0.40`).

## Emergency disarm

Run the `disarm` command, then reload the bridge EA with `InpArmed=false`.
The command removes the permit and any waiting candidate but does not destroy
receipts or unmanaged broker history. The EA continues managing an already-open
bridge position until its normal/hard-kill exit.

## Primary outputs

```text
reports/xauusd_mt5_demo_activation/explicit_demo_arming_summary.json
reports/xauusd_mt5_demo_activation/explicit_demo_arming_verification.json
reports/xauusd_mt5_demo_activation/operational_cycle_summary.json
reports/xauusd_mt5_demo_activation/operational_cycle_failure.json
MQL5/Files/XAUUSD_DEMO_BRIDGE/arming_permit.txt
MQL5/Files/XAUUSD_DEMO_BRIDGE/SOURCE/recent_export_status.txt
MQL5/Files/XAUUSD_DEMO_BRIDGE/demo_candidate.txt   # only for an eligible signal
```
