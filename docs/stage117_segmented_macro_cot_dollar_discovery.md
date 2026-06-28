# Stage117 Segmented Macro/COT/Dollar Discovery

Stage117 starts the next discovery arm after Stage115 and Stage116.

It uses:

- AMarkets H1 XAUUSD bars from the local SQLite `bars` table or H1 CSV fallback.
- `stage115_daily_macro_feature_panel.csv`
- `stage115_cot_gold_weekly_features.csv`
- `stage116_validated_dollar_pressure.csv`
- `stage116_validated_spdr_gld_long.csv` as candidate-only context.

It deliberately excludes WGC ETF and central-bank rows from hard features when Stage116 reports zero validated rows. It also does not require direct DXY; the Stage116 validated dollar-pressure fallback is accepted.

## What it does

- Builds a joined H1 research dataset.
- Computes H120 forward return.
- Splits history into selection / validation / tail-forward-proxy segments.
- Builds selection-only thresholds.
- Tests a small set of thesis-first macro/COT/dollar rules.
- Emits a review queue only. No promotion.

## What it does not do

- No MT5.
- No EA.
- No broker.
- No paper-order.
- No live-order.
- No observer update.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage117_segmented_macro_cot_dollar_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --inbox ~/Downloads/xauusd_fundamental_event_inbox
```

## Outputs

```text
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_segmented_macro_cot_dollar_discovery_summary.json
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_candidate_metrics.csv
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_selected_for_stage118.csv
reports/stage117_segmented_macro_cot_dollar_discovery/stage117_feature_coverage.csv
data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv
```

If `review_gate_pass_count > 0`, Stage118 should hard-audit overlap, robustness, and lag-safety before any observer update.


## Stage117B pandas numeric coercion hotfix

This patch replaces `pd.to_numeric(..., errors="ignore")` with `errors="coerce"` inside Stage117 numeric preparation. Newer pandas/Python environments reject `errors="ignore"`; coercing non-numeric residues to NaN is safer for quantile thresholds and segmented discovery metrics.
