# Stage38A — Gold Market Thesis Reconstruction Roadmap

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Purpose:** بازسازی thesis بازار طلا پیش از هر کدنویسی  
**Status:** Reference roadmap — no code, no backtest, no EA/paper/live authorization

---

چپ‌چین ادامه می‌دهم.

بر اساس بسته انتقالی، Stage38A را از این نقطه شروع می‌کنیم: بازسازی thesis بازار طلا پیش از هر کدنویسی. فعلاً هیچ Stage39، هیچ loader، هیچ backtest، هیچ variant mining، هیچ EA/paper/live مجاز نیست. بسته انتقالی صریحاً می‌گوید خروجی اصلی این فاز باید `Gold Market Thesis Reconstruction Report` باشد و قبل از کدنویسی باید market map، regimeها، reaction matrix، data gap و thesis shortlist روشن شود.

## تصمیم اجرایی Stage38A

جمع‌بندی من این است:

پروژه XAUUSD هنوز نباید کنار گذاشته شود، اما thesisهای قبلی دیگر نباید mining شوند. شواهد Stage36/37 نشان می‌دهد مشکل اصلی implementation نبوده؛ مشکل این بوده که gold ابتدا به‌عنوان بازار ماکرو-روایت‌محور مدل نشده و بعد روی آن ابزار آماری سوار شده است. گزارش اعتبارسنجی هم دقیقاً همین را تأیید می‌کند: مسیر فنی، backtest، forward-shadow و gateها قابل قبول بوده‌اند، اما strict review-ready row صفر مانده و فریم مسئله باید عوض شود.

پس Stage38A باید این سؤال را جواب دهد:

آیا می‌توانیم برای XAUUSD حداکثر سه thesis بازارمحور، قابل اندازه‌گیری، قابل تست و قابل اجرا بسازیم؟

اگر بله، بعداً Stage39 مجاز می‌شود. اگر نه، پروژه طلا باید مثل crypto strategy branch فریز شود.

---

## 1. چرا pipeline قبلی به خروجی اجرایی نرسید؟

علت اصلی این نبود که کدها بد بودند. علت این بود که پروژه طلا را بیش از حد به‌شکل pattern mining دید.

در طلا، یک الگوی قیمتی روی H1 به‌تنهایی معنی ندارد مگر اینکه بدانیم:

- real yield در حال کاهش است یا افزایش؟
- دلار به‌دلیل risk-off قوی شده یا به‌دلیل rate differential؟
- CPI بالا الان inflation-hedge narrative را فعال می‌کند یا rate-hike fear را؟
- بازار قبل از خبر already positioned بوده یا نه؟
- حرکت طلا continuation است یا liquidation/squeeze؟
- setup در daily/H4 با bias بزرگ‌تر هم‌جهت است یا خلاف آن؟

نقد ارشد دقیقاً همین را نقطه شکست دانسته: پروژه XAUUSD را مثل مسئله بهینه‌سازی الگو دیده، در حالی که طلا instrument ماکرو-پولیسی، روایت‌محور و حساس به liquidity است.

نتیجه عملی:

از اینجا به بعد هر سیگنال باید از thesis شروع شود، نه از pattern.

---

## 2. Gold Market Map v0

طلا را باید به‌عنوان حاصل برخورد چند نیروی اصلی دید:

### لایه اول: نرخ واقعی و انتظارات Fed

این مهم‌ترین ستون thesis است.

رفتار پایه:

- real yield در حال کاهش → معمولاً حمایت از طلا
- real yield در حال افزایش → فشار روی طلا
- Fed dovish repricing → حمایت از طلا
- Fed hawkish repricing → فشار روی طلا

اما این رابطه مکانیکی نیست. اگر کاهش real yield ناشی از crisis باشد، طلا می‌تواند سریع‌تر رشد کند. اگر کاهش real yield همراه با risk-on شدید و خروج از safe haven باشد، اثر آن ضعیف‌تر می‌شود.

### لایه دوم: دلار

DXY همیشه inverse ساده با طلا ندارد.

حالت‌های مهم:

- دلار قوی به‌علت افزایش yield آمریکا → معمولاً bearish برای طلا
- دلار قوی به‌علت risk-off جهانی → ممکن است طلا و دلار هم‌زمان رشد کنند
- دلار ضعیف به‌علت dovish Fed → bullish برای طلا
- دلار ضعیف ولی risk-on شدید → طلا ممکن است فقط آرام رشد کند یا range بماند

پس feature خام DXY کافی نیست. باید character حرکت دلار تعریف شود.

### لایه سوم: inflation narrative

CPI بالا همیشه برای طلا مثبت نیست.

سه حالت اصلی:

- inflation hedge regime: CPI بالاتر از انتظار → bullish برای طلا
- rate-hike fear regime: CPI بالاتر از انتظار → bearish برای طلا
- soft-landing regime: CPI بالاتر از انتظار → واکنش mixed یا کوتاه‌مدت

پس event label کافی نیست. باید surprise magnitude و narrative regime داشته باشیم.

### لایه چهارم: risk sentiment و safe-haven demand

در بحران‌های مالی، جنگ، stress بانکی یا shock ژئوپلیتیک، طلا ممکن است مستقل از real yield کوتاه‌مدت حرکت کند.

ویژگی این فاز:

- حرکت‌های تیز
- شکست mean reversion کوتاه‌مدت
- افزایش spread/slippage
- هم‌جهتی احتمالی طلا و دلار
- افزایش خطر ورود دیرهنگام

در این regime، strategyهای عادی H1 ممکن است خراب شوند، مگر اینکه مخصوص crisis/safe-haven طراحی شده باشند.

### لایه پنجم: positioning و flow

این لایه در پروژه قبلی تقریباً غایب بود.

حداقل داده لازم:

- COT gold futures positioning
- ETF flows مثل GLD/IAU
- تغییرات چند هفته‌ای positioning
- extreme percentileها

کاربرد:

- تشخیص crowded long
- تشخیص crowded short
- تشخیص squeeze risk
- جلوگیری از continuation کور در نقطه‌های اشباع

### لایه ششم: ساختار قیمت و liquidity

اینجا جایی است که Stage36E نزدیک‌ترین raw edge را داشت.

مفاهیم مهم:

- liquidity sweep
- reclaim
- acceptance above/below level
- breakout continuation
- failed breakout
- H4/D1 trend alignment
- session timing

اما market structure بدون regime filter کافی نیست. همان high sweep continuation در macro bull می‌تواند continuation باشد؛ در macro bear یا range/confusion می‌تواند trap باشد.

---

## 3. Regime Taxonomy v0

### Regime 1: Gold Bull / Macro Tailwind

منطق:

طلا در محیطی است که نرخ واقعی افت می‌کند، دلار ضعیف است یا safe-haven/inflation demand فعال است، و ساختار روزانه/H4 صعودی یا حداقل حمایتی است.

معیارهای قابل اندازه‌گیری v0:

- real yield slope 20d منفی
- DXY slope 10d یا 20d منفی یا خنثی
- gold بالای MA50 روزانه یا H4 structure صعودی
- ETF flow مثبت یا COT momentum حمایتی، اگر داده موجود باشد
- VIX normal/elevated ولی نه necessarily crisis

Setupهای مجاز:

- pullback long
- breakout continuation long
- high sweep continuation long
- reclaim long پس از false breakdown

Setupهای ممنوع:

- fade کور rally
- short continuation بدون شکست macro regime
- mean reversion سنگین در روزهای trend

ریسک شکست:

- sudden hawkish Fed repricing
- جهش real yield
- reversal شدید دلار
- crowded long positioning

---

### Regime 2: Gold Bear / Macro Headwind

منطق:

real yield بالا می‌رود، دلار قوی است، Fed hawkish است، و بازار gold rallies را می‌فروشد.

معیارهای قابل اندازه‌گیری v0:

- real yield slope 20d مثبت
- DXY slope 20d مثبت
- gold زیر MA50 روزانه یا H4 lower-high/lower-low
- ETF flow منفی یا COT speculative long کاهش‌یابنده
- event surprises بیشتر به‌نفع hawkish repricing تفسیر می‌شوند

Setupهای مجاز:

- rally fade
- failed breakout short
- low sweep continuation short
- bearish retest after breakdown

Setupهای ممنوع:

- high sweep continuation long
- dip-buying کور
- long بعد از CPI/NFP hawkish بدون confirmation

ریسک شکست:

- geopolitical shock
- banking/credit stress
- sudden dovish Fed pivot
- short squeeze در COT extreme short

---

### Regime 3: Range / Macro Confusion

منطق:

driverها mixed هستند. real yield، دلار، equity، inflation و Fed expectation جهت واحد نمی‌دهند. طلا بین سطوح نوسان می‌کند.

معیارهای قابل اندازه‌گیری v0:

- real yield slope نزدیک صفر یا پرنوسان
- DXY بدون trend واضح
- gold بین MA50/MA200 یا H4 range
- ATR فشرده یا نوسان بی‌جهت
- calendar catalyst نزدیک است ولی هنوز منتشر نشده

Setupهای مجاز:

- range fade فقط با R:R محافظه‌کارانه
- liquidity sweep + reclaim
- reduced size
- no-trade نزدیک eventهای high-impact

Setupهای ممنوع:

- trend continuation کور
- breakout chasing
- افزایش تعداد سیگنال برای جبران نبود edge

ریسک شکست:

- breakout واقعی بعد از catalyst
- false confidence از PFهای کوچک
- زیاد شدن transaction cost نسبت به edge

---

### Regime 4: Safe-Haven Spike

منطق:

shock ژئوپلیتیک، crisis مالی یا risk-off شدید باعث demand ناگهانی برای طلا می‌شود. در این حالت طلا می‌تواند حتی همراه دلار رشد کند.

معیارهای قابل اندازه‌گیری v0:

- VIX jump یا equity drawdown تند
- حرکت هم‌زمان gold و DXY به سمت بالا
- ATR gold جهشی
- widening spread
- news/geopolitical catalyst
- شکست سریع سطوح daily/H4

Setupهای مجاز:

- post-spike continuation فقط بعد از confirmation
- pullback shallow long در صورت حفظ structure
- reduced size
- no-trade در لحظه خبر/شوک

Setupهای ممنوع:

- mean reversion فوری بدون evidence
- ورود market در spread wide
- short کردن صرفاً چون قیمت “زیاد رشد کرده”

ریسک شکست:

- headline reversal
- spread/slippage
- false news
- liquidity vacuum

---

### Regime 5: Positioning Squeeze / Crowding Reversal

منطق:

بازار از نظر positioning بیش از حد یک‌طرفه شده و یک catalyst می‌تواند stop cascade ایجاد کند.

معیارهای قابل اندازه‌گیری v0:

- COT net speculative percentile بالای 90 یا پایین 10
- ETF flow reversal
- divergence بین price و flow
- failed breakout در daily/H4
- event shock خلاف positioning غالب

Setupهای مجاز:

- failed breakout reversal
- reclaim after liquidation
- squeeze continuation در جهت خروج crowd
- low-frequency high-conviction setup

Setupهای ممنوع:

- continuation در جهت crowd بدون confirmation
- leverage بالا
- تکیه روی H1 signal بدون positioning context

ریسک شکست:

- crowded positioning می‌تواند مدت طولانی ادامه پیدا کند
- timing سخت است
- sample کم خواهد بود

---

## 4. Conditional Reaction Matrix v0

### CPI Surprise × Regime

CPI بالاتر از انتظار:

- در inflation-hedge regime: احتمالاً bullish gold
- در rate-hike fear regime: احتمالاً bearish gold
- در soft-landing/range: واکنش اولیه ممکن است fake باشد
- در safe-haven regime: اثر CPI ممکن است زیر سایه crisis قرار بگیرد

CPI پایین‌تر از انتظار:

- در Fed-pivot narrative: bullish gold
- در recession fear: bullish یا mixed
- در risk-on شدید: gold ممکن است ضعیف‌تر از انتظار عمل کند

### NFP Surprise × Fed Regime

NFP قوی:

- Fed hawkish/active tightening: bearish gold
- Fed paused/dovish: اثر محدود یا risk-on
- recession fear: کاهش ترس رکود ممکن است safe-haven demand را کم کند

NFP ضعیف:

- pivot expectation: bullish gold
- recession panic: bullish safe-haven
- stagflation fear: بسیار regime-dependent

### FOMC Tone × Pre-positioning

FOMC hawkish:

- اگر بازار از قبل hawkish positioned باشد: sell-the-rumor/buy-the-fact ممکن است
- اگر بازار dovish priced باشد: gold downside شدیدتر
- اگر COT crowded short باشد: واکنش bearish ممکن است پایدار نماند

FOMC dovish:

- در macro bull: continuation long
- در crowded long: spike سپس profit-taking
- در range: fake breakout محتمل

### DXY Impulse × Character

DXY up به‌علت rate/yield:

- bearish gold

DXY up به‌علت global risk-off:

- gold می‌تواند هم‌زمان رشد کند

DXY down به‌علت dovish Fed:

- bullish gold

DXY down به‌علت global risk-on:

- bullish effect ممکن است ضعیف باشد

### Real Yield Slope × Gold Trend

real yield down + gold above MA50:

- continuation long thesis مجاز

real yield up + gold below MA50:

- rally fade/short thesis مجاز

real yield mixed + gold range:

- فقط mean-reversion/sweep-reclaim با سایز کم

real yield up ولی gold strong:

- احتمال safe-haven/central-bank/positioning driver؛ raw yield signal را نباید تنها استفاده کرد

---

## 5. Data Gap Analysis

داده‌هایی که برای Stage38A/Stage39 واقعاً لازم‌اند:

### ضروری سطح 1

- 10Y real yield level و slope
- DXY یا proxy معتبر دلار
- CPI/NFP/PCE/FOMC actual/forecast/previous
- gold D1/H4/H1 OHLC
- broker spread history
- event timestamps دقیق

بدون این‌ها Stage39 نباید شروع شود.

### ضروری سطح 2

- CFTC COT gold futures positioning
- ETF flows یا holdings مثل GLD/IAU
- VIX/SPX برای risk sentiment
- Fed expectation proxy
- ATR percentile و volatility regime

این‌ها برای regime-aware testing لازم‌اند.

### مفید اما غیرضروری در v0

- options skew
- LBMA clearing
- WGC central bank demand فصلی
- intraday depth/DOM
- news classifier پیشرفته

فعلاً نباید پروژه را به این‌ها وابسته کنیم.

---

## 6. Thesis Shortlist v0

حداکثر سه thesis مجاز داریم.

### Thesis 1: Regime-filtered Structure Continuation

منطق:

Stage36E نشان داد high sweep continuation long خام‌ترین edge نزدیک به market logic بوده، اما بدون regime و trade construction drawdown آن زیاد شد. در macro bull یا neutral-bull، sweep سطح بالا می‌تواند نشانه acceptance و continuation باشد، نه exhaustion.

اجرا فقط در:

- macro bull
- neutral-bull
- safe-haven continuation با spread قابل قبول

اجرا ممنوع در:

- macro bear
- range/confusion
- crowded long extreme بدون confirmation

Minimum setup:

- D1/H4 bias صعودی
- real yield slope منفی یا خنثی
- DXY مخالف طلا نباشد یا safe-haven co-rise تشخیص داده شود
- sweep سطح H4/48h high
- close/acceptance بالای سطح
- entry روی retest یا confirmation، نه chase
- stop زیر reclaim/sweep structure با ATR buffer
- time stop اگر طی 3 تا 5 کندل H1 follow-through نیامد
- partial exit در 1R تا 1.5R، ادامه با trailing یا سطح بعدی

معیار ابطال thesis:

اگر در macro bull هم high sweep continuation بعد از cost و structural stop مثبت نباشد، این thesis حذف شود.

---

### Thesis 2: Event Surprise Follow-through / Fade

منطق:

خبر به‌خودی‌خود edge نیست. surprise magnitude و regime تعیین می‌کند طلا باید follow-through کند یا fade شود.

اجرا فقط در:

- CPI/NFP/PCE/FOMC
- surprise_z معنی‌دار
- regime قبل از event مشخص
- spread بعد از event قابل قبول
- ورود فقط post-event، نه قبل از خبر

Minimum setup:

- ثبت actual/forecast/previous
- محاسبه surprise_z
- pre-event drift 24h
- reaction 15m
- confirmation در 30m تا 1h
- ورود فقط اگر direction با regime سازگار باشد
- no-trade اگر reaction با regime conflict دارد
- time stop کوتاه، چون edge خبری decay دارد

نمونه منطق:

CPI بالاتر از انتظار در rate-hike fear regime → فقط short/fade gold rallies مجاز.

CPI پایین‌تر از انتظار در Fed-pivot regime → long continuation مجاز.

معیار ابطال thesis:

اگر surprise_z × regime نتواند جهت follow-through 4h/24h را بهتر از event label خام توضیح دهد، این thesis حذف شود.

---

### Thesis 3: Positioning Squeeze / Exhaustion

منطق:

وقتی positioning بیش از حد یک‌طرفه می‌شود، continuation کور خطرناک است. COT و ETF flow می‌توانند نشان دهند بازار overcrowded است یا نه.

اجرا فقط در:

- COT percentile extreme
- ETF flow reversal یا divergence
- daily/H4 exhaustion
- failed breakout/reclaim
- low-frequency review

Minimum setup:

- COT net speculative percentile > 90 یا < 10
- تغییر 4 هفته‌ای positioning
- ETF flow 20d خلاف price
- شکست سطح daily/H4 و برگشت
- entry فقط پس از failure confirmation
- stop ساختاری
- target حداقل 2R یا سطح daily بعدی
- sample کم پذیرفته می‌شود ولی هر trade باید کیفی review شود

معیار ابطال thesis:

اگر COT/ETF extremeها فقط noisy باشند و نتوانند drawdown setupهای continuation را کاهش دهند، این thesis حذف شود.

---

## 7. Validation Plan برای Stage39، فقط در صورت عبور Stage38A

Stage39 نباید discovery factory باشد.

قواعد:

- هر thesis حداکثر 6 تا 12 variant
- همه filterها باید قبل از backtest تعریف شوند
- هیچ threshold mining بعد از دیدن نتیجه مجاز نیست
- outside-regime trades باید جداگانه گزارش شوند
- failure diagnostics الزامی است

معیارهای pass پیشنهادی:

- net PF حداقل 1.25
- cost-stressed PF حداقل 1.10
- avg R مثبت
- drawdown قابل sizing
- regime consistency حداقل 70%
- performance در regime مجاز بهتر از کل داده
- failureها قابل توضیح باشند
- forward shadow بعد از backtest مجاز شود، نه paper/live

---

## 8. Kill Criteria

پروژه باید در همین مسیر فریز شود اگر:

1. نتوانیم حداقل سه regime قابل اندازه‌گیری بسازیم.
2. event surprise data قابل دسترس یا قابل جایگزینی نباشد.
3. COT/ETF یا حداقل یک proxy positioning وارد نشود.
4. thesisها دوباره به pattern mining خام برگردند.
5. trade construction برای هر thesis روشن نشود.
6. Stage39 بعدی هیچ strict research candidate ندهد.
7. h13/h14 هم در background forward confirmation fail شود.

---

## 9. Stage39 Readiness Decision

وضعیت فعلی:

Stage39 هنوز مجاز نیست.

دلیل:

هنوز این موارد به‌صورت نهایی بسته نشده‌اند:

- معیار کمی regimeها
- event surprise schema
- data source feasibility
- trade construction دقیق برای هر thesis
- validation metric نهایی
- kill criteria برای هر thesis

بنابراین decision فعلی:

Stage38A: GO  
Stage39: NO-GO فعلاً  
EA/paper/live/order: NO-GO قطعی

---

## 10. خروجی قابل تبدیل به فایل repo

نام سند پیشنهادی:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
```

ساختار پیشنهادی سند:

```text
1. Executive Decision
2. Why Previous Pipeline Failed
3. Gold Market Driver Map
4. Regime Taxonomy
5. Conditional Reaction Matrix
6. Data Gap Analysis
7. Thesis Shortlist
8. Minimum Viable Setup Definitions
9. Validation Plan
10. Kill Criteria
11. Stage39 Readiness Decision
```

---

## گام بعدی

گام بعدی باید تکمیل همین Stage38A به نسخه قابل commit باشد، نه کدنویسی.

پیشنهاد عملی:

نسخه کامل فایل `docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md` آماده شود؛ فقط یک فایل Markdown مستند، بدون هیچ کد اجرایی، بدون تغییر app، بدون loader، بدون backtest.

---

## Copy to repo

برای کپی مستقیم این فایل مرجع داخل ریپو:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
cp ~/Downloads/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md docs/STAGE38A_GOLD_MARKET_THESIS_ROADMAP.md
git status --short
git add -A
git commit -m "Add Stage38A gold market thesis roadmap"
git pull --rebase origin main
git push
```
