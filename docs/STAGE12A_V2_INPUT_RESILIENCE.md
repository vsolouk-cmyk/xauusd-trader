# Stage 12A v2 Input Resilience

Stage 12A v1 was structurally correct, but it could show `missing` for macro/event guard if the earlier reports were archived or stored under a different path.

v2 adds:

```text
1. input completeness audit
2. SQLite fallback for macro context
3. fallback scan for Stage 10E / Stage 10D reports
4. explicit MT5 long-signal CSV argument
```

## Run normally

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage12a_consolidated_forward_shadow_report
cat data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md
```

## Run with explicit MT5 EA signal CSV

If MT5 writes the signal file outside the repo/Common Files, pass the file path manually:

```bash
python3 -m app.stage12a_consolidated_forward_shadow_report \
  --long-signal-csv "/path/to/XAUUSD_DryRun_v2_regime_shadow_signals.csv"
```

Or:

```bash
export XAUUSD_LONG_SIGNAL_CSV="/path/to/XAUUSD_DryRun_v2_regime_shadow_signals.csv"
python3 -m app.stage12a_consolidated_forward_shadow_report
```

## Output

```text
data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md
data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.json
```

## Hard rule

Report only. No EA change, no automatic trading, no paper/live authorization.
