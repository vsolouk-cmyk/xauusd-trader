# XAUUSD Cross-Asset Intraday Panel V1.2

Program: `XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1_2_SESSION_ELIGIBILITY_CONTRACT_REPAIR`

## Why V1 failed

V1 required each core H1 four-hour return to be present on at least 90% of all XAUUSD H1 anchor rows. This is incompatible with the locked exact-gap contract: the daily metals maintenance break intentionally invalidates several four-hour windows each day. The observed XAUUSD/XAGUSD coverage near 78% is therefore expected session geometry, not missing source history.

## Repair

- Quality denominator is now the set of XAUUSD rows with a valid exact four-hour history window.
- XAGUSD/EURUSD/USDJPY are measured conditionally on that eligible XAUUSD set.
- A safe `core_h1_4h_history_ready` feature flag is added.
- Future target availability is retained only in the target file, never in features.
- Risk/energy composite requires any two of S&P500, WTI and BRENT and records component count.
- Optional asset availability flags are explicit.
- Near-empty exact-gap columns are retained locally but marked `EXCLUDE_NEAR_EMPTY` for the fixed scan.
- Large feature/target CSVs remain local. `collect` creates a compact evidence ZIP and records their SHA256/size/shape instead of embedding them.
- Existing MT5 exports from program V1 remain accepted. The MQL exporter is byte-identical to V1.1 and does not need recompilation or rerun.

## No execution

No paper, demo, live, broker, order, or position path is introduced.
