# Stage31D Exogenous Candidate Confirmation Patch

Adds:

- `app/stage31d_exogenous_candidate_confirmation.py`

Purpose:

- Re-check the strongest Stage31C exogenous audit candidates with stricter confirmation rules.
- Use Stage31A enriched dataset and Stage31C candidate diagnostics only.
- Recalculate macro and overlay gates using expanding prior-year thresholds.
- Apply event-level deduplication, bootstrap p05, per-year diagnostics, and simple cost-stress checks.
- Remain strictly research/shadow only. No EA, paper/live, order, or execution change.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31d_exogenous_candidate_confirmation
cat data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.md
```

Outputs:

- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.md`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.json`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_year_diagnostics.csv`

Environment overrides:

- `STAGE31D_TOP_N` default `40`
- `STAGE31D_BOOT_N` default `500`
- `STAGE31D_MIN_EVENTS` default `50`
- `STAGE31D_MIN_YEARS` default `3`

Recommended commit:

```bash
git add -A
git commit -m "Add Stage31D exogenous candidate confirmation"
git pull --rebase origin main
git push
```
