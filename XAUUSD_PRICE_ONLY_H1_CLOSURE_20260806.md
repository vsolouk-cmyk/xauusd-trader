# XAUUSD Price-Only H1 Path Closure — 2026-08-06

Decision: `REJECT_LONG_ONLY_ATTRIBUTION_AND_PIVOT_MACRO_DATA`

The fixed long-only volatility-expansion candidate was evaluated on pre-2025 data only, on AMarkets and Dukascopy, against matched controls.

Key results:
- AMarkets LONG: 397 trades, severe mean +5.14 bps, PF 1.118, bootstrap p10 -2.72 bps, 3/5 positive folds, locked-risk CAGR about 0.31%.
- Dukascopy LONG: 409 trades, severe mean +4.29 bps, PF 1.098, bootstrap p10 -3.22 bps, 3/5 positive folds, locked-risk CAGR about 0.27%.
- Cross-feed return correlation was 0.9999, but signal Jaccard was 0.787, below the locked 0.80 threshold.
- Matched-control excess was positive in mean on both feeds, but AMarkets paired-excess bootstrap p10 remained negative.
- No paper, demo, or live promotion follows from this result.

Next program: inventory existing macro/regime data before downloading only the missing official series.
