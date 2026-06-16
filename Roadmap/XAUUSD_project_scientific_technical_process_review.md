# گزارش علمی و فنی بازنگری پروژه XAUUSD

**موضوع:** بازسازی فرآیندی، فنی و تحلیلی پروژه پژوهش و طراحی سیستم معاملاتی طلا  
**نسخه:** Review v1  
**تاریخ تهیه:** 2026-06-16  
**وضعیت:** گزارش بازنگری سطح‌بالا؛ نه patch اجرایی، نه مجوز paper/live، نه مجوز EA/order

---

## 1. خلاصه مدیریتی

این پروژه با هدف ساخت یک سیستم معاملاتی پایدار و قابل استفاده تجاری برای XAUUSD آغاز شد. مسیر اولیه، از نظر مهندسی نرم‌افزار، مرحله‌بندی، کنترل ریسک، جلوگیری از live/paper زودهنگام، و ثبت خروجی‌ها منظم بود. pipeline داده، گزارش‌سازی، gateها، shadow/forward logic، scheduler محلی، و auditهای مرحله‌ای به‌تدریج ساخته شدند و در بسیاری از نقاط، خطاهای پیاده‌سازی شناسایی و اصلاح شدند.

با این حال، نتیجه فعلی پروژه مثبت تجاری نیست. پس از بررسی چند خانواده الگو، چند مسیر exogenous، خانواده‌های dense-forward، handoff، calendar، volatility transition، session/regime، event-risk، volatility compression، market-structure sweep/reclaim، broker cost-window guard و در نهایت non-overlap risk normalization، هیچ candidate به سطح strict review-ready نرسید. آخرین جمع‌بندی Stage37A نشان داد که مجموع strict review-ready برابر صفر است، در حالی که 88 مسیر background باقی مانده‌اند و هیچ مسیر non-overlap نیز pass نشده است.

این نتیجه نباید به‌صورت ساده به معنای «طلا سیستم‌پذیر نیست» تعبیر شود. نتیجه دقیق‌تر این است: در چارچوب thesisها، ویژگی‌ها، تعریف رویدادها، داده‌ها، broker feed و معیارهایی که تاکنون استفاده شد، هیچ مسیر قابل تبدیل به سیستم اجرایی پایدار پیدا نشده است.

نکته مهم این است که پروژه از نظر توسعه فنی شکست نخورده است؛ مسئله اصلی احتمالاً در سطح طراحی مسئله، انتخاب thesis، ساختار فهم بازار طلا، و کافی نبودن مجموعه ویژگی‌ها بوده است. ما طلا را بیش از حد به‌عنوان یک مسئله pattern mining کمی با چند gate آماری دیده‌ایم، در حالی که XAUUSD یک دارایی شدیداً regime-driven، narrative-driven و macro-liquidity-sensitive است. اگر از ابتدا یک مدل بالادستی از بازار طلا، محرک‌های جریان سرمایه، روایت‌های نرخ بهره، دلار، ریسک سیستماتیک، session liquidity، event surprise، positioning، و ساختار execution طراحی می‌شد، مسیر research احتمالاً متفاوت می‌بود.

بنابراین این گزارش با دو هدف نوشته شده است:

1. بازسازی کامل و دسته‌بندی‌شده مسیر پروژه از ابتدا تا Stage37A.
2. آشکار کردن جاهای خالی و ضعف‌های سطح بالا، به‌گونه‌ای که با نگاه یک تحلیل‌گر ارشد و تریدر حرفه‌ای طلا بتوان تصمیم گرفت پروژه باید متوقف شود، بازطراحی شود، یا با یک چارچوب thesis-driven جدید ادامه پیدا کند.

نتیجه پیشنهادی این گزارش: پرونده طلا فعلاً نباید مثل کریپتو بسته شود، اما ادامه دادن به همین سبک discovery نیز نباید انجام شود. گام بعدی درست، یک بازطراحی بازارمحور است: **Gold Market Thesis Reconstruction**، پیش از هر patch یا stage جدید.

---

## 2. هدف اولیه پروژه و فلسفه کاری

هدف نهایی پروژه ساخت یک سیستم معاملاتی XAUUSD بود که بتواند به‌صورت تدریجی از research به shadow، سپس paper-order، و فقط در صورت موفقیت کافی به live نزدیک شود. از ابتدا چند اصل درست تعریف شد:

- تمرکز روی یک نماد: XAUUSD.
- اولویت با baselineهای ساده، نه ML مستقیم.
- ممنوعیت EA/paper/live تا عبور از gateهای forward و risk.
- توجه به broker spread، slippage و تفاوت feed.
- استفاده از داده‌های AMarkets/MT5 برای نزدیک‌تر شدن به محیط execution واقعی.
- استفاده از GitHub/Local pipeline برای تولید گزارش‌های مرحله‌ای.
- ثبت خروجی‌ها در فایل‌های Markdown/JSON/CSV.
- kill-switch برای جلوگیری از ادامه دادن مسیرهای ضعیف.

از نظر فرآیندی، این فلسفه از پروژه کریپتو بهتر بود، چون در XAUUSD از ابتدا سعی شد مسیر به سمت live زودهنگام نرود. اما یک مشکل اساسی باقی ماند: baseline-first اجرا شد، ولی market-thesis-first به‌صورت کافی انجام نشد. یعنی قبل از ساخت baselineها، مدل بالادستی بازار طلا به‌اندازه کافی ساخته نشد.

در بازار طلا، baseline خوب معمولاً از دل یک تز بازار بیرون می‌آید، نه صرفاً از تست آماری روی ساعت، سشن، سقف/کف، یا رویداد. برای نمونه، اینکه «بعد از sweep سقف 48 ساعته ادامه long دارد» می‌تواند یک raw edge باشد، اما بدون دانستن اینکه این رفتار در کدام regime از نرخ بهره واقعی، دلار، risk-off، liquidity، یا session positioning رخ می‌دهد، به سختی به سیستم پایدار تبدیل می‌شود.

---

## 3. نمای کلی فرآیند پروژه

پروژه را می‌توان به چند فاز اصلی تقسیم کرد:

### 3.1 فاز زیرساخت و انتقال پروژه

در ابتدای مسیر، پروژه از تجربه قبلی crypto جدا شد و XAUUSD به‌عنوان محور مستقل انتخاب شد. اسناد پایه شامل project rules، transfer brief، baseline-first plan و بسته انتقال Stage31 ساخته شدند. محیط محلی روی MacBook و repo محلی `~/Desktop/xauusd-trader` تثبیت شد. دیتابیس اصلی `data/local/xauusd_local_store.sqlite` و جدول candles با نام `bars` به‌عنوان منبع OHLC اصلی تثبیت شد.

از نظر فنی، این فاز موفق بود. پروژه دارای ساختار فایل، DB، گزارش، workflow و استاندارد اجرای stageها شد. همین نظم باعث شد خطاهای بعدی قابل شناسایی باشند.

### 3.2 فاز exogenous و macro ingestion

در Stage31، داده‌های exogenous و macro وارد شدند. منابعی مثل DXY، US10Y، real yield، VIX، SPX و oil وارد pipeline شدند. هدف این بود که gold تنها به قیمت خودش محدود نشود و drivers خارجی نیز دیده شوند.

اما نتیجه عملی این مسیر به candidate تجاری نرسید. مهم‌ترین candidate exogenous، با وجود performance تاریخی خوب، cadence forward پایینی داشت و در نهایت به watchlist منتقل شد. این مرحله نشان داد که ورود داده macro به‌تنهایی کافی نیست.

ضعف سطح بالا در این بخش این بود که macro به‌صورت feature ingestion انجام شد، نه به‌صورت market reaction model. برای طلا، متغیرهایی مثل real yield یا DXY فقط وقتی معنا دارند که در یک context تفسیر شوند:

- بازار در regime تورمی است یا disinflation؟
- نرخ واقعی در حال افزایش است یا کاهش؟
- حرکت دلار ناشی از risk-off است یا yield differential؟
- طلا به news به‌عنوان safe haven واکنش می‌دهد یا به‌عنوان asset بدون yield؟
- event surprise چقدر بوده، نه فقط event label چیست؟
- بازار قبل از خبر priced-in بوده یا نه؟

بنابراین شکست macro در این پروژه نباید به معنی بی‌اثر بودن macro روی طلا تلقی شود. احتمال قوی‌تر این است که featureهای macro به شکل ناکافی و غیرساختاری وارد شدند.

### 3.3 فاز dense-forward و candidate discovery

در Stage32، تمرکز روی dense forward shadow و candidate supply بود. هدف این بود که از میان تعداد زیادی candidate، مسیرهایی با forward activity و review readiness پیدا شود.

در Stage32A مشخص شد candidate registry بزرگ است، اما review-ready کافی نداریم. Stage32B و Stage32C queue ساختند و candidateهایی مثل `calendar_drop_friday_h9` و سپس خانواده handoff/h13/h14/h15 ظاهر شدند. در این مرحله اولین مسیرهای امیدوارکننده پیدا شدند، اما مشکل اصلی low frequency و کم بودن forward sample بود.

این فاز از نظر مهندسی و انضباط آماری مفید بود، اما از نظر بازارمحور یک خطر داشت: focus بیش از حد روی candidate mining. وقتی هزاران ترکیب تولید و gate می‌شوند، ممکن است یک مسیر آماری ظاهراً جذاب پیدا شود، اما بدون توضیح بازارمحور مشخص نباشد چرا باید در آینده هم پایدار بماند.

### 3.4 فاز family robustness و handoff path

در Stage33، خانواده handoff بررسی شد. ابتدا h13/h14/h15 دیده شد. h15 ضعف نشان داد، و سپس خانواده repaired h13+h14 ساخته شد. Stage33C نشان داد که h13+h14 از نظر aggregate performance قوی است: PF بالا، win rate بالا، tail PF خوب و cost-stress قابل قبول. اما Stage33D آن را به‌دلیل recent degradation مسدود کرد. آخرین batch ضعیف بود و نسبت degradation پایین آمد.

این یکی از تصمیم‌های درست پروژه بود. اگر صرفاً به aggregate نگاه می‌کردیم، شاید به pre-paper نزدیک می‌شدیم. اما Stage33D جلوی این خطا را گرفت. از دید تریدر حرفه‌ای، اینجا نشانه مهمی بود: یک pattern ممکن است در گذشته زیبا باشد، اما اگر آخرین regime آن را خراب کرده، نباید فقط با میانگین تاریخی اعتماد کرد.

با این حال، همینجا نیز ضعف نگاه بازارمحور دیده می‌شود. ما فهمیدیم h13/h14 recently degraded شده، اما به جای پاسخ به این سؤال که «چرا این degradation رخ داده؟»، بیشتر به ساخت gate و short confirmation رفتیم. سؤال‌های سطح بالا باید این‌ها می‌بودند:

- آیا degradation هم‌زمان با تغییر volatility regime بود؟
- آیا دلار/real yield در این دوره تغییر جهت داده بود؟
- آیا ساختار session عوض شده بود؟
- آیا gold در این دوره خبرمحورتر شده بود؟
- آیا spread/broker condition تغییر کرده بود؟
- آیا h13/h14 به یک market state خاص وابسته بود؟

### 3.5 فاز acceleration و targeted variants

Stage34 و Stage35 برای جلوگیری از انتظار passive ساخته شدند. وقتی h13/h14 low-frequency شد، مسیرهای parallel fast path و targeted variant تعریف شد. Stage35A variant specs ساخت، Stage35B strict evaluator اجرا کرد، و Stage35C trigger/pruner ساخت.

خروجی این فاز این بود که فقط h13/h14 recency-guard به حالت pending forward confirmation باقی ماند. new signal count فقط 1 بود و حداقل 5 event جدید لازم شد. بنابراین این path به background رفت.

این تصمیم از نظر مدیریت زمان درست بود، اما از نظر تحلیل بازار یک نشانه هشدار بود: پروژه کم‌کم از discovery به repair و micro-variant نزدیک می‌شد، بدون اینکه thesis بالادستی عوض شده باشد. یعنی با اینکه ظاهر کار parallel بود، عملاً هنوز در فضای همان نوع الگوها حرکت می‌کردیم.

### 3.6 فاز Stage36: شروع thesisهای جدید

بعد از بحث درباره اینکه نباید فقط منتظر h13/h14 بمانیم، Stage36A پنج شاخه thesis جدید تعریف کرد:

1. session/regime baseline
2. event-risk/no-news guard
3. volatility compression breakout
4. market-structure sweep/reclaim
5. broker cost-window guard

این یک اصلاح جهت‌گیری مهم بود. برای نخستین بار پس از چند stage، پروژه از variant repair وارد thesis sweep جدید شد. اما حتی این thesisها نیز بیشتر به شکل baselineهای تکنیکال/اجرایی تعریف شدند، نه به‌عنوان مدل کامل بازار طلا.

نتایج:

- Stage36B session/regime: strict candidate نداد؛ یک مسیر background ضعیف.
- Stage36C event-risk/no-news: strict candidate نداد؛ event-risk volatility را بالا برد اما direction قابل اتکا نداد.
- Stage36D volatility compression: strict candidate نداد؛ چند مسیر background اما cost/drawdown مشکل داشت.
- Stage36E market-structure: قوی‌ترین raw edge را نشان داد، مخصوصاً high sweep continuation long؛ اما drawdown مانع strict شد.
- Stage36F broker cost-window: فیلترهای spread/session/rollover نتوانستند drawdown را تا حد strict اصلاح کنند.

Stage36 نشان داد که raw edge کاملاً صفر نیست. به‌خصوص market-structure high sweep continuation long عملکرد خام خوبی داشت. اما مشکل این بود که raw edge به executable risk تبدیل نشد.

### 3.7 فاز Stage37A: تصمیم سطح branch

Stage37A برای پاسخ به یک سؤال مهم ساخته شد: آیا drawdown بد به‌خاطر overlap و سیگنال‌های تکراری است یا واقعاً edge قابل اجرا نیست؟

non-overlap و cooldown تست شد. نتیجه همچنان strict نبود. هیچ pass row تولید نشد. top background variant همچنان `stage36e_roll48_high_sweep_continuation_long_h8` باقی ماند، اما nonoverlap نیز نتوانست آن را به strict review برساند.

این stage نقطه تصمیم مهم است. از اینجا به بعد، ادامه دادن به همان style از variant mining توجیه ندارد. اگر پروژه ادامه پیدا کند، باید با بازطراحی مسئله ادامه پیدا کند، نه با patchهای بیشتر روی همان شاخه‌ها.

---

## 4. ارزیابی فنی پیاده‌سازی

از نظر فنی، پروژه نقاط قوت زیادی داشت:

- stageها تفکیک‌شده و قابل audit بودند.
- خروجی‌ها در Markdown/JSON/CSV ثبت شدند.
- هر stage تصمیم صریح داشت.
- no EA / no paper-live / no order تقریباً در همه مراحل رعایت شد.
- data-source audit اضافه شد.
- bugهای timestamp و schema در Stage36B شناسایی و اصلاح شدند.
- scheduler محلی برای background monitoring ساخته شد.
- gateها جلوی promotion زودهنگام را گرفتند.
- cost stress و drawdown gate وارد شدند.
- recent degradation و tail checks اضافه شدند.

بنابراین، در سطح نرم‌افزار، پروژه قابل دفاع است. خطاهای اجرایی وجود داشتند، اما اصلاح شدند و معمولاً خروجی stageها پس از اصلاح معتبر شد. مشکل اصلی به نظر نمی‌رسد که bug نرم‌افزاری پنهان باشد؛ هرچند همیشه باید احتمال bug را صفر ندانست. مشکل اصلی بیشتر در تعریف مسئله و ورودی تحلیلی است.

ضعف فنی مهم‌تر، نه در کد، بلکه در architecture تحقیق بود: pipeline بسیار خوب ساخته شد، اما objective و hypothesis hierarchy به اندازه کافی trader-led نبود. یعنی سیستم برای تست منظم hypothesisها آماده بود، اما خود hypothesisها از یک مدل عمیق بازار طلا استخراج نشده بودند.

---

## 5. ارزیابی بازارمحور و ضعف نگاه بالادستی

از دید تحلیل‌گر و تریدر حرفه‌ای طلا، مشکل پروژه این نیست که «طلا قابل معامله نیست». مشکل این است که ما بازار طلا را بیش از حد به یک مسئله کمّی عمومی تبدیل کردیم.

طلا چند ویژگی خاص دارد:

1. دارایی بدون yield است و به نرخ بهره واقعی حساس است، اما این حساسیت خطی و ثابت نیست.
2. به دلار حساس است، اما دلار در حالت risk-off می‌تواند همراه یا مخالف طلا حرکت کند.
3. در eventهای macro، واکنش اولیه و واکنش ثانویه می‌توانند متفاوت باشند.
4. narrative بازار مهم است: inflation hedge، safe haven، central bank demand، rate-cut expectations، liquidity stress، geopolitical risk.
5. سشن‌ها فقط ساعت نیستند؛ سشن‌ها محل تغییر order flow و liquidity هستند.
6. بازار CFD/MT5 با futures و spot institutional تفاوت execution دارد.
7. spread و rollover و broker microstructure می‌تواند edgeهای کوچک را نابود کند.
8. بازار طلا در برخی دوره‌ها trend-following و در برخی دوره‌ها mean-reverting است.

پروژه بسیاری از این موارد را به‌صورت پراکنده لمس کرد، اما به یک چارچوب منسجم تبدیل نکرد. ما session را تست کردیم، event را تست کردیم، macro را وارد کردیم، structure را تست کردیم، اما این‌ها را زیر یک مدل state machine بازار طلا قرار ندادیم.

مثلاً یک مدل سطح بالا می‌توانست این باشد:

- ابتدا regime macro را تشخیص بده: real-yield falling/rising، dollar trend، risk regime، inflation surprise، policy expectation.
- سپس regime intraday را تشخیص بده: Asia compression، London impulse، NY continuation/reversal، rollover risk.
- سپس setup را انتخاب کن: sweep continuation، sweep reclaim، breakout، fade.
- سپس execution guard را اعمال کن: spread، news blackout، session liquidity، max daily loss، one-position cap.
- سپس outcome را با expectation همان regime بسنج، نه با یک benchmark واحد برای همه شرایط.

در پروژه فعلی، این hierarchy به‌صورت کامل وجود نداشت. ما اغلب setup را مستقیم تست کردیم و بعد با gateهای آماری تصمیم گرفتیم.

---

## 6. چرا macro edge پیدا نشد؟

یافت نشدن macro edge در پروژه فعلی نباید به‌صورت «macro برای gold بی‌فایده است» تفسیر شود. برای طلا، macro یکی از اصلی‌ترین محرک‌هاست. اگر در پروژه ما macro edge پیدا نشده، احتمالاً علت یکی از این موارد است:

### 6.1 macro به‌صورت سطحی وارد شد

داشتن ستون‌های DXY، real yield، oil، VIX و SPX کافی نیست. این‌ها باید به signalهای اقتصادی قابل معامله تبدیل شوند. مثلاً:

- real yield level مهم است یا change؟
- change در چه horizon؟ 1d، 5d، 20d؟
- حرکت DXY ناشی از rate differential است یا safe-haven demand؟
- VIX بالا یعنی gold safe haven می‌شود یا liquidity selling رخ می‌دهد؟
- oil بالا یعنی inflation hedge مثبت برای gold یا rate expectation منفی؟

### 6.2 event surprise وجود نداشت

Calendar event بدون surprise magnitude معمولاً کافی نیست. NFP، CPI، FOMC، PCE و claims زمانی قابل معامله‌اند که مقدار actual/forecast/previous و deviation معنی‌دار وارد شود. صرفاً event label یا expected direction معمولاً edge نمی‌سازد.

### 6.3 regime interaction مدل نشد

طلا در یک regime به CPI بالا مثبت واکنش می‌دهد، چون inflation hedge narrative فعال است؛ در regime دیگر به همان CPI بالا منفی واکنش می‌دهد، چون rate hike expectation تقویت می‌شود. اگر این تعامل مدل نشود، میانگین گرفتن روی کل داده edge را پنهان می‌کند.

### 6.4 real-time availability و lag لحاظ نشد

در معامله واقعی، زمان انتشار، revision، delay داده، و availability مهم است. اگر داده macro روزانه یا با lag وارد شود، باید بسیار دقیق مشخص شود که در لحظه تصمیم چه چیزی واقعاً قابل دانستن بوده است.

### 6.5 market positioning و flow غایب بود

طلا فقط با قیمت و macro رسمی توضیح داده نمی‌شود. positioning، ETF flows، central bank demand، futures open interest، COT، option positioning و liquidity stress می‌توانند تعیین کنند یک محرک macro چگونه price شود. این‌ها در پروژه نبودند.

---

## 7. نقاط ضعف اصلی پروژه

### 7.1 شروع با pipeline، نه با نقشه بازار

ما زود وارد ساخت pipeline، stage، gate و candidate شدیم. این از نظر مهندسی خوب بود، اما از نظر بازارمحور ناقص بود. باید قبل از discovery، یک سند Gold Market Map ساخته می‌شد.

### 7.2 نبود طبقه‌بندی regime

تقریباً همه تست‌ها روی کل دوره یا segmentation ساده انجام شدند. اما gold بدون regime segmentation احتمالاً edge پایدار نمی‌دهد. حداقل regimeهای زیر لازم بودند:

- real-yield rising / falling
- DXY risk-on strength / safe-haven strength
- inflation surprise regime
- policy pivot / hiking / cutting expectation
- geopolitical risk-on/off
- high volatility / low volatility
- liquidity stress / normal liquidity
- trend regime / range regime

### 7.3 ضعف تعریف event

Event فقط زمان وقوع نیست. event باید surprise، importance، direction ambiguity، pre-event drift، post-event reaction و narrative را داشته باشد.

### 7.4 ترکیب نکردن تایم‌فریم‌ها

پروژه روی H1 و برخی horizonها کار کرد، اما multi-timeframe hierarchy جدی نداشت. در gold، setup intraday معمولاً باید با bias روزانه/چهارساعته ترکیب شود.

### 7.5 نبود trade construction واقعی

سیگنال با معامله فرق دارد. بسیاری از خروجی‌ها signal-level بودند. برای تبدیل به سیستم، باید trade construction واقعی تعریف شود:

- entry trigger دقیق
- invalidation
- stop logic
- partial exit
- time stop
- one-position rule
- daily loss limit
- cooldown
- no-trade zones
- session-specific sizing

### 7.6 نگاه بیش از حد آماری به drawdown

Drawdown gate لازم بود، اما drawdown را بیشتر به‌عنوان metric نهایی دیدیم، نه به‌عنوان symptom. باید بررسی می‌شد drawdown در چه نوع روزها و regimeهایی رخ می‌دهد.

### 7.7 نبود human-trader diagnostic loop

هر بار که یک candidate fail می‌شد، باید یک trader-style diagnostic انجام می‌شد:

- چه نوع کندل‌هایی شکست خوردند؟
- آیا شکست‌ها در خبرها بودند؟
- آیا stopها قبل از حرکت اصلی خورده‌اند؟
- آیا setup دیر وارد شده؟
- آیا direction درست بوده ولی horizon اشتباه بوده؟
- آیا TP/SL با volatility سازگار نبوده؟

این لایه کمتر از حد لازم وجود داشت.

---

## 8. نقاط قوت پروژه که نباید از دست بروند

با وجود نقدها، پروژه چند سرمایه مهم دارد:

1. DB محلی بزرگ و سالم با داده AMarkets/MT5.
2. stage framework قابل توسعه.
3. گزارش‌های قابل audit.
4. gateهای محافظ در برابر promotion زودهنگام.
5. تجربه اصلاح data-source bugs.
6. background scheduler.
7. فهرست watchlist از raw edges، مخصوصاً structure high-sweep continuation.
8. تفکیک research از execution.
9. فرهنگ kill-switch و جلوگیری از live خطرناک.

این‌ها نباید دور ریخته شوند. اگر پروژه بازطراحی شود، همین زیرساخت می‌تواند استفاده شود. چیزی که باید تغییر کند، لایه بالادستی hypothesis و feature design است.

---

## 9. آیا باید پرونده طلا بسته شود؟

در وضعیت فعلی، پاسخ کوتاه این است: نه، اما نباید با همین روش ادامه پیدا کند.

پرونده کریپتو به این دلیل freeze شد که مسیر strategy/model workflow آن به نتیجه کافی نرسیده و thesis جدید روشنی وجود نداشت. درباره XAUUSD، هنوز یک تفاوت مهم وجود دارد: بازار طلا از نظر macro و institutional flow بسیار عمیق‌تر و قابل مدل‌سازی‌تر از بسیاری از microcap cryptoهاست. شکست فعلی بیشتر شبیه شکست چارچوب پژوهش است تا شکست asset.

اما اگر پروژه بخواهد همچنان به شکل patch-stage-pattern-mining ادامه پیدا کند، باید متوقف شود. این مسیر احتمالاً خروجی مشابه می‌دهد: backgroundهای زیاد، strict صفر، و انتظار برای forward eventهای کم‌فرکانس.

اگر ادامه بدهیم، باید با یک فاز غیرکدنویسی شروع شود:

**Stage38A — Gold Market Thesis Reconstruction**

این stage نباید کد بزند. باید سند بسازد. هدف آن:

- تعریف محرک‌های اصلی طلا.
- تعریف regimeها.
- تعریف اینکه در هر regime چه setupهایی منطقی‌اند.
- تعریف featureهای لازم که نداریم.
- تعریف داده‌های ناقص.
- تعریف اینکه چه چیزهایی اصلاً با داده فعلی قابل تست نیست.
- تعیین اینکه کدام thesis ارزش پیاده‌سازی دارد.

اگر Stage38A نتواند thesisهای قابل دفاع بسازد، آن وقت باید پروژه طلا را freeze کرد. اما freeze کردن قبل از این بازطراحی زود است.

---

## 10. چارچوب پیشنهادی برای بازطراحی

### 10.1 لایه اول: Gold macro state

برای هر روز/هفته باید state تعریف شود:

- real yield trend
- DXY trend
- US rates expectation
- inflation narrative
- risk sentiment
- geopolitical/safe haven pressure
- liquidity stress
- central bank / ETF / futures positioning اگر داده موجود باشد

### 10.2 لایه دوم: intraday liquidity state

برای هر روز:

- Asia compression/range
- London impulse
- NY data release window
- London-NY overlap
- rollover/low liquidity
- Friday risk

### 10.3 لایه سوم: setup family

Setup فقط وقتی تست شود که با macro/intraday state سازگار باشد:

- sweep continuation
- sweep reclaim
- breakout after compression
- post-news impulse continuation
- post-news reversal after overreaction
- trend-day pullback continuation
- range-day fade

### 10.4 لایه چهارم: execution model

هر setup باید trade construction داشته باشد:

- entry
- stop
- target
- time stop
- invalidation
- max one position
- cooldown
- event blackout
- spread guard
- position sizing

### 10.5 لایه پنجم: evaluation

ارزیابی باید بر اساس independent trade، regime batch، forward batch، و risk-normalized return باشد، نه صرفاً signal-level PF.

---

## 11. تصمیم‌های پیشنهادی پس از این گزارش

### تصمیم 1: عدم ساخت patch معاملاتی جدید

تا زمانی که Stage38A یا معادل آن ساخته نشده، نباید stage جدیدی برای variant mining ساخته شود.

### تصمیم 2: نگه داشتن backgroundها

Stage35C و Stage36/37 watchlist می‌توانند در background بمانند. این‌ها کم‌هزینه‌اند و ممکن است با داده جدید اطلاعات بدهند.

### تصمیم 3: ساخت گزارش thesis reconstruction

گام بعدی باید یک سند تحلیلی باشد، نه کد. اگر قرار است patch ساخته شود، فقط برای استخراج داده‌های diagnostic از existing trades باشد، نه تولید سیگنال جدید.

### تصمیم 4: تعریف معیار توقف

اگر پس از بازطراحی بازارمحور هم هیچ thesis قابل تست و قابل دفاع پیدا نشد، پروژه طلا باید freeze شود. اما این freeze باید پس از بازطراحی انجام شود، نه در نقطه فعلی.

---

## 12. نتیجه نهایی

پروژه XAUUSD از نظر فنی بالغ‌تر از پروژه کریپتو بود، اما از نظر market thesis به‌اندازه کافی عمیق نبود. ما ابزار ساختیم، داده جمع کردیم، gate ساختیم، و candidateها را صادقانه رد کردیم. این‌ها ارزشمند است. اما بازار طلا با ابزار عمومی pattern mining به‌سادگی تسلیم نمی‌شود.

جمع‌بندی دقیق:

- پیاده‌سازی احتمالاً مشکل اصلی نیست.
- داده OHLC فعلی کافی برای baselineهای سطح اول است، اما برای macro/event thesis عمیق کافی نیست.
- featureها و regime definitions ناکافی بوده‌اند.
- raw structure edge دیده شده، اما اجرایی نشده است.
- macro edge پیدا نشدن، نشانه ضعف طراحی macro feature است، نه بی‌اثر بودن macro.
- ادامه دادن به stageهای مشابه، احتمالاً اتلاف زمان است.
- بسته شدن کامل پرونده طلا هنوز زود است.
- گام درست، بازطراحی thesis از بالا به پایین است.

گام بعدی پیشنهادی:

**ساخت Stage38A — Gold Market Thesis Reconstruction Report**

این stage باید پیش از هر کدنویسی جدید پاسخ دهد:

1. طلا را دقیقاً در چه regimeهایی می‌خواهیم معامله کنیم؟
2. چه محرک‌هایی واقعاً قابل مشاهده و قابل استفاده‌اند؟
3. چه داده‌هایی کم داریم؟
4. کدام setupها از دید تریدر حرفه‌ای منطقی‌اند؟
5. کدام setupها فقط حاصل pattern mining هستند و باید حذف شوند؟
6. معیار ورود دوباره به توسعه فنی چیست؟

تا وقتی این سؤالات پاسخ نگیرند، اضافه کردن stage جدید فقط پروژه را طولانی‌تر می‌کند، نه نزدیک‌تر به سیستم تجاری.

---

## پیوست A — منابع داخلی استفاده‌شده

این گزارش بر اساس گزارش‌ها و خلاصه‌های داخلی پروژه تا Stage37A تهیه شده است، از جمله:

- XAUUSD_PROJECT_TRANSFER_BRIEF.md
- XAUUSD_PROJECT_RULES.md
- XAUUSD_STAGE31_TRANSFER_PACK.md
- stage32b تا stage32f reports
- stage33a تا stage33e reports
- stage34a تا stage34c reports
- stage35a تا stage35c reports
- stage36a تا stage36f reports
- stage37a_nonoverlap_risk_normalization_audit.md
- stage37a_summary.json

