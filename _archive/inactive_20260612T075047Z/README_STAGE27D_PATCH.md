# Stage27D Patch

## Purpose

Adds `app.stage27d_db_first_h1_atr_filtered_forward_shadow`, a DB-first research-shadow tracker for the Stage27C validated H1 ATR gate.

## Scope

- Research/shadow only.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- Stage25D remains unchanged.
- No EA change.
- No paper/live/order authorization.
- AMarkets CSV market fallback is disabled.

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage27d_db_first_h1_atr_filtered_forward_shadow_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27d_db_first_h1_atr_filtered_forward_shadow
cat data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md
```

## Git

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add Stage27D H1 ATR filtered forward shadow tracker"
git pull --rebase
git push
```
