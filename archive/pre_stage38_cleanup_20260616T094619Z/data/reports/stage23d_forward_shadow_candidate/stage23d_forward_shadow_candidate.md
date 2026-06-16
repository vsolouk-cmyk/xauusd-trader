# Stage23D Forward-Shadow Candidate Tracker

Generated UTC: 2026-06-16T09:39:45+00:00

## Decision

```text
STAGE23D_NO_ACTIVE_FORWARD_SIGNAL_RESEARCH_ONLY
```

## Scope guardrails

- Research/shadow only.
- Stage18A v2 remains the active operational forward-shadow runner.
- No EA change, no automatic trading, no paper/live/order authorization.
- Stage23D tracks one de-duplicated Stage23B/Stage23C candidate separately; it does not add it to Stage18A.

## Tracked candidate

- Candidate: `S23D_PRIMARY_S23B_B_eff0.60_pb0.1_h180_tp0.6_sl0.65`
- Family: `london_oneway_continuation`
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
- h1_mode: `db_schema_introspection`
- db_first: `True`
- csv_fallback_enabled: `False`
- M1 rows used: `1536273` | span: `2022-05-01 23:01:00+00:00 → 2026-06-16 12:18:00+00:00`
- H1 rows used: `25643` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:00:00+00:00`
- M15 rows derived: `102493` | span: `2022-05-01 23:00:00+00:00 → 2026-06-16 12:15:00+00:00`
- Lookback hours: 336
- Roundtrip cost x1: 0.35

## Run counters

- new_signal_count: 0
- new_forward_open_count: 0
- new_late_backfill_count: 0
- newly_resolved_forward_count: 0
- recent_events_found_in_lookback: 0
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

## Recent tracked events

No rows.

## Interpretation

- An open signal here is still research/shadow-only; it is not an order instruction.
- `LATE_DETECTED_ALREADY_RESOLVED` means the signal was first seen after its outcome was already knowable from SQLite candle history; do not count it as forward proof.
- `FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME` is the useful state for collecting forward-shadow evidence.
- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled in this module.
- Keep Stage18A v2 running separately after each AMarkets CSV refresh/import cycle.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Output files

- `data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.json`
- `data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md`
- `data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_ledger.csv`
- `data/reports/stage23d_forward_shadow_candidate/stage23d_recent_events.csv`
- `data/reports/stage23d_forward_shadow_candidate/stage23d_db_schema_diagnostic.csv`
