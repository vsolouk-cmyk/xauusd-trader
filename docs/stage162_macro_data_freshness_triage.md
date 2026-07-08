# Stage162 macro data freshness triage

Purpose: verify content freshness of the macro/fundamental feature pipeline before using Stage161 macro-aware candidate labels.

This stage is read-only. It does not write MT5 files, does not generate signals, and does not alter demo routing. Stage157 freeze remains active.

Run:

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage162_macro_data_freshness_triage.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox
```

Outputs:

- `reports/stage162_macro_data_freshness_triage/stage162_macro_data_freshness_triage_summary.json`
- `reports/stage162_macro_data_freshness_triage/stage162_macro_file_freshness.csv`
- `reports/stage162_macro_data_freshness_triage/stage162_macro_stale_root_cause_candidates.csv`

Decision use:

- If `STAGE162_MACRO_CONTENT_FRESH_READY_FOR_STAGE161_RECLASSIFICATION`, rerun Stage161 and review labels.
- If `STAGE162_MACRO_CONTENT_STALE_OR_INCOMPLETE_REPAIR_REQUIRED`, inspect stale root-cause rows before rerunning Stage161.
