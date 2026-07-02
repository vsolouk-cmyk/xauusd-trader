# Stage143 Live H1 Bar Exporter

The current blocker is stale H1 input for Stage138:
- the Downloads H1 file stops at `2026.07.01 11:00:00`
- Stage138 cannot create a new signal key until it sees fresh H1 bars

Stage143 solves this by exporting H1 bars directly from MT5 to `MQL5/Files`.

Components:
- MT5 indicator:
  - `Stage143_LiveH1BarExporter.mq5`
- Python collector:
  - `app/stage143_live_h1_bar_exporter_collector.py`

MT5 output:
- `xauusd_stage143_live_h1_bars.csv`
- `xauusd_stage143_live_h1_bar_exporter_kv.csv`

Stage143 is read-only:
- no order send
- no position modification

Recommended Stage138 bars path:
`/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv`
