# XAUUSD Controlled-Paper QA Report

## Build environment

- Build interpreter: Python 3.13.5
- Python 3.14 interpreter in build container: unavailable
- GitHub Actions workflow includes an explicit Python 3.14 matrix job

## Checks completed before delivery

- Clean source compilation: PASS
- Seven unit/regression tests: PASS
- Exact H1 row-position entry/exit (`i+1`, `i+24`): PASS
- Bounded missing-coverage classification (`168 / 146 / 22`): PASS on synthetic contract fixture
- SQLite schema/cadence introspection: PASS
- M5 observed-spread guard: PASS
- Required event context absent → fail closed: PASS
- Missing project dependencies → fail closed: PASS
- Idempotent frozen Stage180 observation ingestion: PASS
- Dynamic import with `sys.modules` registration before `exec_module`: PASS
- Static broker-execution dependency scan: PASS
- Clean ZIP extraction, compilation, and tests: performed after ZIP creation

## Python 3.14 boundary

The exact dynamic-import regression is included in `tests/test_xauusd_controlled_paper.py`. The build container does not provide a Python 3.14 executable, so local execution used Python 3.13.5. The included manual GitHub Actions workflow executes the same suite on both Python 3.13 and Python 3.14.
