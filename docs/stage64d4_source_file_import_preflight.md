# Stage64D4 Source File Import Preflight

Stage64D4 checks raw macro-regime source files before normalization/import. It does not run validation and does not authorize any trading path.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage64d4_source_file_import_preflight.py \
  --root . \
  --config configs/stage64d4_source_file_import_preflight.json \
  --out reports/stage64d4_source_file_import_preflight
```

## Outputs

```text
reports/stage64d4_source_file_import_preflight/stage64d4_source_file_import_preflight_summary.json
reports/stage64d4_source_file_import_preflight/stage64d4_source_file_import_preflight_report.md
reports/stage64d4_source_file_import_preflight/stage64d4_source_file_import_preflight_checks.csv
```

## Decision semantics

- `BLOCK_STAGE64D_RERUN_UNTIL_P0_RAW_FILES_PASS_PREFLIGHT_NO_ORDER`: P0 files are still missing or malformed.
- `P0_READY_FOR_STAGE64D_RERUN_NO_VALIDATION`: P0 files pass raw preflight; rerun Stage64D, but validation remains blocked until Stage64D explicitly unlocks scope.
- `ALL_RAW_FILES_PASS_PREFLIGHT_RERUN_STAGE64D_NO_VALIDATION_YET`: all raw files pass preflight; rerun Stage64D.
