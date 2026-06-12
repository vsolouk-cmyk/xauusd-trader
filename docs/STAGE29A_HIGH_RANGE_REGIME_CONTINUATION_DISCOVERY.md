# Stage29A — DB-First High-Range Regime Continuation Discovery

Stage29A is a research/shadow discovery branch. It does not modify Stage18A, Stage23D, Stage25D, Stage27D, Stage28D, any EA, paper/live mode, or orders.

## Purpose

Stage28C validated that the canonical Stage23/25 lineage is much stronger in high London-range and high prior-day-range regimes, but Stage28D showed the original lineage remains sparse. Stage29A tests whether that same high-range thesis can produce denser continuation candidates.

## Guardrails

- DB-first only through `app.stage25c_deduped_filter_validation.load_bars_from_db`.
- AMarkets CSV market fallback is disabled.
- London session features use completed London range before entries at 13:00 UTC or later.
- Quantile thresholds use prior rolling data only; no full-sample static threshold is used for entry selection.
- All outputs are research-only.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage29a_high_range_regime_continuation_discovery
cat data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_high_range_regime_continuation_discovery.md
```

## Optional runtime controls

```bash
STAGE29A_MAX_RUNTIME_SECONDS=180 \
STAGE29A_MAX_CANDIDATES_PER_FAMILY=8 \
STAGE29A_BOOT_N=80 \
python3 -m app.stage29a_high_range_regime_continuation_discovery
```
