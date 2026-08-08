# XAUUSD / Precious Metals Final RV V1.1 — Server-Epoch Schema Repair

## What this package does

This is a read-only research package with no order path.

It first runs a clustered observable-regime calibration. Only if that passes does it run the one locked Gold–Silver dynamic relative-value strategy described in `docs/PRECIOUS_METALS_FINAL_RV_LOCKED_SPEC.md`.

## V1.1 repair scope

This is a loader-only repair. Strategy, thresholds, costs, validation gates, reference/diagnostic boundaries and governance are unchanged.

The loader now supports the already-established cross-asset export schema exactly:

`program,symbol,timeframe,time_server_epoch,open,high,low,close,tick_volume,spread,real_volume,source`

`time_server_epoch` is interpreted under the same locked AMarkets server-clock contract used by the cross-asset panel: UTC+2 in winter and UTC+3 during EU DST, then converted to UTC. The original server-calendar date is preserved for broker-session daily aggregation.

## Expected inputs

The package auto-detects existing H1 exports under:

`/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/XAUUSD_CROSS_ASSET_HISTORY`

Expected canonical names are `xauusd__h1.csv` and `xagusd__h1.csv`. Explicit `--xau-h1` and `--xag-h1` paths are also supported.

No new MT5 export is expected if the previous cross-asset export directory is intact.

## Commands

### Preflight

```bash
python3 app/precious_metals_final_rv.py preflight --root .
```

Expected decision:

`PASS_PRECIOUS_METALS_RV_PREFLIGHT_REFERENCE_ONLY`

### Run

```bash
python3 app/precious_metals_final_rv.py run --root .
```

Allowed research decisions:

- `REGIME_VALIDATOR_RECALIBRATION_REQUIRED`
- `GOLD_SILVER_RV_NO_REFERENCE_EDGE_CLOSE_ALPHA_EXPANSION`
- `GOLD_SILVER_RV_REFERENCE_PASS_DIAGNOSTIC_BREAKDOWN`
- `GOLD_SILVER_RV_REFERENCE_PASS_READY_FOR_INDEPENDENT_REPLICATION`

### Collect

```bash
python3 app/precious_metals_final_rv.py collect --root .
```

Output:

`~/Downloads/XAUUSD_PRECIOUS_METALS_FINAL_RV_RESULTS.zip`

## Important governance

- No parameter scan.
- No 2018 structural-break hindsight.
- No paper/demo/live orders.
- 2025+ remains uncomputed unless reference passes.
- A Gold–Silver failure does not automatically launch futures, options or a commodity-basket scan.


## V1.2 derived-history contract repair

Preflight no longer uses an arbitrary fixed 2500 synchronized-daily-row threshold.
Data adequacy is derived from the locked strategy contract: 252 completed broker sessions for formation plus at least six post-formation evaluation years (6 x 252 rows), with at least six distinct calendar years. This supports the predeclared 3-fold stability check at roughly two years per fold. No strategy parameter, cost, entry/exit rule, validation performance gate, or 2025+ policy changed.
