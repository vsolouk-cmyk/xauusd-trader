# Stage 12A Long Signal File Probe

Generated UTC: `2026-06-10T20:12:38+00:00`
Tool version: `v1`

> Hard rule: diagnostic only. No EA change, no automatic trading.

## Result
- path: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv`
- exists: `True`
- status: `file_exists_bom_only`
- size_bytes: `2`
- encoding_detected: `utf-16`
- rows: `0`
- headers: `[]`

## Interpretation
- The signal file exists but contains only a byte-order mark. This usually means the EA created the file but has not written any signal/header rows.

## Latest row
```json
{}
```

## Next action
- Keep Stage 12A as dashboard, but treat long-signal file as found-with-zero-signals.
- Let the EA continue running until it writes an actual signal row.
- If you want a persistent heartbeat/header, patch the EA later; do not add order logic.

## Output files
- json: `data/reports/stage12a_long_signal_file_probe/stage12a_long_signal_file_probe.json`
- md: `data/reports/stage12a_long_signal_file_probe/stage12a_long_signal_file_probe.md`
