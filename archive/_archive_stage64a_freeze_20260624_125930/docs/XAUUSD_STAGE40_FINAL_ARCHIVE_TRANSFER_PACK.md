# XAUUSD / Gold Research Transfer Pack — After Stage40 Final Archive

Date: 2026-06-17
Project repo: `~/Desktop/xauusd-trader`
DB: `data/local/xauusd_local_store.sqlite`
Main table: `bars`
Source / symbol / timeframe: `amarkets_mt5 / XAUUSD / H1`
Loaded H1 range used in latest audits: `2022-05-01T23:00:00Z` to `2026-06-16T12:00:00Z`
Loaded H1 rows: `25,643`

## Standing response / workflow preferences

- پاسخ‌ها در پروژه XAUUSD/gold باید با این عبارت شروع شوند: `چپ‌چین ادامه می‌دهم.`
- پاسخ‌ها فارسی، ساده، فنی و بدون wrapper راست‌چین/HTML باشند.
- کد و مسیرها فقط داخل code block بیایند.
- اگر پچ یا فایل دانلودی داده می‌شود، همراه آن دستور آماده انتقال از Downloads به ریپو با `mv` داده شود، نه `cp`.
- وقتی گام بعدی روشن است، سؤال تأییدی غیرضروری پرسیده نشود؛ پچ/فایل و دستورات اجرایی مستقیم داده شود.
- هر پچ باید documentation همراه خودش داشته باشد.
- آخر پیام‌های اجرایی باید «گام بعدی» مشخص و عملیاتی داشته باشد.
- هدف پروژه رسیدن به سیستم قابل اتکا و تجاری است، نه طولانی کردن پژوهش؛ ولی promotion بدون شواهد پایدار ممنوع است.

## Global project gate

Current state after Stage40B:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

No candidate from Stage38, Stage39, or Stage40 may be promoted. No Telegram trade alert, EA/paper-live/live, or execution layer should be built from these archived branches.

## Stage38 final status

Stage38 was archived before Stage39.

Key conclusion:

```text
Stage38 = ARCHIVE
strict_pass_count = 0
promotion = NO_GO
```

Important context:

- COT, macro, GLD, and composite overlays remained context/annotation only.
- No Stage38 candidate survived strict drift-adjusted survivor audit.
- Stage38 should not be rescued by adding more filters.

Existing transfer file in this session:

```text
/mnt/data/XAUUSD_STAGE38_FINAL_ARCHIVE_TRANSFER_PACK.md
```

## Stage39 summary — Reversal / mean-reversion branch

Stage39 tested benchmark-first reversal/mean-reversion logic and progressively audited survivors.

### Stage39A

Stage:

```text
Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN
```

Result:

```text
strict_research_watch_count = 4
soft_watch_count = 2
promotion = NO_GO
```

Strict research-watch rows from Stage39A:

```text
BB_LOWER_REV_LONG_W120_K2.5
RANGE_BOTTOM_REV_LONG_W48_Q0.05
RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5
BB_LOWER_REV_LONG_W24_K2
```

### Stage39B

Stage39B path/tradability audit reduced the valid watch list.

Result:

```text
PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION = 2
WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION = 2
promotion = NO_GO
```

Remaining research-watch rows after Stage39B:

```text
BB_LOWER_REV_LONG_W120_K2.5
RANGE_BOTTOM_REV_LONG_W48_Q0.05
```

### Stage39C

Stage39C microstructure/session-condition diagnostic found condition buckets, but all remained research-only.

Important surviving theme:

```text
RANGE_BOTTOM_REV_LONG_W48_Q0.05
```

Key condition buckets included Monday, London session, prior_ret72 regimes, and trigger severity buckets, but these were not promotion signals.

### Stage39D

Stage39D condition robustness/forward split audit found:

```text
STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION = 5
FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION = 3
FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION = 1
```

### Stage39E

Stage39E frozen-rule OOS audit found:

```text
STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION = 5
FROZEN_OOS_WATCH_ONLY_NO_PROMOTION = 1
FAIL_FROZEN_OOS_NO_PROMOTION = 2
```

But warning signs appeared: recent/OOS segments were much stronger than train/early segments.

### Stage39F

Stage39F recency bias and rule stability audit was decisive:

```text
strict_stable_frozen_watch_count = 0
recency_biased_watch_count = 6
classification = RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39 final decision:

```text
Stage39A-F = ARCHIVE
Stage39G filter extension = NOT_ALLOWED
```

Rules that must not be rescued with additional filters:

```text
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS
RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA
```

Archive patch created in previous session:

```text
stage39_final_archive_after_stage39f_patch.zip
```

## Stage40 summary — Parallel thesis megascan branch

Stage40 was created to reduce back-and-forth by scanning multiple independent theses in parallel.

Stage:

```text
Stage40_PARALLEL_THESIS_MEGASCAN
```

Families scanned:

```text
40A_FALSE_BREAKOUT_SWEEP_REVERSAL
40B_VOLATILITY_COMPRESSION_EXPANSION
40C_SESSION_TRANSITION_IMBALANCE
40D_FAILED_CONTINUATION_AFTER_EXTREME_MOVE
40E_PULLBACK_CONTINUATION_AFTER_TREND
40F_VOLATILITY_SHOCK_REVERSAL
```

Megascan result:

```text
candidate_rows = 304
events_rows_written = 48,248
STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION = 1
SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION = 4
FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY = 259
INSUFFICIENT_EVENTS_RESEARCH_ONLY = 40
promotion = NO_GO
```

Only strict survivor from Stage40 megascan:

```text
family = VOL_COMPRESSION_EXPANSION
candidate = VOL_COMP_EXP_LONG_L120_Q0.15_M2.0
side = LONG
horizon = 72H
```

Important Stage40 megascan metrics for that survivor:

```text
event_clock_n = 88
cost_stressed_mean_bps ≈ +45.20
h1_benchmark_cost_adjusted_residual_bps ≈ +20.20
train_cost_mean_bps ≈ +37.78
oos_cost_mean_bps ≈ +59.56
median_mae_bps ≈ -84.30
touch_stop_100bps_pct ≈ 44.32
worst_quarter_cost_mean_bps ≈ +3.89
worst_quarter_slip16_mean_bps ≈ -12.11
```

Soft rows existed but were not eligible for continuation.

## Stage40B summary — survivor path stability audit

Stage40B audited only the strict Stage40 survivor.

Stage:

```text
Stage40B_SURVIVOR_PATH_STABILITY_AUDIT
```

Result:

```text
classification = FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION
strict_stage40b_survivor_watch_count = 0
recency_or_concentration_watch_count = 0
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Candidate failed:

```text
VOL_COMP_EXP_LONG_L120_Q0.15_M2.0
```

Official hard fail reason:

```text
worst_quarter_slip16_floor
```

Important Stage40B numbers:

```text
full_n = 88
full_cost_mean_bps ≈ +45.20
train_cost_mean_bps ≈ +37.78
oos_cost_mean_bps ≈ +59.56
boot_p10_bps ≈ +23.46
boot_prob_mean_gt_0_pct ≈ 99.8
worst_quarter_cost_mean_bps ≈ +3.89
worst_quarter_slip16_mean_bps ≈ -12.11
oos_median_mae_bps ≈ -105.40
oos_touch_stop_100bps_pct ≈ 53.33
```

Interpretation:

- Mean and bootstrap looked good.
- But the rule was fragile in the weakest quarter after slippage-16.
- OOS path risk was also high.
- Therefore this survivor must be archived.

Stage40 final decision:

```text
Stage40 = ARCHIVE
Stage40C = NOT_ALLOWED
```

Archive patch created in previous session:

```text
stage40_final_archive_after_stage40b_patch.zip
```

## Important anti-overfit constraints for the next session

Do not try to rescue Stage40 by excluding bad buckets after seeing results, including:

```text
hour_utc=7
hour_utc=4
month=10
weekday=Tuesday
year=2022
year=2026
```

These were observed as weak buckets after audit. Removing them now would be post-hoc filtering / overfit.

Do not continue:

```text
VOL_COMP_EXP_LONG_L120_Q0.15_M2.0
RANGE_BOTTOM_REV_LONG_W48_Q0.05
BB_LOWER_REV_LONG_W120_K2.5
Stage39 condition buckets
Stage40 soft-watch rows
```

## Current repo files likely added by recent stages

Important scripts/docs/reports from Stage39/Stage40 may exist in repo:

```text
scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py
scripts/stage39b_event_path_tradability_diagnostic.py
scripts/stage39c_microstructure_session_condition_diagnostic.py
scripts/stage39d_condition_robustness_forward_split_audit.py
scripts/stage39e_frozen_rule_out_of_sample_audit.py
scripts/stage39f_recency_bias_and_rule_stability_audit.py
scripts/stage40_parallel_thesis_megascan.py
scripts/stage40b_survivor_path_stability_audit.py
```

Archive docs/reports:

```text
docs/STAGE39_FINAL_ARCHIVE_AFTER_STAGE39F.md
reports/stage39_final/stage39_final_archive_decision.json

docs/STAGE40_FINAL_ARCHIVE_AFTER_STAGE40B.md
reports/stage40_final/stage40_final_archive_decision.json
```

## Recommended next phase: Stage41

Stage41 must be a new independent thesis phase, not a rescue of Stage39 or Stage40.

Recommended approach:

```text
Stage41_PARALLEL_THESIS_MEGASCAN_V2
```

Keep the same successful workflow from Stage40:

```text
parallel thesis scan
benchmark-first
event-clock metrics
train/OOS split
quarter stability
slip16 stress
LOYO / ex2025 checks
NO promotion at scan stage
```

But use new thesis families, not reused Stage39/40 survivors.

Potential Stage41 thesis directions:

1. Multi-timeframe structure break + retest
   - H1 trigger with H4/D1 structural context.
   - Avoid simple trend drift.

2. News-time exclusion / event-time volatility normalization
   - Not necessarily using external news yet; can use volatility spikes as proxy.
   - Test whether edge only exists outside shock windows.

3. Intraday reversal after NY impulse exhaustion
   - Must be pre-defined, not filtered after results.
   - Prefer symmetric long/short tests.

4. Regime-aware volatility expansion with strict early-quarter survival
   - Different from Stage40 because Stage40 failed on worst-quarter slip16.
   - The rule must require early-quarter and slip16 robustness from the beginning.

5. Multi-bar confirmation after compression expansion
   - Not the same as `VOL_COMP_EXP_LONG_L120_Q0.15_M2.0`.
   - Must define a new trigger such as compression → expansion → controlled retest/hold, and test from scratch.

6. M5/M15 execution feasibility pre-filter scan
   - Only if DB has enough M5/M15 history.
   - Still research-only; no EA/paper/live.

## First prompt to paste into the new session

Use this prompt in a new ChatGPT session:

```text
چپ‌چین ادامه بده.

این پروژه XAUUSD/gold research است. لطفاً این بسته انتقالی را مبنا قرار بده و از ادامه دادن Stage39 یا Stage40 خودداری کن.

وضعیت فعلی:
- Stage38 archive شد؛ no promotion.
- Stage39A-F archive شد؛ Stage39F نشان داد همه survivorها recency-biased هستند و strict_stable_frozen_watch_count=0.
- Stage40 parallel thesis megascan اجرا شد؛ فقط یک strict survivor داشت: VOL_COMP_EXP_LONG_L120_Q0.15_M2.0.
- Stage40B survivor path stability audit اجرا شد و همان survivor با FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION رد شد؛ hard_fail_reasons=worst_quarter_slip16_floor؛ strict_stage40b_survivor_watch_count=0.
- نتیجه نهایی: promotion=NO_GO, EA=NO_GO, paper_live=NO_GO, live=NO_GO.

در سشن جدید می‌خواهم Stage41 را شروع کنیم. Stage41 باید thesisهای واقعاً جدید را benchmark-first و parallel scan کند، نه rescue/filter extension روی Stage39/Stage40. اگر پچ می‌دهی، documentation را داخل همان deliverable بگذار، فایل دانلودی بده، دستور mv از Downloads به ریپو بده، و git commands امن بده.

Repo:
~/Desktop/xauusd-trader
DB:
data/local/xauusd_local_store.sqlite
Table:
bars
symbol/source/timeframe:
XAUUSD / amarkets_mt5 / H1
Latest loaded H1 range:
2022-05-01T23:00:00Z تا 2026-06-16T12:00:00Z
Loaded H1 rows:
25,643

گام بعدی پیشنهادی: طراحی Stage41_PARALLEL_THESIS_MEGASCAN_V2 با thesisهای جدید و بدون promotion.
```

## Files to upload in the new session if needed

Minimum useful files:

```text
reports/stage40b/stage40b_survivor_path_stability_summary.json
reports/stage40b/stage40b_survivor_path_stability_audit.md
reports/stage40/stage40_parallel_thesis_megascan_summary.json
reports/stage40/stage40_parallel_thesis_megascan.md
reports/stage39f/stage39f_frozen_rule_recency_bias_summary.json
reports/stage39f/stage39f_frozen_rule_recency_bias_audit.md
```

Optional archive files:

```text
reports/stage39_final/stage39_final_archive_decision.json
reports/stage40_final/stage40_final_archive_decision.json
docs/STAGE39_FINAL_ARCHIVE_AFTER_STAGE39F.md
docs/STAGE40_FINAL_ARCHIVE_AFTER_STAGE40B.md
```

## Bottom line

The project is still alive, but the current research branches are closed.

```text
Closed branches:
Stage38
Stage39
Stage40

Next allowed branch:
Stage41 with genuinely new thesis families only.
```
