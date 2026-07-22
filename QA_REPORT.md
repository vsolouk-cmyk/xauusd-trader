# QA Report — Controlled-Paper Execution-Ledger Parser Repair

## Reported failure

Preflight located the correct 168-row Commercial Closure execution ledger but failed to prove the 146 evaluated / 22 missing split.

## Root cause

The parser searched status text with positive substring matching before negative matching. Therefore a status such as `UNEVALUATED_MISSING_M5_COVERAGE` could be interpreted as evaluated because it contains the substring `EVALUATED`.

The test fixture also used a simplified three-column ledger and therefore did not exercise the real 25-column production schema.

## Repair

- Normalize status into exact tokens.
- Give negative statuses (`UNEVALUATED`, `MISSING`, `NO_COVERAGE`, and related states) precedence.
- Use only execution fields as execution evidence; `research_gross_bps` is not execution evidence.
- Accept evaluated rows only when status and execution fields are consistent.
- Treat contradictory complete execution evidence plus a negative status as a blocking conflict.
- Prefer the canonical execution ledger over paths marked invalid/archive/backup/old/tmp.
- Emit status counts, classification counts, and conflict examples in future fail-closed diagnostics.
- Replace the simplified fixture with the real production column layout.

## Checks executed

```text
Python 3.13.5 source compilation                         PASS
Production 25-column ledger schema                      PASS
Locked 168 / 146 / 22 split                             PASS
UNEVALUATED substring regression                        PASS
Research-only gross value not execution evidence        PASS
Canonical ledger preferred over invalid-clock copy      PASS
Exact i+1 / i+24 semantics                              PASS
Raw AMarkets spread-source parity                        PASS
High-spread blocking                                    PASS
Missing raw spread source fail-closed                    PASS
One-hour spread-source mismatch fail-closed              PASS
Stage177C semantic contract validation                   PASS
Missing event context fail-closed                        PASS
Python 3.14 dynamic-import regression                    PASS
Static broker-execution dependency scan                  PASS
Unit/regression tests                                    13/13 PASS
```

## Environment limitation

The local container provides Python 3.13.5. The included manual GitHub Actions workflow retains matrix validation on Python 3.13 and 3.14.
