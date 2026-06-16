# Stage32B — Dense Forward Shadow Intake Builder

## Purpose

Stage32B converts the Stage32A-HF1 candidate-supply dashboard into an actionable research/shadow intake queue.

The project objective is the fastest safe path toward a commercially usable XAUUSD trading system. Stage32B is designed to prevent the project from getting stuck around historically attractive but low-cadence candidates.

## Inputs

Default inputs:

```text
data/reports/research_shadow_orchestrator/candidate_supply_summary.csv
data/reports/research_shadow_orchestrator/candidate_registry.csv
data/reports/research_shadow_orchestrator/commercial_readiness_summary.json
```

## Outputs

```text
data/reports/stage32b_dense_forward_shadow_intake/stage32b_dense_forward_shadow_intake.md
data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv
data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.json
data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.csv
data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.json
data/reports/stage32b_dense_forward_shadow_intake/rejected_but_dense_review.csv
data/reports/stage32b_dense_forward_shadow_intake/rejected_but_dense_review.json
data/reports/stage32b_dense_forward_shadow_intake/stage32b_summary.json
```

## Operating logic

Stage32B prioritizes candidate families with enough historical event density to generate forward-observable samples quickly.

Macro/exogenous Stage31 candidates remain watchlist-only unless they become forward-active. Dense but rejected variants are routed to a repair/retest queue, not to promotion.

## Default thresholds

```text
min_event_count = 500
strong_event_count = 1000
max_variants_per_family = 4
max_total_queue = 24
target_forward_days = 30
min_forward_samples_before_review = 20
```

## Commands

Run directly:

```bash
python3 -m app.stage32b_dense_forward_shadow_intake
```

Run through orchestrator after fresh aggregation:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode aggregate
python3 -m app.run_xauusd_research_shadow_orchestrator --mode supply
```

Skip Stage32B from orchestrator if needed:

```bash
python3 -m app.run_xauusd_research_shadow_orchestrator --mode supply --skip-stage32b-intake
```

## Safety

```text
RESEARCH_SHADOW_ONLY
NO_EA_CHANGE
NO_PAPER_LIVE
NO_ORDER_AUTHORIZATION
```
