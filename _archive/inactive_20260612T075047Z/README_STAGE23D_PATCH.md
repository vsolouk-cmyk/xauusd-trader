# Stage23D Patch

This patch adds a narrow forward-shadow tracker for the de-duplicated Stage23B/Stage23C candidate.

## Copy/unzip

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage23d_forward_shadow_candidate_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Safe git commands

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add Stage23D forward shadow candidate tracker"
git pull --rebase
git push
```
