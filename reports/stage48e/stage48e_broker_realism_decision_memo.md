# Stage48E Broker Realism Decision Memo

## Status

```text
stage = Stage48E_BROKER_REALISM_DECISION_MEMO
status = BROKER_SPREAD_EXPORT_ACCEPTED_FOR_COST_MODEL_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = STAGE48F_BROKER_REFERENCE_ALIGNMENT_AND_COST_MODEL_CALIBRATION
```

## Input

Stage48D validated the AMarkets XAUUSD M5 MT5-style export:

```text
csv_path = /Users/vahid/Downloads/amarkets_xauusd_5m.csv
row_count = 292435
start_utc = 2022-05-02T01:00:00Z
end_utc = 2026-06-19T08:55:00Z
coverage_days = 1509.329861111111
numeric_spread_rows = 292426
numeric_spread_coverage_pct = 99.99692239301041
median_spread = 32.0
p90_spread = 42.0
p95_spread = 50.0
p99_spread = 53.0
max_spread = 216.0
```

## Decision

The AMarkets M5 export is accepted as a broker-spread data candidate for cost-model calibration and broker/reference alignment.

This is not a trading signal stage. It does not promote any previous thesis and does not allow EA, paper-live, or live trading.

## Why no immediate scan

The export passes basic spread readiness, but the following must still be calibrated before any broker-real scan:

- spread unit interpretation: broker points versus price units and bps conversion;
- broker OHLC alignment versus TwelveData reference OHLC;
- session-by-session cost distribution;
- rollover and spike behavior;
- duplicated/missing bar audit;
- practical cost assumptions for entry and exit.

## Next allowed step

```text
STAGE48F_BROKER_REFERENCE_ALIGNMENT_AND_COST_MODEL_CALIBRATION
```

Stage48F should produce a broker-real cost model and a reference-alignment report. Only after that can a structurally new broker-real thesis decision be considered.
