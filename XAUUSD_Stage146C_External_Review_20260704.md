# ارزیابی خارجی پروژه XAUUSD — Stage131 تا Stage146C
**نقش:** تحلیل‌گر ارشد طلا، تریدر فارکس با ۲۰+ سال سابقه، توسعه‌دهنده ارشد سیستم
**سند مرجع:** گزارش 2026-07-04
**هدف پروژه:** رسیدن به سیستم تجاری قابل‌اطمینان در سریع‌ترین زمان ممکن
**تاریخ:** 2026-07-04

---

## حکم اجرایی — یک جمله

پروژه از نظر **infrastructure** پیشرفت واقعی کرده، اما از نظر **روش discovery** به یک تله بنیادی افتاده که اگر حالا اصلاح نشود، هر مرحله execution بعدی — هر چقدر هم خوب اجرا شود — نتایج قابل‌اتکایی نخواهد داشت.

---

## بخش ۱ — چه چیزی واقعاً خوب است

قبل از هر نقدی، باید این پیشرفت‌های واقعی را ثبت کرد:

| دستاورد | اهمیت |
|---|---|
| MT5 demo execution واقعی با retcode و deal history | این پروژه را از simulation به reality منتقل کرد |
| Stage144C clean reconciliation | اعتماد به ledger را برقرار کرد |
| Freeze discipline سریع | جلوی ادامه روی family ضعیف را گرفت |
| Loop supervisor مجزا از discovery engine | معماری درستی است |
| Duplicate guard با `feature_date|rule_id` | جلوی خطاهای execution را گرفت |
| Stage146C wildcard unblock | مسیر frequency گیر نکرد |

اینها دستاوردهای واقعی هستند. اما یک مشکل ساختاری وجود دارد که این دستاوردها را در خطر قرار می‌دهد.

---

## بخش ۲ — مشکل بنیادی: discovery و execution از یک منبع داده می‌خورند

این مهم‌ترین ایراد پروژه در این دوره است و باید صریح گفته شود.

### وضعیت فعلی

```text
Stage138 / Stage138C:
  ورودی: xauusd_stage143_live_h1_bars.csv  ← H1 bars از MT5/AMarkets
  خروجی: rule selection + KV rule_state

Stage134 EA:
  ورودی: همان xauusd_stage138_technical_rule_state_kv.csv
  عملکرد: order send روی همان broker/feed
```

**یعنی**: شما rule را از روی همان broker feed انتخاب می‌کنید که بعداً روی همان broker feed execution می‌کنید.

### چرا این یک مشکل بنیادی است

این دقیقاً همان چیزی است که در ادبیات quant به عنوان **in-sample selection bias** شناخته می‌شود. <cite index="4-1">در طراحی سیستم معاملاتی، selection bias زمانی رخ می‌دهد که یک تریدر آنقدر ایده‌های معاملاتی مختلف را آزمایش می‌کند که تقریباً حتماً به یک backtest خوب‌نما برخورد می‌کند — که در واقع چیزی بیشتر از یک اتفاق تصادفی نیست.</cite>

در این پروژه این مشکل به شکل خاصی بروز کرده:

**مرحله Discovery:** Stage138 روی همان H1 bars که MT5/AMarkets broker export کرده، دهها rule را می‌سنجد و بهترین را انتخاب می‌کند — بر اساس validation_mean و tail_mean بالاتر.

**مرحله Execution:** Stage134 همان rule را روی همان broker feed اجرا می‌کند.

این به معنای این است که:
- آنچه Stage138 به‌عنوان "validation window" و "tail window" اندازه می‌گیرد، همه از همان feed هستند که execution هم روی آن انجام می‌شود.
- هیچ جداسازی واقعی بین داده discovery و داده execution وجود ندارد.
- rule انتخاب‌شده ممکن است به noise‌های خاص همان broker (spread pattern، quote timing، وقفه‌های feed) overfit شده باشد، نه به یک edge واقعی بازار.

### تأیید از داده‌های خودِ پروژه

جدول معاملات (بخش ۵ گزارش) این هشدار را تأیید می‌کند:

```text
معامله ۳، ۴، ۵، ۶، ۷ — همه در بازه ۱۵:۰۰ تا ۲۰:۰۰ در تاریخ 2026-07-02
(پنج ترید در پنج ساعت متوالی، روی همان rule family)
```

این clustering زمانی یعنی سیستم در یک بازه کوتاه (یک بعدازظهر) پنج سیگنال متوالی از همان rule دریافت کرده. چنین clustering‌ای برای یک rule با horizon H1 که باید edge معنادار داشته باشد، نشانه‌ای از regime-specific activation است، نه یک edge پایدار.

همچنین: `selection_mean_bps: -0.9699` برای candidate جایگزین در selection window منفی است. این یعنی همان rule که الان به‌عنوان replacement انتخاب شده، در بازه‌ای که Stage138C آن را "recent context" می‌داند، عملکرد زیر صفر داشته. پذیرفتن آن به‌عنوان replacement "چون validation و tail بهتر بودند" دقیقاً همان pattern post-hoc filtering است.

### نتیجه عملی

<cite index="3-1">حداقل ۱۰۰ تا ۲۰۰ ترید لازم است. هر چیزی کمتر از این و شما فقط شانس را آزمایش می‌کنید.</cite>

با ۷ ترید demo، نه تنها به این آستانه نرسیده‌ایم، بلکه این ۷ ترید همه از همان داده‌ای آمده‌اند که discovery هم از آن انجام شده. این دو مشکل با هم، هر نتیجه‌گیری آماری از این ۷ ترید را از نظر quant بی‌اعتبار می‌کند.

---

## بخش ۳ — ایرادات به تفکیک محور

### ۳.۱ محور ایده (Idea)

**IDEA-1: منطق بازاری rule family فعلی مبهم و شکننده است**

قانون فعلی: `ret_3h_bps >= q65 AND ret_48h_bps >= q65`

این یعنی: "اگر طلا در ۳ ساعت اخیر و ۴۸ ساعت اخیر هر دو در quantile ۶۵ام یا بالاتر بودند، buy کن."

این یک **قانون momentum خالص** است بدون هیچ context بازاری. سؤال‌هایی که باید پاسخ داشته باشند:
- چرا momentum در H1 باید در طلا ادامه‌دار باشد (و نه mean-reverting)؟
- این signal در چه regime‌هایی (trending/ranging/news-driven) کار می‌کند؟
- چرا ترکیب ۳h و ۴۸h؟ این ترکیب خاص چه منطق بازاری دارد؟

بدون پاسخ به این سؤال‌ها، این rule یک pattern است، نه یک edge.

**راه‌حل:** قبل از اجرای replacement، برای هر candidate باید یک "market logic statement" یک‌پاراگرافی نوشته شود که توضیح دهد چرا این signal باید در طلا کار کند. اگر نمی‌توان این پاراگراف را نوشت، candidate نباید وارد execution شود.

**IDEA-2: H1 به‌عنوان horizon نه برای discovery و نه برای signal logic مناسب است**

در گزارش‌های قبلی این پروژه (Stage66 و قبل از آن) به‌وضوح ثابت شد که intraday/H1 discovery روی XAUUSD edge پایدار ندارد. Stage131 تا Stage146C دوباره — با ابزار بهتر — همان مسیر را رفته است. این بار execution واقعی‌تر است، اما **ایده بنیادی (H1 technical signal روی CFD gold) تغییری نکرده.**

**راه‌حل:** این خودش یک تصمیم استراتژیک است که باید صریح گرفته شود: آیا پروژه می‌خواهد با proof از شکست H1/intraday discovery (که Stage52، Stage58، و حالا Stage138 همه آن را تأیید کرده‌اند) وارد مسیر D1/macro شود، یا همچنان با H1 ادامه دهد؟ هر دو قابل دفاع است، اما نمی‌توان بدون یک تصمیم صریح هر دو را همزمان دنبال کرد.

---

### ۳.۲ محور متد (Methodology)

**METHOD-1: جداسازی discovery/validation از execution data وجود ندارد**

این همان مشکل بخش ۲ است، اما در اینجا به‌عنوان نقص متدولوژیک مستقل ثبت می‌شود:

Stage138 validation window و tail window هر دو از همان H1 broker bars برگرفته شده‌اند که execution هم از آن انجام می‌شود. <cite index="4-1">تنها out-of-sample واقعی، داده آینده است — چون ما از قبل از آنچه بازار در گذشته انجام داده آگاهیم.</cite>

**راه‌حل:** حداقل یک منبع داده مستقل برای validation لازم است. پیشنهاد عملی:
- اگر AMarkets/MT5 تنها منبع قیمتی قابل‌دسترسی است، validation window باید به‌صورت rolling و با lag کافی از selection window جدا باشد — نه overlap داشته باشد.
- معیار حداقلی: validation window باید حداقل ۶ ماه قبل از آخرین تاریخ selection window پایان یافته باشد. این غیرممکن نیست با داده موجود (۳۰,۰۰۰ کندل H1 که Stage143 export کرده).

**METHOD-2: Stage145 aggregate است، نه per-family**

Stage145 عملکرد ۷ معامله را با هم می‌بیند. اما ۷ معامله از چند family مختلف آمده‌اند:
- معامله ۱: `trend_20_50 + range_pos_24`
- معامله ۲: `ret_48h + trend_50_100`
- معاملات ۳-۷: `ret_48h + trend_50_100` (با واریانت‌های کوچک)

اگر عملکرد aggregate مثبت باشد اما یک family سودده و دیگری زیان‌ده باشد، Stage145 این را نمی‌بیند. این باعث می‌شود freeze تصمیم دستی باقی بماند (که در این دوره اتفاق افتاد) به‌جای اینکه سیستم خودکار این را detect کند.

**راه‌حل:** Stage145 باید per-family ledger داشته باشد. این یک تغییر کوچک در کد است اما تأثیر بزرگی بر کیفیت تصمیم‌گیری دارد.

**METHOD-3: MaxHoldMinutes=60 با signal H1 در تناقض مستقیم است**

یک سیگنال H1 یعنی: "این bar آخرین ساعت نشان‌دهنده یک شرط است." اگر این شرط یک edge واقعی داشته باشد، انتظار می‌رود outcome آن در بازه‌ای بزرگ‌تر از ۶۰ دقیقه آشکار شود — چون اطلاعات H1 خودش ۶۰ دقیقه summarize می‌کند. با MaxHoldMinutes=60، شما effectively یک M5/M15 signal بر اساس H1 data داریم. این یک mismatch اساسی است.

**راه‌حل:** یا MaxHoldMinutes را به حداقل ۴×H1 (یعنی ۲۴۰ دقیقه) برسانید، یا صراحتاً اعلام کنید که horizon به M15 منتقل شده و discovery هم باید روی M15 انجام شود.

**METHOD-4: freeze criterion "دو loss متوالی" آماری بی‌پایه است**

تصمیم freeze family قبلی بر اساس "دو loss متوالی" گرفته شد. این یک heuristic است، نه یک معیار آماری. در یک سیستم با win rate واقعی ۵۵٪، احتمال دو loss متوالی حدود ۲۰٪ است — یعنی به‌طور متوسط در هر ۵ جفت معامله یک بار اتفاق می‌افتد. این به‌تنهایی نشان‌دهنده edge decay نیست.

**راه‌حل:** freeze criterion باید آماری باشد:
```text
freeze_if:
  mean_bps در ۱۰ trade اخیر (per-family) < 0
  AND
  cumulative_net در آن family < 0
  (نه صرفاً دو loss متوالی)
```

---

### ۳.۳ محور پیاده‌سازی (Implementation)

**IMPL-1: retcode 10018 در duplicate guard قفل شده**

گزارش خودش این را به‌عنوان ریسک شناسایی کرده: اگر Stage134 یک failed attempt با retcode=10018 را به‌عنوان "signal already attempted" ثبت کند، بعد از باز شدن بازار هم order نمی‌زند. این یک باگ مشخص است.

**راه‌حل:** در duplicate guard منطق Stage134، یک check اضافه کنید:
```python
# attempt فقط زمانی "قبلاً انجام شده" حساب شود که:
# retcode باشد در {10009, 10010} (order done/executed)
# نه {10018} (market closed) یا سایر rejection codes
```

**IMPL-2: timezone offset MT5 هنوز قطعی نیست**

گزارش (بخش ۴.۸) صراحتاً می‌گوید «اختلاف برچسب UTC/MT5 server time دیده شد». اما این هنوز "برای demo execution blocker نبود" گفته شده. این را نادیده نگیرید: اگر feature_date در KV با UTC server time MT5 یک ساعت اختلاف داشته باشد، کل signal freshness logic ممکن است روی یک ساعت غلط کار کند — مخصوصاً اگر به H1 bars حساس است که کاملاً time-stamp-dependent هستند.

**راه‌حل:** یک تست explicit بنویسید که timestamp در `xauusd_stage143_live_h1_bars.csv` را با یک baseline مستقل (مثلاً gold open از Bloomberg/Investing.com در همان تاریخ به وقت UTC) مقایسه کند. این test باید fail کند اگر اختلاف بیشتر از ۱۵ دقیقه باشد.

**IMPL-3: SL/TP ثابت و non-adaptive است**

SL و TP فعلی در Stage134 ثابت تعریف شده‌اند. در طلا که نوسانات روزانه می‌توانند بین ۰.۵٪ (روزهای آرام) تا ۲٪+ (روزهای FOMC/NFP) متفاوت باشند، یک SL ثابت یعنی:
- در روزهای پرنوسان: SL خیلی زود زده می‌شود (اتفاق معامله ۳ و ۵ در بازه ۱۵:۰۰-۱۸:۰۰ در ۲ ژوئیه — یک دوره پرنوسان بود)
- در روزهای آرام: SL نسبتاً بزرگ و ریسک غیرمتناسب است

**راه‌حل:** TP و SL را به ATR(14) وصل کنید:
```text
SL = entry - 1.5 × ATR(14, H1)
TP = entry + 2.0 × ATR(14, H1)
```
این یک تغییر کوچک در EA است اما کیفیت R:R را بدون تغییر در logic اصلی بهبود می‌دهد.

---

### ۳.۴ محور تست (Testing)

**TEST-1: هیچ تستی وجود ندارد که in-sample contamination را detect کند**

Stage138 validation را روی همان H1 bars انجام می‌دهد که stage143 export کرده. هیچ تستی بررسی نمی‌کند که آیا validation window با execution window overlap دارد یا نه.

**راه‌حل:** یک تست اضافه کنید:
```python
def test_validation_window_no_overlap_with_recent_n_bars():
    # آخرین N bar (مثلاً N=500) باید خارج از validation window باشند
    # validation window باید حداقل M bar (مثلاً M=168 = یک هفته H1) 
    # قبل از آخرین bar اجرا شده باشد
    assert validation_end_date < (latest_execution_date - pd.Timedelta(hours=168))
```

**TEST-2: هیچ تستی برای execution clustering detect نمی‌کند**

معاملات ۳-۷ در پنج ساعت متوالی — همه از همان family. هیچ alertی وجود ندارد که این clustering را به‌عنوان یک ریسک پرچم‌گذاری کند.

**راه‌حل:** در Stage145 یک metric اضافه کنید:
```text
max_trades_in_4h_window: حداکثر معاملات در یک پنجره ۴ ساعته
اگر این عدد > 2 بود: alert بدهد (نه necessarily freeze)
```

**TEST-3: تست‌های Stage138C فقط `py_compile passed` هستند، نه logic tests**

برای مهم‌ترین بخش سیستم (rule selection engine)، تنها تست‌های موجود `py_compile passed` و `pytest 3 passed` هستند. این تست‌ها احتمالاً صحت parse/output format را می‌سنجند، نه صحت منطق selection.

**راه‌حل:** حداقل دو تست logic اضافه کنید:
```python
def test_excluded_rule_truly_absent_from_output():
    # اگر D138C_ret_48h_bps_GEQ65 exclude شده، 
    # نباید در selected_rule_id ظاهر شود
    
def test_selection_uses_validation_window_not_selection_window():
    # اگر selection_mean_bps منفی است اما validation_mean_bps مثبت،
    # باید selected_rule همان validation-based candidate باشد
    # نه selection-window best
```

---

## بخش ۴ — پاسخ به سؤالات ۱۰‌گانه گزارش

| # | سؤال | پاسخ |
|---|---|---|
| ۱ | Freeze family قبلی درست بوده؟ | بله، اما نه به‌خاطر "دو loss متوالی" — به‌خاطر `selection_mean_bps=-0.9699` که نشان می‌دهد در context اخیر edge وجود نداشته. |
| ۲ | Replacement با selection_mean منفی ارزش demo-probe دارد؟ | فقط به‌عنوان یک probe کوچک (۳-۵ trade) برای بررسی behavior، نه به‌عنوان replacement مورد اعتماد. |
| ۳ | H1 replacement ادامه یابد یا به M15/M5 برویم؟ | نه این نه آن. مسیر درست: رفع مشکل in-sample contamination در discovery، سپس تصمیم درباره timeframe. |
| ۴ | Thresholdهای Stage138C مناسب‌اند؟ | نه — مادامی که validation window از همان داده execution است، هیچ threshold‌ای معنا ندارد. |
| ۵ | Stage145 فوراً per-family شود؟ | بله — این یک تغییر کوچک با تأثیر بزرگ است. باید در همین Package بعدی باشد. |
| ۶ | Failed market-closed attempt باید در duplicate guard نادیده گرفته شود؟ | بله، قطعاً. retcode=10018 باید از لیست "successfully attempted" خارج باشد. |
| ۷ | MaxHoldMinutes=60 برای H1 signal منطقی است؟ | خیر — این یک مismatch اساسی است. باید حداقل ۴×H1 = 240 دقیقه باشد. |
| ۸ | TP/SL باید dynamic/ATR-based شود؟ | بله — این اولویت بالایی دارد چون مستقیماً روی P&L کیفی اثر می‌گذارد. |
| ۹ | ادامه demo با purely technical rule بدون news/session filter قابل دفاع است؟ | قابل دفاع نیست با عنوان "سیستم تجاری"، اما برای probe اولیه قابل قبول است — به شرط اینکه نتایج آن را به‌عنوان "شواهد اولیه" نه "edge اثبات‌شده" تفسیر کنید. |
| ۱۰ | معیار عملیاتی توقف replacement چه باشد؟ | پیشنهاد: `mean_bps < 0 پس از ۱۰ ترید per-family` — نه "دو loss متوالی". |

---

## بخش ۵ — اولویت‌بندی اقدامات

### اقدامات فوری (قبل از باز شدن بازار یا اولین session بعدی)

```text
P0-1: رفع retcode=10018 در duplicate guard Stage134
  → این blocker است و بدون آن replacement اصلاً order نمی‌زند

P0-2: MaxHoldMinutes را به 240 تغییر دهید
  → 60 دقیقه با H1 signal ناسازگار است
```

### اقدامات این هفته (Package بعدی)

```text
P1-1: Stage145 را per-family کنید
  → یک روز کار، تأثیر بزرگ بر کیفیت تصمیم

P1-2: ATR-based SL/TP در Stage134 EA
  → کیفیت R:R را واقعی‌تر می‌کند

P1-3: Timezone test explicit برای Stage143 export
  → ریسک hidden bug را حذف می‌کند
```

### اقدامات میان‌مدت (قبل از تصمیم درباره real/live)

```text
P2-1: رفع in-sample contamination در Stage138
  → validation window باید از execution window جدا شود
  → بدون این اصلاح، هیچ نتیجه‌ای از demo execution آماری معتبر نیست

P2-2: تعریف "market logic statement" اجباری برای هر candidate
  → هر rule باید یک توضیح یک‌پاراگرافی "چرا در طلا کار می‌کند" داشته باشد

P2-3: Session/news blackout اولیه
  → حداقل ۳۰ دقیقه قبل و بعد از FOMC/NFP/CPI باید blackout باشد
  → این یک filter ساده است که ریسک بزرگ را کم می‌کند
```

### تصمیم استراتژیک (در اسرع وقت، صرف‌نظر از نتیجه replacement)

```text
P3-1: تصمیم رسمی: آیا H1 technical-only ادامه می‌یابد یا به D1/macro منتقل می‌شویم؟
  مدرک: Stage52 (191 forward signal، mean منفی)، Stage58B (n=34، fail)،
  و حالا Stage138 (discovery contamination) همه یک پیام مشترک دارند:
  H1 technical-only روی CFD gold edge پایدار ایجاد نمی‌کند.
  
  این یک یافته است، نه شکست. اما باید رسماً پذیرفته شود.
```

---

## بخش ۶ — مسیر پیشنهادی برای رسیدن به هدف اصلی

با در نظر گرفتن هدف («سریع‌ترین مسیر به سیستم تجاری قابل‌اطمینان»)، مسیر زیر پیشنهاد می‌شود:

### گام اول: تکمیل infrastructure validation (این هفته)

اصلاحات P0 و P1 را اعمال کنید. این infrastructure را solidify می‌کند بدون اینکه discovery را تغییر دهد.

### گام دوم: رفع contamination و ادامه H1 probe (هفته‌های آینده)

Stage138 را با یک validation window جدا از execution window اجرا کنید. اگر candidate‌های منتخب همچنان edge داشتند، ادامه دهید. اگر نه، این confirmation نهایی است که H1 technical-only جواب نمی‌دهد.

### گام سوم: تصمیم H1 vs D1/Macro

اگر گام دوم نتیجه منفی داد (که محتمل است)، infrastructure ساخته‌شده (Stage134 execution، Stage144C ledger، Stage145 gate) کاملاً قابل استفاده برای D1/macro thesis است — فقط discovery engine (Stage138) باید تغییر کند، نه execution stack.

این مسیر از "ادامه H1 تا شکست کامل" سریع‌تر است چون:
- هم H1 probe را به‌درستی تست می‌کند (با contamination برطرف‌شده)
- هم آماده می‌شود که اگر H1 شکست خورد، بدون از‌دست‌دادن infrastructure به D1 منتقل شود

---

## جمع‌بندی یک‌صفحه‌ای

| محور | مشکل اصلی | اقدام |
|---|---|---|
| **ایده** | H1 technical-only سابقه شکست دارد؛ rule faily بدون market logic | تصمیم صریح: ادامه H1 یا pivot به D1/macro |
| **متد** | Discovery و execution از یک منبع داده — in-sample contamination | Validation window را از execution window جدا کنید |
| **پیاده‌سازی** | retcode=10018 در duplicate guard، MaxHoldMinutes=60 نادرست، SL/TP ثابت | سه fix مشخص که این هفته قابل انجام است |
| **تست** | Stage138C فقط compile/format test دارد؛ clustering و contamination detect نمی‌شوند | Logic tests برای Stage138، clustering alert در Stage145 |

مهم‌ترین جمله برای تیم:

> **Infrastructure این پروژه الان آماده است. مشکل باقی‌مانده discovery است، نه execution. اگر Stage138 را با data separation درست کنید، بقیه stack آماده است که هر strategy ای را — H1 یا D1 — به‌درستی آزمایش کند.**
