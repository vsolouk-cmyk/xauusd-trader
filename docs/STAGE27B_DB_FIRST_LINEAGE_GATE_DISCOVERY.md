# Stage27B — DB-First Lineage Gate Discovery

Stage27B evaluates forward-safe no-trade/regime gates around the stronger Stage23/25 lineage. It does not add a new entry rule and does not modify Stage18A, Stage23D, or Stage25D.

Market candle/regime features are loaded DB-first from SQLite via the validated Stage25C loader. Previous trade CSVs are used only as research artifacts, not as market-data fallback.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27b_db_first_lineage_gate_discovery
cat data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_first_lineage_gate_discovery.md
```
