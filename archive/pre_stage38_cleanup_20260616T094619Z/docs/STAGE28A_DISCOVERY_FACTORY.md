# Stage28A DB-First Discovery Factory

Stage28A is a batch discovery factory, not an operational trading module.

## Scope

- Research/shadow discovery only.
- DB-first market data from `data/local/xauusd_local_store.sqlite`.
- No AMarkets CSV market fallback.
- No EA change, no paper/live/order authorization.
- Active forward-shadow trackers remain separate:
  - Stage18A unified shadow ops cycle
  - Stage23D canonical tracker
  - Stage25D London-range filtered tracker
  - Stage27D H1-ATR filtered tracker

## Why this stage exists

The project found one stronger lineage around Stage23/25/27, but independent discovery through Stage26/27A produced mostly weak raw entries. Stage28A changes the workflow from one-off stage patches to a discovery factory:

1. Pattern registry
2. DB-first feature construction
3. Batch candidate evaluation
4. Family-balanced shortlist
5. Reproducible CSV/JSON/Markdown outputs

## Initial family registry

- `session_compression_expansion_v1`
- `volatility_transition_v1`
- `liquidity_sweep_regime_v1`
- `session_handoff_imbalance_v1`
- `calendar_time_risk_proxy_v1`

## Required command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28a_discovery_factory_batch_runner
cat data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.md
```

## Active suite command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
cat data/reports/active_shadow_suite/active_shadow_suite.md
```

## Safe cleanup/archive

Dry run:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py
```

Apply:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py --apply
```

Include workflows only after reviewing dry-run output:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/archive_inactive_xauusd_artifacts.py --include-workflows
python3 tools/archive_inactive_xauusd_artifacts.py --include-workflows --apply
```
