# Stage64C Macro-Regime Gold Thesis Specification

Stage64C defines the active program after Stage64A/B freeze and corrected audit.

It is a report-only, no-promotion stage. It formalizes the Daily/Weekly Macro-Regime Gold Thesis and writes:

- thesis specification
- regime definitions
- data/feature contract
- lag policy
- validation framework
- next-stage contract for data/loader audit

This stage does not mutate databases, does not place orders, and does not authorize paper-order, paper-live, live, or EA promotion.

## Required command

```bash
python3 app/stage64c_macro_regime_gold_thesis_spec.py \
  --root . \
  --config configs/stage64c_macro_regime_gold_thesis_spec.json \
  --out reports/stage64c_macro_regime_gold_thesis_spec
```

## Expected outputs

- `stage64c_macro_regime_gold_thesis_spec_summary.json`
- `stage64c_macro_regime_gold_thesis_spec_report.md`
- `stage64c_macro_regime_feature_contract.csv/json`
- `stage64c_macro_regime_definitions.csv/json`
- `stage64c_macro_regime_validation_framework.json`

## Governance

Central-bank demand is a regime prior, not a timing signal. All slow macro features must respect publication lag. No historical validation is valid until source availability and lag policy are audited.
