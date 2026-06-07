# Stage 5A CSV Patch Helper v4

This patch replaces the Stage 5A CSV-format patch helper only.

## Why v4 exists

v3 could falsely fail when strings/comments inside the EA contained safety terms such as `CTrade`.
That is too strict for a CSV-format patch helper, because the EA may contain comments like `No CTrade`.

v4 removes comments and string literals before scanning for forbidden executable trade/order tokens.
It also blocks only newly introduced forbidden tokens.

## Scope

Allowed changes only:

- add `FILE_ANSI` to `FILE_COMMON` `FileOpen(...)` calls when missing;
- fix the broken CSV header join around `sma10` and `distance_usd` when the exact pattern is found.

Forbidden:

- no order sending;
- no demo/paper/live execution authorization;
- no lot sizing/risk allocation;
- no strategy logic change.

## Commands

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage5a_patch_ea_csv_format --check
python3 -m app.stage5a_patch_ea_csv_format --apply
python3 -m app.stage5a_ea_safety_audit
```

After applying, redeploy the EA source into MT5 manually and compile it there.
