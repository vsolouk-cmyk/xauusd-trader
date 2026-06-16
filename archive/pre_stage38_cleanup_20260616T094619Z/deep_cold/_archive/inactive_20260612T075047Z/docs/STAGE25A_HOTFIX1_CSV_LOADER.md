# Stage25A Hotfix 1 — Robust MT5/AMarkets CSV Loader

This hotfix replaces `app/stage25a_regime_filter_discovery.py` with a defensive loader that supports MT5 tab-separated exports such as:

```text
<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
```

It does not modify Stage18A v2 or Stage23D and does not authorize EA, paper, live, or orders.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25a_regime_filter_discovery
cat data/reports/stage25a_regime_filter_discovery/stage25a_regime_filter_discovery.md
```
