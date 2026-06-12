# Stage24X Discovery Audit

Research-only diagnostic module for reviewing repeated no-promotion results in Stage24A through Stage24E.

It reads already-produced reports/CSVs under `data/reports/` and creates:

```text
data/reports/stage24x_discovery_audit/stage24x_discovery_audit.md
data/reports/stage24x_discovery_audit/stage24x_discovery_audit.json
data/reports/stage24x_discovery_audit/stage24x_discovery_audit_summary.csv
```

Hard guardrails:

- Does not modify Stage18A v2.
- Does not modify Stage23D.
- Does not authorize EA/paper/live/orders.
- Diagnostic only.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage24x_discovery_audit
cat data/reports/stage24x_discovery_audit/stage24x_discovery_audit.md
```
