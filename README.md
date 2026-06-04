# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 3A: second-source validation skeleton for the fixed XAUUSD baseline candidate.

No ML. No trading bot. No paper order. No live order.

## Fixed candidate

```text
sma10_h12_dist10_cool1
```

## Current stores

Primary:

```text
data/store/xauusd.sqlite
```

Secondary, optional:

```text
data/second_source/second_source.sqlite
```

## Local Stage 3A

Without secondary source:

```bash
python3 -m app.xauusd_stage3a_second_source_validate
```

This should return:

```text
pending_second_source
```

With imported secondary CSV:

```bash
python3 -m app.xauusd_second_source_import \
  --csv /path/to/second_source_1h.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1h \
  --provider mt5_or_other

python3 -m app.xauusd_stage3a_second_source_validate
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 3A Second-Source Validation
```

## Hard rule

Stage 3A still does not authorize ML, paper-order, or live trading.

The project remains baseline-first and data-quality-first.
