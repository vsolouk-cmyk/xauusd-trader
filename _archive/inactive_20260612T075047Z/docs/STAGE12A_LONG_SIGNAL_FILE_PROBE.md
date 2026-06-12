# Stage 12A Long Signal File Probe

This diagnostic distinguishes between:

```text
file_missing
file_exists_empty
file_exists_bom_only
file_exists_header_only
file_exists_with_rows
```

Why it matters:

Stage 12A v2 counts a long signal file as available only when it can read signal rows. If the EA created the file but no signal has been logged yet, the file may exist but still have zero rows.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage12a_long_signal_file_probe \
  --signal-csv "/FULL/PATH/TO/XAUUSD_DryRun_v2_regime_shadow_signals.csv"

cat data/reports/stage12a_long_signal_file_probe/stage12a_long_signal_file_probe.md
```

## If status is `file_exists_bom_only`

That means the EA created the file but has not written any header/signal rows yet.

This is not a trade signal and not an error in Stage 12A.

## Hard rule

Diagnostic only. No EA change, no automatic trading.
