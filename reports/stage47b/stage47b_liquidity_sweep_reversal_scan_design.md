# XAUUSD Stage47B Liquidity-Sweep Reversal Scan Design

Generated UTC: 2026-06-18T18:58:00+00:00

## Stage status

```text
stage = Stage47B_LIQUIDITY_SWEEP_REVERSAL_SCAN_DESIGN
status = IMPLEMENTATION_READY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = RUN_STAGE47B_SCAN_ON_REPO_DATA
```

## Inherited decision

Stage47A selected only one new structural thesis for scan design:

```text
selected_thesis = STRUCT47_A_LIQUIDITY_SWEEP_REVERSAL
```

This package implements only that predefined thesis. It does not rescue Stage41/42/43, does not continue the Stage46 external-context branch, does not tune bad buckets after failure, and does not use ML.

## Thesis definition

XAUUSD may sweep visible liquidity beyond a predefined reference range, fail to continue, close back inside the range, and then mean-revert toward a midpoint, opposite side, or fixed-R target.

Long reversal template:

```text
1. Reference low is predefined from Asia range or prior-day range.
2. Active-window price sweeps below reference low by threshold.
3. Confirmation candle closes back inside the range.
4. Entry is confirmation close.
5. Stop is below sweep extreme plus predefined buffer.
6. Target is midpoint, opposite side, 1R, or 1.5R.
```

Short reversal template:

```text
1. Reference high is predefined from Asia range or prior-day range.
2. Active-window price sweeps above reference high by threshold.
3. Confirmation candle closes back inside the range.
4. Entry is confirmation close.
5. Stop is above sweep extreme plus predefined buffer.
6. Target is midpoint, opposite side, 1R, or 1.5R.
```

## Predefined scan grid

```text
reference_range = Asia, PriorDay
active_window = London, NY
sweep_threshold = max(0.10, ATR14 * 0.10), max(0.10, ATR14 * 0.20), max(0.10, ATR14 * 0.35)
confirmation = close_back_inside, close_back_inside_plus_0.10_ATR
target = midpoint, opposite_side, 1R, 1.5R
max_hold_minutes = 360
max_trades = 1 per side per reference range per day per candidate
```

This grid creates 96 predefined candidates.

## Session definitions

All windows use UTC:

```text
Asia reference range = 00:00-06:59
London active window = 07:00-10:59
NY active window = 13:00-16:59
PriorDay reference range = previous UTC day high/low
```

## Cost model

The scanner uses observed spread if available and otherwise a conservative configured minimum:

```text
default_base_cost_points = 0.50
cost_sensitivity = 1x, 2x, 3x
cost_points = max(observed_entry_spread, default_base_cost_points) * multiplier
```

The cost is treated as a round-trip deduction in XAUUSD price points. This is intentionally conservative because this is not an execution-realistic paper-order stage.

## Loader behavior

The script supports both SQLite and CSV:

```text
SQLite default path = state/xauusd.db
CSV path = user-provided via --csv
SQLite table = auto-detected unless --table is given
```

Accepted column aliases:

```text
timestamp: ts, timestamp, time, datetime, date, open_time, candle_time
open: open, o
high: high, h
low: low, l
close: close, c
spread: spread, spread_points, bid_ask_spread, ask_bid_spread
bid/ask: bid/ask, bid_close/ask_close, close_bid/close_ask
symbol: symbol, instrument, pair
timeframe: timeframe, tf, granularity, interval
```

If no valid data is found, the script writes a `NO_DATA_STOP_NO_PROMOTION` summary instead of crashing.

## Outputs

Running the scanner writes:

```text
reports/stage47b/stage47b_liquidity_sweep_reversal_summary.json
reports/stage47b/stage47b_liquidity_sweep_reversal_candidates.csv
reports/stage47b/stage47b_liquidity_sweep_reversal_trades.csv
reports/stage47b/stage47b_liquidity_sweep_reversal_report.md
```

## Survivor logic

A strict survivor must satisfy all of these:

```text
trade_count >= 30
mean_net_bps > 0
oos_mean_net_bps > 0
worst_quarter_net_bps > 0
bootstrap_p10_net_bps > 0
benchmark_residual_bps > 0
cost_2x_mean_net_bps > 0
max_year_trade_concentration <= 55%
```

A soft survivor is still research-only and weaker. It exists only to define an audit target, not to promote the strategy.

## Kill-switch

```text
KILL if strict_survivor_count == 0 and soft_survivor_count == 0
KILL if all candidates have mean_net_bps <= 0 after base cost
KILL if all candidates have oos_mean_net_bps <= 0
KILL if best candidate has bootstrap_p10_net_bps <= 0
KILL if best candidate depends on one year/quarter only
KILL if results require adding/removing bad buckets after seeing failures
KILL if cost_2x flips every candidate negative
```

## Manual run examples

Default SQLite path:

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py --db state/xauusd.db --out reports/stage47b
```

Explicit SQLite table:

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py --db state/xauusd.db --table candles --timeframe M5 --out reports/stage47b
```

CSV:

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py --csv data/xauusd_m5.csv --timeframe M5 --out reports/stage47b
```

Smoke test only:

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py --smoke-test --out reports/stage47b_smoke
```

## GitHub Actions workflow

This package adds a manual workflow:

```text
Stage47B Liquidity Sweep Reversal Scan
```

Run it from GitHub UI only after candle data exists in the repo or artifact path expected by the command. The workflow is manual (`workflow_dispatch`) and intentionally has no schedule.
