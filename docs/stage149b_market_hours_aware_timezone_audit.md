# Stage149B Market-Hours-Aware Timezone and Bar Audit

Stage149 flagged the Stage143 H1 export as `REVIEW_REQUIRED` because it counted every gap larger than 75 minutes as suspicious. For XAUUSD this over-flags normal weekend and holiday closures.

Stage149B keeps the timestamp checks but separates:

- expected market-closure gaps, such as Friday-to-Monday and holiday clusters;
- suspicious intraweek gaps;
- non-monotonic timestamps;
- bars too far in the future versus local UTC.

A large weekend/holiday gap is not a blocker. Suspicious intraweek gaps remain blockers for promotion/evaluation.

Run:

```bash
python3 app/stage149_stage143_timezone_and_bar_audit.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv"
```

Output:

```text
reports/stage149_stage143_timezone_and_bar_audit/stage149b_market_hours_aware_timezone_and_bar_audit_summary.json
```
