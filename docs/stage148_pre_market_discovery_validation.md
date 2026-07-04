# Stage148 Pre-Market Separated Validation Discovery

Stage148 is the pre-market fix for the main external-review concern: discovery/validation contamination.

It does not send orders and does not modify positions.

It differs from Stage138C by:
- excluding the most recent execution/probe window from scoring;
- requiring selection, validation, and tail windows to pass;
- rejecting candidates with negative selection-window mean by default;
- still applying frozen-family exclusions;
- writing the same Stage134-compatible KV only if a current-active candidate passes.

Recommended run before market open:

```bash
python3 app/stage148_pre_market_discovery_validation.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv" \
  --horizon-hours 24 \
  --min-events 30 \
  --min-selection-mean-bps 0.0 \
  --min-selection-hit 0.50 \
  --min-mean-bps 4.0 \
  --min-hit 0.53 \
  --min-tail-mean-bps 2.0 \
  --min-tail-hit 0.50 \
  --recent-embargo-bars 500 \
  --exclude-rule-substring D138C_ret_48h_bps_GEQ65 \
  --write-mt5
```

If no candidate is selected, do not unfreeze the contaminated H1 replacement. Use the remaining closed-market time to prepare M15/M5 or D1/macro discovery.
