# Stage64J4 LoaderFix1 - Streaming WGC Mapper

This hotfix replaces repeated worksheet cell access with one-pass `iter_rows(values_only=True)` loading for the relevant WGC sheets.

It maps:

- ETF workbook `Demand by month` into `data/macro_regime/raw/gold_etf_holdings_or_flows.csv`
- WGC central-bank `Changes_latest` / `Monthly` into `data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv`

No validation, signal generation, order generation, EA path, paper-live path, live path, or broker connection is authorized.
