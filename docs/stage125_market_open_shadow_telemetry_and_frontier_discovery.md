# Stage125 market-open shadow telemetry and frontier discovery

This is a consolidated, report-only stage. It exists because the market is open and the correct next action is to collect forward shadow telemetry while continuing discovery only where data and thesis coverage justify it.

## Operational decision

Keep the existing `Unified_ObserverOnly_EA` running. It provides the 7-rule rule-status and failure diagnostics.

Do not use Stage124D or Stage124E as permanent replacement EAs on that chart. They were validation/status readers. The correct same-chart path is:

- `Unified_ObserverOnly_EA` remains attached.
- `Stage124F_Rule8OverlayIndicator` is attached as an indicator on the same chart.
- Rule 8 remains observer/shadow only.
- No order path is opened.

## What this script does

- Reads market-open shadow files from `MQL5/Files` and repo shadow/report paths.
- Builds a telemetry snapshot and market-open watch plan.
- Scans frontier discovery candidates without direct DXY or WGC hard-dependency.
- Writes a data-alternative route plan.
- Optionally writes a small Stage125 status KV file to `MQL5/Files`.

## What this script does not do

- It does not send orders.
- It does not use `CTrade` or `OrderSend`.
- It does not modify or replace the active 7-rule EA.
- It does not write EA source files.
- It does not create a live or paper-live path.

## Data alternatives

- Direct DXY is optional. Use FRED/Federal Reserve `DTWEXBGS` broad dollar index as the hard fallback.
- Economic calendar is official-first: FRED release dates, FOMC, Treasury auctions, and BLS/BEA/Census actual releases.
- WGC central-bank data remains reference/candidate-only until a reliable source path is validated. Use SPDR as the validated ETF-flow proxy and build IMF reserve proxy later if central-bank thesis is re-opened.
- COT 2010+ is sufficient for the current broker-history window.

## Expected output

The stage should complete with `NO_ORDER` governance. If `selected_for_stage126_count` is zero, do not build another promotion stage; collect market-open telemetry and only continue discovery after adding a genuinely new data proxy or thesis.
