# QA Report — XAUUSD MT5 Login-Bound Review & Dry Cycle

## Scope

- Accept the actual V1.1 success decision label without weakening any readiness checks.
- Bind review to AMarkets DEMO login `7907958`.
- Keep `InpArmed=false`.
- Create no active `arming_permit.txt`.
- Create no active `demo_candidate.txt` in MT5 Files.
- Permit only an in-repo dry preview.

## Executed checks

- Python compile: PASS.
- Existing MT5 bridge regression tests: 12/12 PASS.
- Login-bound review/dry-cycle tests: 11/11 PASS.
- Combined tests: 23/23 PASS.
- Actual uploaded runtime-preflight integration: PASS.
- Current generic decision acceptance: PASS.
- Wrong-login rejection: PASS.
- Arming-readiness false rejection: PASS.
- Active permit rejection: PASS.
- Active candidate quarantine: PASS.
- Non-executable permit preview: PASS.
- Dry cycle no-signal path: PASS.
- Eligible candidate preview-only path: PASS.
- Event-blackout dry rejection: PASS.
- Weekend stale server-clock tolerance: PASS.
- Python broker API scan: PASS.
- Active MT5 permit/candidate write scan: PASS.

## Not claimed

- No active arming permit was created.
- No order path was enabled.
- No live market candidate was required for this QA.
- No MetaEditor recompilation is required because the EA source is unchanged.
