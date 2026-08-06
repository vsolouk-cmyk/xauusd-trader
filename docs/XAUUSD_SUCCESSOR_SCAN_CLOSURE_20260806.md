# XAUUSD Successor Parallel Scan — Commercial Closure

Decision: `NO_REFERENCE_SURVIVOR_REJECT_SUCCESSOR_SET`

The result package was hash-verified. Trade arithmetic, severe-cost subtraction,
48-hour exact horizons, non-overlap, shortlist/lock identity, and candidate metrics
were independently recomputed from the exported trade ledgers.

## Core findings

- 19 candidates across 9 families were tested on 2015-2024 reference data.
- Reference pass count: 0.
- Only two candidates had positive severe-cost mean:
  - `range_breakout_48h_72`: 2.646 bps, PF 1.058, bootstrap p10 -4.457 bps.
  - `volatility_expansion_48h`: 1.471 bps, PF 1.033, bootstrap p10 -4.531 bps.
- No candidate reached reference PF 1.15.
- All 19 candidates had non-positive bootstrap p10.
- No candidate reached the 2% locked-risk CAGR gate.

The top range breakout remained unstable: the 2021-2022 fold averaged -10.289 bps,
and the combined 2015-2026 replay CAGR was about 0.278%. Its 2025 holdout was
strong while 2026 was sharply negative, indicating regime dependence rather than
a stable unconditional edge.

## Governance defect found

The scanner accessed and locked the 2025+ holdout even though reference pass count
was zero. This does not change the rejection decision, but it unnecessarily consumed
the holdout. Future scanners must stop before holdout access when no reference
candidate passes.

## Only justified follow-up

A post-scan side decomposition showed that `volatility_expansion_48h` was masked by
its short leg. On 2015-2024 AMarkets reference data:

- LONG: mean 9.818 bps, PF 1.246, bootstrap p10 0.837 bps, 4/5 positive folds.
- SHORT: mean -7.352 bps, PF 0.852.

This is not a promotion result because the decomposition was discovered after the
scan and 2025+ has already been observed. The next bounded test is therefore an
attribution audit only: pre-2025 data, fixed parameters, matched bull-drift controls,
and independent Dukascopy feed replication. If that fails, the price-only H1 path
closes and the project pivots to macro-data regime research.

Paper, demo, and live order authorization remain false for this research path.
