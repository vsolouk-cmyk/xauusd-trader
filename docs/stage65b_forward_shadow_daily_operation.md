# Stage65B — Forward-Shadow Daily Operation Wrapper

## هدف

این بسته برای ادامه عملیات روزانه Stage65 ساخته شده است.

کار آن:
- کنترل وجود و current بودن دیتاست macro-regime `Stage64K`
- کنترل وجود و current بودن external spot D1
- اجرای اسکریپت فعلی Stage65 فقط در صورت عبور preflight
- تولید گزارش روزانه عملیاتی

این بسته هیچ مسیر order، broker، EA، paper-live یا live اضافه نمی‌کند.

## فایل‌های اضافه‌شده

```text
app/stage65b_forward_shadow_daily_ops.py
configs/stage65b_forward_shadow_daily_ops.json
.github/workflows/stage65_forward_shadow_daily.yml
docs/stage65b_forward_shadow_daily_operation.md
```

## اجرای محلی

از ریشه repo:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage65b_forward_shadow_daily_ops.py \
  --root . \
  --config configs/stage65b_forward_shadow_daily_ops.json \
  --out reports/stage65b_forward_shadow_daily_ops
```

## اجرای فقط preflight

برای اینکه فقط بفهمیم فایل‌ها آماده اجرای Stage65 هستند یا نه:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage65b_forward_shadow_daily_ops.py \
  --root . \
  --config configs/stage65b_forward_shadow_daily_ops.json \
  --out reports/stage65b_forward_shadow_daily_ops \
  --preflight-only
```

## فایل‌های ورودی لازم

```text
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv
app/stage65_forward_shadow_signal_ledger_fastlane.py
configs/stage65_forward_shadow_signal_ledger_fastlane.json
```

## خروجی‌ها

```text
reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json
reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_report.md
```

اگر Stage65 اجرا شود، خروجی‌های اصلی Stage65 هم طبق روال قبلی آپدیت می‌شوند:

```text
reports/stage65_forward_shadow_signal_ledger_fastlane/stage65_forward_shadow_signal_ledger_summary.json
reports/stage65_forward_shadow_signal_ledger_fastlane/stage65_forward_shadow_signal_ledger_report.md
data/forward_shadow/stage65_macro_signal_ledger.csv
data/forward_shadow/stage65_observation_ledger.csv
data/forward_shadow/stage65_forward_shadow_state.json
```

## GitHub Actions

Workflow جدید:

```text
.github/workflows/stage65_forward_shadow_daily.yml
```

از GitHub UI این workflow را اجرا کن:

```text
Stage65 Forward Shadow Daily Operation
```

برای اجرای معمول، inputها را روی مقدار پیش‌فرض بگذار:

```text
preflight_only=false
allow_stale_run=false
```

برای فقط کنترل آمادگی داده‌ها:

```text
preflight_only=true
allow_stale_run=false
```

## تصمیم عملیاتی

- اگر status برابر `STAGE65B_DAILY_OPERATION_COMPLETE_NO_PROMOTION` بود: عملیات روزانه درست انجام شده و Stage65 ادامه دارد.
- اگر status برابر `PREFLIGHT_FAIL` بود: اول دیتاست macro یا external D1 باید refresh شود.
- اگر status برابر `STAGE65B_STAGE65_EXECUTION_FAIL_NO_ORDER` بود: مشکل در اجرای خود Stage65 یا config قبلی است.

## Hard blocks

این بسته عمداً این محدودیت‌ها را حفظ می‌کند:

```text
NO_PAPER_ORDER
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_BROKER_CONNECTION
NO_ORDER_AUTHORIZATION_FROM_STAGE65
NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE
NO_POST_HOC_EVENT_EXCLUSION
NO_REDUCED_SCOPE_RETEST
NO_RESCUE_FILTERING
NO_NEW_INTRADAY_SCAN
NO_THRESHOLD_TUNING
NO_COMMERCIALIZATION_WITHOUT_LATER_FORWARD_AND_BROKER_GOVERNANCE
```
