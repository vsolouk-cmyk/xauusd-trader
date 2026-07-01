# Stage134B Trade-log Priority Collector Hotfix

Fixes collector classification when `xauusd_stage134_demo_executor_status_kv.csv` is stale but `xauusd_stage134_demo_executor_trade_log.csv` contains an accepted or rejected demo order attempt.

This patch does not change the EA and does not send orders. It only changes collector interpretation.

Priority order:
1. Accepted/rejected trade log attempt.
2. Fresh status KV.
3. Missing/stale status.

If the latest trade log has `ok=true` and retcode `10009`, the collector decision becomes `STAGE134_DEMO_ORDER_ACCEPTED_COLLECT_PNL`.
