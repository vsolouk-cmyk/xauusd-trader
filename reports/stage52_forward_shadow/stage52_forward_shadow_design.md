# Stage52 Volatility Squeeze Forward Shadow Design

## Purpose

Stage51 produced hard-audit pass candidates for the broker-real volatility squeeze breakout thesis. Stage52 converts those pass candidates into a stateful forward-shadow evidence collector.

This is not an EA, not paper-live, not live trading, and not promotion. It records hypothetical signals from closed AMarkets candles and evaluates them only after the configured M5 horizon has matured.

## Inputs

- Persistent AMarkets MultiTF SQLite DB:
  - `data/broker_normalized/amarkets_multitf.sqlite`
- Stage48F broker-real cost model:
  - `reports/stage48f/stage48f_cost_model.json`
- Stage51 pass candidates:
  - primary: `reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv`
  - fallback frozen config: `configs/stage52_forward_shadow_candidates.json`

## Candidate source

Only candidates with:

```text
HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN
```

are eligible.

## State

The script maintains a persistent SQLite state DB:

```text
data/shadow/stage52_forward_shadow.sqlite
```

Each signal is keyed by candidate, entry time, and direction. Re-running the script after data updates is safe: existing signals are skipped, and pending signals are evaluated after enough M5 bars are available.

## Outputs

```text
reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_summary.json
reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_report.md
reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_signals.csv
```

## Gate

Forward shadow must accumulate enough genuinely forward evidence before any later step. This stage still has:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```
