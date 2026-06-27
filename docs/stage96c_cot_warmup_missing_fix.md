# Stage96C COT warm-up missing-row fix

Stage96B successfully fixed the COT/macros join, but real COT data starts later than the macro dataset and COT z-score features require a warm-up window.

Stage96C changes only the missing-row accounting:

- Missing required feature values before the first row where all rule-required columns are simultaneously available are counted as `warmup_missing_rows_ignored`.
- Missing required values after that first complete row remain `missing_required_feature_rows` and can still fail the candidate.
- Thesis rules, thresholds, splits, scoring, hard blocks, MT5/EA state, and order state are unchanged.

This prevents valid COT candidates from being rejected only because the macro dataset begins in 2011 while normalized COT coverage begins in 2012 and z-score windows need observations.
