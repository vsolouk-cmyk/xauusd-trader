# Stage23A v3 Runtime Diagnostic Patch

Copy this patch into `~/Desktop/xauusd-trader`.

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage23a_v3_runtime_diagnostic_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```

Fast diagnostic run:

```bash
cd ~/Desktop/xauusd-trader
STAGE23A_MAX_RUNTIME_SECONDS=120 STAGE23A_EXACT_RESERVED_SECONDS=40 STAGE23A_MAX_CANDIDATES_TOTAL=45 STAGE23A_MAX_EXACT=8 python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```
