# Stage26B Hotfix 1 — DB Loader Alignment

This hotfix keeps Stage26B DB-first and disables CSV fallback. It aligns Stage26B with the already-working Stage25C schema-introspection loader, instead of using the faulty local M1/H1 loader.

## Apply

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage26b_hotfix1_db_loader_alignment_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage26b_db_first_family_coverage_discovery
cat data/reports/stage26b_db_first_family_coverage_discovery/stage26b_db_first_family_coverage_discovery.md
```

## Guardrails

- Research/shadow discovery only.
- No EA change.
- No paper/live/order authorization.
- CSV fallback remains disabled.
