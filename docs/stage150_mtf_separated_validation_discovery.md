# Stage150 MTF Separated Validation Discovery

Stage150 prepares the M15/M5 fallback path before the market opens.

It addresses a practical issue with simply reusing Stage148 on M15/M5: Stage148 feature names were H1-native. Stage150 is timeframe-aware:

- `ret_3h_bps` is really 3 hours, not 3 bars;
- `range_pos_24` is really 24 hours;
- target horizon is in hours and converted to bars;
- recent embargo is in hours, not bars.

Stage150 writes separate rule-state files:

```text
xauusd_stage150_m15_rule_state_kv.csv
xauusd_stage150_m5_rule_state_kv.csv
```

It does not send orders. It only writes MT5 files when `--write-mt5` is passed.

Recommended M15 run:

```bash
python3 app/stage150_mtf_separated_validation_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars ~/Downloads/amarkets_xauusd_15m.csv \
  --tf m15 \
  --timeframe-minutes 15 \
  --horizon-hours 4 \
  --min-events 80 \
  --min-selection-mean-bps 0.0 \
  --min-selection-hit 0.50 \
  --min-mean-bps 2.0 \
  --min-hit 0.53 \
  --min-tail-mean-bps 1.0 \
  --min-tail-hit 0.50 \
  --recent-embargo-hours 720 \
  --exclude-rule-substring D138C_ret_48h_bps_GEQ65
```

Recommended M5 run:

```bash
python3 app/stage150_mtf_separated_validation_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars ~/Downloads/amarkets_xauusd_5m.csv \
  --tf m5 \
  --timeframe-minutes 5 \
  --horizon-hours 4 \
  --min-events 150 \
  --min-selection-mean-bps 0.0 \
  --min-selection-hit 0.50 \
  --min-mean-bps 2.0 \
  --min-hit 0.53 \
  --min-tail-mean-bps 1.0 \
  --min-tail-hit 0.50 \
  --recent-embargo-hours 720 \
  --exclude-rule-substring D138C_ret_48h_bps_GEQ65
```

Decision:

- If M15/M5 selected candidates are empty, keep Stage148 H1 as the only limited demo-probe or pivot to D1/macro.
- If M15/M5 selected candidate is better than Stage148 H1, point Stage134 to the relevant Stage150 KV after market open.
