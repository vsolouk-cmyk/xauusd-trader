# Stage32A-HF1 — Commercial Candidate Supply Orchestrator

This hotfix upgrades Stage32A from a passive report aggregator into a commercial candidate-supply dashboard.

Scope:

- Research/shadow only.
- No EA change.
- No paper/live/order authorization.
- DB-first / SQLite source-of-truth diagnostics.
- Keeps observation, discovery, lineage validation, forward tracking, candidate aggregation, and readiness diagnostics visible together.

Main command:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode observation
```

Candidate-supply run:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode supply
```

Fast aggregation-only check:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode aggregate
```

Optional flags:

```bash
--run-data-refresh-arm      # run Stage16E separately; normally active suite already runs it
--run-discovery-arms        # run supply arms even in observation mode
--skip-active-wrapper       # skip active shadow wrapper
--skip-module-runs          # aggregate existing artifacts only
--fail-on-core-error        # non-zero exit if required active wrapper fails
```

New outputs:

```text
data/reports/research_shadow_orchestrator/research_shadow_orchestrator.md
data/reports/research_shadow_orchestrator/candidate_registry.csv
data/reports/research_shadow_orchestrator/candidate_supply_summary.csv
data/reports/research_shadow_orchestrator/commercial_readiness_summary.json
data/reports/research_shadow_orchestrator/db_data_freshness.csv
```

Commercial interpretation:

- If `LOW_CADENCE_CANDIDATE_SUPPLY` dominates, the next work should expand discovery density.
- If DB freshness is stale/missing, fix AMarkets/FRED import before candidate interpretation.
- If optional discovery arms error, repair the broken arm before treating the registry as complete.
- If review-ready candidates appear, prepare a separate commercial transition gate; do not auto-promote.
