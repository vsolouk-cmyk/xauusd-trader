# Stage68 Signal Frequency Audit

Diagnostic-only frequency audit for the active Stage67D6 + Stage66J3 path.

## Purpose

Stage68 measures how often the locked rules would historically be active on the current macro dataset:

- H64L v2
- D3 H60
- D1 backup
- D4 backup

It reports active days, contiguous active episodes, no-overlap entry count, yearly distribution, and combined rule activity.

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No EA promotion
- No paper-live
- No live
- No threshold tuning from this audit alone

## Run

```bash
python3 app/stage68_signal_frequency_audit.py   --root .   --config configs/stage68_signal_frequency_audit.json   --out reports/stage68_signal_frequency_audit
```

## Outputs

- `reports/stage68_signal_frequency_audit/stage68_signal_frequency_audit_summary.json`
- `reports/stage68_signal_frequency_audit/stage68_signal_frequency_audit_report.md`
- `reports/stage68_signal_frequency_audit/stage68_signal_frequency_yearly.csv`
- `reports/stage68_signal_frequency_audit/stage68_signal_frequency_entries.csv`
