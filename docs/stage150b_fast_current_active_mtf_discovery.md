# Stage150B Fast Current-Active MTF Discovery

Stage150 full M5 scan can take too long because it scores every candidate over 300k+ M5 rows.

Stage150B keeps executable selection logic but speeds up operational refresh:

- generate the same candidate specs;
- check whether each rule is current-active on the latest bar;
- by default score only current-active candidates exactly;
- skip inactive candidates because they cannot be selected for Stage134 execution anyway;
- preserve `--score-inactive` for full offline diagnostics.

Recommended M5 fast run:

```bash
python3 app/stage150_mtf_separated_validation_discovery.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars /Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv \
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
  --exclude-rule-substring D138C_ret_48h_bps_GEQ65 \
  --write-mt5
```

Full diagnostic mode:

```bash
python3 app/stage150_mtf_separated_validation_discovery.py ... --score-inactive
```
