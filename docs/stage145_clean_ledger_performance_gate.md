# Stage145 Clean Ledger Performance Gate

Stage145 reads the clean reconciled ledger from Stage144 and produces an operational performance gate.

It does not send orders and does not modify positions.

Default rules:
- fewer than 10 closed trades: continue demo accumulation, no live promotion
- 3 consecutive losses: freeze/repair current rule
- after enough trades: continue only if win rate and mean bps remain positive enough
- never promote to real/live from small-N demo outcomes

Input:
- `data/demo_execution/stage144_clean_demo_execution_ledger.csv`

Outputs:
- `reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json`
- `data/demo_execution/stage145_clean_ledger_performance_gate_snapshots.csv`
