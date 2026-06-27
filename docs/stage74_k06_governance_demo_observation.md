# Stage74 K06 Governance Demo Observation

## Purpose

Stage74 converts the validated `K06_RESILIENT_GOLD_VS_DXY` thesis into a no-order operational observation protocol.

It is not a new research audit. It does not tune thresholds. It does not authorize demo, broker, EA, paper-live, or live orders.

## Inputs

- Macro dataset: `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- Required validation locks:
  - Stage70B disposition: `PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE`
  - Stage71 disposition: `K06_PASSES_LOCKED_HISTORICAL_FORWARD`
  - Stage72 disposition: `K06_PASSES_HISTORICAL_DAILY_REPLAY`
  - Stage73B disposition: `K06_PASSES_CORRECTED_ASOF_VALIDATION`

## K06 rule

```text
long K06_RESILIENT_GOLD_VS_DXY
horizon_trading_days = 120
entry_cooldown_trading_days = 120
conditions:
  gold_sma20_over_50 > 0
  dxy_ret_20d > 0
  real_yield_change_20d < 0
```

## Decisions

```text
STAGE74_K06_GOVERNANCE_READY_WAIT_SIGNAL_NO_ORDER
STAGE74_K06_REVIEW_ONLY_ACTIVATION_PACKET_READY_NO_ORDER
STAGE74_K06_GOVERNANCE_BLOCKED_NO_ORDER
```

## Review-only activation packet

If all locks pass, data is fresh, and K06 is active, Stage74 creates a review-only activation packet. This packet is evidence only and cannot authorize any order.

The packet records:

- latest feature date
- condition values
- rule and horizon
- reference metrics from Stage71/72/73B
- hard blocks
- manual review instruction

## Hard blocks

```text
NO_AUTOMATED_ORDER
NO_PAPER_ORDER
NO_BROKER_CONNECTION
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_ORDER_AUTHORIZATION_FROM_STAGE74
NO_THRESHOLD_TUNING_FROM_GOVERNANCE_BRIDGE
NO_PROMOTION_FROM_STAGE74_WITHOUT_SEPARATE_MANUAL_AUTHORIZATION
```

## Validation rule after Stage73B

Historical-as-of validation is the primary validation method. Real future rows are not required for statistical proof or daily replay sanity. Real future data is used only for operational freshness, latency, and source-discipline checks.
