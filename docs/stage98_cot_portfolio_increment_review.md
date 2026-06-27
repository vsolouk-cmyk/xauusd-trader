# Stage98 COT Portfolio Increment Review

Purpose: review Stage97 COT hard-audit survivors against the current 5-rule unified observer portfolio before any observer expansion.

This is not an order, broker, EA, or MT5 change stage. It produces only review outputs and, if justified, a selected list for Stage99 unified observer expansion.

Key controls:

- Requires Stage97 disposition `COT_HARD_AUDIT_SHORTLIST_READY_FOR_STAGE98_PORTFOLIO_REVIEW`.
- Rebuilds current unified portfolio active mask from macro data.
- Joins COT as-of using `available_after_utc` or conservative report-date lag.
- Evaluates incremental active days, overlap with current unified portfolio, latest active status, and pairwise overlap among selected COT additions.
- Emits selected COT rules only for Stage99 observer expansion, never for order authorization.
