# XAUUSD Cross-Asset Fixed Thesis Scan V1

Program: `XAUUSD_CROSS_ASSET_FIXED_THESIS_SCAN_V1_2_PANDAS3_STREAMING_CSV_READER_REPAIR`

## Purpose

Run one compact, cost-aware, non-overlapping scan of 12 fixed cross-asset intraday theses against the passed causal panel.

## Governance

- Reference selection uses only `2016-01-01` through `2024-12-31`.
- `2025+` is seen diagnostic evidence and is never used for candidate selection.
- If no candidate passes all reference gates, diagnostic evaluation is not produced.
- If reference survivors exist, the survivor contract is written before diagnostic access.
- Diagnostic evidence is kill-only and cannot authorize promotion by itself.
- No paper, demo, live, broker, MT5, or order path exists.

## Candidate families

- USD / precious-metals consensus
- Gold / silver relative value
- Rates / USD alignment
- Risk / rates divergence
- Energy / inflation impulse
- DXY / silver shock

## Execution assumptions

- Decision hours: 06:00 through 19:00 UTC
- Official-event blackout active: excluded
- Horizons: exact 4h and exact 12h
- Signals within one candidate: non-overlapping
- Normal cost: 3 bps
- Severe cost: 6 bps
- Locked notional/equity: `0.1570396406876166`

## Reference gates

- At least 80 trades
- Severe-cost mean positive
- Profit factor at least 1.20
- Block-bootstrap p10 positive
- Positive after removing largest winner
- Matched year/hour excess mean and bootstrap p10 positive
- At least 2 of 3 reference folds positive
- Worst fold mean at least -5 bps
- Maximum positive-year profit share at most 45%
- Locked-risk CAGR at least 2%

## Commands

```bash
python3 app/xauusd_cross_asset_fixed_scan.py preflight --root .
python3 app/xauusd_cross_asset_fixed_scan.py run --root .
python3 app/xauusd_cross_asset_fixed_scan.py collect --root .
```

Expected artifact:

`~/Downloads/XAUUSD_CROSS_ASSET_FIXED_SCAN_RESULTS.zip`


## V1.1 repair

- Handles zero trades across the full packaged registry with an explicit headered empty trade artifact.
- Rejects schema-less CSV writes before pandas can raise an opaque internal error.
- Records the active stage, candidate id/index, and full traceback in failure evidence.
- Does not change candidates, thresholds, costs, time boundaries, or order permissions.

## V1.2 repair

- Replaces the one-shot pandas C-parser `read_csv(..., usecols=...)` path with a bounded streaming projection reader.
- Forces pandas `StringDtype` during CSV ingestion, then converts timestamps/numerics explicitly downstream.
- Avoids pandas 3.0.x `_concatenate_chunks` IndexError caused by mixed-type selected columns under low-memory inference.
- Adds header uniqueness and projected-column contract checks.
- Retains a Python-engine fallback only for parser-internal `IndexError`.
- Does not change candidates, thresholds, costs, periods, or order permissions.
