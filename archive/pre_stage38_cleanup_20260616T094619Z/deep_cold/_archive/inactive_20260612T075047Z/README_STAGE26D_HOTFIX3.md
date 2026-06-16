# Stage26D Hotfix 3 — Duplicate-Column-Safe Mirror Metrics

This hotfix fixes the runtime pandas error raised in `_group_metrics` after Hotfix 2:

```text
TypeError: arg must be a list, tuple, 1-d array, or Series
```

Cause: original PnL columns were renamed onto existing mirror column names, creating duplicate pandas labels. In that state `df.get()` may return a DataFrame instead of a Series.

Fixes:

- Adds `_numeric_series()` to always return a 1-D numeric Series, even if duplicate labels appear.
- Computes original metrics through an explicit `original_view` DataFrame instead of renaming onto existing mirror columns.
- Keeps Stage26D research/shadow-only.
- Keeps market data DB-first and keeps CSV market fallback disabled.
- Keeps Stage18A, Stage23D, and Stage25D unchanged.

Validation performed before packaging:

```text
python3 -m py_compile app/stage26d_artifact_mirror_diagnostic.py
full smoke run with synthetic DB + stage26a/b/c exact-trade artifacts
smoke manifest loaded all three artifacts and completed _group_metrics
```

Run:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage26d_hotfix3_duplicate_column_metrics_patch.zip -d .
python3 -m app.stage26d_artifact_mirror_diagnostic
cat data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.md
```
