# Stage76C K06 MT5 Observer Clean EA Compile Fix

This package replaces the Stage76 observer EA with a clean observer-only source that avoids banned execution-function tokens even in comments or strings.

## Purpose

- Keep the EA stable and installed once.
- Daily operation updates only `k06_observer_signal.csv`.
- No broker execution logic is present.
- `InpAllowTrading=true` intentionally blocks initialization.

## Files

- `mt5/K06_ObserverOnly_EA.mq5`
- `tests/test_stage76c_k06_mt5_observer_clean_ea.py`

## Local test

```bash
PYTHONPATH=. python3 tests/test_stage76c_k06_mt5_observer_clean_ea.py
```
