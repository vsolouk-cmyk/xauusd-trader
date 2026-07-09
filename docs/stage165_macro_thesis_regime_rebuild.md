# Stage165 Macro Thesis Regime Rebuild

Stage165 is a read-only thesis rebuild after the M5 active-router path and the higher-timeframe technical scan failed under the current macro regime.

It does not write MT5 KV files, does not authorize demo orders, and does not change Stage157 freeze.

## Purpose

Stage161 identified the current macro regime as `USD_REAL_YIELD_HEADWIND_FOR_GOLD` and classified the Stage159 long technical shortlist as macro-conflicted. Stage163B then found no M5 short-side candidate under the same macro pressure. Stage164B found no robust H1/H4/D1 macro-supported technical shortlist either.

Stage165 changes the question from “which technical pattern should we route now?” to “which macro-regime thesis has historically paid, at daily horizons, and is the current regime one of them?”

## Inputs

- AMarkets M5 CSV from the fundamental/event inbox.
- Stage161 macro-aware classifier summary.
- Stage115 daily macro feature panel.

Default paths:

```bash
/Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv
/Users/vahid/Desktop/xauusd-trader/reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json
/Users/vahid/Desktop/xauusd-trader/data/fundamental_event_inbox/features/stage115_daily_macro_feature_panel.csv
```

## What it scans

Stage165 aggregates M5 bars to D1 and joins them with daily macro features using as-of joins. It creates coarse, lag-safe macro regimes:

- `USD_REAL_YIELD_HEADWIND_FOR_GOLD`
- `USD_REAL_YIELD_TAILWIND_FOR_GOLD`
- `USD_UP_REAL_YIELD_DOWN_MIXED`
- `USD_DOWN_REAL_YIELD_UP_MIXED`
- `SAFE_HAVEN_MIXED_DOLLAR_HEADWIND`
- `MACRO_NEUTRAL_OR_INCOMPLETE`

For each regime, side, and horizon it evaluates forward bps outcomes:

- side: LONG / SHORT
- horizons: 1d, 3d, 5d by default
- chronological four-fold stability
- recent-fold performance

## Outputs

```bash
reports/stage165_macro_thesis_regime_rebuild/stage165_macro_thesis_regime_rebuild_summary.json
reports/stage165_macro_thesis_regime_rebuild/stage165_macro_thesis_candidate_scores.csv
reports/stage165_macro_thesis_regime_rebuild/stage165_macro_thesis_shortlist.csv
reports/stage165_macro_thesis_regime_rebuild/stage165_macro_thesis_regime_context.json
```

## Execution

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage165_macro_thesis_regime_rebuild.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars-m5 /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --stage161-summary reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json \
  --timestamp-shift-hours -3 \
  --horizons-days 1,3,5 \
  --min-events 40 \
  --min-mean-bps 8.0 \
  --min-hit-rate 0.53 \
  --min-recent-mean-bps 3.0 \
  --min-positive-folds 3
```

## Decision rules

- `STAGE165_CURRENT_MACRO_THESIS_CANDIDATE_REVIEW_REQUIRED_NO_DEMO_RELEASE`: a current-regime thesis exists, but manual review is required before any execution patch.
- `STAGE165_HISTORICAL_MACRO_THESIS_EXISTS_BUT_NOT_CURRENT_REGIME_KEEP_FREEZE`: a thesis exists historically, but not for the current regime.
- `STAGE165_NO_ROBUST_MACRO_THESIS_CANDIDATE_KEEP_FREEZE`: no robust daily macro thesis survives.

In all cases, Stage165 keeps order routing disabled.
