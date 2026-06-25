# Stage64J4 - WGC ETF and Central-Bank Mapper

Purpose: convert inspected World Gold Council workbooks into Stage64 raw source CSV schemas.

This stage maps:

- WGC ETF workbook `Demand by month` into `data/macro_regime/raw/gold_etf_holdings_or_flows.csv`
- WGC central-bank changes workbook `Monthly` into `data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv`

It does not run validation, generate targets, create signals, connect to a broker, or authorize order/paper/live.

Important assumptions:

- ETF historical release timestamps are not embedded in the inspected workbook; Stage64J4 applies a conservative lag after period end.
- Central-bank reserve changes are aggregated across countries into a global monthly net-demand proxy with a conservative 75-day release lag.
- Event-calendar archive remains blocked unless acquired separately; forward-only governance cannot be used for historical backtest uplift.
- Broker/spot alignment remains required before any commercialization claim.

After this stage, rerun Stage64J1 source preflight.
