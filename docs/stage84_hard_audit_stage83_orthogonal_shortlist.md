# Stage84 Hard Audit - Stage83 Orthogonal Shortlist

Stage84 hard-audits the Stage83 orthogonal discovery shortlist before any observer-only portfolio expansion.

## Scope

- Input: Stage83 orthogonal discovery shortlist and the lag-safe daily macro dataset.
- Output: a strict shortlist for Stage85 portfolio-increment review.
- No MT5 or EA changes.
- No order authorization.
- No threshold tuning.

## Method

Stage84 recomputes each Stage83 shortlisted rule from the macro dataset and applies stricter gates:

- total entries, mean, median, win rate, and worst loss
- validation, locked-forward, final-holdout, and post-as-of metrics
- year concentration
- overlap with the current Stage77B observer portfolio
- incremental union active days
- missing required feature rows after natural rolling/return warm-up
- lookahead violations

The current observer portfolio remains:

- `K06_RESILIENT_GOLD_VS_DXY_H120`
- `K03_SAFE_HAVEN_REALYIELD_H120`
- `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`

## Expected follow-up

If Stage84 selects candidates, Stage85 should run portfolio-increment review. Stage84 does not authorize adding the candidates to MT5 directly.

## Hard blocks

- `NO_AUTOMATED_ORDER`
- `NO_PAPER_ORDER`
- `NO_BROKER_CONNECTION`
- `NO_EA_PROMOTION`
- `NO_PAPER_LIVE`
- `NO_LIVE`
- `NO_ORDER_AUTHORIZATION_FROM_STAGE84`
- `NO_THRESHOLD_TUNING_FROM_STAGE84_HARD_AUDIT`
- `NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE84`
