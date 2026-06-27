# Stage92 Intraday Session Residual Thesis Discovery

## Purpose

Stage92 begins the intraday/session data-frontier path after Stage89 found no additional defensible residual macro-only thesis. It is intentionally thesis-first and residual-first:

- it uses local AMarkets intraday CSVs, preferably M15;
- it evaluates only a small locked set of session hypotheses;
- it filters entries to days when the current unified macro observer portfolio is inactive;
- it produces a shortlist for Stage93 hard audit only.

## Non-goals

Stage92 does not:

- authorize any order;
- write or modify MT5 observer CSVs;
- change any EA;
- run broker connection logic;
- tune thresholds after seeing results;
- revive the old candidate-first intraday promotion process.

## Candidate families

The stage evaluates thesis-first long-only XAUUSD session families such as:

- Asia compression followed by London upside breakout;
- Asia downside sweep followed by New York reclaim;
- London selloff followed by New York or next-day reversal;
- risk-off intraday pullback;
- DXY/real-yield headwind absorption through session reclaim;
- low-range continuation.

## Time convention

All sessions are defined in UTC:

- Asia: 00:00–06:59
- London: 07:00–11:59
- New York: 13:00–17:59
- Day panel: 00:00–21:59

This avoids broker-local timezone assumptions.

## Outputs

The stage writes:

- `stage92_intraday_session_residual_thesis_discovery_summary.json`
- `stage92_intraday_session_residual_thesis_discovery_report.md`
- `stage92_intraday_session_candidate_metrics.csv`
- `stage92_intraday_session_shortlist.csv`
- `stage92_intraday_session_entry_returns.csv`
- `stage92_intraday_file_inventory.csv`

## Decision logic

If at least one candidate passes discovery gates, the decision is:

`STAGE92_INTRADAY_SESSION_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER`

Otherwise:

`NO_INTRADAY_SESSION_THESIS_SHORTLIST_NO_ORDER`

In either case all no-order hard blocks remain active.
