# XAUUSD Stage 3C Overlap-Aligned Feed Diagnostics

- Generated at UTC: `2026-06-04T11:47:17.138107+00:00`
- Decision: `overlap_second_source_pass`
- Reason: `Fixed candidate passed overlap-aligned second-source checks.`

## Data windows

- Primary full: `{'rows': 25745, 'start_utc': '2022-05-27T13:00:00+00:00', 'end_utc': '2026-06-04T07:00:00+00:00'}`
- Secondary full: `{'rows': 21071, 'start_utc': '2022-05-02T01:00:00+00:00', 'end_utc': '2025-11-20T13:00:00+00:00'}`
- Common overlap: `{'start_utc': '2022-05-27T13:00:00+00:00', 'end_utc': '2025-11-20T13:00:00+00:00', 'overlap_days': 1273.0}`

## Exact timestamp comparison

| Source | Trades | Total net | PF | Cost x4 | Fold+ ratio | Month+ ratio |
|---|---:|---:|---:|---:|---:|---:|
| primary | 665 | 667.3575 | 1.141 | -30.8925 | 1.000 | 0.619 |
| secondary | 657 | 731.8500 | 1.153 | 42.0000 | 0.800 | 0.571 |

## Secondary time-shift diagnostics

| Shift hours | Status | Secondary total | Ratio vs primary | Secondary PF |
|---:|---|---:|---:|---:|
| -3 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| -2 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| -1 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| 0 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| 1 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| 2 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |
| 3 | overlap_second_source_pass | 731.8500 | 1.097 | 1.153 |

