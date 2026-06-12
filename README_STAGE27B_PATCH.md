# Stage27B DB-First Lineage Gate Discovery Patch

## Scope

- Research/shadow gate discovery only.
- No EA, paper, live, or order authorization.
- Stage18A, Stage23D, and Stage25D are not changed.
- Candles/regime features are DB-first through the validated Stage25C loader.
- Prior trade CSVs are research artifacts only.

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage27b_db_first_lineage_gate_discovery_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27b_db_first_lineage_gate_discovery
cat data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_first_lineage_gate_discovery.md
```
