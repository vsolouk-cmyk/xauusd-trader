# XAUUSD Cross-Asset Intraday Readiness V1

This package inventories—not trades—the broker's cross-asset symbols and existing local files before building a materially different intraday regime panel.

Core categories:

- USD proxy: DXY/USDX, or both EURUSD and USDJPY
- US rates proxy: US10Y/UST10/TNX/10-year Treasury CFD
- precious confirmation: XAGUSD/silver

Optional categories:

- VIX/volatility CFD
- US500/SPX500
- WTI/Brent

The MQL5 file is a read-only Script. It enumerates matching symbols, current spread, and M15/H1/D1 history metadata. It contains no order, position, or trade-request functions.

The Python collector normalizes the MT5 CSV, scans existing local files, creates readiness reports, and packages:

`~/Downloads/XAUUSD_CROSS_ASSET_INTRADAY_READINESS_RESULTS.zip`

No paper, demo, or live order is authorized by this package.
