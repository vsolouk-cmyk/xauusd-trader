# Stage28D Forward-Safe Meta-Gate Forward-Shadow Tracker

Generated UTC: 2026-06-14T17:59:29+00:00

## Decision

```text
STAGE28D_NO_ACTIVE_META_GATE_FORWARD_SIGNAL_RESEARCH_ONLY
```

## Scope guardrails

- Research/shadow only.
- Stage18A, Stage23D, Stage25D, and Stage27D remain unchanged.
- No EA change, no automatic trading, no paper/live/order authorization.
- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.
- The meta-gate uses only forward-safe features known at entry time.
- Quantile thresholds are expanding/event-by-event and use only prior canonical candidate events.

## Tracked candidate and meta-gate

- Candidate: `S28D_META_FILTERED_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65_london_q60_prior_q25`
- Family: `london_oneway_continuation`
- Gate: `stage28c_london_q60_prior_q25_expanding`
- Gate rule: `london_range >= prior-event q60` AND `prior_day_range >= prior-event q25`
- Minimum prior calibration events: `25`
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
- m1_rows: `1534217`
- m1_span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- h1_mode: `db_schema_introspection`
- h1_rows: `25608`
- h1_span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows_stage28d: `1534217`
- h1_rows_stage28d: `25608`
- m15_rows_stage28d: `102355`
- M1 rows used: `1534217` | span: `2022-05-01 23:01:00+00:00 → 2026-06-12 23:54:00+00:00`
- H1 rows used: `25608` | span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:00:00+00:00`
- M15 rows derived: `102355` | span: `2022-05-01 23:00:00+00:00 → 2026-06-12 23:45:00+00:00`

## Gate diagnostics

```json
{
  "events_before_gate_recent": 0,
  "events_before_gate_total": 99,
  "gate_basis": "event_by_event_expanding_prior_candidate_events",
  "gate_dropped_recent": 0,
  "gate_dropped_total": 56,
  "gate_kept_recent": 0,
  "gate_kept_total": 43,
  "gate_name": "stage28c_london_q60_prior_q25_expanding",
  "gate_retained_ratio_recent": 0.0,
  "gate_retained_ratio_total": 0.43434343434343436,
  "insufficient_calibration_count": 25,
  "london_range_quantile": 0.6,
  "lookback_hours": 336,
  "min_calib_events": 25,
  "missing_london_range": 0,
  "missing_prior_day_range": 0,
  "prior_day_range_quantile": 0.25
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

## Recent meta-gate tracked events

No rows.

## Meta-gate diagnostics in current lookback

No rows.

## Interpretation

- This tracker is research-shadow only; an open signal is not an order instruction.
- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after the outcome was already knowable; it is not forward proof.
- Stage28D tracks the Stage28C validated meta-gate, but forward evidence still has to be collected separately.
- The active operational suite remains unchanged until this tracker accumulates forward-valid outcomes.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage28d_forward_safe_meta_gate_tracker
```

## Output files

- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.json`
- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.md`
- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_meta_gate_forward_shadow_ledger.csv`
- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_recent_meta_gate_events.csv`
- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_meta_gate_diagnostics.csv`
- `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_db_schema_diagnostic.csv`
