# Stage 9D Macro-Aware Forward Shadow Report

Stage 9D combines the Stage 8D forward-shadow candidate with Stage 9C numeric macro regimes.

## Why report-only

Stage 9C showed that the candidate remained profitable across numeric regimes. The hostile sample was too small and profitable, so a macro block rule would be filter-mining at this point.

Therefore Stage 9D adds monitoring context only.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage9d_macro_aware_forward_shadow_report
cat data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.md
```

## Outputs

```text
data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.md
data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_signals_macro_annotated.csv
data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_outcomes_macro_annotated.csv
data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_outcomes_macro_summary.csv
data/reports/stage9d_macro_aware_forward_shadow_report/stage9d_macro_aware_forward_shadow_report.json
```

## Decision

No EA change, no macro guard, no demo/paper/live authorization.
