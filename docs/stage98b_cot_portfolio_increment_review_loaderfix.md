# Stage98B COT Portfolio Increment Review Loader Fix

## Purpose

Fix a pandas 3.14 compatibility failure in Stage98 COT portfolio increment review.

## Fixed issue

The previous loader used:

```python
pd.to_numeric(..., errors="ignore")
```

On the user's local Python/pandas stack this raises:

```text
ValueError: invalid error value specified
```

Stage98B replaces that call with a safe numeric conversion helper:

- numeric-looking columns are converted with `errors="coerce"`
- genuinely textual columns are preserved if conversion would make all values null

## Scope

This is a loader/runtime compatibility fix only.

No changes to:

- Stage98 thesis/rule logic
- Stage98 portfolio gates
- COT rule thresholds
- MT5
- EA
- unified observer CSV
- order authorization

## Hard blocks remain

- NO_AUTOMATED_ORDER
- NO_PAPER_ORDER
- NO_BROKER_CONNECTION
- NO_EA_PROMOTION
- NO_PAPER_LIVE
- NO_LIVE
- NO_ORDER_AUTHORIZATION_FROM_STAGE98
- NO_THRESHOLD_TUNING_FROM_STAGE98_PORTFOLIO_REVIEW
- NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE98
