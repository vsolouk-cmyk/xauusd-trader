# Stage64R - External Broker/Spot D1 Intake Transfer Fastlane

Purpose: avoid slow memo-only progression after Stage64Q by combining external broker/spot D1 intake, schema normalization, preflight, and locked survivor transfer validation in a single no-order stage.

This stage does not generate signals, connect to a broker, authorize paper/live execution, or scan new hypotheses.

Expected optional input:

```text
data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv
```

Accepted core columns are flexible but must include a parseable date/timestamp and close price. Preferred canonical schema:

```text
date_utc,open,high,low,close,volume,source,available_after_utc
```

If the file is missing, the stage writes/keeps a template and exits with a data-required decision. If the file is present and passes preflight, it evaluates the locked survivor only:

```text
H64L_H1_FULL_MACRO_TAILWIND_LONG
horizon = 120
benchmark = external spot/broker trend-only B1
```

No retuning, no alternative rule discovery, and no event-calendar historical filtering are allowed.
