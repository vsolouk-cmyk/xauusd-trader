# XAUUSD Historical-As-Of Replay — Source-Proven Cost Contract Repair

This overlay replaces the four speculative replay repairs with a contract taken
from the actual Commercial Closure generator and validated against the actual
168-row execution ledger supplied by the user.

## Proven frozen formulas

Source: `app/commercial_closure_sprint.py`, lines 523–565 in the forensic input.

```text
side/gross:
  gross = direction * (exit_close / entry_open - 1) * 10,000

stress 8:
  m5_gross_bps - max(8.0, observed_spread_bps + 4.0)

stress 10:
  m5_gross_bps - max(10.0, observed_spread_bps + 6.0)
```

The earlier V4 formula omitted the `+4` and `+6` slippage add-ons. That is why
exactly four high-spread rows failed.

## Real-artifact validation completed before packaging

The supplied canonical artifacts were read directly:

```text
signals                 168
evaluated               146
missing                  22
LONG                     55
SHORT                    91
spread-sensitive rows     4
row-level cost errors      0
commercial metric errors  0
```

All normal, severe, stress-8, and stress-10 aggregate metrics reproduced the
saved `commercial_closure_summary.json` within floating-point precision.

## Expected decision

Because the current forward logger remains `LONG_ONLY` while the frozen
commercial reference contains both LONG and SHORT trades, the expected replay
result is:

```text
PASS_HISTORICAL_COMMERCIAL_REPLAY_BLOCK_FORWARD_POLICY_PARITY
```

This means historical replay is complete without forward waiting, but demo/live
remain blocked until forward direction policy is reconciled.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m py_compile \
  app/xauusd_controlled_paper.py \
  app/xauusd_controlled_paper_historical_replay.py \
  tests/test_xauusd_controlled_paper.py \
  tests/test_xauusd_controlled_paper_historical_replay.py

python3 -m unittest -v \
  tests.test_xauusd_controlled_paper \
  tests.test_xauusd_controlled_paper_historical_replay

rm -f \
  reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json \
  reports/xauusd_controlled_paper_replay/historical_asof_replay_failure.json

python3 app/xauusd_controlled_paper_historical_replay.py --root .
```

No broker, demo, or live order path is added.
