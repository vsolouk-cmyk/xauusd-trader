# QA Report — Historical Replay V5 Source-Proven Cost Contract Repair

## Root cause proven from actual source

The actual generator contains:

```python
"stress_8bps_net_bps": gross - max(8.0, observed_spread_bps + 4.0)
"stress_10bps_net_bps": gross - max(10.0, observed_spread_bps + 6.0)
```

V4 tested `max(floor, observed_spread)` and therefore omitted the fixed
slippage add-ons. The four failing rows are precisely the rows where
`observed_spread_bps > 4`, so the omitted add-ons change the result.

## Forensic artifacts used

```text
commercial_closure_sprint.py
SHA-256 1c114d624fa56115c92a0bb1ac270c05c5ca55cea4c96a122bde0bef53ceddcc

commercial_closure_execution_ledger.csv
SHA-256 7d2bb519a280e09136afc7779d953206bde556cb6a2671a051d079fb121c2b5b

commercial_closure_summary.json
SHA-256 878c01d0495a951b4bf709ede70bafaeb86a2b7e3231fd6c1de5fc685c5be99f
```

## Actual-data tie-out

- Total ledger rows: 168 — PASS
- Evaluated rows: 146 — PASS
- Missing rows: 22 — PASS
- Probability-tail sides: 55 LONG / 91 SHORT — PASS
- Side-adjusted execution gross, all 146 rows — PASS
- Normal net/cost parity, all 146 rows — PASS
- Severe net/cost parity, all 146 rows — PASS
- Source-proven stress-8 parity, all 146 rows — PASS
- Source-proven stress-10 parity, all 146 rows — PASS
- Spread-plus-slippage branch rows: 4 — PASS
- Execution metrics vs saved summary — PASS
- Severe metrics vs saved summary — PASS
- Stress-8 metrics vs saved summary — PASS
- Stress-10 metrics vs saved summary — PASS
- Maximum numeric aggregate difference: < 1e-9 bps — PASS

## Test execution

- Historical replay tests without project artifacts: 28 tests, 27 PASS, 1 expected skip
- Historical replay tests with actual forensic artifacts: 28/28 PASS
- Combined controlled-paper and replay tests with actual artifacts: 43/43 PASS
- Python 3.13.5 compilation: PASS
- End-to-end CLI synthetic 168/146/22 smoke: PASS
- Smoke decision: `PASS_HISTORICAL_COMMERCIAL_REPLAY_BLOCK_FORWARD_POLICY_PARITY`
- Clean extraction: PASS
- Manifest verification: PASS
- Broker execution token scan: PASS

## Boundary

The real aligned SQLite database was not included in the forensic package.
However, the user's V4 run had already passed signal timestamp, `i+1/i+24`,
entry/exit price, side, and gross parity for all rows and failed only the four
stress fields. V5 changes only the stress formula and its tests.
