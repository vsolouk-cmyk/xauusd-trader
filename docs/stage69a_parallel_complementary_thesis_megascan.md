# Stage69A Parallel Complementary Thesis Megascan

Stage69A exists to prevent the project from waiting passively for the current low-frequency robust selector.

It runs a pre-registered complementary thesis megascan across the daily macro/gold dataset and shortlists only candidates that meet minimum frequency, return, win-rate, period-robustness, and concentration constraints.

## Policy

- No orders.
- No broker connection.
- No EA promotion.
- No paper-live or live path.
- No threshold tuning from Stage69A output alone.
- Pass-fast output only authorizes a later hard audit of a shortlist candidate.

## Active strategic role

Stage67D6, Stage67E, and Stage68F remain the daily robust shadow selector path.

Stage69A is the parallel discovery path for faster commercial progress:
- It avoids waiting for D3/H64L/D4 to become active.
- It searches thesis families with different macro mechanisms.
- It outputs a shortlist, not a promotion.

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 tests/test_stage69a_parallel_complementary_thesis_megascan.py

python3 app/stage69a_parallel_complementary_thesis_megascan.py   --root .   --config configs/stage69a_parallel_complementary_thesis_megascan.json   --out reports/stage69a_parallel_complementary_thesis_megascan
```

## Outputs

- `stage69a_parallel_complementary_thesis_megascan_summary.json`
- `stage69a_parallel_complementary_thesis_megascan_report.md`
- `stage69a_parallel_complementary_thesis_megascan_candidates.csv`
- `stage69a_parallel_complementary_thesis_megascan_yearly.csv`
