# Stage25D DB-First Filtered Forward-Shadow Tracker

Generated UTC: 2026-06-16T09:40:12+00:00

## Decision

```text
STAGE25D_NO_ACTIVE_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains unchanged and remains the active operational forward-shadow runner.
- Stage23D remains separate; this module does not modify it.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.

## Tracked candidate and filter

- Candidate: `S25D_FILTERED_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65_london_range_drop_low30`
- Family: `london_oneway_continuation`
- Filter: `london_range_drop_low30`
- Filter quantile: `0.3`
- Minimum calibration days: `250`
- Anti-leakage rule: full `early_ny_range` filters are intentionally not used at entry hour 13 because the full 13-16 window is not knowable at entry time.
- Parameters:
```json
{
  "eff_min": 0.6,
  "entry_hour": 13,
  "horizon_min": 180,
  "london_move_atr_min": 0.9,
  "ny_confirm_atr_min": 0.15,
  "pullback_atr_max": 0.1,
  "sl_atr": 0.65,
  "tp_atr": 0.6
}
```

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- m1_mode: `db_schema_introspection`
- m1_rows: `1536273`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-16 12:18:00+00:00`
- h1_mode: `db_schema_introspection`
- h1_rows: `25643`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:00:00+00:00`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows_stage25d: `1536273`
- h1_rows_stage25d: `25643`
- m15_rows_stage25d: `102493`
- M1 rows used: `1536273` | span: `2022-05-01 23:01:00+00:00 → 2026-06-16 12:18:00+00:00`
- H1 rows used: `25643` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:00:00+00:00`
- M15 rows derived: `102493` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:15:00+00:00`

## Run counters

- new_signal_count: 0
- new_forward_open_count: 0
- new_late_backfill_count: 0
- newly_resolved_forward_count: 0
- recent_events_before_filter: 0
- recent_events_after_filter: 0
- ledger_total_rows: 0
- open_signal_count_now: 0
- resolved_signal_count_in_ledger: 0
- forward_valid_resolved_count: 0

## Forward-valid resolved metric snapshot

These metrics include only outcomes whose first recorded observation happened before or at exit time.

```json
{
  "events": 0,
  "pf_x1": 0.0,
  "pf_x4": 0.0,
  "total_x1": 0.0,
  "win_rate_x1": 0.0
}
```

## Recent filtered tracked events

No rows.

## Filter diagnostics in current lookback

No rows.

## Interpretation

- This tracker is research-shadow only; an open signal is not an order instruction.
- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after the outcome was already knowable; it is not forward proof.
- The default filter is `london_range_drop_low30` because Stage25C validated it and it is knowable before the Stage23D entry hour.
- The stronger Stage25C composite using `early_ny_range` is not used here because it would leak future information at entry hour 13.
- Keep Stage18A v2 and Stage23D running separately after each AMarkets CSV refresh.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md

python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```

## Output files

- `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.json`
- `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.md`
- `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_filtered_forward_shadow_ledger.csv`
- `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_recent_filtered_events.csv`
- `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_filter_diagnostics.csv`
