# Stage176 Vintage Recovery Repair Manifest

Files:

- `app/stage176_central_bank_allocation_falsification.py`
- `configs/stage176_central_bank_allocation_falsification.json`
- `tests/test_stage176_central_bank_allocation_falsification.py`
- `docs/STAGE176_WGC_VINTAGE_RECOVERY_REPAIR.md`

Research contract changes: none.

Operational changes:

- visible publication-date extraction;
- quarter-aware page parsing;
- dedicated Central Banks section recovery;
- XLS/XLSX/PDF/ZIP attachment recovery;
- curl fallback for WGC downloads;
- failed-manifest automatic rebuild;
- regional duplicate exclusion.

Validation:

- Python compile: PASS
- Unit tests: 25/25 PASS
- Existing cache reuse: covered
- Visible date fallback: covered
- YTD-vs-quarter semantic regression: covered
- Section-page priority: covered
- Exact-quarter XLSX mapping: covered
- PDF layout-column mapping: covered
- Existing invalid manifest rebuild: covered
- Revised-series substitution: still rejected
- Order/demo/paper/live code path: absent
