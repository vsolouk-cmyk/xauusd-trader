# XAUUSD Stage116C FRED Core Release-History Runbook

Install the package into the existing repository, run the combined tests, then
run the existing Stage113–116 pipeline with:

```bash
python3 scripts/run_xauusd_fundamental_unify_normalize_pipeline.py \
  --download-first \
  --event-core-only \
  --build-historical-event-context \
  --run-replay
```

Expected downloader progress includes one line for each locked release ID.
The new core file is downloaded even if an older global FRED calendar exists.

Do not use `--force-refresh` unless explicitly troubleshooting unrelated
sources. The new core file has its own validity contract and incomplete caches
are invalidated automatically.
