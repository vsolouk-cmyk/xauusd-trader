# Stage23A v2 Hotfix Patch

This patch replaces the first Stage23A module with a runtime-capped version.

Copy target:

```text
~/Desktop/xauusd-trader
```

Run after copying:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```

Fast override:

```bash
cd ~/Desktop/xauusd-trader
STAGE23A_MAX_RUNTIME_SECONDS=180 STAGE23A_MAX_CANDIDATES_TOTAL=90 STAGE23A_MAX_EXACT=12 python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```
