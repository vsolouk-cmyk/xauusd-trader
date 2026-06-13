# Stage31C Exogenous Fragile-Edge Audit Patch

## Purpose

Adds a research-only Stage31C module that audits Stage31B weak/fragile exogenous gates with expanding prior-year thresholds and a small set of forward-safe diagnostic overlays.

This patch does **not** change EA behavior, active shadow runners, paper/live execution, or any order pathway.

## Files

- `app/stage31c_exogenous_edge_audit.py`
- `docs/README_STAGE31C_EXOGENOUS_EDGE_AUDIT.md`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31c_exogenous_edge_audit
cat data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.md
```

## Outputs

- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.md`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.json`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.csv`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_candidate_review.csv`
- `data/reports/stage31c_exogenous_edge_audit/stage31c_year_diagnostics.csv`

## Interpretation rules

- `STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY`: candidate survives stricter audit, still not executable.
- `STAGE31C_FRAGILE_EXOGENOUS_POSITIVE_DIAGNOSTIC_ONLY`: positive but fragile; needs deeper validation.
- `STAGE31C_HAS_WEAK_EXOGENOUS_WATCHLIST_REVIEW_ONLY`: weak improvement only.
- `STAGE31C_NO_ROBUST_EXOGENOUS_EDGE_REVIEW_ONLY`: do not continue simple macro gates.

## Notes

Stage31C focuses on the diagnostic signs from Stage31B, especially weak/fragile candidate-specific exogenous filters. It also intersects them with a short set of known forward-safe overlays such as H1 ATR rank and London/prior-day range gates. All thresholds are calibrated from prior years only.
