# Stage174B Package Manifest

- `app/stage174_h64l_contract_resolution_and_track_a_final_audit.py`
  - MT5 `<DATE>/<TIME>/<OHLC>` schema support
  - normalized schema support retained
  - explicit OHLC and schema diagnostics
  - corrected integration-defect program state
- `tests/test_stage174_h64l_contract_resolution_and_track_a_final_audit.py`
  - original Stage174 tests
  - actual MT5 split-schema regression test
  - normalized timestamp regression test
  - diagnostic error test
- `docs/STAGE174B_MT5_SCHEMA_BUGFIX.md`
  - execution and governance documentation
