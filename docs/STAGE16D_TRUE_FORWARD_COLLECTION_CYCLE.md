# Stage 16D True-Forward Collection Cycle

Stage 16D is an operational research-only cycle runner for Stage 16C.

It prevents a common mistake:

```text
collector_start_utc is newer than local bar data
```

If the local store has no bars after collector start, no true-forward signal can be discovered yet.

## Run without refresh

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage16d_true_forward_collection_cycle
cat data/reports/stage16d_true_forward_collection_cycle/stage16d_true_forward_collection_cycle.md
```

## Run with a refresh command

Use your existing local-store refresh command, for example:

```bash
python3 -m app.stage16d_true_forward_collection_cycle --refresh-cmd "python3 -m app.stage6b_persist_runner"
```

If your refresh module has a different name, replace the command string.

## Outputs

```text
data/reports/stage16d_true_forward_collection_cycle/stage16d_true_forward_collection_cycle.md
data/reports/stage16d_true_forward_collection_cycle/stage16d_true_forward_collection_cycle.json
```

## Decisions

```text
CYCLE_WAITING_FOR_POST_START_DATA
CYCLE_ACTIVE_NO_FORWARD_SIGNAL_YET
CYCLE_TRUE_FORWARD_SIGNAL_OPEN
CYCLE_TRUE_FORWARD_OUTCOMES_AVAILABLE
CYCLE_FAILED_STAGE16C_ERROR
CYCLE_NO_BAR_DATA
```

## Hard rule

Research shadow cycle only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
