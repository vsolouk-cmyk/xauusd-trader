# Stage164 Higher-Timeframe Macro-Regime Rebuild

Read-only rebuild stage after Stage161 and Stage163 rejected the active M5 shortlist under the current macro pressure.

## What it does

- Loads full AMarkets M5 or H1 data.
- Handles MT5 TSV exports with `<DATE>` and `<TIME>` columns.
- Resamples to H1, H4, and D1.
- Builds higher-timeframe return, trend, range-position, and ATR features.
- Reads Stage161 macro context.
- Restricts the shortlisted side to the macro-supported side:
  - `USD_REAL_YIELD_HEADWIND_FOR_GOLD` -> SHORT only.
  - macro tailwind -> LONG only.
  - unknown/neutral -> both sides, research-only.
- Writes research reports only.

## What it does not do

- It does not write MT5 KV files.
- It does not release demo orders.
- It does not modify Stage157 freeze.
- It does not authorize SELL execution.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage164_higher_tf_macro_regime_rebuild.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars-m5 /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --stage161-summary reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json \
  --timestamp-shift-hours -3 \
  --horizon-hours 24 \
  --min-events 80 \
  --min-mean-bps 3.0 \
  --min-hit-rate 0.525 \
  --min-recent-mean-bps 2.0 \
  --min-positive-folds 3
```

## Outputs

```text
reports/stage164_higher_tf_macro_regime_rebuild/stage164_higher_tf_macro_regime_rebuild_summary.json
reports/stage164_higher_tf_macro_regime_rebuild/stage164_higher_tf_macro_regime_candidate_scores.csv
reports/stage164_higher_tf_macro_regime_rebuild/stage164_higher_tf_macro_regime_shortlist.csv
reports/stage164_higher_tf_macro_regime_rebuild/stage164_higher_tf_macro_regime_current_active.csv
reports/stage164_higher_tf_macro_regime_rebuild/stage164_higher_tf_macro_regime_context.json
```

## Decision interpretation

- `NO_HIGHER_TF...KEEP_FREEZE`: no macro-aligned higher-timeframe candidate survived.
- `SHORTLIST_EXISTS_BUT_NOT_CURRENTLY_ACTIVE`: a research shortlist exists but no current signal.
- `CANDIDATES_REVIEW_ONLY_NO_DEMO_RELEASE`: shortlist exists and is currently active, but still requires manual review and a separate execution/governance stage.
