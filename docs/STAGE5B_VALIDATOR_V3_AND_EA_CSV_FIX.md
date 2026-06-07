# Stage 5B Validator v3 + Stage 5A EA CSV-format fix

This patch does not authorize demo, paper, or live trading.

## What v3 fixes

Validator v3 handles:

- MT5/Wine encoding artifacts such as BOM/replacement/null characters.
- UTF-8, UTF-16, ANSI/latin-style text.
- tab/comma/semicolon/pipe-delimited logs.
- header-only files before the market produces real tick/log rows.
- native EA columns already observed in `XAUUSD_DryRun_v1_signals.csv`, including:
  - `logged_at_gmt`
  - `signal_closed_h1_time_server`
  - `signal_closed_h1_time_gmt_now`
  - `session_utc`
  - `close_h1`
  - `sma10`
  - `distance_usd`

## Observed problem in current log

The current CSV header showed two issues:

1. The first header column has encoding/BOM artifacts.
2. `sma10` and `distance_usd` may be joined as `sma10distance_usd`.

Validator v3 can inspect this more safely, but the EA source should be patched before using logs as evidence.

## Safe EA CSV-format patch helper

Run check mode first:

```bash
python3 -m app.stage5a_patch_ea_csv_format --check
```

If it reports patchable CSV-format issues:

```bash
python3 -m app.stage5a_patch_ea_csv_format --apply
python3 -m app.stage5a_ea_safety_audit
```

This helper only targets CSV formatting:

- `sma10distance_usd` -> `sma10\tdistance_usd`
- add `FILE_ANSI` to `FileOpen(...)` calls that already use `FILE_COMMON`

It does not add any order/trade logic.

## Important

After patching the repo EA source, the updated `.mq5` still needs to be copied/compiled in MT5 before the deployed EA changes. Also archive/delete the old malformed Common Files CSV before collecting fresh market-open evidence.
