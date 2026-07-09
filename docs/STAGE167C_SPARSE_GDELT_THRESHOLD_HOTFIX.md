# Stage167C Sparse GDELT Threshold Hotfix

## Decision context

Stage166F proved that GitHub Actions can fetch GDELT and produced a historical event panel. Stage167B still fast-stopped because it computed event quantiles over every M5 train bar. Sparse event panels are expected: most M5 bars have no external-news pressure. All-bar event quantiles can therefore collapse to zero even when thousands of train bars have valid event exposure.

## Fix

Stage167C keeps the Stage167B protections, but changes event thresholding:

- Event thresholds (`shock_q50/q60/q70/q80`, `long_q60/q75`, `short_q60/q75`) are computed on strictly positive train values.
- All-bar event quantiles are preserved only as diagnostics (`shock_allbar_q80`, etc.).
- Fast-stop remains active for truly empty panels or panels with insufficient train active-event bars.
- Default still skips full all-rule trade ledger unless `--export-all-rule-trades` is supplied.

## Interpretation rule

If Stage167C scans rules and returns zero shortlist, the problem is no longer missing event history. The rule space should be rebuilt or killed according to the commercial objective. Do not return to waiting for more low-frequency samples.

## Safety

Read-only research/audit stage:

- `order_routing_allowed = false`
- `demo_release_allowed = false`
- no MT5 execution files are written
