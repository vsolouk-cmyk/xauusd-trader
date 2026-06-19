# Stage48A Structural Thesis Decision Gate

Generated UTC: `2026-06-19T05:34:38.526837+00:00`

## Status

```text
stage = Stage48A_STRUCTURAL_THESIS_DECISION_GATE
status = DECISION_COMPLETE_NO_TRADING_SCAN_RECOMMENDED
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = STAGE48B_EXECUTION_REALISM_AND_DATA_SOURCE_FEASIBILITY_PRECHECK
```

## Locked prior state

- Stage46 external-context branch is archived with no promotion.
- Stage47B liquidity-sweep reversal is archived with no promotion.
- Stage47C audit is not allowed because Stage47B produced zero strict and zero soft survivors.

## Evidence carried into Stage48A

```text
Stage47B rows_loaded = 25,905
Stage47B trade_count = 2,658
Stage47B candidate_count = 27
Stage47B strict_survivor_count = 0
Stage47B soft_survivor_count = 0
numeric spread available = false
cost_bps assumption = 8.0
```

The Stage47B rerun was large enough to reject promotion. It also showed that the pipeline can process a realistic 90-day M5 history, so the failure is not primarily a loader failure. However, the data still lacks broker-real bid/ask spread, real execution conditions, and scheduled event labels.

## Decision

```text
DO_NOT_START_ANOTHER_CANDLE_ONLY_RULE_SCAN
```

A new scan based only on OHLC/session candles is not recommended. After multiple cost-aware rule branches have failed, another candle-only thesis would likely drift into post-hoc filter search rather than a genuinely new structural thesis.

## Candidate thesis review

| candidate_id | idea | verdict | reason |
|---|---|---|---|
| S48_CAND_A_EVENT_ANCHORED_SHOCK_RESPONSE | Macro-news shock follow-through/fade around event timestamps | DEFER_NOT_SCANNABLE_WITH_CURRENT_DATA | Requires reliable event timestamps and labels |
| S48_CAND_B_BROKER_SPREAD_MICROSTRUCTURE_GATE | Use real broker bid/ask spread/session spread as primary gate | VALID_DATA_PRECHECK_NOT_TRADING_SCAN | Cost-overwhelm has dominated failures, but bid/ask/MT5 collection is required first |
| S48_CAND_C_CFD_REFERENCE_FEED_DIVERGENCE | Broker CFD feed vs REST/reference feed divergence | DEFER_REQUIRES_MULTI_FEED_DATA | Requires synchronized broker and reference feed |
| S48_CAND_D_CANDLE_ONLY_VOL_COMPRESSION_EXPANSION | OHLC compression-to-expansion breakout/reversal | REJECT_TOO_CLOSE_TO_PRIOR_BASELINES | Too close to prior ATR/range/session candle-only families |

## Recommended next step

```text
Stage48B_EXECUTION_REALISM_AND_DATA_SOURCE_FEASIBILITY_PRECHECK
```

Stage48B should not scan a trading thesis. It should answer whether the project can collect the data necessary for a genuinely different next phase:

1. MT5/broker M1/M5 OHLC with bid/ask spread or tick-derived spread.
2. Session-tagged spread distribution.
3. Rollover/spread spike detection.
4. Compatibility between broker feed and current TwelveData reference feed.
5. Optional event-calendar timestamps for macro-news shock studies.

Only after Stage48B passes should a new Stage48C/Stage49 structural scan be considered.

## Hard prohibitions

- No rescue of Stage41/42/43/46/47B candidates.
- No post-hoc bad bucket filtering after observed failures.
- No ML before a robust cost-aware rule baseline survives.
- No EA, paper-live, or live.
- No new candle-only scan unless Stage48A is explicitly revised with a genuinely new, pre-defined structural rationale.

## Operational interpretation

The project is not dead, but the current research mode should shift from signal discovery to execution-realism data validation. The strongest unresolved question is whether the apparent edge failures are partly caused by missing real spread/slippage structure, or whether XAUUSD candle-only baselines simply do not offer enough robust edge under realistic costs.
