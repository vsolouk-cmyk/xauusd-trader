# Stage27D — DB-First H1 ATR Filtered Forward-Shadow Tracker

Research/shadow-only tracker for the Stage27C validated `h1_atr_drop_low30_strict_completed` gate around the canonical Stage23/25 lineage.

It does not modify Stage18A, Stage23D, Stage25D, EA, paper/live mode, or orders.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27d_db_first_h1_atr_filtered_forward_shadow
cat data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md
```

The gate uses only completed H1 candles with `h1_bar_end <= signal_time`.
