# QA Report — Controlled-Paper Contract/Test-Isolation Repair

## Defects reproduced

### 1. Unit-test environment leak

The missing-raw-CSV regression fixture retained production fallback candidates such as `~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv`. On the user's Mac, that real file exists, so the test did not exercise the intended missing-file branch and instead compared a current 2026 CSV against the fixture's 2015 SQLite data.

### 2. Brittle Stage177C contract gate

The production Stage177C artifact contains the correct EU DST contract, shifts, timestamp semantics, PASS decision, and no-holdout selection. The bridge nevertheless used a brittle raw decision comparison and emitted insufficient diagnostics.

## Repair

- Unit fixtures now override `spread_source.csv_candidates` with one temporary fixture-only path.
- No unit test can fall through to the user's home or Downloads directories.
- Stage177C validation now checks substantive fields:
  - `contract = EU_DST_GMT_OFFSET_PAIR`
  - `dst_calendar = EU`
  - `standard_shift_minutes = -120`
  - `dst_shift_minutes = -180`
  - `shift_semantics = timestamp_utc = timestamp_naive + shift_minutes`
  - `selection_used_holdout = false`
  - canonical PASS decision or exact Stage177C identity
- Harmless casing and surrounding whitespace are normalized.
- Diagnostics now include decision, stage, shift semantics, no-holdout state, individual checks, and evidence route.
- Actual semantic mismatch remains fail-closed.

## Checks executed

```text
Python source compilation                              PASS
Missing-file fixture isolation                         PASS
No fallback to real ~/Downloads during unit tests      PASS
Exact Stage177C production-contract semantics           PASS
Decision casing/whitespace normalization               PASS
Invalid DST shift fail-closed                          PASS
Aligned DB without spread + raw CSV regression         PASS
Exact i+1 / i+24 semantics                             PASS
Raw spread guard high-spread block                     PASS
One-hour source misalignment fail-closed               PASS
EU DST winter/summer mapping                           PASS
Missing event context fail-closed                      PASS
No-signal idempotency                                  PASS
Python 3.14 dynamic-import regression                  PASS
Static broker-execution dependency scan                PASS
Unit/regression tests                                  11/11 PASS
```

## Remaining environment limitation

Local execution used the available container Python. The included GitHub workflow retains Python 3.13 and 3.14 matrix validation.
