# Stage32F Mac Scheduler HF1 — explicit wrapper execution state

## Purpose

This hotfix updates `tools/stage32f_scheduler_runner.zsh` so that
`data/reports/stage32f_mac_scheduler/latest_scheduler_state.env` explicitly reports whether the heavy wrapper was executed.

## Why

The first scheduler state file only recorded the preflight decision. For decisions like:

```text
DECISION=RUN_BUT_LOW_SAMPLE_PROBABILITY
WRAPPER_RECOMMENDED=True
```

the state file was ambiguous. In default mode, the scheduler should skip this low-probability case unless `XAUUSD_RUN_LOW_PROB=1` is set.

## New state fields

```text
FINAL_DECISION=SKIP_WRAPPER | RUN_STAGE32F_WRAPPER_STARTED | WRAPPER_COMPLETED | WRAPPER_FAILED
WRAPPER_EXECUTED=True | False
WRAPPER_RC=NA | RUNNING | <return code>
RUN_LOW_PROB=0 | 1
REASON=<why the wrapper was skipped or executed>
```

## Install

```bash
cd ~/Desktop/xauusd-trader
cp ~/Downloads/stage32f_mac_scheduler_hf1_patch/stage32f_mac_scheduler_hf1_patch/tools/stage32f_scheduler_runner.zsh tools/
chmod +x tools/stage32f_scheduler_runner.zsh
cp ~/Downloads/stage32f_mac_scheduler_hf1_patch/stage32f_mac_scheduler_hf1_patch/docs/STAGE32F_MAC_LAUNCHD_SCHEDULER_HF1.md docs/
```

Then restart the LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist
launchctl start com.xauusd.stage32f.scheduler
```

## Expected behavior

For low-probability preflight:

```text
DECISION=RUN_BUT_LOW_SAMPLE_PROBABILITY
FINAL_DECISION=SKIP_WRAPPER
WRAPPER_EXECUTED=False
REASON=low_probability_skipped_by_default
```

For strict runnable preflight:

```text
DECISION=RUN_WRAPPER_RECOMMENDED
FINAL_DECISION=WRAPPER_COMPLETED
WRAPPER_EXECUTED=True
WRAPPER_RC=0
```

## Optional override

To force wrapper execution even when low probability:

```bash
export XAUUSD_RUN_LOW_PROB=1
```

Do not use this as the default; it is only for manual diagnostic runs.
