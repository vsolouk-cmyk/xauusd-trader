# Stage170 Non-News Commercial Alpha Rebuild

## Purpose

Stage168/169 killed GDELT/news as an independent execution alpha. Stage170 returns commercial discovery to non-news intraday XAUUSD behavior while keeping GDELT/news only as a guard/context input.

## Safety

- Read-only research stage.
- Does not write MT5 signal/KV files.
- `order_routing_allowed=false`.
- `demo_release_allowed=false`.
- Any positive shortlist still requires Stage171 execution replay before demo release.

## What is scanned

Stage170 scans non-news intraday rule families:

- `TREND_MOMENTUM`
- `MOMENTUM_FADE`
- `RANGE_BREAKOUT`
- `WICK_REVERSAL`
- `ASIA_RANGE_BREAKOUT`

It evaluates multiple sessions, horizons, sides, and event guard policies.

## Event/news role

Event/news is not an entry alpha in this stage. It is used only as guard/context through policies:

- `NONE`
- `EXCLUDE_HIGH_EVENT`
- `EXCLUDE_OPPOSING_EVENT`

This preserves Stage169's verdict: GDELT/news is useful for current-regime awareness, not for independent execution discovery.

## Output

Reports are written to:

`reports/stage170_non_news_commercial_alpha_rebuild/`

Key files:

- `stage170_non_news_commercial_alpha_rebuild_summary.json`
- `stage170_commercial_shortlist.csv`
- `stage170_decision.md`
- `stage170_all_rule_scores.csv`
- `stage170_top_rule_trades.csv`

## Decision logic

If shortlist is positive:

`STAGE170_NON_NEWS_COMMERCIAL_CANDIDATES_FOUND_REQUIRES_STAGE171_EXECUTION_REPLAY`

If shortlist is zero:

`STAGE170_NO_NON_NEWS_COMMERCIAL_HOLDOUT_CANDIDATE_REDESIGN_OR_KILL_TECH_RULESPACE`

No demo/live release is allowed from Stage170 output alone.
