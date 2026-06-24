# Stage38A — AMarkets XAUUSD Symbol Spec Capture

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Manual capture template for MT5 XAUUSD symbol specification  
**Generated UTC:** 2026-06-16T12:39:13Z  
**Status:** Required before converting `spread_points` into price/USD/R cost  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند برای ثبت مشخصات نماد XAUUSD در AMarkets/MT5 است. هدف این است که اعداد spread که در audit دیده‌ایم، مثل:

```text
p50 = 37
p75 = 43
p90 = 49
p95 = 51
p99 = 70
max = 183
```

از حالت مبهم `spread_points` به cost قابل‌فهم در price-unit و بعداً R تبدیل شوند.

تا وقتی این مشخصات ثبت نشود، نتایج cost-aware فقط diagnostic هستند و نباید به‌عنوان net R نهایی یا آمادگی Stage39 تفسیر شوند.

---

## 1. Why This Is Needed

در جدول `bars` مقدار spread داریم، اما هنوز نمی‌دانیم:

```text
1 spread point دقیقاً چند واحد قیمت XAUUSD است؟
آیا 37 یعنی 0.37 دلار؟ 3.7 دلار؟ یا چیز دیگر؟
tick size چیست؟
tick value چیست؟
contract size چیست؟
commission هست یا نه؟
swap long/short چقدر است؟
rollover چه ساعتی اعمال می‌شود؟
```

بدون این اطلاعات، مدل هزینه v0 باید در واحد زیر باقی بماند:

```text
spread_points
```

این برای مقایسه diagnostic کافی است، ولی برای net R واقعی کافی نیست.

---

## 2. Where to Find This in MT5

در MT5:

```text
Market Watch
Right-click on XAUUSD
Specification
```

یا:

```text
Ctrl+U
Select XAUUSD
Properties / Specification
```

از پنجره Specification همین موارد را کپی کن.

---

## 3. Manual Capture Form

لطفاً این فرم را با اطلاعات دقیق MT5 پر کن.

```text
CAPTURE_DATE_UTC:
CAPTURED_BY:
BROKER:
SERVER:
ACCOUNT_TYPE:
SYMBOL:
SYMBOL_DESCRIPTION:

DIGITS:
POINT:
TICK_SIZE:
TICK_VALUE:
CONTRACT_SIZE:

MIN_VOLUME:
MAX_VOLUME:
VOLUME_STEP:

SPREAD_TYPE:
CURRENT_SPREAD_SHOWN:
AVERAGE_SPREAD_IF_SHOWN:

COMMISSION:
COMMISSION_UNIT:
COMMISSION_PER_LOT_OR_SIDE:

SWAP_LONG:
SWAP_SHORT:
SWAP_MODE:
TRIPLE_SWAP_DAY:

TRADING_HOURS_SERVER_TIME:
QUOTE_HOURS_SERVER_TIME:
ROLLOVER_TIME_SERVER:
ROLLOVER_TIME_UTC_IF_KNOWN:

PROFIT_CURRENCY:
MARGIN_CURRENCY:
CALCULATION_MODE:

STOP_LEVEL:
FREEZE_LEVEL:

NOTES:
```

اگر بعضی فیلدها در MT5 دیده نمی‌شوند، خالی نگذار؛ بنویس:

```text
NOT_SHOWN
```

اگر مطمئن نیستی:

```text
UNCLEAR
```

---

## 4. Minimum Required Fields

برای اینکه T1 read-only script بتواند cost را از `spread_points` به price-unit تبدیل کند، حداقل این‌ها لازم‌اند:

```text
SYMBOL:
DIGITS:
POINT:
TICK_SIZE:
TICK_VALUE:
CONTRACT_SIZE:
COMMISSION:
SWAP_LONG:
SWAP_SHORT:
TRIPLE_SWAP_DAY:
ROLLOVER_TIME_SERVER:
```

اگر فقط همین‌ها ثبت شوند، برای نسخه اول کافی است.

---

## 5. Expected Interpretation Logic

بعد از ثبت مشخصات، باید بتوانیم این تبدیل را انجام دهیم:

```text
spread_price_distance = spread_points * POINT
```

مثلاً اگر:

```text
POINT = 0.01
spread_points = 37
```

آنگاه:

```text
spread_price_distance = 0.37 XAUUSD price units
```

ولی این مثال فقط نمونه است. تا وقتی `POINT` از MT5 تأیید نشود، نباید فرض شود.

---

## 6. Cost Conversion Rule for Future Script

اگر مشخصات کامل شد:

```text
COST_UNIT_RESOLVED = true
```

در این حالت script آینده می‌تواند:

```text
spread_points -> price distance -> R impact
```

اگر مشخصات ناقص بود:

```text
COST_UNIT_RESOLVED = false
```

در این حالت script آینده فقط باید گزارش diagnostic بدهد:

```text
gross_R
spread_points_sensitivity
no final net_R claim
```

---

## 7. Required File to Create Locally

بعد از پر کردن فرم، یک فایل manual بساز:

```text
data/manual/amarkets_xauusd_symbol_spec_YYYYMMDD.txt
```

مثلاً:

```text
data/manual/amarkets_xauusd_symbol_spec_20260616.txt
```

---

## 8. Suggested Local Command

بعد از اینکه اطلاعات MT5 را کپی کردی، این فایل را بساز:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p data/manual
nano data/manual/amarkets_xauusd_symbol_spec_20260616.txt
```

متن فرم بخش 3 را داخل آن paste کن و مقادیر را پر کن.

اگر nano سخت بود:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p data/manual
cat > data/manual/amarkets_xauusd_symbol_spec_20260616.txt <<'EOF'
CAPTURE_DATE_UTC:
CAPTURED_BY:
BROKER:
SERVER:
ACCOUNT_TYPE:
SYMBOL:
SYMBOL_DESCRIPTION:

DIGITS:
POINT:
TICK_SIZE:
TICK_VALUE:
CONTRACT_SIZE:

MIN_VOLUME:
MAX_VOLUME:
VOLUME_STEP:

SPREAD_TYPE:
CURRENT_SPREAD_SHOWN:
AVERAGE_SPREAD_IF_SHOWN:

COMMISSION:
COMMISSION_UNIT:
COMMISSION_PER_LOT_OR_SIDE:

SWAP_LONG:
SWAP_SHORT:
SWAP_MODE:
TRIPLE_SWAP_DAY:

TRADING_HOURS_SERVER_TIME:
QUOTE_HOURS_SERVER_TIME:
ROLLOVER_TIME_SERVER:
ROLLOVER_TIME_UTC_IF_KNOWN:

PROFIT_CURRENCY:
MARGIN_CURRENCY:
CALCULATION_MODE:

STOP_LEVEL:
FREEZE_LEVEL:

NOTES:
EOF
```

بعد فایل را باز کن و مقادیر را کامل کن:

```bash
open data/manual/amarkets_xauusd_symbol_spec_20260616.txt
```

---

## 9. How This Updates Stage38A

بعد از ثبت این فایل:

```text
POINT_TO_PRICE_CONVERSION = RESOLVED_OR_PARTIAL
SPREAD_POINTS_MODEL = CONVERTIBLE
T1_COST_MODEL = STRONGER
T1_READ_ONLY_SCRIPT = SAFER
```

اگر فیلدهای اصلی کامل باشند:

```text
T1_READ_ONLY_SCRIPT can report net R under cost scenarios.
```

اگر کامل نباشند:

```text
T1_READ_ONLY_SCRIPT can still run, but only diagnostic gross/cost-sensitivity mode is allowed.
```

---

## 10. Git Commit After Manual Spec Capture

بعد از اینکه فایل manual را ساختی و پر کردی:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Add AMarkets XAUUSD symbol specification capture"
git pull --rebase origin main
git push
```

---

## 11. Recommended Commit for This Template

برای انتقال همین template به repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_CAPTURE.md docs/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_CAPTURE.md
git status --short
git add -A
git commit -m "Add Stage38A AMarkets XAUUSD symbol spec capture template"
git pull --rebase origin main
git push
```

---

## 12. Practical Next Step

1. این template را commit کن.
2. از MT5 بخش Specification نماد XAUUSD را باز کن.
3. فرم بخش 3 را در فایل زیر پر کن:

```text
data/manual/amarkets_xauusd_symbol_spec_20260616.txt
```

4. خروجی را بفرست تا تبدیل spread و cost model را نهایی کنیم.

تا قبل از این، script آینده یا باید cost را unresolved نگه دارد، یا فقط diagnostic اجرا شود.
