# Stage28B Hotfix2 — Strict Forward-Safe Meta Feature Screen

This hotfix replaces the raw Stage28B feature screen with a strict forward-safe whitelist.

Why:

- The first Stage28B run found very strong gates based on `day_range`.
- Full-day range/high/low/close are not knowable at the canonical entry time.
- `exit`, `tp`, and `sl` columns are outcome/order-derived and must not be used as model features.

Strict mode keeps only features intended to be knowable at or before entry:

- `prior_day_range`
- `asia_range`, `asia_eff`
- `london_range`, `london_eff`
- `prior_day_aligned`
- `direction`, `dir_mult` as diagnostics
- `entry_hour`, `dow`, `month`, `year`

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28b_ml_meta_feature_screen
cat data/reports/stage28b_ml_meta_feature_screen/stage28b_ml_meta_feature_screen.md
```

No EA/paper/live/order authorization is added.
