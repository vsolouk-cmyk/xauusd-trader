# Stage 11B Alternative Short Thesis Lab

Stage 11A found no robust short candidate for the direct short-side continuation thesis.

Stage 11B tests different short-side structures instead of over-filtering Stage 11A.

## Thesis families

```text
1. short_compression_breakdown
2. short_rally_rejection
3. short_bearish_impulse_after_compression
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11b_alternative_short_thesis_lab
cat data/reports/stage11b_alternative_short_thesis_lab/stage11b_alternative_short_thesis_lab.md
```

Quiet run:

```bash
python3 -m app.stage11b_alternative_short_thesis_lab --progress-every 0
```

## Outputs

```text
data/reports/stage11b_alternative_short_thesis_lab/stage11b_alternative_short_thesis_lab.md
data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv
data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_trades.csv
data/reports/stage11b_alternative_short_thesis_lab/stage11b_alternative_short_thesis_lab.json
```

## Decision

```text
short_candidate_found
```

permits only robustness/execution-replay research next.

It does not permit EA order code, paper, or live execution.
