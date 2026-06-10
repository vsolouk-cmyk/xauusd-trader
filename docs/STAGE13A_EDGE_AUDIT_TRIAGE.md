# Stage 13A Edge Audit / Strategy Triage

Stage 13A is not another strategy lab. It is a decision audit.

It answers:

```text
Do we have enough evidence to keep the current XAUUSD trading-system path?
Or do we need redesign/stop?
```

## Output decision

```text
KEEP_RESTRICTED_LONG_ONLY_WITH_REGIME_WAIT
KEEP_RESTRICTED_LONG_ONLY_COLLECT_FORWARD_EVIDENCE
KEEP_RESTRICTED_LONG_ONLY_BUT_FIX_TELEMETRY_ONCE
REDESIGN_REQUIRED
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage13a_edge_audit_triage
cat data/reports/stage13a_edge_audit_triage/stage13a_edge_audit_triage.md
```

## Outputs

```text
data/reports/stage13a_edge_audit_triage/stage13a_edge_audit_triage.md
data/reports/stage13a_edge_audit_triage/stage13a_edge_audit_triage.json
data/reports/stage13a_edge_audit_triage/stage13a_evidence_inventory.csv
```

## Hard rule

Audit only:

```text
No EA change
No automatic trading
No paper/live authorization
No new grid
No new dashboard
```
