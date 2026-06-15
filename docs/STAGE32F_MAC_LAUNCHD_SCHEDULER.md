# Stage32F Mac Launchd Scheduler

## Purpose

Run Stage32F unattended on macOS without wasting time on the heavy active wrapper.

The scheduler does this:

1. Runs `app.stage32f_amarkets_csv_preflight` first.
2. Runs the heavy `app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper` only if preflight returns `RUN_WRAPPER_RECOMMENDED`.
3. Skips `RUN_BUT_LOW_SAMPLE_PROBABILITY` by default.
4. Uses a lock directory to prevent overlapping runs.
5. Logs every run under `data/reports/stage32f_mac_scheduler/`.
6. Sends a macOS notification only when Stage32F errors or a pre-commercial robustness queue appears.

## Files

- `tools/stage32f_scheduler_runner.zsh`
- `launchd/com.xauusd.stage32f.scheduler.plist`

## Install manually

From the repository root:

```bash
mkdir -p data/reports/stage32f_mac_scheduler
cp ~/Downloads/stage32f_mac_scheduler_patch/tools/stage32f_scheduler_runner.zsh tools/
chmod +x tools/stage32f_scheduler_runner.zsh
mkdir -p ~/Library/LaunchAgents
cp ~/Downloads/stage32f_mac_scheduler_patch/launchd/com.xauusd.stage32f.scheduler.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist
launchctl start com.xauusd.stage32f.scheduler
```

## Check status

```bash
launchctl list | grep xauusd
cat data/reports/stage32f_mac_scheduler/latest_scheduler_state.env
ls -lt data/reports/stage32f_mac_scheduler | head
```

## Stop scheduler

```bash
launchctl unload ~/Library/LaunchAgents/com.xauusd.stage32f.scheduler.plist
```

## Low probability mode

By default, the scheduler skips `RUN_BUT_LOW_SAMPLE_PROBABILITY`. This avoids burning 10–15 minutes when H1 has advanced but tracked signal hours were not crossed.

To override, edit the plist and set:

```xml
<key>XAUUSD_RUN_LOW_PROB</key>
<string>1</string>
```

Then reload the agent.

## Important

The scheduler cannot export AMarkets CSVs from MT5 by itself. It only reacts to CSV files that already exist in the configured folder. If AMarkets export is still manual, your only manual task is placing/exporting new CSV files. The scheduler then handles preflight and Stage32F automatically.
