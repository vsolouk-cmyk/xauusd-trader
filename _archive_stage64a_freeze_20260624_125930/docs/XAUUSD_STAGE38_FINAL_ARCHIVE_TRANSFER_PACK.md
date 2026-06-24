# XAUUSD Stage38 Final Archive Transfer Pack

## Purpose

This transfer pack closes Stage38 after the drift-adjusted survivor audit. It should be used to start a clean new session without losing technical continuity.

## Standing project rules

- Keep responses left-aligned.
- Minimize back-and-forth.
- When the next technical step is clear, provide files and copy-ready terminal commands.
- Use `mv` from Downloads to the repository, not `cp`.
- Keep session size under control; create transfer packs when the session becomes heavy.
- No Stage39/EA/paper-live/live promotion unless a candidate survives strict benchmark, cost, robustness, and forward-shadow requirements.
- Current state: no candidate has survived.

## Repository and environment

```text
repo = ~/Desktop/xauusd-trader
db = data/local/xauusd_local_store.sqlite
main bars table = bars
source = amarkets_mt5
symbol = XAUUSD
primary timeframe = H1
```

Known data coverage:

```text
H1 AMarkets rows = 25,643
H1 date range = 2022-05-01T23:00:00Z → 2026-06-16T12:00:00Z
M1 source exists and was used to derive M5/M15
M5/M15/H1 availability after derivation = PASS
```

## Stage38 final decision

```text
STAGE38_ACTIVE_RESEARCH = ARCHIVE
STAGE38_TO_STAGE39_PROMOTION = NO-GO
EA = NO-GO
PAPER_LIVE = NO-GO
LIVE = NO-GO
```

## Stage-by-stage summary

### Stage38A / T1 structural filter retest

Result:

```text
T1 = LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
promotion = NO-GO
```

T1 did not provide robust multi-year evidence and remained 2025-dominated.

### Stage38B / COT data and T3 overlays

Completed:

- official CFTC COT gold weekly data foundation,
- normalized COT loader,
- anti-lookahead H1 join,
- T3 COT feature states,
- standalone COT diagnostic,
- COT x T1 interaction diagnostic,
- restricted overlay gate.

Decision:

```text
COT_DATA_FOUNDATION = KEEP
COT_SIGNAL_PROMOTION = NO-GO
COT_OVERLAY = MARGINAL / CONTEXT_ONLY
```

COT remains useful as context/annotation only.

### Stage38C / H1 simple baseline lab

Result:

```text
H1 simple baseline candidates = weak
ASIA_RANGE_BREAKOUT = low-confidence / 2025-dominated
promotion = NO-GO
```

### Stage38D / M5/M15 session baseline

Completed:

- M5/M15 derived from M1,
- M5/M15 availability audit passed,
- session baseline lab,
- deep diagnostics.

Final candidate:

```text
D1_M5_ASIA_RANGE_BREAKOUT_LONG_FIRST_48
mean = +2.41 bps
pre2025 = +0.60 bps
first_half = negative
promotion = NO-GO
```

Decision:

```text
Stage38D = ARCHIVE
```

### Stage38E / FRED macro-risk foundation

Completed:

- FRED public CSV download without API key,
- series: DGS10, DGS2, DFII10, T10YIE, DTWEXBGS, VIXCLS,
- daily macro/risk features,
- anti-lookahead H1 join,
- macro context diagnostic,
- era recheck,
- macro pass-candidate gate.

Final gate decision:

```text
MACRO_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION
```

Macro remains useful as context/annotation only.

### Stage38F / SPDR GLD ETF data foundation

Completed:

- SPDR GLD Historical Archive source availability,
- workbook parse audit,
- GLD daily loader,
- GLD flow/holding features,
- anti-lookahead H1 join,
- GLD context diagnostic,
- GLD pass-candidate gate.

GLD data foundation passed:

```text
parsed_rows = 5,425
daily_rows_written = 5,425
feature_rows_written = 5,425
h1_joined_count = 25,643 / 25,643
lookahead = 0
date_range = 2004-11-18 → 2026-06-15
```

Final GLD gate decision:

```text
GLD_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION
```

Best event-clock residual before drift adjustment:

```text
BLOCK_FLOW_20D_OUTFLOW / 120H
stage uplift = +7.37 bps
```

### Stage38G / Composite exogenous overlay gate

Inputs:

- COT,
- macro/risk,
- GLD.

Result:

```text
COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION
```

Best composite uplift:

```text
24H best uplift ≈ +0.50 bps
72H best uplift ≈ +2.19 bps
120H best uplift ≈ +4.28 bps
```

Composite did not improve enough over GLD-only.

### Stage38H / Bull drift and tradability audit

Result:

```text
BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION
```

Drift references:

```text
Daily anchor:
24H  = +7.24 bps
72H  = +23.04 bps
120H = +38.85 bps

H1 all overlapped:
24H  = +8.50 bps
72H  = +25.00 bps
120H = +41.35 bps
```

Important year close-to-close drift:

```text
2022 = -392.22 bps
2023 = +1312.76 bps
2024 = +2711.31 bps
2025 = +6438.02 bps
2026 YTD = -9.73 bps
```

Conclusion: many positive forward-return results are mostly explained by bull drift, especially 2025.

### Stage38I / Drift-adjusted survivor audit

Result:

```text
status = PASS
decision = DRIFT_ADJUSTED_WATCH_ONLY_NO_PROMOTION
strict_pass_count = 0
watch_count = 2
context_only_watch_count = 31
no_promotion_count = 126
```

Only two event-clock survivors remained, both weak:

```text
Stage38F_GLD_GATE / BLOCK_FLOW_20D_OUTFLOW / 120H
raw_mean = +55.55 bps
event_clock = +44.92 bps
drift_reference = +38.85 bps
drift_adjusted = +6.07 bps
stage_uplift = +7.37 bps
survivor_decision = WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY

Stage38F_GLD_GATE / BLOCK_FLOW_20D_OUTFLOW / 72H
raw_mean = +32.60 bps
event_clock = +26.37 bps
drift_reference = +23.04 bps
drift_adjusted = +3.33 bps
stage_uplift = +4.67 bps
survivor_decision = WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY
```

No strict pass.

## Final conclusion

Stage38 produced valuable data foundations and diagnostic infrastructure but no tradable candidate. It should be archived, not extended with more filters.

## Useful retained assets

Keep these as future context inputs:

```text
cot_gold_weekly
cot_gold_features
cot_gold_h1_features_joined
stage38e_macro_risk_daily_features
stage38e_macro_risk_h1_joined
stage38f_spdr_gld_daily
stage38f_spdr_gld_features
stage38f_spdr_gld_h1_joined
stage38h_bull_drift_summary
stage38i_drift_adjusted_survivor_items
```

## What not to do next

Do not:

- promote Stage38 to EA,
- start paper-live,
- create Telegram trade alerts,
- add more filters to Stage38 candidates,
- overfit the two weak watch-only residuals,
- treat context-only residuals as signal candidates without event-clock gate.

## Suggested next branch

Start a clean, benchmark-first branch. A suitable label is:

```text
Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN
```

Important: this is only a research-stage label. It is not Stage39 in the sense of EA/paper/live readiness.

Rationale:

- Long drift is already strong, so long-only continuation edges must beat drift.
- A more promising direction may be benchmarked reversal/mean-reversion after extreme moves, spread stress, or unfavorable drift-adjusted contexts.
- Any new candidate must be evaluated against:
  - daily anchor drift,
  - H1 all drift,
  - year split,
  - 2025 exclusion,
  - leave-one-year-out,
  - cost stress,
  - MAE/MFE tradability,
  - event-clock opportunity cost.

## Prompt for next session

Paste this in the new session:

```text
چپ‌چین ادامه بده. این بسته انتقالی پروژه XAUUSD بعد از Stage38I است. Stage38 کامل archive شد: COT، macro، GLD و composite overlays فقط context/annotation هستند و هیچ candidateای بعد از drift-adjusted survivor audit strict pass نگرفت. Stage39/EA/paper-live/live همچنان NO-GO است. اگر تایید می‌کنی، گام بعدی را با Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN شروع کن، اما فقط به‌عنوان research-stage، نه promotion. فایل و دستور آماده بده، بدون سؤال اضافه.
```

## Commit command

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Archive Stage38 after drift-adjusted survivor audit"
git pull --rebase origin main
git push
```
