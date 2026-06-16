# Stage23C — Promotion-Candidate Validation

Stage23B found strong research-only promotion-review candidates in the `london_oneway_continuation` family. Stage23C validates those locked candidates without expanding the grid.

## Purpose

- Validate Stage23B promotion-review candidates on exact M1 replay.
- Detect duplicate or redundant parameter variants.
- Stress-test by cost multipliers, chronological splits, year, direction, and exit reason.
- Treat `pf_2026 = inf` as a warning when it comes from zero losing trades.

## Guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- No operational promotion is performed by this module.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23c_promotion_candidate_validation
cat data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.md
```

## Outputs

```text
data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.md
data/reports/stage23c_promotion_candidate_validation/stage23c_promotion_candidate_validation.json
data/reports/stage23c_promotion_candidate_validation/stage23c_candidate_summary.csv
data/reports/stage23c_promotion_candidate_validation/stage23c_split_diagnostics.csv
data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv
```
