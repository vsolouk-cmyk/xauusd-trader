# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2J: candidate stability analysis after fast Stage 2D grid lab.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Workflow chain: one GitHub Actions workflow starts after another workflow completes.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Grid lab: controlled testing of simple baseline parameter combinations.
- Candidate stability: checking that a baseline works across time segments, not just one lucky region.
- Positive month ratio: fraction of months with positive net performance.
- Cost x3: performance after tripling assumed transaction cost.

## Local sequence

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
```

## GitHub workflow order

Run manually or let schedule run:

```text
XAUUSD Persistent Data Store Refresh
```

After it completes successfully, GitHub automatically triggers the active analysis workflow:

```text
XAUUSD Stage 2J Candidate Stability Analysis
```

## GitHub Actions secrets

```text
TWELVEDATA_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Hard rule

If a candidate does not survive Stage 2J, do not proceed to ML or paper-order.

Telegram messages are reports only, not signals.
