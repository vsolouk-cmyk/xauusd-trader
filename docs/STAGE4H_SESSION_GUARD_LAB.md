# Stage 4H — Session Guard Lab

Purpose: inspect weak segments from Stage 4G v2 AMarkets non-overlap replay without changing the EA.

Hard rule: this stage does not authorize demo, paper, or live orders.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage4h_session_guard_lab
cat data/reports/stage4h_session_guard_lab/stage4h_session_guard_lab.md
```

## Optional: run on offset +3 trade list

```bash
python3 -m app.stage4h_session_guard_lab \
  --trades-csv data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv \
  --out-dir data/reports/stage4h_session_guard_lab_offset3
cat data/reports/stage4h_session_guard_lab_offset3/stage4h_session_guard_lab.md
```

## Interpretation

- `base_all` is the current locked dry-run candidate.
- `no_asia` tests whether the weak Asia segment should be removed.
- `overlap_other`, `london_ny_overlap_only`, `new_york_only`, and `other_only` are research candidates only.
- A good Stage 4H result is not enough for demo-order. It only tells us what should be replayed/monitored next.
