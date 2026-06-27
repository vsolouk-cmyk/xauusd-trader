# Stage76E K06 Observer Mode Fix

Purpose: rewrite the K06 observer bridge CSV as `key,value` and explicitly export both `mode` and `ea_mode` as `OBSERVER_ONLY_NO_TRADE`.

This stage does not authorize orders and does not connect to a broker.

Run:

```bash
python3 app/stage76e_k06_observer_mode_fix.py \
  --root . \
  --config configs/stage76e_k06_observer_mode_fix.json \
  --out reports/stage76e_k06_observer_mode_fix
```

Copy this CSV to `MQL5/Files`:

```text
data/mt5_bridge/k06_observer_signal.csv
```
