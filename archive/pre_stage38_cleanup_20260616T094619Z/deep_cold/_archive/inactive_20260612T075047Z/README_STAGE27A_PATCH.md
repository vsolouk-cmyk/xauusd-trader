# Stage27A Patch

Copy into the repo and run:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage27a_db_first_outcome_surface_discovery_patch.zip -d .
python3 -m app.stage27a_db_first_outcome_surface_discovery
cat data/reports/stage27a_db_first_outcome_surface_discovery/stage27a_db_first_outcome_surface_discovery.md
```

Optional constrained run:

```bash
STAGE27A_MAX_RUNTIME_SECONDS=120 STAGE27A_MAX_EXACT=12 STAGE27A_MAX_EXACT_PER_FAMILY=3 python3 -m app.stage27a_db_first_outcome_surface_discovery
```
