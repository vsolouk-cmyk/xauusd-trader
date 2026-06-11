# Stage25D patch

Copy with:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage25d_db_first_filtered_forward_shadow_patch.zip -d .
```

Run with:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25d_db_first_filtered_forward_shadow
cat data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.md
```

This is research/shadow only and does not alter Stage18A, Stage23D, EA, paper/live, or orders.
