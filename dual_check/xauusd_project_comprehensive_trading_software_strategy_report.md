# گزارش جامع مسیر پژوهش و پیاده‌سازی XAUUSD / Gold Trading

**پروژه:** XAUUSD / Gold Trading Research  
**هدف اصلی:** رسیدن به یک مسیر معاملاتی قابل اتکا، cost-aware، broker-realistic و قابل دفاع برای XAUUSD، بدون پرش زودهنگام به ML، paper-live یا live.  
**وضعیت گزارش:** جمع‌بندی تا آخرین اجرای Stage52/Stage58B/Stage59/Stage63 در 2026-06-24  
**مخاطب هدف:** متخصص تریدینگ طلا، متخصص توسعه نرم‌افزار/اعتبارسنجی پیاده‌سازی، و استراتژیست ارشد تصمیم‌گیری محصول/پژوهش

---

## 1. خلاصه اجرایی

این پروژه با فرض محوری «baseline-first و data-quality-first» آغاز شد: قبل از هرگونه مدل‌سازی ML یا اجرای سفارش، باید نشان داده می‌شد که در XAUUSD یک baseline ساده، قابل توضیح، مثبت بعد از هزینه، و قابل تکرار در forward shadow وجود دارد. این رویکرد عمداً با مسیرهای رایج ولی پرریسک «اول مدل بسازیم، بعد شاید edge پیدا شود» فاصله داشت.

در طول پروژه، چند خانواده ایده‌ی معاملاتی روی طلا طراحی، پیاده‌سازی، اسکن، audit و در مواردی forward shadow شد. ایده‌ها شامل روند/مومنتوم چندتایم‌فریمی، شکست محدوده آسیا/جلسه، open range breakout، liquidity sweep reversal، volatility squeeze breakout، overlayهای COT/macro/GLD، context-aware regime filters، و نهایتاً execution sandbox در MT5 بودند.

نتیجه کلی تا این نقطه چنین است:

1. مسیرهای پرفرکانس یا نیمه‌پرفرکانس که در backtest یا hard audit ظاهر مثبت داشتند، در forward یا cost-aware audit معمولاً فرو ریختند.
2. کاندیداهای خام Stage52 که ابتدا promising بودند، با افزایش نمونه true-forward به وضوح deteriorate کردند.
3. کاندیدای context-aware Stage58B هنوز مثبت است، اما کم‌فرکانس و کم‌نمونه است؛ دقیقاً همان الگویی که ریسک بن‌بست قبلی را تکرار می‌کند: candidateهای با فرکانس کافی شکست می‌خورند و candidateهای باقی‌مانده آن‌قدر کم‌فرکانس‌اند که تصمیم‌پذیری عملیاتی و تجاری را کند و مبهم می‌کنند.
4. پیاده‌سازی از نظر data ingestion، broker spread/cost، stateful forward shadow، و MT5 demo execution به مرحله‌ی قابل اعتبارسنجی رسیده است؛ مسئله‌ی اصلی دیگر زیرساخت نیست، بلکه کیفیت و پایداری edge است.
5. هیچ مسیر فعلی اجازه‌ی promotion، paper-order، paper-live یا live ندارد.

تصمیم رسمی Stage63 این بود:

```text
Stage52 raw = DEMOTE_TO_PASSIVE_REFERENCE_NO_PROMOTION
Stage58B context = PRIMARY_CONTEXT_FORWARD_WATCH_NO_PROMOTION
Paper-order = NO_GO
Paper-live = NO_GO
Live = NO_GO
```

آخرین وضعیت حتی این تصمیم را قوی‌تر کرده است. Stage52 raw در آخرین گزارش به وضعیت شکست forward رسیده:

```text
true_forward_signals = 191
evaluated_signals = 191
evaluated_mean_stress_bps = -2.725
evaluated_median_stress_bps = -0.570
evaluated_win_rate = 45.03%
negative_candidate_mean_count = 12 / 12
```

در مقابل، Stage58B هنوز مثبت اما کم‌نمونه است:

```text
true_forward_signals = 48
evaluated_signals = 34
pending_signals = 14
evaluated_mean_stress_bps = 4.266
evaluated_median_stress_bps = 3.461
evaluated_win_rate = 61.76%
negative_candidate_mean_count = 0
```

برداشت استراتژیک: پروژه احتمالاً به همان ساختار بن‌بست قبلی نزدیک شده است. مسیرهای کافی‌فرکانس، بعد از اعمال واقعیت هزینه و forward، edge کافی نشان نمی‌دهند. مسیرهای باقی‌مانده به context filtering سنگین وابسته‌اند و بنابراین فرکانس پایین دارند. اگر Stage58B بعد از رسیدن به حداقل sample هم deteriorate کند، باید thesis فعلی intraday/technical XAUUSD را به‌طور جدی متوقف یا pivot کرد، نه اینکه با filterهای ریزتر آن را نجات داد.

---

## 2. مبنای گزارش و دامنه

این گزارش بر پایه‌ی مجموعه‌ی stage reportها، summaryها، تصمیم‌های مرحله‌ای، patchهای تولیدشده، و حافظه پروژه نوشته شده است. هدف آن صرفاً توصیف سطحی نیست؛ بلکه باید برای سه گروه قابل استفاده باشد.

### 2.1 متخصص تریدینگ طلا

باید بتواند بفهمد:

- چه فرضیه‌های معاملاتی روی XAUUSD بررسی شده‌اند.
- آیا منطق بازار پشت ایده‌ها قابل دفاع است یا نه.
- هزینه، spread، session، regime، macro context و feed broker چگونه لحاظ شده‌اند.
- چرا بعضی ایده‌ها شکست خوردند و آیا شکست ناشی از data/implementation بوده یا خود thesis.

### 2.2 متخصص توسعه نرم‌افزار

باید بتواند اعتبارسنجی کند:

- pipeline داده چگونه ساخته شده است.
- stateful forward shadow چگونه از backfill تفکیک شده است.
- loaderها، schema، timezone، spread و cost model چگونه مدیریت شده‌اند.
- آیا اجرای MT5 demo واقعاً order plumbing را نشان داده یا edge را.
- آیا خروجی‌ها reproducible و audit-ready هستند.

### 2.3 استراتژیست ارشد

باید بتواند استخراج کند:

- پروژه از کجا شروع شد و چرا مسیر عوض شد.
- کدام تصمیم‌ها بر اساس evidence بوده‌اند.
- کدام گلوگاه‌ها ساختاری‌اند، نه صرفاً فنی.
- آیا ادامه پروژه با همین thesis ارزش دارد یا باید pivot/stop شود.

---

## 3. فلسفه طراحی و قواعد عملیاتی پروژه

### 3.1 Baseline-first

قبل از ML، ابتدا باید baselineهای ساده و قابل توضیح بررسی می‌شدند. دلیل این قاعده این است که در XAUUSD نویز زیاد، sensitivity به session/news/spread بالا، و خطر overfit بسیار جدی است. اگر یک baseline ساده بعد از هزینه مثبت نباشد، مدل پیچیده احتمالاً فقط noise را یاد می‌گیرد.

### 3.2 Data-quality-first

هر ایده‌ای فقط وقتی قابل بررسی بود که:

- timestampها سالم باشند؛
- gapها قابل شناسایی باشند؛
- spread یا cost proxy وجود داشته باشد؛
- feed broker با اجرای احتمالی سازگار باشد؛
- normalization و timezone قابل audit باشد.

### 3.3 No paper-order before forward shadow

حتی اگر backtest یا hard audit مثبت بود، تا زمانی که forward shadow واقعی و بدون backfill حداقل گیت‌ها را پاس نمی‌کرد، هیچ paper-order یا paper-live مجاز نبود.

### 3.4 Broker realism

چون XAUUSD در CFD/MT5 ممکن است از نظر spread، session rollover، symbol spec، execution و feed با منابع REST متفاوت باشد، پروژه به سمت AMarkets MT5 broker feed pivot کرد.

### 3.5 Kill-switch discipline

هر خانواده thesis باید kill-switch داشته باشد. اگر پس از اعمال هزینه، forward، یا context audit شکست می‌خورد، نباید با post-hoc filtering آن را نجات داد.

---

## 4. محیط و معماری فعلی پروژه

### 4.1 مسیرهای اصلی

```text
Repo root:
    /Users/vahid/Desktop/xauusd-trader

Downloads:
    ~/Downloads

DB:
    /Users/vahid/Desktop/xauusd-trader/data/broker_normalized/amarkets_multitf.sqlite

Forward state:
    /Users/vahid/Desktop/xauusd-trader/data/shadow/stage52_forward_shadow.sqlite
    /Users/vahid/Desktop/xauusd-trader/data/shadow/stage58b_context_forward_shadow.sqlite
```

### 4.2 CSVهای broker feed

```text
~/Downloads/amarkets_xauusd_1m.csv
~/Downloads/amarkets_xauusd_5m.csv
~/Downloads/amarkets_xauusd_15m.csv
~/Downloads/amarkets_xauusd_30m.csv
~/Downloads/amarkets_xauusd_1h.csv
```

### 4.3 مدل داده‌ی candle

جدول اصلی SQLite معمولاً این ستون‌ها را دارد:

```text
source
symbol
timeframe
utc_time
open
high
low
close
volume
spread
```

### 4.4 state table برای forward shadow

Stage52 و Stage58B هر دو stateful هستند و سیگنال‌ها را در SQLite ثبت می‌کنند. ستون‌های کلیدی:

```text
signal_id
candidate_id
entry_time_utc
direction
entry_price
horizon_m5_bars
stress_cost_bps
spread_cost_bps
status
planned_exit_time_utc
exit_time_utc
exit_price
gross_bps
stress_bps
created_utc
evaluated_utc
is_backfill
source_run_id
```

Stage58B همچنین ستون‌های context-specific دارد:

```text
base_candidate_id
context_tag
params_json
context_json
```

### 4.5 cost model

مدل هزینه از Stage48F استخراج شد:

```text
stress_cost_bps ≈ 2.982
extreme_cost_bps ≈ 3.038
selected broker time offset = +3 hours
aligned spread coverage = 100%
```

این اعداد در forward shadow و gateها به‌عنوان حداقل هزینه execution realism لحاظ شدند.

---

## 5. ایده‌های اولیه و thesisهای ساخته‌شده برای ترید طلا

### 5.1 Higher-timeframe trend / persistence

ایده: اگر XAUUSD در تایم‌فریم‌های بالاتر ساختار روندی یا persistence داشته باشد، ورود intraday در جهت trend می‌تواند edge بدهد.

منطق بازار:

- طلا در دوره‌های macro-driven ممکن است trend persistence قوی داشته باشد.
- نرخ بهره حقیقی، DXY، yields و risk sentiment می‌توانند جهت‌گیری چندروزه بسازند.
- اما ورود مستقیم trend-following روی broker CFD با spread و whipsaw intraday حساس است.

نتیجه کلی:

- برخی حالت‌ها در اسکن اولیه promising بودند.
- در hard audit و cost-aware بررسی‌ها survival واقعی نداشتند.
- مسیر به‌عنوان thesis مستقل promotion نشد.

### 5.2 Asia range breakout / session range breakout

ایده: محدوده آسیا در XAUUSD می‌تواند انرژی فشرده ایجاد کند؛ شکست آن در London/NY می‌تواند حرکت directional بدهد.

منطق بازار:

- liquidity در Asia متفاوت است.
- London و NY حجم بیشتری دارند.
- شکست محدوده آسیا یکی از ایده‌های رایج روی XAUUSD/FX است.

مشکل عملی:

- breakoutها بدون context به false break و mean reversion حساس‌اند.
- broker spread و زمان‌بندی session روی CFD اثر زیادی دارد.
- edge خام اگر exists باشد، با هزینه و rollover/news noise شکننده می‌شود.

نتیجه:

- در Stage38C بعضی baselineها مانند Asia range breakout از نظر backtest ساده قابل توجه بودند.
- اما در ادامه مسیر hard audit/promotion به سطح قابل اجرا نرسید.

### 5.3 London/NY open range breakout

ایده: شروع sessionهای بزرگ ممکن است directional imbalance ایجاد کند.

پیاده‌سازی:

- Stage50 session open range breakout.
- بررسی session open و شکست محدوده.
- اعمال هزینه و audit سخت.

نتیجه:

- تعداد candidate زیاد بود، اما hard audit pass نداشت.
- Stage50 archive شد.

### 5.4 Liquidity sweep reversal

ایده: XAUUSD پس از sweep کردن high/lowهای کوتاه‌مدت ممکن است reversal بدهد؛ مخصوصاً در اطراف session boundaries یا liquidity pools.

منطق بازار:

- gold به stop hunt، sweep و برگشت‌های سریع حساس است.
- در CFD/MT5، wick behavior و spread می‌تواند بسیار اثرگذار باشد.

پیاده‌سازی:

- Stage47 liquidity sweep reversal scan.
- چند loader fix برای parsing و source selection.
- Stage48 cost-aware diagnostic با broker spread.

نتیجه:

- پس از cost-aware audit، survivors = 0.
- این مسیر archive شد.
- یکی از درس‌ها: ایده‌هایی که از نظر price action جذاب‌اند، وقتی با spread و broker execution واقع‌بینانه سنجیده شوند، ممکن است edgeشان کاملاً از بین برود.

### 5.5 Volatility squeeze breakout

ایده: پس از دوره‌های compression/volatility squeeze، XAUUSD ممکن است expansion کوتاه‌مدت بدهد. اگر context مناسب باشد، breakout می‌تواند سودآور شود.

پیاده‌سازی:

- Stage51 volatility squeeze breakout.
- Stage52 true forward shadow.
- Stage58A context-aware regime audit.
- Stage58B context forward shadow.

نتیجه:

- Raw Stage52 ابتدا promising بود اما در forward deteriorate کرد.
- Context-aware Stage58B هنوز positive است ولی low-frequency و under-sampled است.

این thesis در حال حاضر تنها مسیر زنده‌ی اصلی است، ولی با ریسک بالای بن‌بست کم‌فرکانس.

### 5.6 COT / macro / GLD / exogenous overlays

ایده: طلا strongly macro-sensitive است؛ overlayهای COT، DXY، US10Y، real yield، GLD و calendar events ممکن است regime filter بدهند.

پیاده‌سازی:

- Stage38 overlay research.
- Join audit با COT و H1 data.
- بررسی stateهایی مثل LONG_CROWDED, SHORT_CROWDED, EXTREME_LONG/SHORT.
- بررسی overlay retest مانند LONG_PERMITTED_ONLY.

نتیجه:

- بعضی overlayها marginal/watch بودند.
- اما candidateهای نهایی به حد promotion نرسیدند.
- داده‌های خارجی به دلیل محدودیت دسترسی، blocking و کیفیت/به‌روزرسانی، operationally سخت بودند.

### 5.7 Context-aware filtering

ایده: اگر raw thesis در بعضی contextها شکست می‌خورد، به جای مدل ML، فیلترهای ساده context/regime برای خاموش/روشن کردن baseline استفاده شود.

پیاده‌سازی:

- Stage57 context source precheck.
- Stage58A context-aware Stage51 audit.
- Stage58B true-forward context shadow.

فیلترها شامل:

- range state؛
- spread percentile؛
- session overlap؛
- no rollover؛
- context tags روی M15/M5.

نتیجه:

- این مسیر فعلاً بهترین وضعیت را دارد.
- اما مشکل ساختاری فرکانس پایین دارد.

### 5.8 Demo execution sandbox

ایده: حتی بدون edge promotion، plumbing اجرای MT5 باید بررسی شود تا بعداً اگر edge پیدا شد، execution path ناشناخته نباشد.

پیاده‌سازی:

- Stage61 Demo Execution Harness.
- MQL5 compile-safe patch.
- telemetry و signal parse.
- tiny demo order test.
- کنترل demo account، AllowTrading، schema، volume و market status.

نتیجه:

- order plumbing در demo پاس شد.
- اما فقط plumbing را اثبات کرد، نه edge.
- هیچ مجوز paper-live یا live ایجاد نکرد.

---

## 6. متدها و رویکردهای پیاده‌سازی‌شده

### 6.1 Parallel thesis megascan

برای جلوگیری از اتلاف وقت در هر ایده به‌صورت خطی، پروژه به سمت اسکن موازی thesis families رفت. منطق این بود:

1. scan سریع و گسترده؛
2. shortlist فقط candidateهای زنده؛
3. promotion/hard audit فقط برای shortlist.

مزیت:

- سرعت بالا در حذف ایده‌های ضعیف؛
- کاهش زمان تلف‌شده روی candidateهای بی‌کیفیت.

عیب:

- اگر تمام خانواده‌ها از یک نوع داده/feature فنی مشابه استفاده کنند، ممکن است شکست‌ها correlated باشند.
- اسکن زیاد بدون context قوی ممکن است فقط overfitهای متعدد تولید کند.

### 6.2 Hard audit

پس از scan، candidateها باید از audit سخت عبور می‌کردند:

- حداقل تعداد رخداد؛
- mean/median بعد از هزینه؛
- win rate؛
- drawdown proxy؛
- concentration؛
- negative candidate mean count؛
- session/year/regime concentration.

این auditها سبب شدند بسیاری از ایده‌ها قبل از forward حذف شوند.

### 6.3 Cost-aware evaluation

هزینه broker به‌عنوان first-class concern وارد شد:

- spread coverage؛
- broker offset؛
- stress_cost_bps؛
- extreme_cost_bps؛
- session cost profile.

این باعث شد ایده‌هایی که روی gross returns خوب بودند ولی با هزینه از بین می‌رفتند، حذف شوند.

### 6.4 True-forward shadow no backfill

یکی از مهم‌ترین تغییرات فنی، تفکیک strict true-forward از backfill بود. در Stage52 loaderfix، forward shadow به‌گونه‌ای اصلاح شد که:

- watermark داشته باشد؛
- initial backfill تولید نکند؛
- فقط candleهای جدید بعد از watermark را signal کند؛
- signalها را بعد از horizon واقعی evaluate کند.

این اصلاح برای اعتبار forward حیاتی بود.

### 6.5 Context regime tables

برای Stage58، context tables ساخته شد:

```text
reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv
reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv
```

Stage62 LoaderFix1 تضمین کرد که context refresh قبل از Stage58B اجرا شود تا stale context باعث از دست رفتن signal نشود.

### 6.6 Execution realism / MT5 sandbox

Execution path جدا از edge validation بررسی شد:

- MQL5 EA compile؛
- CSV signal schema؛
- telemetry؛
- AllowTrading و RequireDemoAccount؛
- market closed retcode؛
- invalid volume retcode؛
- tiny demo order.

این قسمت نشان داد که سیستم از نظر اجرای demo قابل راه‌اندازی است، اما عمداً از strategy promotion جدا نگه داشته شد.

---

## 7. مسیر تغییرات و pivotها

### 7.1 از REST/Twelve Data به AMarkets MT5 broker feed

ابتدا داده‌های REST/cloud برای سرعت مناسب بودند، اما چند مشکل ظاهر شد:

- region blocking؛
- API limitations؛
- parsing problems؛
- feed mismatch با broker execution؛
- spread information ناکافی.

پروژه به AMarkets MT5 CSV و SQLite broker-normalized data pivot کرد.

### 7.2 از raw baselineها به cost-aware broker diagnostics

وقتی baselineها در حالت ساده promising بودند، مشخص شد بدون spread و broker cost قابل اعتماد نیستند. بنابراین Stage48 به cost realism اختصاص یافت.

### 7.3 از raw technical signals به context-aware filtering

Raw Stage52 ابتدا مثبت بود اما deteriorate کرد. بنابراین تمرکز از raw volatility squeeze به Stage58B context-aware منتقل شد.

### 7.4 از frequency-seeking به evidence discipline

پروژه بارها وسوسه داشت مسیرهای پرفرکانس را زنده نگه دارد، اما gateها نشان دادند که frequency کافی بدون کیفیت forward کافی، فقط false confidence ایجاد می‌کند.

### 7.5 از order readiness به no-order discipline

Stage61 demo plumbing پاس شد، اما چون edge پاس نشده بود، اجرای order path متوقف ماند. این pivot مهم بود: execution readiness نباید با strategy readiness اشتباه شود.

---

## 8. مشکلات عملی که ایده‌های اصلی را زیر سوال بردند

### 8.1 محدودیت داده و دسترسی

- APIهای خارجی مانند Twelve Data در بعضی مواقع blocked/401 بودند.
- CFTC/COT و منابع خارجی در ایران دسترسی سخت داشتند.
- GitHub Actions cron unreliable بود.
- نیاز به VPN و محدودیت اینترنت باعث شد داده‌گیری cloud دشوار شود.

اثر روی thesis:

- macro/context ایده جذابی بود، اما operationally سخت شد.
- broker feed به عنوان مسیر execution-realistic انتخاب شد.

### 8.2 feed mismatch

XAUUSD CFD broker feed با REST feed یا futures data متفاوت است. این تفاوت شامل:

- spread؛
- session gaps؛
- rollover behavior؛
- broker time offset؛
- wick/tick behavior؛
- symbol specifications.

اثر:

- بسیاری از ایده‌های price-action اگر روی feed غیرواقعی خوب باشند، در broker feed قابل اعتماد نیستند.

### 8.3 parsing / schema / loader fragility

در مراحل مختلف مشکلاتی رخ داد:

- normalized CSV parse failures؛
- timestamp column mismatch؛
- source/timeframe selection errors؛
- tz-naive vs tz-aware errors؛
- stale context tables؛
- file copy zero-byte issue در مسیر MT5/Wine؛
- schema compatibility در EA signal CSV.

این مشکلات با loaderfixها حل شدند، اما نشان دادند که research pipeline بدون schema introspection و smoke test شکننده است.

### 8.4 low-frequency survivor problem

مهم‌ترین مشکل استراتژیک فعلی:

- candidateهای پرفرکانس‌تر در forward/cost-aware fail می‌شوند؛
- candidateهای مثبت باقی‌مانده با context filters کم‌فرکانس می‌شوند؛
- زمان لازم برای رسیدن به evidence کافی زیاد می‌شود؛
- احتمال رسیدن به بن‌بست بالا می‌رود.

این دقیقاً همان نگرانی کاربر در پیام اخیر است.

### 8.5 deterioration در forward

Stage52 نمونه روشن است:

ابتدا:

```text
mean ≈ 10 bps
WR ≈ 75%
```

سپس:

```text
mean ≈ 4 bps
WR ≈ 55%
```

بعد:

```text
mean ≈ 1 bps
WR ≈ 49%
```

آخرین وضعیت:

```text
mean = -2.725 bps
WR = 45.03%
negative candidate mean count = 12/12
```

این نشان می‌دهد که initial forward optimism می‌تواند ناشی از concentrated market regime باشد.

### 8.6 context filter هم هنوز قطعی نیست

Stage58B فعلاً مثبت است، اما:

- evaluated فقط 34؛
- true-forward فقط 48؛
- span فقط حدود 2 روز؛
- max_day_share هنوز 0.458؛
- mean از 10.5 به 4.27 افت کرده.

بنابراین هنوز ممکن است پس از افزایش نمونه همان مسیر Stage52 را طی کند.

---

## 9. نتایج مرحله‌ای

### 9.1 Stage38: COT / macro / GLD / composite overlay

نتیجه:

- چند overlay marginal بودند.
- T1 و overlayها promotion نگرفتند.
- Stage38 archived شد.

برداشت:

- macro context برای طلا مهم است، اما پیاده‌سازی قابل اتکای آن با داده‌های در دسترس و cadence فعلی سخت بود.
- بدون event/news precision، overlayها کافی نبودند.

### 9.2 Stage39: reversal/mean reversion benchmark

نتیجه:

- تحقیق و diagnostics انجام شد.
- چند loader issue رفع شد.
- promotion حاصل نشد.

### 9.3 Stage47: liquidity sweep reversal

نتیجه:

- scan و loader fixes؛
- بعد از اصلاح داده و backfill، candidateها بررسی شدند؛
- survivors = 0؛
- archived.

### 9.4 Stage48: broker spread / cost realism

نتیجه:

- AMarkets M5 spread export validated.
- cost model ساخته شد.
- liquidity sweep در حالت cost-aware هم شکست خورد.
- Stage48 مسیر execution realism را تقویت کرد، نه edge.

### 9.5 Stage49: multi-timeframe trend persistence

نتیجه:

- initial diagnostic survivors داشت؛
- hard audit pass = 0؛
- archived.

### 9.6 Stage50: session open range breakout

نتیجه:

- 96 candidates؛
- hard_audit_pass = 0؛
- archived.

### 9.7 Stage51: volatility squeeze breakout

نتیجه:

- تعدادی candidate از hard audit عبور کردند.
- به forward shadow منتقل شدند.
- این خانواده به مسیر Stage52/58B تبدیل شد.

### 9.8 Stage52: raw volatility squeeze forward shadow

نتیجه نهایی فعلی:

- در ابتدا promising؛
- سپس deterioration؛
- Stage63 demotion؛
- آخرین داده‌ها شکست را قوی‌تر کردند.

آخرین metrics:

```text
total_state_rows = 191
true_forward_signals = 191
evaluated_signals = 191
mean_stress_bps = -2.725
median_stress_bps = -0.570
win_rate = 45.03%
negative_candidate_mean_count = 12
```

تصمیم:

```text
FAILED_FORWARD_REFERENCE_ONLY
```

### 9.9 Stage58A/58B: context-aware Stage51

Stage58A:

- context audit برای Stage51.
- candidateهای context انتخاب شدند.

Stage58B:

- true-forward context shadow.
- آخرین وضعیت:

```text
true_forward_signals = 48
evaluated_signals = 34
pending_signals = 14
mean_stress_bps = 4.266
median_stress_bps = 3.461
win_rate = 61.76%
negative_candidate_mean_count = 0
```

تصمیم:

```text
PRIMARY_CONTEXT_FORWARD_WATCH_NO_PROMOTION
```

### 9.10 Stage60: context-aware parallel scan

نتیجه:

- scan بزرگ؛
- hard_audit_pass_count = 0؛
- archived.

### 9.11 Stage61: demo execution sandbox

نتیجه:

- MQL5 EA compile passed.
- signal parse passed.
- demo order path eventually passed.
- فقط plumbing اثبات شد، نه edge.

### 9.12 Stage63: forward watch decision

تصمیم:

```text
Stage52 raw demoted
Stage58B primary context watch
No promotion
No paper-order
No paper-live
No live
```

---

## 10. وضعیت حاضر

### 10.1 وضعیت استراتژی‌ها

```text
Stage52 raw:
    status = failed/reference only
    role = control stream, not promotion path

Stage58B context:
    status = primary forward watch
    role = only live thesis under observation
    limitation = low sample, low frequency, short span

Stage61 demo:
    status = execution plumbing passed
    role = infrastructure readiness only

All order paths:
    disabled
```

### 10.2 وضعیت داده

داده broker feed سالم به نظر می‌رسد:

- append-only import؛
- parse_fail = 0؛
- bad_timestamp = 0؛
- bad_ohlc = 0؛
- spread numeric coverage در runها خوب؛
- DB state consistent.

بنابراین مشکل فعلی داده نیست؛ مشکل edge است.

### 10.3 وضعیت decision gates

Stage52:

- sample pass؛
- quality fail؛
- span fail؛
- candidate mean fail؛
- no promotion.

Stage58B:

- quality pass فعلی؛
- sample fail؛
- span fail؛
- max_day_share fail؛
- no promotion.

### 10.4 ریسک بن‌بست

ریسک بن‌بست بالا است، چون:

- raw thesis شکست خورد؛
- context thesis کم‌فرکانس است؛
- فرکانس برای forward validation کافی نیست؛
- اگر برای افزایش کیفیت فیلتر بیشتری اضافه شود، فرکانس کمتر می‌شود؛
- اگر فیلتر کمتر شود، کیفیت احتمالاً مثل raw deteriorate می‌کند.

این trade-off همان bottleneck اصلی است.

---

## 11. تحلیل برای متخصص تریدینگ طلا

### 11.1 نکته مثبت

پروژه روی ایده‌های مرتبط با طلا متمرکز بوده، نه الگوهای generic:

- session effects؛
- volatility expansion؛
- spread/rollover؛
- context filters؛
- macro/COT exploration؛
- broker feed realism.

### 11.2 نکته منفی

تا اینجا هیچ thesis پرفرکانس/نیمه‌پرفرکانس، بعد از هزینه و forward، edge پایدار نشان نداده است.

### 11.3 پرسش کلیدی برای متخصص طلا

آیا volatility squeeze intraday روی XAUUSD بدون خبر/real yield/DXY regime واقعاً thesis کافی دارد؟

اگر پاسخ منفی باشد، مسیر Stage58B هم احتمالاً فقط یک فیلتر تصادفی روی یک regime کوتاه است.

### 11.4 احتمال نیاز به pivot معاملاتی

مسیرهای احتمالی بعدی از نظر trading logic:

1. **event-aware gold trading**  
   ورود/عدم ورود نزدیک news، CPI، FOMC، NFP، yields shock.

2. **macro-regime gated technical entry**  
   technical entry فقط وقتی DXY/yields/real-yield regime هم‌راستا است.

3. **session microstructure با داده tick/spread واقعی**  
   اگر قرار است intraday/CFD بمانیم، candle M5 شاید کافی نباشد.

4. **ترک intraday و رفتن به swing/H1-H4**  
   کاهش حساسیت به spread و noise.

5. **benchmark futures vs CFD alignment**  
   بررسی اینکه آیا edge در futures هست اما در CFD از بین می‌رود.

---

## 12. تحلیل برای متخصص توسعه نرم‌افزار

### 12.1 نقاط قوت پیاده‌سازی

- repo مشخص؛
- data path مشخص؛
- append-only importer؛
- SQLite state؛
- clear stage outputs؛
- JSON/MD reportهای قابل audit؛
- true-forward no-backfill؛
- broker cost model؛
- context table refresh؛
- MQL5 demo harness؛
- gate-driven decision.

### 12.2 نقاطی که باید audit شوند

1. **Watermark correctness**
   - آیا Stage52 و Stage58B همیشه فقط بعد از previous watermark signal می‌سازند؟
   - آیا context refresh قبل از Stage58B در همه runها انجام می‌شود؟

2. **No lookahead**
   - آیا context tags فقط از داده‌های قبل/همزمان signal ساخته می‌شوند؟
   - آیا horizon evaluation بعد از signal زمان‌بندی درست دارد؟

3. **Cost application**
   - آیا stress_cost_bps consistent در همه evaluationها اعمال می‌شود؟
   - آیا spread_cost_bps از broker export درست map می‌شود؟

4. **Timezone alignment**
   - server UTC offset = +3؛
   - آیا DST یا broker server drift وجود دارد؟
   - آیا session tags با UTC درست‌اند؟

5. **State idempotency**
   - اجرای مجدد Stage62 نباید duplicate signal بسازد.
   - inserted_new_signals باید با signal_id uniqueness محافظت شود.

6. **Report provenance**
   - هر report باید input files، generated_utc، root و config را ثبت کند.

### 12.3 نتیجه برای توسعه نرم‌افزار

پیاده‌سازی به اندازه کافی بالغ است که بتوان گفت شکست Stage52 احتمالاً شکست implementation نیست. اگر auditor مستقل بخواهد سیستم را بررسی کند، اولویت audit باید روی no-lookahead و cost/time alignment باشد، نه روی زیرساخت کلی.

---

## 13. تحلیل برای استراتژیست ارشد

### 13.1 روند تصمیم‌گیری

پروژه با روش صحیح evidence-driven حرکت کرده:

1. baselineها؛
2. data quality؛
3. broker realism؛
4. hard audit؛
5. true-forward؛
6. demo execution جدا از edge؛
7. demotion بر اساس evidence.

این از نظر governance مثبت است.

### 13.2 مشکل استراتژیک

مسئله این نیست که هنوز یک candidate داریم یا نه. مسئله این است که candidate باقی‌مانده low-frequency است و از یک context filter حاصل شده، در حالی که raw parent thesis شکست خورده است.

این وضعیت از نظر استراتژیک خطرناک است چون:

- زمان تصمیم‌گیری طولانی می‌شود؛
- opportunity cost بالا می‌رود؛
- احتمال overfitting با ادامه فیلترسازی بیشتر می‌شود؛
- پروژه می‌تواند در چرخه‌ی «یک candidate کم‌فرکانس دیگر منتظر بمانیم» گیر کند.

### 13.3 تصمیم‌پذیری پیشنهادی

به جای ادامه نامحدود، باید یک stop/go policy سخت برای Stage58B تعریف شود.

پیشنهاد:

```text
اگر Stage58B پس از رسیدن به:
    evaluated_signals >= 60
یا:
    true_forward_signals >= 100
هر کدام زودتر/معنادارتر شد

این شرایط را نداشت:
    mean_stress_bps >= 2
    median_stress_bps >= 0
    win_rate >= 0.53
    negative_candidate_mean_count <= 1
    max_day_share رو به کاهش و نهایتاً <= 0.35
then:
    archive/pivot
```

همچنین اگر تا چند روز آینده فرکانس همچنان پایین ماند و به 60 evaluated نرسید، باید این هم به عنوان failure mode ثبت شود:

```text
FAIL_BY_INSUFFICIENT_DECISION_FREQUENCY
```

---

## 14. جمع‌بندی نهایی

### 14.1 چه چیزهایی یاد گرفتیم؟

- XAUUSD intraday technical edge با broker cost بسیار سخت‌تر از backtest اولیه است.
- Raw volatility squeeze در forward شکست خورد.
- Context filtering کمک می‌کند، اما به قیمت کاهش فرکانس.
- زیرساخت داده/forward/execution تا حد خوبی بالغ شده است.
- تصمیم‌گیری باید اکنون بیشتر استراتژیک باشد تا صرفاً توسعه‌ای.

### 14.2 وضعیت فعلی در یک جمله

```text
زیرساخت قابل قبول است؛ raw edge شکست خورده؛ تنها context edge باقی‌مانده کم‌فرکانس و هنوز اثبات‌نشده است.
```

### 14.3 توصیه مستقیم

ادامه کوتاه‌مدت Stage58B قابل قبول است، اما فقط با stop/go rule سخت. اگر Stage58B هم پس از رسیدن به حداقل sample افت کند یا فرکانس تصمیم‌پذیر ندهد، باید thesis فعلی را archive کرد و pivot جدی انجام داد؛ نه اینکه با فیلترهای بیشتر آن را مصنوعاً زنده نگه داریم.

---

## 15. گام‌های پیشنهادی بعد از این گزارش

### 15.1 گام فوری

ادامه‌ی Stage62 فقط برای Stage58B evidence accumulation:

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage62_market_open_ops_runner.py \
  --root . \
  --config configs/stage62_market_open_ops.json \
  --out reports/stage62_market_open_ops \
  --execute
```

### 15.2 گام تحلیلی بعدی

اگر Stage58B به evaluated >= 60 رسید:

- Stage64 hard gate / promotion-prep بدون order؛
- تحلیل candidate-level؛
- تحلیل session/day concentration؛
- تصمیم archive یا continue.

### 15.3 گام استراتژیک جایگزین

اگر Stage58B deteriorate کرد یا low-frequency ماند:

- archive thesis فعلی؛
- pivot به event-aware/macro-regime/gold-specific framework؛
- توقف مسیر intraday technical-only XAUUSD.

---

## 16. پیوست: جدول خلاصه مسیرها

| Stage / Family | Thesis | نتیجه |
|---|---|---|
| Stage38 | COT/macro/GLD overlays | marginal، بدون promotion |
| Stage39 | reversal/mean reversion benchmark | بدون promotion |
| Stage47 | liquidity sweep reversal | survivors = 0، archive |
| Stage48 | broker spread/cost realism | زیرساخت cost model، نه edge |
| Stage49 | multi-TF trend persistence | hard audit pass = 0 |
| Stage50 | session open range breakout | hard audit pass = 0 |
| Stage51 | volatility squeeze breakout | وارد forward شد |
| Stage52 | raw volatility squeeze forward | شکست forward، reference only |
| Stage58A/B | context-aware volatility squeeze | primary watch، کم‌نمونه |
| Stage60 | context-aware parallel scan | hard audit pass = 0 |
| Stage61 | demo execution sandbox | plumbing pass، نه edge |
| Stage63 | forward watch decision | Stage52 demote، Stage58B primary watch |

---

## 17. پیوست: معیارهای کلیدی فعلی

### Stage52 raw

```text
true_forward_signals = 191
evaluated_signals = 191
pending_signals = 0
evaluated_mean_stress_bps = -2.725
evaluated_median_stress_bps = -0.570
evaluated_win_rate = 45.03%
negative_candidate_mean_count = 12
decision = FAILED_FORWARD_REFERENCE_ONLY
```

### Stage58B context

```text
true_forward_signals = 48
evaluated_signals = 34
pending_signals = 14
evaluated_mean_stress_bps = 4.266
evaluated_median_stress_bps = 3.461
evaluated_win_rate = 61.76%
negative_candidate_mean_count = 0
decision = PRIMARY_CONTEXT_FORWARD_WATCH_NO_PROMOTION
```

---

## 18. پیام پایانی برای ارزیاب مستقل

اگر این گزارش را یک متخصص مستقل بررسی کند، سؤال اصلی نباید این باشد که «آیا هنوز یک عدد مثبت وجود دارد؟» بلکه باید این باشد:

```text
آیا پروژه بعد از حذف raw edge و باقی ماندن فقط یک context-filtered low-frequency edge، هنوز مسیر تجاری قابل دفاعی دارد؟
```

پاسخ فعلی:

```text
هنوز رد قطعی نشده، اما ریسک بن‌بست بالا است.
ادامه فقط با stop/go rule سخت قابل دفاع است.
هیچ order/paper/live مجاز نیست.
```
