# Stage31A Hotfix4 — Markdown report without mandatory tabulate

## Problem

GitHub Actions failed inside `app.stage31a_exogenous_feature_ingestion` while writing the markdown report:

```text
ImportError: `Import tabulate` failed. Use pip or conda to install the tabulate package.
```

`pandas.DataFrame.to_markdown()` requires the optional `tabulate` package. The workflow runner did not have it available.

## Fix

- `app/stage31a_exogenous_feature_ingestion.py`
  - Adds `_df_to_markdown_safe(...)`.
  - Uses a built-in fallback markdown table renderer if `to_markdown()` fails.
  - Replaces deprecated `pd.Timestamp.utcnow()` with `pd.Timestamp.now(tz="UTC")`.

- `.github/workflows/xauusd_fred_exogenous.yml`
  - Installs `tabulate` after requirements as an additional safety layer.
  - Still keeps Stage31A robust even if `tabulate` is not installed.

## Validation

- `python3 -m py_compile app/stage31a_exogenous_feature_ingestion.py`
- YAML parse check for `.github/workflows/xauusd_fred_exogenous.yml`

## Notes

This patch does not change strategy logic, trading behavior, EA behavior, or any paper/live/order authorization. It only prevents report-generation failure in the GitHub FRED exogenous workflow.
