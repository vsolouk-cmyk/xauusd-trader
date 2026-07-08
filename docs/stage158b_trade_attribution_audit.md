# Stage158B Trade Attribution Audit Bar Loader Fix

Stage158B is a read-only audit. It does not write any MT5 execution KV and cannot send orders.

## Why this exists

Stage158 confirmed the global freeze decision, but its summary showed `bar_count=0`. That means the first attribution pass did not parse the AMarkets M5 file, so it could not compute MFE/MAE or theoretical 4-hour outcome. Without those fields we cannot separate rule failure from execution/exit failure.

Stage158B fixes the M5 loader for AMarkets/MT5 tab-separated exports:

```text
YYYY.MM.DD    HH:MM:SS    open    high    low    close    tick_volume    volume    spread
```

## Outputs

- `stage158_trade_attribution_audit_summary.json`
- `stage158_trade_attribution_audit_trades.csv`
- `stage158_diagnosis_summary.csv`
- `stage158_family_attribution_summary.csv`
- `stage158_cohort_attribution_summary.csv`

## Safety

Keep Stage157 freeze active while reviewing this audit.

This stage is not a router. It does not create a signal, does not write `xauusd_stage155...` execution KV, and does not send orders.
