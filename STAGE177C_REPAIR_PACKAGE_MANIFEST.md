# Stage177C Python 3.14 Correlation Repair

- Replaces pandas-aligned lag return calculation with positional NumPy logic.
- Replaces Series.corr with a shared finite-mask Pearson correlation.
- Adds a regression test for non-identical Series indexes.
- Keeps all DST selection, train/holdout, and fail-closed thresholds unchanged.
