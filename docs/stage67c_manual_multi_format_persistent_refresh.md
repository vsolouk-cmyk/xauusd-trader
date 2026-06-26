# Stage67C Manual Multi-Format Persistent Refresh

Local-only manual data refresh and Stage66J2 readiness runner.

Supported source inputs in `~/Downloads`:
- `amarkets_xauusd_5m.csv` from MT5 with `<DATE>`, `<TIME>`, `<OPEN>` headers.
- `US Dollar Index Historical Data.csv` or `dxy.csv` from Investing.
- `DFII10.csv` or `real_yield.csv` from FRED.
- `VIXCLS.csv` or `vix.csv` from FRED.
- `ETF_Flows*.xlsx` or `etf_flow.csv` from WGC.
- `World_official_gold_holdings*.xlsx` or `central_bank_demand.csv` from WGC.

Policy:
- No internet download.
- Append/upsert by date; never truncate existing history.
- XLSX files are raw-extracted into `data/exogenous/wgc_raw_extracted/` and best-effort mapped only if clear date/value columns are found.
- No order, broker, EA, paper-live, or live authorization.
