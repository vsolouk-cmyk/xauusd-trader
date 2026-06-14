# XAUUSD Collectors Workflow Hotfix — Optional Legacy Stage10B

This patch updates `.github/workflows/xauusd_collectors.yml` so the legacy `app.stage10b_event_pipeline_update` collector no longer hard-fails GitHub Actions when Stage10B has been archived or is absent from the checkout.

## What changed

- The Stage10B/GDELT step now checks whether `app/stage10b_event_pipeline_update.py` exists.
- If present, it runs the original command with the same arguments:
  - `--gdelt-timespan 7d`
  - `--gdelt-max-records 10`
  - `--gdelt-query-mode rate_safe`
  - `--gdelt-timeout 60`
  - `--gdelt-retries 2`
  - `--gdelt-query-delay 20`
- If missing, the workflow writes a small placeholder report and skips the legacy collector instead of failing.
- `if-no-files-found: ignore` was added to artifact upload steps to prevent missing optional outputs from failing the workflow.

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_collectors_optional_stage10b_patch.zip -d .
```

## Commit and push

```bash
cd ~/Desktop/xauusd-trader

git add -A
git commit -m "Make legacy Stage10B collector optional"
git pull --rebase origin main
git push
```

If `git pull --rebase` reports conflicts, resolve them before pushing.
