# Stage 4G — AMarkets broker-feed backfill validation

This stage validates the locked XAUUSD candidate on the actual AMarkets MT5 broker feed exported from the user's terminal.

Hard rule: this is validation only. It does not authorize demo, paper, or live orders.

## Locked candidate

`xauusd_long_tp24_sl15_no_london_v1`

- Direction: long-only
- Signal timeframe: H1
- SMA window: 10
- Signal rule: `close - SMA10 >= 10 USD`
- Entry model: next H1 open
- Take-profit: 24 USD
- Stop-loss: 15 USD
- Time exit: 12 H1 bars
- Blocked session: `london` only
- Allowed sessions: `asia`, `london_ny_overlap`, `new_york`, `other`

## Required local files

Expected defaults:

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage4g_amarkets_backfill_validation
```

AMarkets live signal rows showed server time around UTC+2, so the default is:

```text
--server-utc-offset-hours 2
```

For sensitivity checking, also run:

```bash
python3 -m app.stage4g_amarkets_backfill_validation --server-utc-offset-hours 3 --out-dir data/reports/stage4g_offset3
```

## Outputs

```text
data/reports/stage4g_amarkets_backfill_validation.json
data/reports/stage4g_amarkets_backfill_validation.md
data/reports/stage4g_amarkets_backfill_trades.csv
```

## Interpretation

- `PASS`: local AMarkets backfill criteria passed. This still does not authorize orders.
- `PASS_WITH_WARNINGS`: usable, but warnings must be inspected before demo-order design.
- `FAIL`: do not advance beyond dry-run; inspect mismatch.

## Why this matters

The previous MT5 export ended around 2025-11-20. Now that the terminal is connected to AMarkets, this stage checks whether the locked rule still holds on the broker feed that will matter for dry-run/demo design.
