# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2K: walk-forward validation after Stage 2J candidate stability analysis.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Candidate stability: checking that a baseline works across time segments, not just one lucky region.
- Walk-forward validation: testing performance as time moves forward.
- Fold: one chronological segment of trades.
- Rolling window: a moving block of consecutive trades.
- Tail performance: recent trades, such as the last 50 trades.

## Local sequence

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2k_walkforward --data-db data/store/xauusd.sqlite
```

## GitHub workflow order

Run manually or let schedule run:

```text
XAUUSD Persistent Data Store Refresh
```

After it completes successfully, GitHub automatically triggers the active validation workflow:

```text
XAUUSD Stage 2K Walk-Forward Validation
```

## GitHub Actions secrets

```text
TWELVEDATA_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Hard rule

If a candidate does not survive Stage 2K, do not proceed to ML or paper-order.

Telegram messages are reports only, not signals.
