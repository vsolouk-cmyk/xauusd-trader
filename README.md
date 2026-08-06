# XAUUSD Cross-Asset Panel Compact Diagnostic Collector V1

Creates a compact ZIP for diagnosing a failed cross-asset panel build without copying the full feature/target CSV files.

It includes:
- report JSON/MD/manifest files;
- app/test/config files when present;
- full column coverage profiles;
- coverage by year, UTC hour, and weekday for H1 ret4 columns;
- feature/target timestamp-sequence tie-out;
- gzipped key-column subsets;
- source-export row/calendar/hash profiles and samples.

No broker, order, position, network, or data modification path exists.
