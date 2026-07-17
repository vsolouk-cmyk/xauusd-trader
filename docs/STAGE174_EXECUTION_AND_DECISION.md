# Stage174 — H64L Contract Resolution and Track A Final Audit

## Purpose

Stage174 does not search for a new strategy. It closes the remaining Stage173 blockers by resolving the original H64L holding horizon and DXY source contract, then runs only the final historical-as-of H64L audit.

## Why Stage173 was not yet final

Stage173 correctly reconciled the WGC ETF feature and showed that the historical Stage64K ETF series matches the corrected semantics. It nevertheless treated all horizon references equally, causing direct Stage64R `120-day` evidence to be mixed with incidental `1` and `60` values. Stage174 applies an authority hierarchy rather than raw candidate counting.

DXY is resolved using two independent layers:

1. direct text/config/manifest evidence from Stage64K/64R artifacts;
2. numerical fingerprinting of candidate DXY series against `dxy_ret_20d` in the locked Stage64K dataset.

A generic file called `dxy.csv` is not sufficient by itself. Its semantic contract must be identified as ICE DXY or FRED DTWEXBGS.

## Hard controls

- No orders, demo, paper-order or live.
- No ML.
- No Track B rerun.
- No threshold or horizon scan.
- The horizon is selected only from authoritative archived contracts.
- Missing availability timestamps block the audit; Stage174 does not invent a lag.

## Final Track A classifications

- `KILL`: insufficient holdout episodes, non-positive cost-adjusted expectancy, or failure to beat both gold drift and a simple SMA20-over-SMA50 trend baseline.
- `OVERLAY_ONLY`: core edge gates pass, but opportunity frequency, drawdown or concentration does not support a primary generator.
- `SHADOW_CANDIDATE`: all gates pass. This remains log-only and is not an execution authorization.
- `INCONCLUSIVE_BLOCKED`: exact source/horizon/input contract remains unresolved.

## Primary outputs

- `stage174_summary.json`
- `stage174_decision.md`
- `stage174_horizon_contract_evidence.csv`
- `stage174_dxy_contract_evidence.json`
- `stage174_dxy_fingerprint_scores.csv`
- `stage174_h64l_episodes.csv` when the audit runs
- `stage174_simple_trend_baseline_episodes.csv` when the audit runs

## Expected next decision

If H64L is killed, the rescue path closes. The next permitted action is only a narrow, pre-written material-delta review of one genuinely unfinished thesis, currently the `high_sweep_continuation_long + H4/regime` candidate. It is not automatically authorized for testing.

If H64L is overlay-only, unattended observation can continue, but a primary trade generator is still required.
