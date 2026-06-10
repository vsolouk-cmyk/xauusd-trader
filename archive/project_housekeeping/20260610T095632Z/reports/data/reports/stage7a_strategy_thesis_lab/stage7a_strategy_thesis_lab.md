# Stage 7A Strategy Thesis Lab

Generated UTC: `2026-06-09T12:52:20+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- h1_rows: `24225`
- m1_rows: `1449867`
- macro_event_windows: `4`
- roundtrip_cost_usd: `0.35`

## Thesis ranking
| Thesis | Variant | Decision | Raw signals | Macro blocked | Trades | Total | PF | Median | Win rate | Max DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| volatility_compression_breakout | unguarded | KILL_LOW_PF | 814 | 0 | 664 | 142.0505 | 1.034906 | -5.2 | 0.412651 | -370.7248 |
| volatility_compression_breakout | macro_blocked | KILL_LOW_PF | 814 | 1 | 663 | 107.7892 | 1.026487 | -5.39 | 0.411765 | -370.7248 |
| baseline_sma_distance_v1_control | unguarded | KILL_LOW_PF | 2977 | 0 | 1108 | 222.59 | 1.026388 | -5.51 | 0.430505 | -658.68 |
| baseline_sma_distance_v1_control | macro_blocked | KILL_LOW_PF | 2977 | 3 | 1108 | 222.59 | 1.026388 | -5.51 | 0.430505 | -658.68 |
| asia_range_breakout | unguarded | KILL_NEGATIVE_TOTAL | 939 | 0 | 829 | -101.3836 | 0.979917 | -2.45 | 0.433052 | -594.87845 |
| asia_range_breakout | macro_blocked | KILL_NEGATIVE_TOTAL | 939 | 1 | 828 | -139.4336 | 0.972379 | -2.475 | 0.432367 | -594.87845 |
| trend_pullback_continuation | macro_blocked | KILL_NEGATIVE_TOTAL | 894 | 1 | 527 | -365.94704 | 0.889844 | -3.35 | 0.421252 | -465.247662 |
| trend_pullback_continuation | unguarded | KILL_NEGATIVE_TOTAL | 894 | 0 | 528 | -381.14254 | 0.885792 | -3.37 | 0.420455 | -480.443162 |
| range_mean_reversion | macro_blocked | KILL_NEGATIVE_TOTAL | 1841 | 3 | 718 | -613.455927 | 0.865352 | -1.33 | 0.462396 | -965.867819 |
| range_mean_reversion | unguarded | KILL_NEGATIVE_TOTAL | 1841 | 0 | 721 | -673.576926 | 0.854082 | -1.45 | 0.460472 | -965.867819 |

## Interpretation rules
- `PROMISING_RESEARCH_ONLY` means worth deeper validation, not tradable.
- `KILL_*` means do not tune filters around this version; either redesign the thesis or discard it.
- Compare `unguarded` vs `macro_blocked`. Macro guard is useful only if it improves robustness, not merely because it reduces trades.

## Macro/event guard
- `2026-06-10T10:30:00+00:00` → `2026-06-10T16:30:00+00:00` | US CPI | high | block
- `2026-06-11T11:00:00+00:00` → `2026-06-11T15:30:00+00:00` | US PPI | high | block
- `2026-06-17T15:00:00+00:00` → `2026-06-18T00:00:00+00:00` | FOMC | high | block
- `2026-06-05T10:30:00+00:00` → `2026-06-05T16:30:00+00:00` | US NFP | high | block

## Decision
- Do not lock no_asia or any other filter from Stage 7A alone.
- Use Stage 7A to choose which thesis family deserves Stage 7B deeper validation.
- Current v1 dry-run can continue only as evidence collection.
