# Stage153 Locked MTF Timestamp Normalization

Stage152 correctly moved freshness from file modified time to `feature_date`, but Stage151 M5 revealed a timestamp-basis mismatch: AMarkets M5 CSV timestamps are broker-server time while the KV marked them as UTC.

Stage153 adds:

```text
--timestamp-shift-hours
```

For the current AMarkets/MT5 status use:

```text
--timestamp-shift-hours -3
```

This writes normalized UTC `feature_date` while preserving the locked rule feature calculation.

Recommended run:

```bash
python3 app/stage151_locked_mtf_rule_state_writer.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
  --source-summary /Users/vahid/Desktop/xauusd-trader/reports/stage150_mtf_separated_validation_discovery/m5/stage150_mtf_separated_validation_discovery_summary.json \
  --tf m5 \
  --timeframe-minutes 5 \
  --max-feature-age-sec 7200 \
  --timestamp-shift-hours -3 \
  --write-mt5
```

Stage134 EA from Stage152 remains required.
