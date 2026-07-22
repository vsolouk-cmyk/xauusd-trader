# QA Report — Controlled-Paper Operational Freshness Guard

## Defect reproduced

A controlled-paper run generated at `2026-07-22T12:50:32Z` reported ACTIVE while:

- latest aligned H1 was `2026-07-22T03:00:00Z`;
- latest AMarkets M5/spread source was `2026-07-22T03:50:00Z`;
- the Stage180 summary/observation was from the earlier refresh cycle.

The previous implementation checked source-to-database parity but did not check wall-clock freshness.

## Repair

- Added conservative XAUUSD open/closed schedule handling.
- Added mandatory Stage180-summary, aligned-H1, and spread-source age gates.
- Added future-clock-skew blocking.
- Added stale-data decision output while preserving summary/report generation.
- Ensured stale runs perform no signal or position ledger mutation.
- Kept weekend closure usable without weakening future-clock checks.

## QA results

- Python compilation: PASS
- Unit/regression tests: 15/15 PASS
- Open-market stale-data reproduction: PASS
- No-ingest/no-position mutation under stale data: PASS
- Fresh open-market run: PASS
- Weekend closure age deferral: PASS
- Existing exact i+1/i+24 semantics: PASS
- Existing 168/146/22 coverage parser: PASS
- Existing AMarkets spread parity and guard: PASS
- Missing dependency/event/spread fail-closed tests: PASS
- Broker dependency static scan: PASS

The package must also be run through the included GitHub Actions matrix on Python 3.13 and 3.14.
