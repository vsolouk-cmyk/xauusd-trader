# Stage36A + Stage35C Scheduler HF4

Purpose: start a distinct thesis branch immediately while keeping the current h13/h14 forward confirmation trigger active in the existing Mac scheduler.

This patch is research-only. It does not authorize EA changes, paper-live, or orders.

## Files

- `app/stage36a_new_thesis_parallel_intake.py`
- `tools/stage32f_scheduler_runner.zsh`
- `docs/STAGE36A_AND_STAGE35C_SCHEDULER_HF4.md`

## What changes

1. The existing Stage32F Mac scheduler continues to run the AMarkets CSV preflight and wrapper logic.
2. On every scheduler cycle, the runner now also executes Stage35C if installed.
3. Stage36A runs once per UTC day, or immediately if its report is missing.
4. Stage35C state and Stage36A state are written to:

- `data/reports/stage35c_stage36a_scheduler/latest_pipeline_state.env`

## Why this is needed

Stage35C says the current h13/h14 branch is waiting for more forward events. Waiting several days without starting a non-overlapping thesis branch is not aligned with the commercial fast path.

Stage36A starts distinct thesis branches now:

- session/regime baseline scout
- news/no-news guard
- volatility compression breakout
- structure sweep/reclaim
- broker cost-window guard

These are not continuation of the same h13/h14 variant mining path.

## Manual commands after installation

Restart LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist
launchctl start com.xauusd.stage32f.scheduler
```

Check state:

```bash
cat ~/Desktop/xauusd-trader/data/reports/stage35c_stage36a_scheduler/latest_pipeline_state.env
```

Run Stage36A manually once if desired:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage36a_new_thesis_parallel_intake
```

## Expected next stage

If Stage36A returns:

`STAGE36A_START_NEW_THESIS_BRANCHES_WHILE_STAGE35C_WAITS_RESEARCH_ONLY`

then the immediate next development patch should be:

`Stage36B Session/Regime Baseline Scout`
