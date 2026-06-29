# Stage124C consolidated shadow CSV / EA path / combo overlay / discovery note

Status: patch over Stage124B. No order and no broker action.

## Fixes

- Corrects the default MT5 Expert path to:
  `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD`
- Keeps the MT5 Files path unchanged.
- Writes the MT5 shadow CSV in two-column key/value format so the observer EA reads state values rather than wide-header fragments.
- Keeps repo/report CSVs in wide audit-friendly format.
- Generates a non-active unified combo overlay preview showing how Stage124C can be merged as an 8th shadow rule later without overwriting the active Stage109/Stage108 combo CSV.
- Continues next-frontier discovery in the same run and writes selected candidates only if gates pass.

## Operator decision

Stage124C does not overwrite `data/mt5_bridge/unified_observer_signal.csv`. The current 7-rule combo should keep running. The Stage124C rule is ready for shadow observation, and merge into the unified combo should be done only through a dedicated combo-EA readiness patch, not by attaching order logic.

## Outputs added or changed

- `data/shadow_observer/stage124_xauusd_shadow_observer_signal.csv` — wide repo/audit CSV.
- `data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv` — key/value MT5-readable CSV copy in repo.
- `MQL5/Files/xauusd_stage124_shadow_observer_signal.csv` — key/value CSV when `--write-shadow-mt5-csv` is used.
- `MQL5/Experts/Advisors/XAUUSD/XAUUSD_Stage124_ShadowObserverOnly.mq5` — observer-only EA when `--write-mql5-ea` is used.
- `data/shadow_observer/stage124c_unified_observer_signal_overlay_preview.csv` — preview only; not active combo update.

## Hard blocks

- No automated order.
- No paper order.
- No broker connection.
- No trade request.
- No `OrderSend`.
- No `CTrade`.
- No paper-live or live.
