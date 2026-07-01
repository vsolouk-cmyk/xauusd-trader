# Stage138B MT5 Export Parser Hotfix

Problem:
- Stage138 parsed only comma-delimited normalized bars.
- AMarkets MT5 export is tab-delimited with columns:
  - `<DATE>`
  - `<TIME>`
  - `<OPEN>`
  - `<HIGH>`
  - `<LOW>`
  - `<CLOSE>`
  - `<TICKVOL>`
  - `<VOL>`
  - `<SPREAD>`

Fix:
- delimiter autodetect: tab/comma/semicolon
- angle-bracket column normalization
- DATE + TIME composition
- MT5 date format support: `YYYY.MM.DD HH:MM:SS`
- explicit `--bars` path no longer silently falls back if missing
- summary includes both `raw_row_count` and normalized `bar_count`

No order path is added. Stage138B only writes Stage134-compatible rule-state files.
