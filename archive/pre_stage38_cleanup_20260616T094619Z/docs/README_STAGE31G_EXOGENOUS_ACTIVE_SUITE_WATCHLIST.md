# Stage31G Exogenous Active-Suite Watchlist Patch

This patch adds status-only observation for the confirmed low-cadence Stage31D/31E exogenous candidate.

## Files

- `app/stage31g_exogenous_active_suite_watchlist.py`
- `app/run_active_shadow_suite_with_exogenous_watchlist.py`

## Guardrails

- Research/shadow status only.
- No EA change.
- No paper/live/order authorization.
- Does not create trade instructions.
- Does not fetch internet data.

## Run standalone watchlist status

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31g_exogenous_active_suite_watchlist
cat data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_exogenous_active_suite_watchlist.md
```

By default Stage31G runs Stage31F first with lookbacks `336,720,2160,4320`. To reuse the latest Stage31F output without rerunning it:

```bash
STAGE31G_RUN_STAGE31F=0 python3 -m app.stage31g_exogenous_active_suite_watchlist
```

## Run active suite plus exogenous watchlist wrapper

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite_with_exogenous_watchlist
cat data/reports/active_shadow_suite_exogenous_watchlist/active_shadow_suite_exogenous_watchlist.md
```

This wrapper calls the existing `app.run_active_shadow_suite` unchanged, then appends Stage31G status-only watchlist reporting.

## Commit

```bash
git add -A
git commit -m "Add exogenous watchlist status to active shadow suite"
git pull --rebase origin main
git push
```
