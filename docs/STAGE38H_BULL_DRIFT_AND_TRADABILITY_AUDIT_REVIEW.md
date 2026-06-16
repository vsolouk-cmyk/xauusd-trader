# STAGE38H Bull Drift and Tradability Audit Review

## Status

`PASS`

## Final decision

`BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION`

Stage38H confirms that a large part of the positive forward returns seen in earlier Stage38 diagnostics can be explained by the unconditional bull drift of XAUUSD during the available AMarkets H1 sample, especially the very strong 2025 regime.

This does **not** invalidate the data foundations built in Stage38B to Stage38G. It does invalidate promotion of any prior candidate unless it can show residual, event-clock, multi-year value after comparison with the drift reference.

## Key observations

### Daily anchor drift reference

| Horizon | Sample | Long mean bps | Median bps | Win rate | t-stat | Decision |
|---:|---:|---:|---:|---:|---:|---|
| 24H | 1283 | 7.24 | 7.11 | 0.536 | 2.21 | DRIFT_REFERENCE |
| 72H | 1281 | 23.04 | 20.80 | 0.547 | 4.14 | BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION |
| 120H | 1279 | 38.85 | 33.43 | 0.565 | 5.59 | BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION |

These numbers are close to, or stronger than, many prior candidate/event-clock baselines. Therefore positive raw forward returns are not enough to indicate edge.

### H1 all-bars overlapped drift reference

| Horizon | Sample | Long mean bps | Median bps | Win rate | t-stat |
|---:|---:|---:|---:|---:|---:|
| 24H | 25619 | 8.50 | 7.48 | 0.538 | 11.71 |
| 72H | 25571 | 25.00 | 19.24 | 0.549 | 20.56 |
| 120H | 25523 | 41.35 | 36.19 | 0.567 | 26.43 |

The overlapped H1 result is not a tradable independent sample, but it confirms the dominant upward drift in the available dataset.

### Year close-to-close drift

| Year | Return bps | Interpretation |
|---:|---:|---|
| 2022 | -392.22 | negative partial year |
| 2023 | +1312.76 | bullish |
| 2024 | +2711.31 | strongly bullish |
| 2025 | +6438.02 | extreme bull regime |
| 2026 | -9.73 | flat partial year through 2026-06-16 |

2025 dominates much of the apparent edge. Earlier candidate promotion attempts were correctly blocked because they were often 2025-driven, weak pre-2025, or weak after event-clock accounting.

## Implication for Stage38B-G

The following sources remain useful only as annotations/context until they pass drift-adjusted survivorship:

- COT foundation and states.
- Macro/risk foundation and states.
- GLD holdings/flow foundation and states.
- Composite exogenous overlays.
- H1/M5/M15 session baselines.

None of them has been promoted to strategy, Stage39, EA, paper-live, or live.

## Required next step

Run a drift-adjusted survivor audit that compares previous Stage38 candidates and overlays against the Stage38H drift reference.

The next audit must not rely on raw mean return. It should require:

1. Event-clock residual return above drift.
2. Multi-year support.
3. Leave-one-year-out robustness.
4. No major chronological half mismatch.
5. No low-sample promotion.
6. No Stage39 or execution promotion.

## Current go/no-go state

```text
Stage39 = NO-GO
EA = NO-GO
paper-live = NO-GO
live = NO-GO
candidate promotion = NO-GO until drift-adjusted survivor audit passes
```
