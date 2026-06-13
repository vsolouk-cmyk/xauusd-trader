# XAUUSD Collectors workflow hotfix — optional legacy collectors

This patch updates `.github/workflows/xauusd_collectors.yml` so archived legacy collectors do not break GitHub Actions.

Legacy collectors made optional:

- `app.stage10b_event_pipeline_update`
- `app.stage9b_macro_numeric_update`
- `app.stage9b_macro_event_calendar_update`

Behavior:

- If the module file exists, the workflow runs it normally.
- If the module file is missing/archived, the workflow writes a small skip report and continues.
- Artifact upload uses `if-no-files-found: ignore`.

This patch does not restore archived Python modules and does not change strategy, EA, paper/live, or order behavior.
