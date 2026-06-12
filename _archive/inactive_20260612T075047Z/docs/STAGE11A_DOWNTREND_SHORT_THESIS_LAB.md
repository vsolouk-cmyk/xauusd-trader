# Stage 11A Downtrend Short-Side Thesis Lab

Stage 11A tests a short-side counterpart to the selected long-only Stage 8D thesis.

## Thesis

```text
H4 downtrend
H1 compression
H1 liquidity/breakdown continuation
SHORT entry at next H1 open
time_exit_12h
emergency_stop_30
nonoverlap
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11a_downtrend_short_thesis_lab
cat data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.md
```

## Outputs

```text
data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.md
data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_summary.csv
data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_trades.csv
data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.json
```

## Hard rule

Research only. No EA change, no paper/live/order authorization.
