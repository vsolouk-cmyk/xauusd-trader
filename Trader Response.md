الف) پرسش‌های یک‌باره درباره روش

(قطعی) قبل از شروع labeling، تریدر باید این موارد را صریح پاسخ دهد:

ساختار ساید
آیا B1 همیشه LONG و B2 همیشه SHORT است؟
آیا SSL می‌تواند ساید را برخلاف رنگ Beta تعیین کند؟
در چه شرایطی یک B1/B2 رد می‌شود؟
اجزای SSL مورد استفاده
Baseline؟
Upper/Lower Channel؟
SSL1؟
SSL2 dots؟
SSL Exit line/arrows؟
رنگ baseline یا bar؟
ATR bands؟
Signal diamonds؟
Risk Level یا Entry Distance؟
رابطه زمانی
cross باید روی همان Beta باشد؟
قبل از Beta رخ دهد؟
بعد از Beta نیاز به confirmation دارد؟
حداکثر چند کندل فاصله قابل‌قبول است؟
ساختار و کیفیت کندل
حداقل اندازه بدنه چگونه تعیین می‌شود؟
اندازه نسبت به ATR مهم است؟
چند کندل قبلی بررسی می‌شوند؟
اولین Beta بعد از تغییر روند مهم است یا Betaهای ادامه‌دهنده نیز معتبرند؟
موقعیت
قیمت باید بیرون channel باشد یا صرفاً در سمت baseline؟
فاصله زیاد از baseline باعث رد می‌شود؟
شیب یا انحنای baseline چقدر اهمیت دارد؟
swing/pivot/support/resistance بررسی می‌شود؟
تایم‌فریم
آیا تصمیم واقعاً فقط با M1 گرفته می‌شود؟
اگر M5/M15/H1 استفاده می‌شود، دقیقاً برای چه شرطی؟
ورود
close کندل signal؟
open کندل بعد؟
limit روی pullback؟
stop-entry روی شکست؟
ورود چند کندل اعتبار دارد؟
خروج و ریسک
SSL Exit cross؟
arrow؟
تغییر رنگ؟
HA reversal؟
TP/SL؟
trailing؟
partial exit؟
ب) اطلاعات لازم برای هر سیگنال

(قطعی) این اطلاعات باید قبل از نمایش کندل آینده ثبت شوند:

record_id
symbol
signal_bar_utc
decision = LONG | SHORT | NO_TRADE
trigger_type = B1 | B2 | OTHER
trigger_candle_description
entry_order_type = NEXT_OPEN | MARKET | LIMIT | STOP
entry_activation_time_utc
entry_price_or_exact_rule
entry_expiry_bars
initial_sl_price_or_rule
sl_anchor
tp1_price_or_rule
tp1_size_percent
tp2_price_or_rule
tp2_size_percent
remaining_position_exit_rule
break_even_rule
trailing_rule
pre_entry_invalidation_rule
ssl_components_used
other_context_used
confidence = 1 | 2 | 3
short_reason

(قطعی) اگر تریدر TP1 یا TP2 ندارد، مقدار باید صریحاً NONE باشد؛ نباید از روی position box تصاویر برای او قاعده اختراع کنیم.

ج) اطلاعات لازم هنگام خروج

پس از ورود و با آشکارشدن تدریجی کندل‌ها:

actual_entry_time_utc
actual_entry_real_price
exit_decision_bar_utc
exit_order_type
exit_fill_time_utc
exit_real_price
exit_reason
tp1_hit_time
tp2_hit_time
sl_hit_time
partial_exit_percentages
manual_override_reason

(قطعی) قیمت‌های اجرایی باید از real CoinEx OHLC ثبت شوند، حتی اگر تصمیم بصری روی چارت Heikin-Ashi گرفته شده باشد.

د) اطلاعات لازم برای NO_TRADE

(قطعی) فقط ثبت معاملات انتخاب‌شده کافی نیست. برای هر B1/B2 گسترده‌ای که تریدر رد می‌کند باید ثبت شود:

candidate_bar_utc
implied_side
decision = NO_TRADE
primary_rejection_reason
secondary_rejection_reason
missing_required_condition

دلیل‌های نمونه:

WRONG_BASELINE_SIDE
WEAK_OR_FLAT_SLOPE
TOO_EXTENDED
SSL1_DISAGREEMENT
SSL2_DISAGREEMENT
EXIT_LINE_WRONG_STATE
CHOP_OR_CONSOLIDATION
WEAK_BETA
LATE_ENTRY
NEAR_SUPPORT_RESISTANCE
POOR_RISK_REWARD
HIGH_VOLATILITY
OTHER

(قطعی) یک توضیح آزاد کوتاه نیز کنار reason code لازم است؛ فهرست آماده نباید تریدر را مجبور کند انتخاب واقعی خود را در یکی از دسته‌های ما جا بدهد.

هـ) شواهد ممیزی

برای هر معامله دو تصویر لازم است:

تصویر لحظه تصمیم، با سمت راست چارت کاملاً بریده و بدون آینده؛
تصویر پس از خروج.

اما هر تصویر باید همراه با این موارد باشد:

symbol
UTC timestamp
record_id
side

(قطعی) screenshot بدون timestamp و structured record دوباره همان نقص ۱۲ تصویر فعلی را ایجاد می‌کند.

چیزی که تریدر نباید ارائه کند

(قطعی) تریدر نباید پس از دیدن نتیجه، گذشته را بازنویسی کند یا فقط معاملات موفق را تحویل دهد.

(قطعی) این موارد را خود پایپلاین محاسبه می‌کند:

gross PnL
net PnL
MFE
MAE
holding time
TP/SL order
drawdown
win rate
expectancy

تریدر باید تصمیم و منطق تصمیم را بدهد، نه ارزیابی آماری نتیجه را.