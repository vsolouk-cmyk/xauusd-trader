# XAUUSD Stage38 Transfer Pack After Exogenous Overlay Path

## Purpose

This package transfers the current XAUUSD/gold research state into a new session after completing Stage38A through Stage38G.

The current session has become long and the exogenous-overlay branch has reached a clear stopping point. Continue in a fresh session using this file as the primary context.

## Project operating rules

- Always continue left-aligned.
- Minimize unnecessary back-and-forth.
- When the next technical step is clear, provide ready-to-copy files and commands directly.
- Use `mv` from Downloads to repo, not `cp`.
- Use safe git commands only.
- Data-quality-first.
- Baseline-first.
- Kill weak paths quickly.
- No ML before simple baselines pass.
- No Stage39, EA, paper-live or live work unless a later phase explicitly promotes a robust candidate after strict review and forward shadow.

## Local environment

```text
Local repo: ~/Desktop/xauusd-trader
Database: data/local/xauusd_local_store.sqlite
Primary bars table: bars
Main source: amarkets_mt5
Main symbol: XAUUSD
Primary H1 candle range: 2022-05-01T23:00:00Z to 2026-06-16T12:00:00Z
H1 rows: 25,643
M1 rows: ~1,536,273
Derived M5 rows: 307,334
Derived M15 rows: 102,493
```

## Global trading/production status

```text
Stage39 = NO-GO
EA = NO-GO
MT5 live/paper execution = NO-GO
Telegram trade alerts = NO-GO
ML = NO-GO
```

Everything so far is research/data diagnostics only.

---

# Completed stages

## Stage38A / T1 structural candidate

Final label:

```text
LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
```

Key result:

- Candidate had some positive signs but was 2025-dominated.
- Not promotable.
- No Stage39.
- No EA/paper/live.

## Stage38B / COT data foundation and T3 COT diagnostics

Data foundation:

```text
COT weekly data loaded successfully
Rows: 910
Date range: 2009-01-06 to 2026-06-09
H1 anti-lookahead join: PASS
Joined H1 rows: 25,643 / 25,643
Lookahead violations: 0
```

Diagnostics:

- COT standalone context showed some positive slices but low sample/year concentration.
- COT x T1 interaction did not produce reliable synergy.
- Restricted overlay retest showed only marginal value.

Final label:

```text
COT_DATA_FOUNDATION_KEEP
COT_STRATEGY_OR_OVERLAY_PROMOTION = NO-GO
```

## Stage38C / H1 simple baseline lab

Main candidates:

- ASIA_RANGE_BREAKOUT H1 24H
- ATR_EXP_CONT_T1P5

Findings:

- ASIA range H1 had small positive mean but weak pre-2025 and 2025/2026 dominance.
- Direction split showed long side better than short side, but event-clock filter uplift was marginal.

Final label:

```text
H1_SIMPLE_BASELINE_LOW_CONFIDENCE_RESEARCH_ONLY
NO_PROMOTION
```

## Stage38D / M5/M15 session baseline

Data work:

- M5 and M15 derived from M1 successfully.
- M1/M5/M15/H1 all passed availability audit.

Baseline results:

- Only weak WATCH candidate survived: `D1_M5_ASIA_RANGE_BREAKOUT_LONG_FIRST_48`.
- Deep diagnostics result:

```text
mean = +2.41 bps
median = +0.59 bps
win_rate = 0.509
t-stat = 1.66
pre2025 = +0.60 bps
first_half = -0.36 bps
note = WEAK_FIRST_HALF_LT_0_5BPS
```

Final label:

```text
LOW_CONFIDENCE_RESEARCH_ONLY
ARCHIVE_OR_PIVOT
NO_PROMOTION
```

## Stage38E / Macro-risk data foundation and macro context diagnostics

Data foundation:

FRED series:

```text
DGS10
DGS2
DFII10
T10YIE
DTWEXBGS
VIXCLS
```

Loader/audit:

```text
series_pass_count = 6 / 6
daily_feature_rows = 6,901
h1_joined_count = 25,643 / 25,643
lookahead_violation_count = 0
```

Macro context diagnostics:

- Initial diagnostic had year-split issue.
- Era recheck fixed it.
- Some macro contexts passed separation watch.
- Event-clock pass-candidate gate did not promote.

Macro gate key results:

```text
LONG_PERMITTED_EXCLUDE_HOSTILE_OR_RISK_ELEVATED
72H uplift = +1.74 bps
120H uplift = +2.65 bps
```

Final label:

```text
MACRO_DATA_FOUNDATION_KEEP
MACRO_CONTEXT_KEEP_AS_ANNOTATION
MACRO_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION
```

## Stage38F / SPDR GLD ETF holdings/flow data foundation and diagnostics

Source audit:

- WGC page available.
- One WGC XLSX passed, one WGC XLSX returned 403.
- SPDR Historical Archive XLSX passed.
- Parser selected SPDR GLD as first usable source.

GLD loader:

```text
parsed_rows = 5,425
daily_rows_written = 5,425
feature_rows_written = 5,425
h1_joined_count = 25,643 / 25,643
lookahead = 0
date_range = 2004-11-18 to 2026-06-15
```

GLD feature diagnostic:

- Stronger than COT and macro diagnostics.
- Multiple context slices passed separation watch.
- Examples:

```text
ETF_STRONG_OUTFLOW / 120H: mean +80.90 bps, diff_vs_all +43.34 bps
ETF_STRONG_INFLOW / 120H: mean +71.64 bps, diff_vs_all +34.09 bps
FLOW_5D_INFLOW / 120H: mean +67.05 bps, diff_vs_all +29.49 bps
```

GLD event-clock gate:

- No promotion.
- Best avoid-long gate:

```text
BLOCK_FLOW_20D_OUTFLOW / 120H
trade_mean = +55.55 bps
event_clock_mean = +44.92 bps
baseline_event_clock_mean = +37.56 bps
uplift = +7.37 bps
```

Final label:

```text
GLD_DATA_FOUNDATION_KEEP
GLD_CONTEXT_KEEP_AS_ANNOTATION_OR_COMPOSITE_INPUT
GLD_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION
```

## Stage38G / Composite exogenous overlay gate

Combined sources:

- COT
- Macro/risk
- GLD holdings/flows

Audit result:

```text
status = PASS
decision = COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION
gld_rows_loaded = 25,643
event_count = 1,035
events_written = 30,960
summary_rows_written = 30
pass_count = 0
watch_count = 20
no_promotion_count = 7
warning_count = 0
```

Key event-clock outcomes:

```text
24H baseline = +7.27 bps
Best 24H uplift = +0.50 bps

72H baseline = +21.71 bps
Best 72H uplift = +2.19 bps

120H baseline = +37.56 bps
Best 120H uplift = +4.28 bps
```

Most important 120H policy:

```text
BLOCK_GLD_ETF_OR_FLOW20_OUTFLOW
trade_count = 787
trade_mean = +54.76 bps
event_clock_mean = +41.84 bps
baseline_event_clock_mean = +37.56 bps
uplift = +4.28 bps
decision = WATCH_COMPOSITE_OVERLAY_GATE
note = LOW_EVENT_CLOCK_UPLIFT_LT_5BPS
```

Supportive-only policies had good trade means but poor event-clock accounting:

```text
LONG_ONLY_GLD_SUPPORTIVE / 120H
trade_mean = +77.18 bps
event_clock_mean = +24.65 bps
uplift = -12.90 bps

LONG_ONLY_GLD_SUPPORTIVE_AND_MACRO_NOT_HOSTILE / 120H
trade_mean = +103.21 bps
event_clock_mean = +22.85 bps
uplift = -14.71 bps
```

Final label:

```text
COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION
```

---

# Current strategic conclusion

The project now has strong exogenous data foundations:

- COT weekly positioning.
- FRED macro/risk daily features.
- SPDR GLD ETF holdings/flow daily features.
- Anti-lookahead joins to H1.

But no tested exogenous overlay has produced enough event-clock improvement to promote a baseline.

The main repeated pattern:

```text
Subset/trade mean can look good.
Event-clock uplift remains too weak after skipped events are counted.
```

Therefore:

```text
No exogenous-only strategy.
No composite exogenous overlay promotion.
Keep these datasets as context/annotation/features for later research only.
```

---

# Recommended next session direction

The next session should not continue brute-force exogenous overlays.

Recommended next options, in priority order:

## Option A — Gold drift decomposition / tradability audit

Goal:

Determine whether the positive forward returns observed in many diagnostics are mostly secular gold bull drift rather than tradable edge.

Why:

Many baselines and context groups show positive 72H/120H forward return, but event-clock overlays fail to outperform baseline materially.

Suggested stage:

```text
Stage38H_BULL_DRIFT_AND_TRADABILITY_AUDIT
```

Core diagnostics:

- Buy-and-hold / always-long drift by year and month.
- Forward-return distribution by year.
- Overlap-adjusted event-clock drift.
- Regime separation: pre-2025 vs 2025 vs 2026.
- Check whether apparent edge disappears after subtracting year/month drift.

## Option B — Reversal after exogenous disagreement extremes

Goal:

Only test a small number of pre-declared thesis-driven cases where GLD/macro/COT disagree sharply.

Examples:

- GLD strong outflow but price remains strong.
- Macro hostile but gold does not fall.
- COT crowded long but price still breaks higher.

Constraint:

No broad search; only a few explainable hypotheses.

## Option C — Stop research and prepare operational monitor only

Goal:

Keep collecting data and producing context reports, but do not try to force a strategy until a clearer thesis appears.

This is conservative and commercially safer.

---

# Recommended immediate next step

Start a new session and paste this transfer pack.

Suggested first message in the new session:

```text
چپ‌چین ادامه بده. این بسته انتقالی پروژه XAUUSD بعد از Stage38G است. لطفاً آن را مبنا قرار بده. مسیر exogenous-overlay promotion بسته شد و Stage39/EA/paper/live همچنان NO-GO است. اگر تایید می‌کنی، گام بعدی را با Stage38H_BULL_DRIFT_AND_TRADABILITY_AUDIT شروع کن و فایل/دستور آماده بده، بدون سؤال اضافه.
```

## Git commands after moving final docs/scripts

After saving the final review and transfer pack:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Archive Stage38G exogenous overlay and add transfer pack"
git pull --rebase origin main
git push
```
