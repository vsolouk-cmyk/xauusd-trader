# Stage 4E Session Filter Validation

## Purpose

Stage 4D passed, but session breakdown showed London was negative.

Stage 4E tests a small number of predefined session filters. This is not free grid search.

## Session filter

A session filter allows trades only during selected UTC trading sessions.

## Local command

```bash
python3 -m app.xauusd_stage4e_session_filter_validate
```

## Hard rule

Stage 4E is diagnostic only.

It does not authorize demo, paper-order, or live trading.
