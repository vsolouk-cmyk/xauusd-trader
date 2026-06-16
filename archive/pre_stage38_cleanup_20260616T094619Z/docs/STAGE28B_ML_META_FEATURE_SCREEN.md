# Stage28B ML-lite Meta-Feature Screen

Stage28B is a research/shadow diagnostic stage. It does not change Stage18A, Stage23D, Stage25D, or Stage27D.

It screens available features in the canonical Stage23/25 lineage trade artifact and tests nonlinear single-feature and pairwise gates. It is designed as a lightweight meta-labeling bridge before any heavier ML model is introduced.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28b_ml_meta_feature_screen
cat data/reports/stage28b_ml_meta_feature_screen/stage28b_ml_meta_feature_screen.md
```

Optional:

```bash
STAGE28B_TRADE_ARTIFACT=data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv \
python3 -m app.stage28b_ml_meta_feature_screen
```

Guardrails:

- DB-first market sanity via Stage25C loader.
- No market CSV fallback.
- Prior trade CSV is only a research artifact.
- No EA/paper/live/order authorization.
