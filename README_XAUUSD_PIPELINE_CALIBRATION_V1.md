# XAUUSD Pipeline Calibration / Positive-Control Audit V1

Program: `XAUUSD_PIPELINE_CALIBRATION_POSITIVE_CONTROL_AUDIT_V1_REFERENCE_LOCKED`

## Purpose

This is **not a new alpha scan** and does not promote a trading strategy. It tests whether the validation machinery that rejected earlier XAUUSD candidates is capable of:

1. rejecting a known null;
2. detecting deliberately planted positive edge at controlled strengths/sample sizes;
3. distinguishing statistical edge detection from commercial promotion;
4. producing a non-decisive empirical sanity benchmark using classical 12-month volatility-scaled time-series momentum on the existing XAUUSD CFD proxy.

No 2025+ diagnostic data are evaluated. No paper, demo, or live orders are permitted.

## Why two pass concepts exist

The previous fixed-scan gate includes a locked 2% CAGR hurdle. That is a **commercial hurdle**, not a pure test of whether alpha is statistically detectable.

This audit therefore reports:

- `statistical_detection_rate`: all locked fixed-scan robustness gates except CAGR;
- `commercial_promotion_rate`: all locked fixed-scan gates including CAGR.

A planted edge can be detected statistically but rejected as commercially too small. That is intentional and must not be interpreted as "the pipeline cannot see alpha".

## Synthetic control design

The audit loads only 2016-2024 rows from the existing cross-asset target file and uses XAUUSD exact 4h forward returns in the same 06:00-19:00 UTC weekday universe used by the fixed scan.

It then:

- greedily creates non-overlapping 4h opportunities;
- removes observed year/hour drift from 4h returns;
- randomizes side so the null has no directional market bias;
- plants controlled **severe-net** edge of 0, 4, 8, 12, 16, or 20 bps;
- repeats the experiment at 100, 300, 600, and 1000 trades;
- runs 40 Monte Carlo trials per cell;
- applies the same PF, block-bootstrap, remove-largest-winner, matched-excess, fold, worst-fold, year-concentration and locked-risk CAGR gates used by the fixed cross-asset reference scan.

There are 24 cells and 960 trials total.

### Locked calibration decision thresholds

`PIPELINE_CALIBRATED_PASS` requires all of the following:

- statistical false-positive rate at n=1000, alpha=0 <= 5%;
- statistical detection rate at n=100, alpha=12bps >= 70%;
- statistical detection rate at n=300, alpha=8bps >= 80%;
- commercial false-positive rate at n=1000, alpha=0 <= 5%;
- commercial promotion rate at n=1000, alpha=16bps >= 80%;
- no detection-curve monotonicity drop greater than 15 percentage points.

If false positives are controlled but power is inadequate, decision is:

`PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED`

Other unresolved calibration failures produce:

`PIPELINE_INCONCLUSIVE`

## Empirical TSMOM sanity benchmark

The empirical benchmark implements the core published specification:

`sign(past 12-month return) × 40% / ex-ante volatility × next-month return`

with a past-only exponentially weighted volatility estimate using a 60-day center of mass and monthly formation.

Reference specification:

- Tobias J. Moskowitz, Yao Hua Ooi, Lasse Heje Pedersen, *Time Series Momentum*, Journal of Financial Economics 104 (2012), 228-250, DOI 10.1016/j.jfineco.2011.11.003.

Important limitation: this package uses the **existing XAUUSD CFD proxy only**. It does not reconstruct the paper's 58 futures/forward portfolio, roll return, or risk-free excess-return series. Therefore TSMOM is reported as:

`EMPIRICAL_SANITY_BENCHMARK_NOT_CALIBRATION_DECIDER`

Its result cannot by itself label the pipeline good or bad.

## Required existing input

Default:

`reports/xauusd_cross_asset_intraday_panel/cross_asset_intraday_targets.csv`

Required columns:

- `decision_time_utc`
- `entry_open`
- `forward_return_4h_bps`

No panel rebuild or MT5 export is required.

## Outputs

Under:

`reports/xauusd_pipeline_calibration/`

- `pipeline_calibration_summary.json`
- `pipeline_calibration_decision.md`
- `calibration_contract.json`
- `input_manifest.json`
- `synthetic_control_profile.json`
- `synthetic_detection_curve.csv`
- `synthetic_gate_pass_rates.csv`
- `empirical_tsmom_summary.json`
- `empirical_tsmom_monthly.csv`

Collector output:

`~/Downloads/XAUUSD_PIPELINE_CALIBRATION_RESULTS.zip`

## Safety contract

- No strategy discovery.
- No threshold optimization against historical alpha candidates.
- No access to 2025+ for decision making.
- No paper orders.
- No demo orders.
- No live orders.
- No network/API access.
- No MQL/MetaTrader dependency.

## Interpretation

### If `PIPELINE_CALIBRATED_PASS`

The result supports the claim that the validation stack is capable of both saying **NO** to null edge and **YES** to sufficiently strong planted edge. Previous candidate KILL decisions should still be interpreted only for their exact formulations, but there is no evidence that the validator is mechanically incapable of producing a positive result.

### If `PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED`

Do not resume alpha discovery and do not lock a commercial pivot. Recalibrate the validation framework first.

### If `PIPELINE_INCONCLUSIVE`

Stop both research expansion and commercial pivot decisions until the calibration failure is diagnosed.
