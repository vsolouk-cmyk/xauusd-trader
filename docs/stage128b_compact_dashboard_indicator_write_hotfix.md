# Stage128B compact dashboard indicator write hotfix

This is a hotfix only. It does not rerun discovery and does not change any EA trading logic.

It writes:

- `XAUUSD_Stage128_CompactShadowDashboardIndicator.mq5` to repo and MT5 indicator paths
- `xauusd_stage128_forward_shadow_and_megascan_status_kv.csv` to MT5 Files

The indicator is optional. The main operational runtime remains:

- `Unified_ObserverOnly_EA`
- Stage124F Rule8 overlay
- Stage126/127 Rule9 overlay
- No order path
