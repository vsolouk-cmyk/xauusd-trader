# Stage76D K06 MT5 Observer Bridge Schema Fix

This patch makes the Python bridge and MT5 EA agree on one CSV schema.

- `app/stage76d_k06_mt5_observer_bridge_schema_fix.py` writes `data/mt5_bridge/k06_observer_signal.csv` in `key,value` format.
- `mt5/K06_ObserverOnly_EA.mq5` reads that key-value CSV from `MQL5/Files`.
- The EA is observer-only and contains no trade path.

Daily routine: keep the EA installed; replace only `k06_observer_signal.csv` after each refresh.
