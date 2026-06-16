# Stage27D DB-First H1 ATR Filtered Forward-Shadow Tracker

Generated UTC: 2026-06-16T09:40:41+00:00

## Decision

```text
STAGE27D_NO_ACTIVE_H1_ATR_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains unchanged and remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate; this module does not modify either one.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.
- H1 ATR gate uses only a completed H1 bar with `h1_bar_end <= signal_time`.

## Tracked candidate and gate

- Candidate: `S27D_H1_ATR_FILTERED_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65_h1atr_drop_low30`
- Family: `london_oneway_continuation`
- Gate: `h1_atr_drop_low30_strict_completed`
- H1 ATR quantile: `0.3`
- H1 ATR period: `20`
- Minimum calibration days: `250`
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
- m1_rows_stage27d: `1536273`
- h1_rows_stage27d: `25643`
- m15_rows_stage27d: `102493`
- M1 rows used: `1536273` | span: `2022-05-01 23:01:00+00:00 → 2026-06-16 12:18:00+00:00`
- H1 rows used: `25643` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:00:00+00:00`
- M15 rows derived: `102493` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:15:00+00:00`

## Gate diagnostics in current lookback

```json
{
  "events_before_gate": 0,
  "gate_dropped": 0,
  "gate_kept": 0,
  "gate_name": "h1_atr_drop_low30_strict_completed"
}
```

## Run counters

- new_signal_count: 0
- new_forward_open_count: 0
- new_late_backfill_count: 0
- newly_resolved_forward_count: 0
- recent_events_before_gate: 0
- recent_events_after_gate: 0
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

## Recent H1 ATR filtered tracked events

No rows.

## H1 ATR gate diagnostics in current lookback

No rows.

## Interpretation

- This tracker is research-shadow only; an open signal is not an order instruction.
- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after the outcome was already knowable; it is not forward proof.
- This module tracks the Stage27C validated H1 ATR no-trade gate around the canonical Stage23/25 lineage.
- The gate is anti-leakage constrained: only completed H1 bars at or before signal time are used.
- Keep Stage18A v2, Stage23D, and Stage25D running separately after each AMarkets CSV refresh/import cycle.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
python3 -m app.stage27d_db_first_h1_atr_filtered_forward_shadow
```

## Output files

- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.json`
- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md`
- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_h1_atr_filtered_forward_shadow_ledger.csv`
- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_recent_h1_atr_filtered_events.csv`
- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_h1_atr_gate_diagnostics.csv`
- `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_schema_diagnostic.csv`
