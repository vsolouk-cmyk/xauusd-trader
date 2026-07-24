# XAUUSD Historical-As-Of Replay V7 Runbook

## Purpose

Close the forward direction-policy mismatch without waiting for a future signal.

## Inputs

- canonical Commercial Closure execution ledger;
- canonical Commercial Closure summary;
- aligned AMarkets H1 database;
- controlled-paper runtime config.

## Validated formulation

```text
LONG  = probability_up >= 0.60
SHORT = probability_up <= 0.40
entry = H1 i+1 open
exit  = H1 i+24 close
```

The replay validates all 146 evaluated trades, 22 missing-evidence rows, source-proven cost formulas, and all saved commercial metric blocks.

## Command

```bash
python3 app/xauusd_controlled_paper_historical_replay.py --root .
```

## Expected result after this overlay

```text
program = XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V7_OFFICIAL_EVENT_CONTEXT_CLOSURE
current_forward_policy_parity.pass = true
forward_wait_required_for_replay = false
```

With currently absent historical event context, the expected decision is:

```text
PASS_FULL_HISTORICAL_EVENT_AWARE_REPLAY_DEMO_DESIGN_ALLOWED_NO_FORWARD_WAIT
```

This permits continued controlled paper logging but does not authorize demo/live design. Historical event context remains the bounded pre-demo gap.
