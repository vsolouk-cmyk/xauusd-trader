# QA Report

## Exact production failure signature

Confirmed from the supplied failure artifact:

- BLS events: 4
- BEA events: 4
- FED events: 155
- Missing category: `BLS_ECI`

## Root-cause regression

- Current-year-only core cache is rejected: PASS
- All seven official release IDs are requested: PASS
- Per-release endpoint output is merged canonically: PASS
- Employment Cost Index is restored: PASS
- Personal Income and Outlays is restored: PASS
- Stage114B -> Stage115 all-category bridge: PASS
- Required historical years are represented: PASS
- Realistic BLS/BEA frequencies pass the unchanged coverage floors: PASS
- Streaming child output retained: PASS

## Combined QA

- Python compilation: PASS
- Combined unit/integration tests: 70 passed, 1 conditional artifact test skipped
- Clean patch extraction: PASS
- Manifest verification: PASS
- No broker/demo/live execution path added: PASS

The skipped test requires the user's canonical commercial artifacts and is
unrelated to the FRED downloader repair.
