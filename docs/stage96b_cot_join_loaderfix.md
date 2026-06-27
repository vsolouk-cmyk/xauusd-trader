# Stage96B COT Join Loader Fix

This patch fixes the Stage96 COT-to-macro join when the macro dataset already contains an `available_after_utc` column. The COT availability field is now kept as `cot_available_after_utc`, while `available_after_utc` remains as a backward-compatible report alias for the COT availability date.

No thesis logic, thresholds, gates, MT5 files, observer files, or order state are changed.

Hard blocks remain:

- NO_AUTOMATED_ORDER
- NO_PAPER_ORDER
- NO_BROKER_CONNECTION
- NO_EA_PROMOTION
- NO_PAPER_LIVE
- NO_LIVE
- NO_ORDER_AUTHORIZATION_FROM_STAGE96
- NO_THRESHOLD_TUNING_FROM_STAGE96_DISCOVERY
- NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE96
