# Stage23A v3 — Lite Proxy-Then-Exact Discovery

Research-only discovery module. It does not modify Stage18A v2, does not modify any EA, and does not authorize paper/live/orders.

## Why v3 exists

Stage23A v2 controlled total runtime, but proxy evaluation could consume the full runtime cap. In that case the report could show `Exact replayed: 0`, which is not useful for diagnostics.

v3 fixes this by:

- reserving runtime for exact M1 replay;
- caching repeated signal-event generation across candidates that differ only by TP/SL/horizon;
- lowering default candidate caps;
- keeping exact replay diagnostic even when proxy candidates are weak.

## Default runtime controls

```text
STAGE23A_MAX_RUNTIME_SECONDS=180
STAGE23A_EXACT_RESERVED_SECONDS=45
STAGE23A_MAX_CANDIDATES_TOTAL=60
STAGE23A_MAX_EXACT=12
STAGE23A_MAX_EXACT_PER_FAMILY=4
STAGE23A_PROXY_BOOTSTRAP_ITERS=20
STAGE23A_EXACT_BOOTSTRAP_ITERS=80
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```

## Fast diagnostic run

```bash
cd ~/Desktop/xauusd-trader
STAGE23A_MAX_RUNTIME_SECONDS=120 STAGE23A_EXACT_RESERVED_SECONDS=40 STAGE23A_MAX_CANDIDATES_TOTAL=45 STAGE23A_MAX_EXACT=8 python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```
