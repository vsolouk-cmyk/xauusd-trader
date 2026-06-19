# Stage47B3 next step

Run the TwelveData M5 history backfill from the repository root.

```bash
python3 app/stage47b3_twelvedata_m5_history_backfill.py \
  --days 90 \
  --chunk-days 7 \
  --sleep-sec 8 \
  --min-rows 5000 \
  --min-days 20 \
  --out reports/stage47b3
```

Then send:

```text
reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_summary.json
reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_report.md
```

If the generated status is `DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION`, rerun Stage47B on the generated normalized CSV.
