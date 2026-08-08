# QA — XAUUSD Pipeline Calibration / Positive-Control Audit V1

## Final package QA performed before delivery

### Package integrity

- Clean extraction into an empty directory: PASS
- `SHA256SUMS.txt` verification: PASS
- Package manifest present: PASS
- Python compile (`python3 -m compileall -q app tests`): PASS
- Unit tests with `ResourceWarning` promoted to error: **16/16 PASS**
- Static AST scan for network/order imports/calls: PASS
- Missing-input fail-closed path: PASS
- Collector path: PASS

### Real project evidence smoke / end-to-end

Input used:

- compact evidence derived from the real cross-asset target panel;
- 61,823 total target rows in source evidence;
- 52,393 reference rows loaded for 2016-2024;
- 8,708 non-overlapping eligible 4h opportunities;
- compact target evidence SHA256: `f251ef9173a6ce4d436a616054aa1bc0335ed93102691a8637d11645c2827ba8`.

2025+ rows used in decision: **0**.

Observed calibration result on this real evidence:

`PIPELINE_CALIBRATED_PASS`

Observed key rates:

- Statistical false positive, n=1000 / planted edge=0bps: **0.00**
- Statistical detection, n=100 / planted severe-net edge=12bps: **1.00**
- Statistical detection, n=300 / planted severe-net edge=8bps: **0.95**
- Commercial false positive, n=1000 / planted edge=0bps: **0.00**
- Commercial promotion, n=1000 / planted severe-net edge=16bps: **1.00**
- Maximum statistical monotonicity drop: **0.00**
- Maximum commercial monotonicity drop: **0.00**

### Empirical TSMOM sanity benchmark on the same XAUUSD CFD proxy

This result does not control the calibration verdict.

- Months: 95
- Formation period: 2017-01 through 2024-11
- Gross annualized mean return: ~6.38%
- Gross annualized volatility: ~43.84%
- Gross zero-risk-rate Sharpe: ~0.145
- Gross max drawdown: ~-83.8%
- Directionally positive: YES
- Investable / promoted by this package: **NO**

The poor risk-adjusted profile is precisely why this is treated as an empirical sanity benchmark rather than a strategy candidate.

### What was not tested in this environment

- Native execution against the user's uncompressed local `cross_asset_intraday_targets.csv`; the compact evidence contains the same reference row sequence/fields needed by the audit, but the user-local raw file itself was not mounted here.
- Native MetaTrader / MetaEditor compile: not applicable; package contains no MQL.
- Live/demo/paper execution: intentionally prohibited.
