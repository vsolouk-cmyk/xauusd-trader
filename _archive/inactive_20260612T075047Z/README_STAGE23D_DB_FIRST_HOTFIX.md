# Stage23D DB-first hotfix

Copy this patch into `~/Desktop/xauusd-trader`.

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage23d_db_first_hotfix_patch.zip -d .
```

Then run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

Expected report signs:

- `db_first = True`
- `csv_fallback_enabled = False`
- M1/H1 rows should align with Stage25D DB-first counts after the latest import.

Research/shadow only. No EA, paper, live, or order authorization.
