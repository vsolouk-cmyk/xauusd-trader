# Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN

## وضعیت

```text
stage = Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN
scope = research-stage only
promotion = NO-GO
EA = NO-GO
paper-live = NO-GO
live = NO-GO
```

این پچ بعد از archive شدن Stage38 و نتیجه Stage38I ساخته شده است. هدف آن شروع یک شاخه تمیز و benchmark-first برای بررسی reversal / mean-reversion روی XAUUSD H1 است؛ نه ادامه دادن Stage38، نه اضافه کردن فیلتر به survivorهای ضعیف Stage38، و نه آماده‌سازی EA.

## منطق فنی

نتیجه Stage38 این بود که positive forward returnها، مخصوصاً در longها، تا حد زیادی با bull drift توضیح داده می‌شوند. بنابراین Stage39A از ابتدا هر candidate را با benchmark می‌سنجد:

```text
candidate signed return
minus direction-matched H1 all drift
minus cost stress
minus daily anchor drift reference
minus robustness penalties by year split / 2025 exclusion / leave-one-year-out
```

برای long candidateها، benchmark همان drift مثبت XAUUSD است. برای short candidateها، benchmark جهت‌دار می‌شود؛ یعنی short باید نسبت به short-unconditional drift و همچنین هزینه، residual مثبت نشان دهد. این کار مانع می‌شود که یک short صرفاً به دلیل چند رویداد پراکنده یا یک رژیم خاص به‌عنوان edge دیده شود.

## فایل‌های پچ

```text
scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py
docs/STAGE39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN.md
reports/stage39a/.gitkeep
```

## ورودی پیش‌فرض

```text
db = data/local/xauusd_local_store.sqlite
table = bars
symbol = XAUUSD
source = amarkets_mt5
timeframe = H1
horizons = 24,72,120
cost_bps = 8.0
min_events = 30
```

اسکریپت با schema introspection نوشته شده و نام ستون‌های رایج را تشخیص می‌دهد:

```text
timestamp: ts_utc / timestamp_utc / time_utc / datetime / time / date / ...
ohlc: open/high/low/close یا معادل‌های کوتاه o/h/l/c
symbol/source/timeframe: اگر ستون وجود داشته باشد، فیلتر می‌شود
spread: اگر وجود داشته باشد، فقط برای یک خانواده optional استفاده می‌شود
```

## خانواده candidateها

Stage39A عمداً ساده و benchmark-first است:

```text
RETURN_ZSCORE_REVERSAL
- long بعد از downside extreme
- short بعد از upside extreme

ROLLING_RANGE_REVERSAL
- long نزدیک کف rolling range
- short نزدیک سقف rolling range

RSI_REVERSAL
- long در oversold
- short در overbought

BOLLINGER_REVERSAL
- long پایین‌تر از باند منفی
- short بالاتر از باند مثبت

SPREAD_STRESS_FADE
- فقط اگر ستون spread در دیتابیس وجود داشته باشد
```

## خروجی‌ها

بعد از اجرا، این فایل‌ها ساخته می‌شوند:

```text
reports/stage39a/stage39a_reversal_mean_reversion_scan.csv
reports/stage39a/stage39a_reversal_mean_reversion_scan_summary.json
reports/stage39a/stage39a_reversal_mean_reversion_scan.md
reports/stage39a/stage39a_reversal_mean_reversion_event_clock_events.csv
```

## ستون‌های کلیدی خروجی

```text
raw_n
raw_mean_bps
raw_hit_rate_pct

event_clock_n
event_clock_mean_bps
event_clock_cost_stressed_mean_bps

directional_h1_all_drift_bps
directional_daily_anchor_drift_bps
h1_drift_adjusted_residual_bps
daily_anchor_adjusted_residual_bps
h1_benchmark_cost_adjusted_residual_bps

pre2025_mean_bps
ex2025_mean_bps
y2025_mean_bps
first_half_mean_bps
second_half_mean_bps
leave_one_year_out_min_mean_bps

median_mae_bps
median_mfe_bps
classification
```

## تفسیر classification

```text
STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION
```

یعنی candidate فقط ارزش diagnostic مرحله بعدی دارد. حتی این حالت هم promotion نیست.

```text
WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION
```

یعنی residual اولیه بعد از benchmark و cost مثبت است، اما robust enough نیست.

```text
FAIL_BENCHMARK_RESEARCH_ONLY
```

یعنی نباید با فیلترهای بیشتر توسعه داده شود.

```text
INSUFFICIENT_EVENTS_RESEARCH_ONLY
```

یعنی تعداد رویدادهای non-overlapping کافی نیست.

## دستور اجرای پیشنهادی

از ریشه ریپو:

```bash
cd ~/Desktop/xauusd-trader
python3 scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py \
  --db data/local/xauusd_local_store.sqlite \
  --table bars \
  --symbol XAUUSD \
  --source amarkets_mt5 \
  --timeframe H1 \
  --horizons 24,72,120 \
  --cost-bps 8.0 \
  --min-events 30 \
  --output-dir reports/stage39a
```

## معیار توقف

اگر خروجی شامل strict research-watch نبود:

```text
Stage39A = ARCHIVE
promotion = NO-GO
```

اگر strict research-watch وجود داشت، فقط گام مجاز بعدی:

```text
Stage39B_EVENT_PATH_AND_TRADABILITY_DIAGNOSTIC
```

Stage39B هم باید research-stage باشد، نه promotion.

## کارهایی که نباید انجام شود

```text
do_not_promote_to_EA
do_not_start_paper_live
do_not_start_live
do_not_create_trade_alerts
do_not_stack_filters_on_weak_rows
do_not_treat_2025_only_strength_as_edge
do_not_ignore_direction_matched_drift
```
