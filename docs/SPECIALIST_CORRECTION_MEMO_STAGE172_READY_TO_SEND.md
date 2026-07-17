# یادداشت اصلاحی کوتاه برای بازبینی متخصص — Stage171→173

**هدف:** اصلاح چند واقعیت پروژه پیش از استفاده از گزارش قبلی در تصمیم‌گیری بعدی. این یادداشت درخواست توقف عملیات نیست؛ reconciliation و archaeology محدود در Stage173 هم‌زمان ادامه دارد.

## ۱. اصلاح طبقه‌بندی Track A در Stage172

Track A در Stage172 اجرا نشد، چون جدول historical-as-of موردنیاز پیدا نشد. بنابراین خروجی صحیح آن:

```text
INCONCLUSIVE_BLOCKED
```

است، نه `KILL`. هیچ metric تاریخی H64L در Stage172 محاسبه نشد.

## ۲. باگ ETF فعلی اثبات شده، اما تعمیم آن به Stage64R هنوز اثبات نشده است

در parser فعلی Stage171H، ستون مبهم WGC با عنوان `All units in tonnes unless otherwise specified` به‌اشتباه holdings تلقی شده؛ این ستون عملاً با سری قیمت طلا سازگار است. جمع holdings صندوق‌ها با `col_3` سازگار است.

بااین‌حال، ledger قدیمی Stage65 مقدار سه‌ماهه حدود `-55.28t` ثبت کرده که با تغییر واقعی holdings فوریه تا مه ۲۰۲۶ نزدیک است. بنابراین:

```text
Current Stage171H ETF materializer = wrong
Original Stage64R ETF implementation = unresolved
```

از باگ فعلی نمی‌توان بدون archaeology نتیجه گرفت z تاریخی Stage64R نیز روی ETF خراب ساخته شده است.

## ۳. COT مسیر غایب پروژه نبوده است

داده CFTC/COT قبلاً وارد پروژه شده و در Stage38 به‌عنوان state/overlay بررسی شده است. نتیجه به promotion نرسید. بنابراین ایجاد یک Track C گسترده جدید بر مبنای percentile scan مجاز نیست.

COT فقط در دو حالت قابل استفاده است:

1. فیلتر یک generator مستقل و از قبل مثبت؛
2. یک mechanism محدود که صریحاً ثابت شود در Stage38 تست نشده است.

## ۴. تفسیر صحیح Track B

Stage172 نسخه‌های دقیق زیر را پس از هزینه روی holdout کشت:

- SMA-trend + EMA pullback، long و short؛
- London/NY range continuation، long و short.

این نتیجه باید به همان formulationهای دقیق محدود بماند. در عین حال، rerun عمومی همان خانواده‌ها بدون نوشتن تفاوت مادی با Stage49/50/52/58 ممنوع است.

Volatility-expansion در Stage172 صفر معامله داشت و در آن مرحله ارزیابی performance نشد؛ اما سوابق منفی Stage52/58 همچنان مانع rerun عمومی آن است.

## ۵. DXY و holding horizon هنوز باید از artifact اصلی استخراج شوند

پیش از audit نهایی H64L باید مشخص شود Stage64R واقعاً از کدام قرارداد استفاده کرده است:

```text
ICE DXY / direct DXY
یا
DTWEXBGS broad dollar proxy
```

همچنین افق نگهداری باید از artifact اصلی بازیابی شود؛ انتخاب چند horizon و نگه‌داشتن بهترین نتیجه مجاز نیست.

## حکم عملیاتی پیشنهادی

```text
H64L = SUSPENDED_PENDING_SOURCE_RECONCILIATION
Stage172 exact technical formulations = KILLED
ML = FORBIDDEN
Broad scan = FORBIDDEN
Orders/demo/live = FORBIDDEN
```

پس از Stage173 فقط در صورت بازیابی قراردادهای ETF، DXY و horizon، Track A historical-as-of دوباره اجرا می‌شود. مسیر پروژه برای انتظار پاسخ متخصص متوقف نمی‌شود.

## درخواست بازبینی محدود

لطفاً فقط این سه مورد را challenge یا تایید کنید:

1. آیا شواهدی دارید که ETF implementation تاریخی Stage64R نیز از ستون اشتباه استفاده کرده است، برخلاف ledger قدیمی `-55.28t`؟
2. آیا منبع DXY و holding horizon اصلی Stage64R را از artifact مشخصی می‌شناسید؟
3. آیا با ممنوعیت Track C گسترده COT و محدودکردن rerunها به material-delta از پیش نوشته‌شده موافقید؟
