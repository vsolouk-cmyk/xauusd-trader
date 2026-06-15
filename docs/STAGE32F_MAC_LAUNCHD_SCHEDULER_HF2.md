# Stage32F Mac Scheduler HF2 — PID-aware stale lock cleanup

This hotfix replaces the Stage32F launchd scheduler runner with a PID-aware lock.

## Why

Repeated `SKIP_ALREADY_RUNNING` entries can happen when:

1. A previous scheduler instance is genuinely still running.
2. The lock from a previous run became stale.

HF2 stores the process PID inside the lock directory and checks whether that PID is alive. If the PID is not alive, the lock is removed automatically and the scheduler proceeds.

## Files

- `tools/stage32f_scheduler_runner.zsh`
- `docs/STAGE32F_MAC_LAUNCHD_SCHEDULER_HF2.md`

## Behavior

The latest state file now reports the PID in the reason when an active instance is really running:

```text
FINAL_DECISION=SKIP_ALREADY_RUNNING
REASON=another_scheduler_instance_is_running_pid_<PID>
```

If a stale lock is detected, the log includes:

```text
Removed stale lock pid=<PID> ts=<timestamp>
```

## Default policy

- `RUN_WRAPPER_RECOMMENDED` runs the wrapper.
- `RUN_BUT_LOW_SAMPLE_PROBABILITY` is skipped by default.
- To force low-probability wrapper runs, launch manually with `RUN_LOW_PROB=1`.
