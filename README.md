# Stage180 pandas datetime-resolution repair

This patch makes MT5 timestamp conversion independent of pandas' internal datetime unit.
It converts parsed timestamps explicitly to `datetime64[ms]` before extracting integer epoch values.

Files:
- `app/stage180_refresh_frozen_amarkets_alignment.py`
- `tests/test_stage180_frozen_alignment_refresh.py`
