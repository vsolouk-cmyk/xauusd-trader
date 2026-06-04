# Stage 2B Baseline Validation

## Purpose

Stage 2B checks whether Stage 2A candidates survive basic validation.

The key problem in Stage 2A is overlapping trades. For example, a 1h strategy with a 3-bar horizon can create a new trade every candle while old trades are still open. That inflates apparent evidence.

## What Stage 2B changes

- Uses larger data if Twelve Data allows it.
- Applies non-overlap filtering.
- Keeps assumed cost model.
- Produces separate Stage 2B summaries and trade CSV.
- Sends Telegram notification.

## Key definitions

- Overlapping trades: trades whose holding periods overlap in time.
- Non-overlap filter: accepts a new trade only after the previous trade has exited, plus optional cooldown.
- Cooldown: waiting period after a trade exits before a new trade may enter.
- Robust candidate: a baseline that remains positive after non-overlap filtering, assumed costs, and basic drawdown sanity check.

## Local command

First collect a larger snapshot:

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 5000
```

If 5000 fails because of API limits, try:

```bash
python3 -m app.xauusd_stage1_snapshot --outputsize 1000
```

Then run validation:

```bash
python3 -m app.xauusd_stage2b_validate_baselines
```

## Expected outputs

```text
data/reports/stage2b_validation_summary_*.json
data/reports/stage2b_validation_summary_*.md
data/reports/stage2b_trades/stage2b_nonoverlap_trades_*.csv
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 2B Baseline Validation
```

Recommended first input:

```text
outputsize: 5000
include_run_link: false
```

If Twelve Data rejects 5000, rerun with:

```text
outputsize: 1000
```

## Interpretation

- `robust_candidate_found`: continue with larger/cleaner validation.
- `need_more_data`: increase data if API allows; otherwise backfill from another source.
- `no_robust_candidate`: do not proceed to ML from this baseline set.
