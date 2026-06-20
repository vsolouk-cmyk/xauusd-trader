# Stage53 Runbook — Weekend / Market-Closed Preparation

## Routine after market opens

1. Update AMarkets exports.
2. Run Stage52 combined import + true-forward runner.
3. Run Stage53 gate report.
4. Do not reset Stage52 state unless intentionally reinitializing the whole forward test.

## Commands

```bash
python3 app/stage52_import_then_forward_shadow.py \
  --root . \
  --input-dir ~/Downloads \
  --db data/broker_normalized/amarkets_multitf.sqlite \
  --cost-model reports/stage48f/stage48f_cost_model.json \
  --candidates reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv \
  --out reports/stage52_forward_shadow

python3 app/stage53_forward_shadow_gate_report.py \
  --root . \
  --state-db data/shadow/stage52_forward_shadow.sqlite \
  --out reports/stage53_forward_shadow_prep
```

## Kill-switch principles

- If backfill signals are nonzero, do not use the evidence for forward promotion.
- If the watermark does not advance, do not expect new signals.
- If one candidate dominates more than the configured limit, continue collecting evidence.
- If evaluated evidence is positive only in a very short recent window, continue collecting evidence.

## Current intended state

Stage52 is waiting for fresh AMarkets bars beyond the current watermark. Stage53 can be run repeatedly; it only reports readiness.
