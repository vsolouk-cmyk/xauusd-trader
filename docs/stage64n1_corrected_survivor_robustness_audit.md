# Stage64N1 Corrected Survivor Robustness Audit

Purpose: audit the single Stage64M corrected survivor without creating new candidates, tuning thresholds, scanning hypotheses, connecting to a broker, or authorizing orders.

Audits:

- A1: reproduce Stage64M accounting from the immutable Stage64K dataset and Stage64L design.
- A2: run non-parametric/bootstrapped diagnostics against the primary benchmark.
- A3: test ETF and central-bank source-lag/staleness sensitivity.
- A4: run feature-ablation governance diagnostics to check whether the survivor is interpretable as full-scope macro edge rather than a trend artifact.
- A5: retain the broker/spot alignment blocker before any commercialization claim.

No event-calendar historical feature or post-hoc exclusion is permitted. Forward-only event governance remains a future operational control only.
