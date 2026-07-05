# Stage151 Locked MTF Rule State Writer

Stage151 solves the operational runtime problem: after Stage150B has selected a candidate, do not rescan all candidates every refresh. Instead, read the locked selected rule from the Stage150B summary, recompute current MTF features on the latest CSV, evaluate only that locked rule, and write a Stage134-compatible KV.

Recommended M5 refresh after market open:

```bash
python3 app/stage151_locked_mtf_rule_state_writer.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --source-summary /Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_mtf_separated_validation_discovery_summary.json \
  --tf m5 \
  --timeframe-minutes 5 \
  --write-mt5
```

Stage134 input after this:

```text
InpRuleStateKvFile:
xauusd_stage151_m5_locked_rule_state_kv.csv

InpAllowedRules:
D150C_M5_trend_8_20_bps_GEQ65__trend_50_100_bps_GEQ35
```

Use full Stage150B only offline or when replacing the locked rule.
