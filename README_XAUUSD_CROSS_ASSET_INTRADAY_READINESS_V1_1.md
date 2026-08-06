# XAUUSD Cross-Asset Intraday Readiness V1.1

This repair makes the read-only MT5 inventory export atomic and recoverable when the Script is launched more than once or the canonical CSV is temporarily locked.

## Repair

- Every run writes a unique complete snapshot first.
- The snapshot is flushed and closed before publication.
- Publication to `mt5_cross_asset_inventory.csv` uses `FileMove(..., FILE_REWRITE)` with retries.
- If the canonical file is locked, the complete timestamped snapshot remains valid.
- The Python collector scans the canonical file and snapshots, rejects header-only/corrupt files, and selects the newest valid inventory.
- One Script execution is sufficient; running it on multiple charts is unnecessary.

The package remains inventory-only. It has no paper, demo, live, order, position, or trade-request path.
