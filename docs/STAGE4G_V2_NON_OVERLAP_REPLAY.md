# Stage 4G v2 — AMarkets non-overlap replay

Purpose: rerun AMarkets broker-feed backfill with an execution-realistic one-position-at-a-time replay.

Why this patch exists:

- Stage 4G v1 reported every qualifying H1 signal as a replayed trade.
- That is useful as a diagnostic signal-frequency view, but it can overstate trade count and does not match an executable one-position strategy when the trade has a 12 H1-bar horizon.
- v2 reports both:
  - `overlap_every_signal`: diagnostic only.
  - `non_overlap`: decision basis. It skips new entries while a prior dry-run trade is unresolved.

Default input files:

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
```

Default output folder:

```text
data/reports/stage4g_v2/
```

Run default offset UTC+2:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage4g_amarkets_backfill_validation
cat data/reports/stage4g_v2/stage4g_v2_amarkets_backfill_validation.md
```

Run offset UTC+3 sensitivity:

```bash
python3 -m app.stage4g_amarkets_backfill_validation --server-utc-offset-hours 3 --out-dir data/reports/stage4g_v2_offset3
cat data/reports/stage4g_v2_offset3/stage4g_v2_amarkets_backfill_validation.md
```

Hard rule: this is backfill validation only. It does not authorize demo, paper, or live orders.
