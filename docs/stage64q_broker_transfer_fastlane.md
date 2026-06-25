# Stage64Q Broker Transfer Fastlane

Purpose: respond to Stage64P broker/spot alignment failure with one compact no-order action.

Stage64Q does not tune thresholds, introduce new hypotheses, connect to a broker, or authorize paper/live/EA. It derives broker D1 bars from local historical AMarkets SQLite bars and reruns the locked Stage64 survivor rule on broker-derived prices over the available overlap.

The audit uses broker-derived trend features for the benchmark and survivor trend condition, while retaining the lag-safe macro/ETF/central-bank features from Stage64K. This is a broker-transfer diagnostic, not a commercialization claim.

Possible decisions:

- `BROKER_TRANSFER_VALIDATION_PASS_RESEARCH_ONLY_STAGE64R_ALLOWED_NO_ORDER`
- `BROKER_TRANSFER_VALIDATION_FAIL_OR_INCONCLUSIVE_EXTERNAL_SPOT_D1_REQUIRED_NO_ORDER`
- `BROKER_TRANSFER_DATA_UNAVAILABLE_EXTERNAL_BROKER_D1_REQUIRED_NO_ORDER`

Hard blocks remain: no order, no broker connection, no paper-live, no live, no EA promotion, no historical event-calendar filter, no rescue filtering.
