# Stage176 404/date-filter patch manifest

Files:

- `app/stage176_central_bank_allocation_falsification.py`
  - no retry/backoff for HTTP 400/404/410
  - filters discovered WGC reports before 2010Q1
  - chronological report ordering
- `tests/test_stage176_central_bank_allocation_falsification.py`
  - regression test for single-attempt 404 handling
  - regression test for excluding pre-2010 reports
- `configs/stage176_central_bank_allocation_falsification.json`
  - retained unchanged for deployable package completeness
- `docs/STAGE176_WGC_404_AND_DATE_FILTER_BUGFIX.md`
  - execution notes

Research contract changes: none.
Order/demo/live/ML changes: none.
