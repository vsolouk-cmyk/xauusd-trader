# Stage24E Mirror / Anti-Signal Discovery

Research/shadow-only discovery module. No EA, no paper/live/order authorization.

Stage24A-D repeatedly rejected several fade/reversal/continuation clusters after cost stress. Stage24E tests whether selected failed-reversal/fade ideas have value in the mirror direction.

Families:

1. `day_open_extension_continuation`
2. `prev_day_expansion_continuation`
3. `london_range_breakout_hold_continuation`

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage24e_mirror_anti_signal_discovery
cat data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.md
```

Fast diagnostic run:

```bash
cd ~/Desktop/xauusd-trader
STAGE24E_MAX_RUNTIME_SECONDS=150 STAGE24E_EXACT_RESERVED_SECONDS=45 STAGE24E_MAX_CANDIDATES_TOTAL=60 STAGE24E_MAX_EXACT=9 python3 -m app.stage24e_mirror_anti_signal_discovery
cat data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.md
```
