# Stage26D Hotfix 2 — Artifact Normalizer

This patch replaces `app/stage26d_artifact_mirror_diagnostic.py`.

## Purpose

The previous Stage26D run loaded only Stage26C because Stage26A and Stage26B exact-trade CSVs did not contain a literal `timestamp` column. This hotfix no longer requires `timestamp` for artifact-level mirror diagnostics.

## Guardrails

- Research/shadow diagnostic only.
- No EA changes.
- No paper/live/order authorization.
- Market candles remain DB-first from SQLite.
- AMarkets CSV market fallback remains disabled.
- Previous exact-trade CSV files are research artifacts only.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage26d_artifact_mirror_diagnostic
cat data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.md
```

## Git

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Fix Stage26D artifact mirror normalization"
git pull --rebase
git push
```
