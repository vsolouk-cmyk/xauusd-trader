# XAUUSD Project — اعتبارسنجی نقد ارشد و نقشه حرکت بازطراحی بازارمحور

**نسخه:** 1.0  
**تاریخ تهیه:** 2026-06-16  
**نقش تحلیلی:** تحلیل‌گر ارشد بازار طلا / تریدر حرفه‌ای / ناظر فنی پروژه  
**وضعیت:** گزارش تصمیم‌سازی؛ بدون مجوز اجرای EA، paper-live یا order  
**مبنای گزارش:** خروجی‌های پروژه تا Stage37A + گزارش نقد ارشد `XAUUSD_Senior_Analyst_Review.md`

---

## 1. خلاصه مدیریتی

نتیجه اصلی این بازنگری این است که نقد ارشد با شواهد واقعی پروژه تا حد زیادی هم‌خوان است. پروژه از نظر فنی، داده‌خوانی، ساخت ابزار، تولید گزارش، backtest، forward-shadow و gateهای ریسک مسیر قابل قبولی طی کرده است؛ اما خروجی‌ها نشان می‌دهند که مشکل اصلی در «پیاده‌سازی» نبوده، بلکه در «فریم مسئله» و «انتخاب thesisهای بازارمحور» بوده است.

پروژه ابتدا طلا را عمدتاً به‌عنوان یک مسئله کشف الگوی کمی، زمان‌بندی، session، volatility، handoff و gateهای آماری دید. این نگاه باعث شد مسیر از لحاظ کدنویسی پیش برود، خطاهای فنی مرحله‌به‌مرحله اصلاح شوند، اما در نهایت هیچ مسیر strict review-ready ایجاد نشود.

تا Stage37A، جمع‌بندی پروژه چنین است:

- تمام شاخه‌های Stage36 شامل session/regime، event-risk، volatility compression، market structure، cost-window و non-overlap risk normalization بررسی شدند.
- مجموع strict review-ready row برابر صفر ماند.
- ۸۸ مسیر background باقی ماندند، اما هیچ‌کدام به سطح strict research review نرسیدند.
- بهترین raw edge در شاخه market-structure، یعنی high sweep continuation long، از نظر PF و avg جذاب بود، اما drawdown و risk-normalization آن را از مسیر اجرایی خارج کرد.
- h13/h14 هنوز در background forward confirmation زنده است، ولی هنوز sample کافی برای تصمیم نهایی ندارد.

بنابراین تصمیم درست این نیست که پروژه طلا فوراً کنار گذاشته شود؛ اما ادامه mining همان thesisها هم درست نیست. پروژه باید وارد یک فاز بازطراحی سطح بالا شود:

**Stage38A — Gold Market Thesis Reconstruction**

این فاز باید قبل از هر کدنویسی جدید انجام شود. خروجی آن باید یک نقشه بازار طلا، تعریف regimeهای قابل اندازه‌گیری، ماتریس واکنش conditional، data gap analysis، و سه thesis قابل دفاع از نگاه بازار باشد. تنها پس از آن، کدنویسی Stage39 مجاز است.

---

## 2. وضعیت واقعی پروژه تا نقطه فعلی

### 2.1 مسیر طی‌شده در پروژه

پروژه از یک مسیر baseline-first و research-shadow شروع شد و به‌تدریج این شاخه‌ها را طی کرد:

| محور | Stageهای اصلی | نتیجه |
|---|---|---|
| exogenous/macro اولیه | Stage31 | یک candidate تاریخی پیدا شد، اما recent cadence و forward evidence کافی نبود |
| dense forward و handoff/calendar | Stage32 تا Stage35 | h13/h14 به‌عنوان تنها مسیر زنده باقی ماند، اما pending forward confirmation شد |
| شاخه‌های thesis جدید | Stage36A تا Stage36F | همه شاخه‌ها فقط background شدند، strict candidate صفر ماند |
| branch-level risk normalization | Stage37A | حتی با non-overlap/cooldown هم pass row ایجاد نشد |

### 2.2 وضعیت نهایی Stage37A

Stage37A به‌درستی برای جلوگیری از دو خطا ساخته شد:

1. promote کردن زودهنگام یک مسیر non-strict.
2. kill کردن زودهنگام یک raw edge قبل از تست overlap و risk-normalization.

نتیجه Stage37A:

| شاخص | مقدار |
|---|---:|
| total_strict_review_ready_rows | 0 |
| total_background_rows | 88 |
| nonoverlap_pass_rows | 0 |
| background_watchlist_rows | 20 |
| top_background_variant | stage36e_roll48_high_sweep_continuation_long_h8 |

این خروجی نشان می‌دهد که مشکل «فقط drawdown ناشی از overlap» نبود. حتی پس از کاهش overlap با cooldown، مسیرها strict نشدند. بنابراین پروژه در سطح current-thesis sweep به نقطه توقف تحلیلی رسیده است.

---

## 3. اعتبارسنجی نقد ارشد در برابر شواهد پروژه

### 3.1 ادعای اول: فریم اصلی مسئله غلط بوده است

**ادعای نقد ارشد:** پروژه XAUUSD را به‌عنوان مسئله pattern mining دیده، در حالی که طلا instrument ماکرو-پولیسی و narrative-driven است.

**مطابقت با پروژه:** بالا.

شواهد:

- Stage31 تا Stage37 عمدتاً روی کشف الگوهای کمی، ساعت، session، volatility state، handoff، calendar، sweep و gate آماری جلو رفت.
- هیچ سند اولیه جامع با عنوان Gold Market Map یا conditional reaction model وجود نداشت.
- macro/exogenous داده وارد شد، اما ساختار causal/conditional آن بر اساس narrative بازار طلا تعریف نشد.
- نهایتاً هیچ strict candidate ساخته نشد، در حالی که pipeline فنی به‌اندازه کافی گسترده بود.

**نتیجه اعتبارسنجی:** این نقد معتبر است. مسیر پروژه بیش از حد از پایین به بالا بود و از ابتدا با بازارشناسی طلا هدایت نشد.

---

### 3.2 ادعای دوم: Regime به‌درستی تعریف نشده است

**ادعای نقد ارشد:** Regime واقعی طلا باید بر اساس real yield، DXY character، inflation narrative، safe-haven state، positioning و risk sentiment تعریف شود؛ نه صرفاً session، volatility یا calendar label.

**مطابقت با پروژه:** بالا.

شواهد:

- Stage36B session/regime را تست کرد، اما strict candidate نداد.
- Stage36C event-risk/no-news را تست کرد، اما only-background شد.
- Stage36D volatility compression را تست کرد، اما strict نشد.
- Stage36E market-structure raw edge نشان داد، ولی بدون regime filter drawdown غیرقابل قبول شد.
- Stage37A نشان داد non-overlap هم مشکل را حل نکرد.

**نتیجه اعتبارسنجی:** پروژه regime را عمدتاً به‌صورت proxy آماری دیده است. این برای طلا کافی نیست.

---

### 3.3 ادعای سوم: macro featureها خام و context-free بوده‌اند

**ادعای نقد ارشد:** DXY، real yield، VIX و oil به‌صورت raw column کافی نیستند؛ باید slope، relative position، driver character، surprise و narrative context ساخته شود.

**مطابقت با پروژه:** بالا.

شواهد:

- پروژه macro_daily_regime و macro_context_h1 داشت، اما خروجی Stage31 و Stage36 نشان نداد که macro layer بتواند یک setup عملی را فعال/غیرفعال کند.
- Event surprise magnitude برای CPI، NFP، FOMC، PCE و Claims ساخته نشده بود.
- گزارش‌های event-risk به تفکیک event/no-event رسیدند، اما directionally exploitable edge تولید نکردند.
- expected direction در Stage36C به‌دلیل نبود mapping معتبر event surprise عملاً سیگنال قابل اتکا نداد.

**نتیجه اعتبارسنجی:** نقد درست است. پروژه macro data داشت، اما macro interpretation نداشت.

---

### 3.4 ادعای چهارم: Reaction Logic مدل نشده است

**ادعای نقد ارشد:** یک event یکسان در regimeهای مختلف اثر متفاوت دارد؛ مثلاً CPI بالاتر از انتظار گاهی برای طلا bullish است و گاهی bearish.

**مطابقت با پروژه:** بسیار بالا.

شواهد:

- پروژه event-risk را به clean/event windows تقسیم کرد، اما event × regime × surprise × pre-event drift را مدل نکرد.
- Stage36C نشان داد event-risk volatility را زیاد می‌کند، اما direction و tradability ایجاد نکرد.
- شاخه event expected/contra direction سیگنال مؤثری نداشت.

**نتیجه اعتبارسنجی:** این یکی از خلأهای اصلی پروژه است و باید در Stage38A به‌طور مستقیم حل شود.

---

### 3.5 ادعای پنجم: trade construction واقعی غایب بوده است

**ادعای نقد ارشد:** سیگنال با معامله فرق دارد؛ entry precision، stop logic، target structure، time stop، partial exit و sizing باید از ابتدا تعریف شوند.

**مطابقت با پروژه:** بالا.

شواهد:

- پروژه روی signal-level، horizon، TP/SL و cost stress کار کرده، اما trade construction حرفه‌ای کامل نشده است.
- در high sweep continuation، raw PF مناسب بود؛ ولی بدون entry retest، structural stop، time stop و partial exit، drawdown خراب شد.
- non-overlap کمک کرد، اما کافی نبود؛ یعنی فقط کنترل تعداد سیگنال مشکل را حل نمی‌کند.

**نتیجه اعتبارسنجی:** مسیر بعدی باید trade-first باشد، نه signal-first.

---

### 3.6 ادعای ششم: positioning و flow داده‌های مهم غایب بوده‌اند

**ادعای نقد ارشد:** COT، ETF flows، WGC data، central bank demand، options skew و flow layer باید وارد شوند.

**مطابقت با پروژه:** بالا.

شواهد:

- در خروجی‌های پروژه evidence جدی از COT، ETF flows یا central bank demand دیده نمی‌شود.
- macro featureها بیشتر rate/USD/event محور بوده‌اند.
- نبود positioning باعث شده crowding/squeeze و reversal risk درست مدل نشود.

**نتیجه اعتبارسنجی:** معتبر است. حداقل COT و ETF flow باید وارد data stack شوند.

---

### 3.7 ادعای هفتم: execution realism هنوز کامل نیست

**ادعای نقد ارشد:** broker spread لحاظ شده، اما news slippage، rollover، partial fill، requote و gap مدل نشده‌اند.

**مطابقت با پروژه:** متوسط تا بالا.

شواهد:

- پروژه AMarkets/MT5 H1/M1 و spread را وارد کرده است.
- Stage36F از spread quantile و cost-window guard استفاده کرده است.
- اما slippage مخصوص news، rollover spike، Sunday gap، partial fill و stop skip هنوز به‌صورت مستقل stress نشده‌اند.

**نتیجه اعتبارسنجی:** پروژه نسبت به بسیاری از backtestهای خام واقع‌گراتر است، اما برای paper/live هنوز کافی نیست.

---

## 4. جمع‌بندی اعتبارسنجی

| محور نقد ارشد | میزان انطباق با شواهد پروژه | توضیح |
|---|---:|---|
| فریم اشتباه pattern mining | 90% | مسیر stageها این را تأیید می‌کند |
| نبود Gold Market Map | 95% | سند مرجع بازارمحور قبل از کد وجود نداشت |
| Regime سطحی یا proxy-based | 85% | session/ATR/event جایگزین macro regime شده بود |
| macro feature خام | 85% | feature بود، reaction model نبود |
| نبود event surprise | 95% | از خلأهای قطعی پروژه |
| نبود trade construction کامل | 80% | signal-level غالب بوده است |
| نبود positioning/flow | 90% | COT/ETF/flow وارد نشده‌اند |
| execution realism ناکامل | 70% | بخشی از cost لحاظ شده، اما نه همه |
| نتیجه‌گیری freeze کامل طلا | 40% | هنوز زود است؛ اول Stage38A لازم است |

---

## 5. تصمیم استراتژیک: آیا طلا را کنار بگذاریم؟

پاسخ کوتاه: **نه، هنوز نه.**

اما نباید پروژه با همان رویکرد ادامه پیدا کند.

وضعیت درست چنین است:

1. ادامه variant mining در شاخه‌های فعلی ممنوع.
2. h13/h14 فقط در background forward confirmation بماند.
3. Stage36/37 background watchlist فقط monitor شود.
4. کدنویسی strategy جدید تا پایان Stage38A متوقف شود.
5. پروژه وارد فاز thesis reconstruction شود.

اگر Stage38A نتواند حداقل سه thesis بازارمحور، قابل تست، و قابل execution تولید کند، آن‌وقت freeze کردن طلا تصمیم منطقی خواهد بود.

---

## 6. مسیر حرکت پیشنهادی

### فاز 0 — توقف controlled و snapshot پروژه

**هدف:** جلوگیری از ادامه mining بی‌هدف و ثبت وضعیت فعلی.

**خروجی‌ها:**

- ثبت وضعیت Stage37A
- commit وضعیت فعلی repo
- فعال ماندن فقط scheduler background برای Stage35C
- تهیه archive از گزارش‌ها و CSVهای Stage31 تا Stage37

**عملیات:**

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Freeze current thesis sweep after Stage37A branch-level decision"
git pull --rebase origin main
git push
```

**زمان:** نیم‌روز  
**موفقیت مورد انتظار:** 95%  
**ریسک:** پایین

---

### فاز 1 — Stage38A: Gold Market Thesis Reconstruction

**هدف:** ساخت سند مرجع بازار طلا قبل از کدنویسی جدید.

**خروجی‌های ضروری:**

1. Gold Market Map
2. Regime taxonomy
3. Conditional reaction matrix
4. Setup universe
5. Data gap analysis
6. سه thesis نهایی قابل تست
7. go/no-go criteria

**Regimeهای پیشنهادی:**

| regime | تعریف مفهومی | featureهای لازم |
|---|---|---|
| macro bull | کاهش real yield، ضعف دلار، inflation hedge یا safe-haven demand | real yield slope، DXY slope، VIX، ETF flow |
| macro bear | رشد real yield، دلار قوی، Fed hawkish | real yield level/slope، Fed expectation، DXY |
| range/confusion | سیگنال‌های متضاد، catalyst waiting | ATR compression، mixed macro score |
| safe-haven spike | crisis/war/financial stress | VIX jump، news classifier، DXY/gold co-rise |
| positioning squeeze | crowded positioning و reversal risk | COT percentile، ETF flow reversal |

**زمان:** 3 تا 5 روز  
**موفقیت مورد انتظار:** 75%  
**ریسک:** متوسط؛ چون نیاز به قضاوت بازارمحور دارد، نه فقط کد.

---

### فاز 2 — Data Gap Closure

**هدف:** ساخت داده‌هایی که در پروژه کم بودند.

**داده‌های ضروری:**

| داده | کاربرد | منبع پیشنهادی | اولویت |
|---|---|---|---|
| 10Y real yield level/slope | macro regime | FRED DFII10 | بالا |
| DXY / broad dollar trend | دلار و فشار نرخ | FRED یا داده بازار | بالا |
| CPI/NFP/FOMC/PCE surprise | event reaction model | economic calendar source | بسیار بالا |
| COT gold futures positioning | crowding/squeeze | CFTC COT | بالا |
| Gold ETF flows | investment flow | World Gold Council | بالا |
| VIX/SPX | risk sentiment | FRED/market data | متوسط |
| AMarkets spread/slippage logs | execution realism | broker/MT5 | بالا |
| H4/Daily OHLC | multi-timeframe hierarchy | AMarkets/MT5 | بالا |

**توضیح منابع:**  
CFTC گزارش‌های COT را به‌عنوان گزارش عمومی موقعیت‌های معامله‌گران منتشر می‌کند. FRED سری DFII10 را برای real yield ده‌ساله در دسترس دارد. World Gold Council نیز داده‌های ETF holdings/flows را منتشر می‌کند.

**زمان:** 5 تا 10 روز  
**موفقیت مورد انتظار:** 65% تا 80%  
**ریسک:** متوسط؛ مخصوصاً برای event surprise history و کیفیت forecast/actual.

---

### فاز 3 — Stage38B: Gold Regime Classifier v0

**هدف:** ساخت classifier ساده و قابل توضیح، نه ML سنگین.

**ورودی‌ها:**

- real yield 20d slope
- real yield 12m percentile
- DXY 10d/20d slope
- VIX regime
- gold daily trend 50/200
- ATR percentile
- COT net speculative percentile
- ETF flow 20d sum
- event-risk flag

**خروجی:**

- regime label
- confidence score
- allowed setup types
- blocked setup types

**نمونه rule:**

```text
اگر real_yield_slope_20d < 0
و DXY_slope_20d <= 0
و gold_daily_close > MA50
آنگاه regime = macro_bull
و setupهای مجاز: pullback long، high-sweep continuation، breakout continuation
```

**زمان:** 5 تا 7 روز  
**موفقیت مورد انتظار:** 60% تا 70%  
**ریسک:** متوسط؛ خطر over-engineering و rule inflation.

---

### فاز 4 — Stage38C: Event Surprise Reaction Model

**هدف:** تبدیل event از label ساده به مدل واکنش.

**برای هر event باید ساخته شود:**

| ستون | توضیح |
|---|---|
| event_type | CPI/NFP/PCE/FOMC/Claims |
| actual | مقدار واقعی |
| forecast | consensus |
| previous | مقدار قبلی |
| surprise_z | surprise normalized |
| pre_event_drift_24h | حرکت طلا قبل از event |
| reaction_15m | واکنش اولیه |
| followthrough_4h | ادامه حرکت |
| regime_at_event | regime از classifier |
| reaction_consistency | آیا reaction با regime سازگار بود؟ |

**زمان:** 7 تا 12 روز  
**موفقیت مورد انتظار:** 50% تا 65%  
**ریسک:** بالا؛ چون event forecast history ممکن است ناقص، پولی یا inconsistent باشد.

---

### فاز 5 — Stage39A: Thesis Shortlist و Minimum Viable Setup

**هدف:** تعریف حداکثر سه thesis که واقعاً بازارمحور باشند.

**سه thesis پیشنهادی اولیه:**

#### Thesis 1 — Regime-filtered Structure Continuation

پایه آن از Stage36E آمده است. high-sweep continuation raw edge داشت، اما بدون regime و trade construction drawdown بالا بود.

**منطق بازار:**  
در macro bull یا neutral-bull، sweep high می‌تواند نشانه liquidity acceptance و continuation باشد، نه exhaustion.

**شرایط اولیه:**

- فقط در macro_bull یا neutral_bull
- H4 trend هم‌جهت
- ورود پس از retest یا close confirmation
- stop ساختاری، نه صرفاً fixed
- time stop اگر follow-through رخ نداد

#### Thesis 2 — Event Surprise Follow-through / Fade

**منطق بازار:**  
اثر CPI/NFP/FOMC به surprise magnitude و narrative بستگی دارد. event label تنها کافی نیست.

**شرایط اولیه:**

- فقط eventهای high-impact
- surprise_z معنی‌دار
- regime مشخص
- pre-event drift کنترل‌شده
- ورود بعد از reaction confirmation، نه قبل از خبر

#### Thesis 3 — Positioning Squeeze / Exhaustion

**منطق بازار:**  
وقتی COT/ETF positioning بیش از حد کشیده است، continuation کور خطرناک می‌شود و squeeze/reversal محتمل‌تر است.

**شرایط اولیه:**

- COT percentile extreme
- ETF flow divergence
- daily/H4 exhaustion
- entry فقط روی failure/reclaim

**زمان:** 3 تا 5 روز  
**موفقیت مورد انتظار:** 70% برای تعریف thesis، 30% تا 45% برای یافتن candidate قابل strict review در تست بعدی.

---

### فاز 6 — Stage39B/C/D: Backtest بازارمحور

**هدف:** تست سه thesis، نه mining گسترده.

**اصول تست:**

- هر thesis حداکثر 6 تا 12 variant داشته باشد.
- هر variant باید market logic داشته باشد.
- test فقط در regime مجاز انجام شود.
- خارج از regime مجاز، سیگنال نباید شمرده شود.
- خروجی باید شامل توضیح failure باشد، نه فقط gate.

**معیارهای pass:**

| معیار | آستانه پیشنهادی |
|---|---:|
| PF net | ≥ 1.25 |
| cost-stressed PF | ≥ 1.10 |
| avg R | مثبت و معنادار |
| max DD per 100 trades | قابل کنترل با sizing |
| regime consistency | حداقل 70% سازگار |
| degradation explanation | قابل توضیح |
| forward candidate | بله، اگر logic + stats همسو باشند |

**زمان:** 7 تا 12 روز  
**موفقیت مورد انتظار:** 25% تا 40% برای تولید strict research candidate  
**ریسک:** بالا؛ احتمال overfitting همچنان وجود دارد.

---

### فاز 7 — Forward Shadow بازارمحور

**هدف:** بررسی thesis در داده جدید و واقعی.

**الزامات:**

- forward فقط برای thesisهای strict
- حداقل 10 تا 20 signal برای high-frequency
- برای low-frequency، review کیفی هر trade الزامی است
- هر trade باید با regime، context و setup explanation ذخیره شود

**زمان:** 3 تا 6 هفته  
**موفقیت مورد انتظار:** 20% تا 35%  
**ریسک:** زمان‌بر بودن، sample کم، تغییر regime.

---

### فاز 8 — Paper / Micro Live فقط در صورت pass

**شرط ورود:**

- backtest regime-aware pass
- forward shadow pass
- execution stress pass
- max drawdown قابل sizing
- no unresolved degradation

**زمان:** 2 تا 4 هفته paper  
**موفقیت مورد انتظار:** 10% تا 20% برای رسیدن به micro-live قابل دفاع  
**ریسک:** execution slippage، psychology، broker-specific behavior.

---

## 7. جدول زمان‌بندی کلان

| فاز | عنوان | مدت تقریبی | خروجی اصلی | احتمال موفقیت فاز |
|---|---|---:|---|---:|
| 0 | freeze و snapshot | 0.5 روز | repo و گزارش‌ها تثبیت شوند | 95% |
| 1 | Stage38A Gold Market Map | 3-5 روز | سند thesis reconstruction | 75% |
| 2 | Data Gap Closure | 5-10 روز | داده COT/ETF/event surprise | 65-80% |
| 3 | Regime Classifier v0 | 5-7 روز | regime label قابل تست | 60-70% |
| 4 | Event Surprise Model | 7-12 روز | event reaction DB | 50-65% |
| 5 | Thesis Shortlist | 3-5 روز | سه setup بازارمحور | 70% |
| 6 | Regime-aware Backtest | 7-12 روز | strict research candidate یا no-go | 25-40% |
| 7 | Forward Shadow | 3-6 هفته | اعتبارسنجی forward | 20-35% |
| 8 | Paper/Micro Live | 2-4 هفته | تصمیم تجاری محدود | 10-20% |

**جمع‌بندی زمان:**  
برای رسیدن به تصمیم معتبر research-to-paper، حدود 6 تا 10 هفته لازم است.  
برای رسیدن به micro-live قابل دفاع، در صورت موفقیت مراحل قبل، حدود 10 تا 14 هفته منطقی‌تر است.

---

## 8. ریسک‌های اصلی و راهکار کنترل

| ریسک | شدت | احتمال | کنترل پیشنهادی |
|---|---:|---:|---|
| ادامه mining بدون thesis | خیلی بالا | بالا | freeze همه variantهای فعلی |
| event surprise data ناقص | بالا | متوسط | شروع با CPI/NFP/FOMC محدود |
| overfitting در regime classifier | بالا | متوسط | rule ساده، تعداد کم feature |
| sample کم برای low-frequency thesis | متوسط | بالا | trade review کیفی + forward بلندتر |
| تغییر regime در زمان forward | بالا | متوسط | regime-aware monitoring |
| execution slippage در news | بالا | بالا | no-trade یا post-event only entry |
| drawdown ساختاری در setupهای sweep | بالا | بالا | structural stop + sizing + time stop |
| اعتماد بیش از حد به PF | بالا | بالا | regime consistency و trade construction |
| دسترسی نداشتن به flow data خوب | متوسط | متوسط | COT/ETF رایگان به‌عنوان v0 |
| زمان‌بر شدن پروژه | متوسط | بالا | milestone go/no-go در هر فاز |

---

## 9. برآورد درصد موفقیت کلی

این اعداد تضمین سود نیستند. این‌ها احتمال موفقیت milestoneهای پروژه‌اند.

| سطح موفقیت | تعریف | احتمال تخمینی |
|---|---|---:|
| ساخت سند thesis معتبر | Stage38A thesis قابل دفاع بدهد | 70-80% |
| ساخت data stack کافی | COT/ETF/event/regime قابل استفاده شوند | 60-75% |
| یافتن strict research candidate | حداقل یک setup regime-aware pass شود | 25-40% |
| forward shadow قابل قبول | candidate در forward خراب نشود | 20-35% |
| ورود به paper defensible | بعد از backtest+forward مجاز شود | 15-25% |
| micro-live کوچک قابل دفاع | با risk خیلی محدود | 8-15% |

**تفسیر:**  
پروژه هنوز ارزش یک تلاش بازطراحی دارد. اما احتمال رسیدن به سیستم تجاری پایدار بالا نیست. این طبیعی است؛ trading system development در بازار طلا دشوار است. تفاوت این است که مسیر جدید اگر fail شود، failure آن علمی‌تر و قابل دفاع‌تر خواهد بود.

---

## 10. Go / No-Go پیشنهادی

### Go مشروط

پروژه طلا ادامه پیدا کند اگر Stage38A بتواند:

1. حداقل 3 regime قابل اندازه‌گیری تعریف کند.
2. حداقل 3 thesis بازارمحور با منطق causal بسازد.
3. data gapهای اصلی را با منابع در دسترس پر کند.
4. برای هر thesis trade construction واقعی تعریف کند.
5. مشخص کند چه چیزی باعث no-trade می‌شود.

### No-Go

پروژه freeze شود اگر:

1. event surprise data قابل دسترسی نباشد و نتوان جایگزین ساخت.
2. COT/ETF/flow layer وارد نشود.
3. thesisها دوباره فقط به pattern mining برگردند.
4. after Stage39 هیچ strict research candidate ساخته نشود.
5. h13/h14 هم در forward confirmation fail شود.

---

## 11. مسیر اجرایی پیشنهادی دقیق

### گام اول: ساخت Stage38A بدون کد اجرایی

**عملیات:**  
ساخت یک گزارش MD در repo با عنوان:

```text
docs/STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md
```

**محتوا:**

- Gold Market Map
- Regime taxonomy
- Conditional reaction matrix
- Data gap matrix
- Thesis shortlist
- Trade construction template
- Go/no-go criteria

**زمان:** 3 تا 5 روز

---

### گام دوم: ساخت Data Gap Loaderها

فقط پس از تأیید Stage38A.

**فایل‌های احتمالی:**

```text
app/data_sources/cot_gold_loader.py
app/data_sources/gold_etf_flow_loader.py
app/data_sources/event_surprise_loader.py
app/gold_regime_classifier.py
```

**زمان:** 5 تا 10 روز

---

### گام سوم: ساخت Regime Classifier v0

**اصل مهم:** rule-based، ساده، قابل توضیح.

**خروجی:**

```text
data/reports/stage38b_gold_regime_classifier/stage38b_regime_daily.csv
data/reports/stage38b_gold_regime_classifier/stage38b_regime_h1.csv
```

---

### گام چهارم: Stage39 Thesis Backtests

سه thesis، هرکدام محدود و قابل توضیح.

**نه مجاز:**

- ساخت 1000 variant
- mining کور
- آستانه‌سازی بعد از دیدن نتیجه

**مجاز:**

- 6 تا 12 variant برای هر thesis
- filterهای از پیش تعریف‌شده
- failure diagnostics

---

### گام پنجم: Forward Shadow

فقط اگر Stage39 strict candidate داد.

---

## 12. نتیجه نهایی

نقد ارشد معتبر است. پروژه در نقطه‌ای شکست نخورده که باید طلا را کنار گذاشت؛ بلکه در نقطه‌ای رسیده که روش قبلی باید متوقف شود.

کدنویسی ابزارها خوب بوده است. مشکل در سطح بالاتر بوده:

- بازار طلا قبل از مدل‌سازی نقشه‌برداری نشد.
- macro reaction logic ساخته نشد.
- event surprise وارد نشد.
- positioning/flow غایب بود.
- trade construction کامل نبود.
- regime واقعی با proxyهای ضعیف جایگزین شد.

بنابراین مسیر درست این است:

**نه ادامه mining، نه رها کردن فوری طلا.**

مسیر درست:

**بازسازی thesis بازارمحور، سپس data gap closure، سپس regime-aware backtest، سپس forward shadow.**

اگر این مسیر هم بعد از Stage39/forward شکست بخورد، آن وقت freeze کردن پروژه طلا یک تصمیم منطقی و حرفه‌ای خواهد بود.

---

## 13. تصمیم پیشنهادی نهایی

**تصمیم:** ادامه مشروط پروژه XAUUSD برای یک چرخه بازطراحی 6 تا 10 هفته‌ای.

**شرط:** توقف کامل توسعه strategy جدید تا پایان Stage38A.

**اولین خروجی لازم:**  
`STAGE38A_GOLD_MARKET_THESIS_RECONSTRUCTION.md`

**معیار موفقیت کوتاه‌مدت:**  
در پایان Stage38A باید حداقل سه thesis بازارمحور، قابل تست و قابل execution داشته باشیم.

**اگر این معیار حاصل نشد:**  
پروژه طلا freeze شود، همان‌طور که crypto strategy development freeze شد.

**اگر حاصل شد:**  
Stage38B/38C برای داده و regime classifier شروع شود.
