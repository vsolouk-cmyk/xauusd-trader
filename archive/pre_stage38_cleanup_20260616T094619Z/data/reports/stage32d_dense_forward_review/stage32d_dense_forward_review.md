# XAUUSD Stage32D — Dense Forward Review / Tightening Plan

Generated UTC: 2026-06-16T09:41:49+00:00

## Decision

```text
DECISION = STAGE32D_HAS_PROMISING_LOW_N_DENSE_CANDIDATES_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_SHADOW_ONLY
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
PRIMARY_OBJECTIVE = TIGHTEN_DENSE_FORWARD_REVIEW_CANDIDATES_WITHOUT_COMMERCIAL_PROMOTION
```

## Why this stage exists

Stage32C found dense forward-shadow activity and at least one candidate reached the research review queue. Stage32D inspects that candidate and produces a tightening plan. It does not authorize EA, paper/live, or orders.

## Summary

```text
candidate_summary_rows = 9
ledger_rows = 188
diagnostic_rows = 9
reviewable_needs_extended_count = 0
extended_review_ready_count = 0
promising_low_n_count = 2
pause_or_repair_count = 4
min_review_signals = 20
extended_min_signals = 40
min_pf_x4 = 1.25
min_win_rate = 0.55
```

## Candidate diagnostics

| rank | candidate | family | signal_count | pf_x4 | avg_net_x4 | win_rate_x4 | tail_pf_x4 | max_drawdown_x4 | stage32d_decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 3.043089 | 2.243025 | 0.846154 | inf | -14.272175 | PROMISING_LOW_N_ACCELERATE_COLLECTION |
| 2 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 2.612842 | 2.174892 | 0.846154 | 1.734659 | -17.5303 | PROMISING_LOW_N_ACCELERATE_COLLECTION |
| 3 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 1.141681 | 0.297066 | 0.52 | 1.159715 | -17.73745 | REVIEW_FLAG_BUT_METRIC_WEAK_RECHECK |
| 4 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 1.298189 | 0.668022 | 0.684211 | 0.564206 | -30.683475 | KEEP_COLLECTING_OR_REPAIR_RESEARCH_ONLY |
| 5 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 0.933662 | -0.147248 | 0.541667 | 1.197193 | -18.9303 | KEEP_COLLECTING_OR_REPAIR_RESEARCH_ONLY |
| 6 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 22 | 0.843633 | -0.474349 | 0.6 | 0.327474 | -45.034175 | PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW |
| 7 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 25 | 0.817511 | -0.456615 | 0.5 | 0.417467 | -33.07835 | PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW |
| 8 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 0.748923 | -0.759812 | 0.615385 | 0.711997 | -18.840375 | PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW |
| 9 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 0.468069 | -2.119478 | 0.473684 | 0.779321 | -43.820675 | PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW |

## Tightening plan

| rank | candidate | family | signal_count | action | next_test | commercial_status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 15 | ACCELERATE_FORWARD_SAMPLE_COLLECTION | Keep in tracker; do not evaluate until minimum review sample count is reached. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 2 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 15 | ACCELERATE_FORWARD_SAMPLE_COLLECTION | Keep in tracker; do not evaluate until minimum review sample count is reached. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 3 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | KEEP_SECONDARY_COLLECTION | Continue collecting; not review-ready. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 4 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | KEEP_SECONDARY_COLLECTION | Continue collecting; not review-ready. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 5 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | DEMOTE_TO_REPAIR_OR_BACKGROUND | Do not consume primary attention until retested or repaired. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 6 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 22 | PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION | Move to repair queue; check direction inversion, hour suppression, and overlap with stronger variants. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 7 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 25 | PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION | Move to repair queue; check direction inversion, hour suppression, and overlap with stronger variants. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 8 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 15 | PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION | Move to repair queue; check direction inversion, hour suppression, and overlap with stronger variants. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |
| 9 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION | Move to repair queue; check direction inversion, hour suppression, and overlap with stronger variants. | RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE |

## Family action plan

| family | signal_count | reviewable_candidate_count | promising_low_n_count | negative_or_pause_count | recommendation |
| --- | --- | --- | --- | --- | --- |
| session_handoff_imbalance_v1 | 45 | 0 | 2 | 1 | ACCELERATE_COLLECTION_FOR_PROMISING_LOW_N_VARIANTS |
| calendar_time_risk_proxy_v1 | 79 | 0 | 0 | 1 | REVIEW_DENSE_FORWARD_CANDIDATES |
| volatility_transition_v1 | 64 | 0 | 0 | 2 | KEEP_COLLECTING_FORWARD_SAMPLES |

## Operational interpretation

```text
1. A Stage32C review flag is not a commercial transition gate.
2. The current fast path is extended dense shadow on the best candidate while suppressing weak sibling variants.
3. Do not start EA/paper/live/order routing from this stage.
4. If the leading candidate survives extended shadow, the next stage should be a pre-commercial robustness gate.
```

## Output files

- `data/reports/stage32d_dense_forward_review/stage32d_dense_forward_review.md`
- `data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv`
- `data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv`
- `data/reports/stage32d_dense_forward_review/dense_family_action_plan.csv`
- `data/reports/stage32d_dense_forward_review/stage32d_summary.json`
