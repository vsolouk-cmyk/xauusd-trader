# Stage32F Mac Scheduler HF3 — Legacy Lock + PID-Aware State

## Purpose

HF3 replaces the Stage32F scheduler runner with a stricter PID-aware lock mechanism.

It fixes the case where `latest_scheduler_state.env` keeps showing:

```text
DECISION=SKIP_ALREADY_RUNNING
REASON=another_scheduler_instance_is_running
```

without reporting which process is supposedly active.

## What changed

- Uses a lock directory: `data/reports/stage32f_mac_scheduler/stage32f_scheduler.lock.d`
- Stores runner PID in `pid` and timestamp in `ts_utc`
- Detects stale lock directories and removes them automatically
- Detects old legacy `*.lock` files from previous runners
- If a legacy lock has no PID, scans for actual Stage32F / active-wrapper processes
- Writes explicit state fields:
  - `RUNNING_PID`
  - `LOCK_KIND`
  - `LOCK_PATH`
  - PID-aware `REASON`

## Expected state examples

Real active process:

```text
FINAL_DECISION=SKIP_ALREADY_RUNNING
REASON=another_scheduler_instance_is_running_pid_12345
RUNNING_PID=12345
LOCK_KIND=pid_lock_dir
```

Old legacy lock but no actual process:

```text
FINAL_DECISION=SKIP_WRAPPER
REASON=preflight_decision_...
LOCK_KIND=pid_lock_dir
```

Wrapper execution:

```text
FINAL_DECISION=WRAPPER_COMPLETED
WRAPPER_EXECUTED=True
WRAPPER_RC=0
```

## Manual installation

```bash
cd ~/Downloads
unzip xauusd_stage32f_mac_scheduler_hf3_patch.zip -d stage32f_mac_scheduler_hf3_patch

cd ~/Desktop/xauusd-trader
cp ~/Downloads/stage32f_mac_scheduler_hf3_patch/stage32f_mac_scheduler_hf3_patch/tools/stage32f_scheduler_runner.zsh tools/
chmod +x tools/stage32f_scheduler_runner.zsh
cp ~/Downloads/stage32f_mac_scheduler_hf3_patch/stage32f_mac_scheduler_hf3_patch/docs/STAGE32F_MAC_LAUNCHD_SCHEDULER_HF3.md docs/
```

Restart LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist
launchctl start com.xauusd.stage32f.scheduler
```

Check state:

```bash
cat ~/Desktop/xauusd-trader/data/reports/stage32f_mac_scheduler/latest_scheduler_state.env
```

## No workflow changes

This patch is local-Mac only. It does not change GitHub Actions.
