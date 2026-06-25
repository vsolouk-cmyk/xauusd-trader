# Stage64J3 WGC Workbook Inspector

This stage inspects locally downloaded WGC workbook files under:

- `data/macro_regime/raw/_vendor/wgc_etf`
- `data/macro_regime/raw/_vendor/wgc_central_bank`

It captures sheet names, dimensions, preview rows, and candidate header rows. It does not transform data into raw model files and does not run validation.

Outputs:

- `reports/stage64j3_wgc_workbook_inspector/stage64j3_wgc_workbook_inspector_summary.json`
- `reports/stage64j3_wgc_workbook_inspector/stage64j3_wgc_workbook_inspector_report.md`
- `reports/stage64j3_wgc_workbook_inspector/stage64j3_workbook_inventory.json`
- `reports/stage64j3_wgc_workbook_inspector/stage64j3_workbook_sheet_inventory.csv`

Hard blocks remain:

- no paper-order
- no EA promotion
- no paper-live/live
- no broker connection
- no validation scan
- no reduced-scope retest
- no rescue filtering
- no new intraday scan
