# Stage166 Current Event Shock Overlay

## Decision

Stage166 is a corrective commercial stage, not another low-frequency thesis scan.

The recurring project failure mode is now treated as a hard design constraint:

- low-frequency candidate rules,
- weak or unstable edge quality,
- waiting for more forward samples,
- then pivoting after too much time.

Stage166 therefore introduces a high-cadence current-event/news-shock overlay that can be used by the next discovery stage as a regime feature, permission filter, blackout filter, or shock context. It is not an execution signal and it does not authorize demo/live orders.

## Why this stage exists

The prior macro/fundamental pipeline covers scheduled and structured data, but it is incomplete for gold because gold reacts strongly to unscheduled geopolitical, military, sanctions, energy, and safe-haven shocks.

The missing dimension is not merely “news text.” It is a time-indexed, scored current-event pressure panel that can be joined to M5/M15/M30/H1 bars and used in discovery.

## What the patch adds

File added:

- `app/stage166_current_event_shock_overlay.py`

Documentation added:

- `docs/STAGE166_CURRENT_EVENT_SHOCK_OVERLAY.md`

Outputs written at runtime:

- `reports/stage166_current_event_shock_overlay/stage166_current_event_shock_overlay_summary.json`
- `reports/stage166_current_event_shock_overlay/stage166_normalized_current_events.csv`
- `reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv`
- `reports/stage166_current_event_shock_overlay/stage166_current_event_daily_panel.csv`
- `reports/stage166_current_event_shock_overlay/stage166_current_event_overlay_config.json`
- `reports/stage166_current_event_shock_overlay/stage166_holdout_map.json`
- `reports/stage166_current_event_shock_overlay/stage166_fetch_status.json`

## Data inputs

Defaults match the project memory:

- root: `~/Desktop/xauusd-trader`
- event inbox: `~/Downloads/xauusd_fundamental_event_inbox`
- broker M5: `~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv`

The stage reads local files from the event inbox and can optionally fetch fresh GDELT DOC article lists with `--fetch-gdelt`.

## Scoring model

Stage166 uses deterministic transparent keyword buckets, not a black-box model:

- `geopolitical_escalation_score`
- `deescalation_score`
- `macro_policy_hawkish_score`
- `macro_policy_dovish_score`
- `inflation_energy_shock_score`
- `gold_direct_score`

It then derives:

- `gold_long_pressure`
- `gold_short_pressure`
- `shock_abs`
- `event_side_bias`
- `event_shock_regime`

The panel can mark:

- `EVENT_SAFE_HAVEN_LONG_PRESSURE`
- `EVENT_RISK_ON_OR_HAWKISH_SHORT_PRESSURE`
- `EVENT_VOLATILITY_SHOCK_NO_DIRECTION`
- `EVENT_NEUTRAL`

## Holdout policy

Stage166 writes a strict newest-20% holdout map from M5 bars:

- training segment: oldest 80%
- holdout segment: newest 20%

The next stage must not tune on the holdout segment. It can only evaluate final candidate behavior there.

## Commercial rule

Do not solve low frequency by waiting.

The next discovery stage should prefer one of these paths:

1. event overlay as a permission filter for existing medium-frequency technical candidates,
2. event overlay as a blackout/risk-expansion filter around shock windows,
3. intraday technical rule discovery conditioned on current-event regime,
4. rejection of candidates that remain low-frequency and weak after event conditioning.

## Recommended next stage

Stage167 should be:

`Stage167_EVENT_AWARE_MEDIUM_FREQUENCY_DISCOVERY_AND_HOLDOUT_GATE`

Required behavior:

- read Stage166 intraday and daily event panels,
- join to M5/M15/M30/H1 broker bars,
- reserve newest 20% as locked holdout,
- scan event-aware medium-frequency rules,
- reject rules that rely on rare event spikes only,
- output only candidates that pass cost-aware holdout and frequency minimums,
- still do not release demo orders unless gate metrics justify it.

## Safety

Stage166 is read-only:

- `order_routing_allowed = false`
- `demo_release_allowed = false`

It is a data/feature gate for discovery, not a trading executor.
