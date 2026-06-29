# Stage128 market-open forward shadow and frontier megascan

This package is report-only and no-order.

It continues the market-open forward-shadow watch for:

- the 7-rule `Unified_ObserverOnly_EA`
- Stage124F / Rule8 shadow overlay
- Stage126 / Rule9 shadow overlay

It also runs a stricter frontier megascan using available Stage117 macro/COT/dollar/SPDR/VIX data. The scan uses selection-only thresholds and requires deconcentration across validation, tail, and non-overlap segments.

No order path is opened. No EA trading logic is modified.
