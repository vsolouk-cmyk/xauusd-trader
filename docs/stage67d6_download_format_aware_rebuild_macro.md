# Stage67D6 Download-Format-Aware Rebuild Macro

Purpose: rebuild local canonical macro inputs from the actual downloaded file formats supplied by the operator.

Supported local inputs in `~/Downloads`:

- `amarkets_xauusd_5m.csv`: AMarkets MT5 tab-delimited M5 file with `<DATE>`, `<TIME>`, `<OPEN>`, `<HIGH>`, `<LOW>`, `<CLOSE>`, `<SPREAD>`.
- `US Dollar Index Historical Data.csv`: Investing DXY export with `Date, Price, Open, High, Low, Vol., Change %`; dates are parsed explicitly as month-first `MM/DD/YYYY`.
- `DFII10.csv`: FRED 10Y real yield with `observation_date,DFII10`; dates are strict ISO.
- `VIXCLS.csv`: FRED VIX with `observation_date,VIXCLS`; dates are strict ISO.
- `ETF_Flows_2026-06-02_1536.xlsx`: WGC ETF workbook; mapped from `Demand by month`, column A date serial and column D `Tonnes` / monthly tonnes delta.
- `World_official_gold_holdings_as_of_Jun2026_IFS.xlsx`: WGC central-bank holdings cross-section. It is extracted as raw cross-section only. It is not a 3-month central-bank demand time series.

No internet download, no broker, no order, no paper-live/live.
