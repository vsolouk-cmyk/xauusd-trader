# Stage 5B Validator v5 — London/NY overlap hotfix

## Purpose

Fix a false `FAIL` in the Stage 5B dry-run log validator.

Validator v4 treated any session name beginning with `london_` as a blocked London session. That was wrong for the locked strategy because `london_ny_overlap` is an explicitly allowed session; only the standalone `london` session is blocked.

## Expected result

A live dry-run signal row such as:

```text
session_utc = london_ny_overlap
```

must pass the No-London filter check.

## Scope

This patch changes only:

```text
app/stage5b_dryrun_log_validator.py
```

It does not change the EA, strategy rules, MQL5 code, order behavior, or any execution permissions.

## Hard rule

This remains dry-run log validation only. It does not authorize demo, paper, or live orders.
