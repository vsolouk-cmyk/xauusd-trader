# Core Macro Source Plan

This inventory does not download data. When a series is missing, the next package should use these primary sources:

- Broad USD: Federal Reserve/FRED series DTWEXBGS.
- 10Y real yield: Federal Reserve/FRED series DFII10 or U.S. Treasury real yield curve.
- 10Y nominal yield: Federal Reserve/FRED series DGS10.
- 10Y breakeven: Federal Reserve/FRED series T10YIE.
- VIX: Cboe VIX historical daily data.
- GVZ: Cboe GVZ historical daily data.
- Gold positioning: CFTC Disaggregated COT, GOLD - COMMODITY EXCHANGE INC.
- Official event calendar: existing BLS/BEA/FED calendar.
- Optional quarterly prior: World Gold Council Gold Demand Trends, aligned by publication date.
- Optional ETF flow proxy: official fund holdings/shares data with documented availability.

Causality:
- Daily closes become usable next trading session.
- CFTC data becomes usable at release availability, not report date.
- Quarterly demand data becomes usable at publication date, not quarter-end.
