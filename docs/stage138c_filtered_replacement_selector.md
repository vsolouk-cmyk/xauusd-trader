# Stage138C Filtered Replacement Technical Demo Discovery

Stage138C is a direct repair of the demo-execution discovery feed.

It does not send orders and does not modify positions.

Purpose:
- keep Stage134 demo execution moving,
- exclude frozen weak rule families,
- write only a filtered replacement rule-state KV for Stage134.

Use this after the D138C ret_48h GEQ65 family is frozen.

Recommended first run:

```bash
python3 app/stage138_broker_technical_demo_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv" \
  --horizon-hours 24 \
  --min-events 30 \
  --min-mean-bps 4.0 \
  --min-hit 0.53 \
  --min-tail-mean-bps 2.0 \
  --min-tail-hit 0.50 \
  --exclude-rule-substring D138C_ret_48h_bps_GEQ65 \
  --write-mt5
```

If no current-active replacement is selected on H1, do not unfreeze the failed family. Move to M15/M5 replacement feed.
