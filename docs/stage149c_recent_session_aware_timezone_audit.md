# Stage149C Recent Session-Aware Timezone and Bar Audit

Stage149B still over-blocked because it treated exchange holidays, early closes, and routine broker/session maintenance gaps as suspicious.

Stage149C is practical for the current goal:

- expected weekend, holiday and early-close gaps are logged but not blockers;
- small routine session/broker maintenance gaps are logged as expected;
- historical suspicious gaps are logged but do not block the current demo probe;
- recent suspicious intraweek gaps, non-monotonic timestamps, and future timestamps remain blockers.

Default recent audit window: 90 days from the last parsed bar.

Run:

```bash
python3 app/stage149_stage143_timezone_and_bar_audit.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --bars "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv" \
  --recent-audit-days 90
```

Output:

```text
reports/stage149_stage143_timezone_and_bar_audit/stage149c_recent_session_aware_timezone_and_bar_audit_summary.json
```
