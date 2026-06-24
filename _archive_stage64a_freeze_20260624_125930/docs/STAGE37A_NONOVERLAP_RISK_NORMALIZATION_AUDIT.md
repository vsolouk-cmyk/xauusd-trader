# Stage37A Non-Overlap Risk Normalization Audit

This patch adds a branch-level decision stage after Stage36B-F.

Purpose:

- Summarize all Stage36 thesis branches.
- Confirm that no strict review candidate has emerged.
- Preserve useful background candidates without promoting them.
- Check whether overlapping signal evaluation inflated drawdown for structure/cost-window candidates.
- Decide whether the next step should be strict non-overlap review or background-only monitoring.

Run:

```bash
python3 -m app.stage37a_nonoverlap_risk_normalization_audit
```

Outputs:

```text
data/reports/stage37a_nonoverlap_risk_normalization_audit/stage37a_nonoverlap_risk_normalization_audit.md
data/reports/stage37a_nonoverlap_risk_normalization_audit/stage37a_summary.json
```

No EA, paper-live, or order authorization is introduced by this patch.
