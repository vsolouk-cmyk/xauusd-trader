# گزارش فشرده برای ارزیابی خارجی پروژه XAUUSD پس از آخرین نظر متخصص

تاریخ تهیه: 2026-07-04  
دامنه گزارش: اقدامات، تست‌ها، خروجی‌ها، تصمیم‌ها و فایل‌های درگیر از زمان ورود به مسیر عملیاتی demo-live execution تا وضعیت فعلی قبل از باز شدن بازار.

---

## 1. خلاصه مدیریتی

پس از آخرین ارزیابی متخصص، مسیر پروژه از observer/forward-only به سمت **demo-live execution loop** منتقل شد تا به‌جای حذف واقعیات با forward-test طولانی، رفتار واقعی order، fill، rejection، time-exit، deal history و PnL روی حساب demo MT5 دیده شود.

نتیجه مهم تا این لحظه:

- اتصال MT5، تولید telemetry، ارسال order demo، دریافت deal history و ساخت ledger عملیاتی تا حد قابل اتکا برقرار شده است.
- اجرای demo واقعی انجام شده و ۷ معامله demo بسته‌شده داریم.
- ledger نهایی معتبر پس از اصلاح Stage144C:
  - successful buy attempts: 7
  - closed trades: 7
  - open/unmatched: 0
  - profit count: 4
  - loss count: 3
  - win rate: 57.14%
  - total net profit: +17.10
  - mean net profit: +2.44
  - total bps: +43.83
  - mean bps: +6.26
- rule-family قبلی `D138C_ret_48h_bps_GEQ65...` بعد از فرسایش edge و دو loss متوالی موقتاً frozen شد.
- replacement selector در Stage138C فعال شد و candidate جایگزین زیر را پیدا کرد:
  - `D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65`
  - validation mean: +23.6651 bps
  - validation hit rate: 60.59%
  - tail mean: +10.6789 bps
  - tail hit rate: 55.52%
- اولین تلاش برای order روی replacement انجام شد، اما با retcode `10018 market closed` رد شد. یعنی blocker فعلی strategy/discovery نیست، بلکه بسته بودن بازار است.

تصمیم فعلی قبل از باز شدن بازار:

- live-real ممنوع است.
- family قبلی frozen بماند.
- Stage134 آماده demo execution با replacement باشد.
- اگر بعد از باز شدن بازار retcode غیر از 10018 بود ولی order باز نشد، مشکل احتمالی retry/duplicate logic در Stage134 است و باید دقیقاً همان نقطه اصلاح شود.

---

## 2. هدف عملیاتی پس از نظر متخصص

هدف اجرایی اصلاح‌شده:

1. ورود به حلقه demo-live execution با اندازه 0.01 lot.
2. ثبت order واقعی demo، fill، rejection، TP/SL، time-exit، deal history و PnL.
3. تصمیم سریع:
   - rule خوب بود: ادامه تا sample بیشتر.
   - rule ضعیف شد: freeze سریع.
   - execution گیر کرد: فقط blocker مستقیم execution اصلاح شود.
4. جلوگیری از بازگشت به چرخه‌ی بی‌پایان observer/audit بدون order.

اصل تجاری که در طول کار بارها نقض/اصلاح شد:

- telemetry و audit فقط وقتی مجاز است که مستقیم برای execution یا outcome لازم باشد.
- هدف، جمع کردن closed demo outcomes است، نه ساختن reportهای بیشتر.

---

## 3. وضعیت محیط اجرایی

### Repo و مسیرها

Repo:

```text
/Users/vahid/Desktop/xauusd-trader
```

MT5 MQL5/Files:

```text
/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files
```

MT5 Expert Advisors:

```text
/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD
```

فایل زنده H1 صادرشده از MT5:

```text
/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/xauusd_stage143_live_h1_bars.csv
```

### وضعیت MT5

- حساب: DEMO
- symbol: XAUUSD
- Stage134 EA روی چارت XAUUSD
- Stage138C فقط rule-state KV می‌نویسد؛ order نمی‌زند.
- Stage134 order-capable است ولی demo-only.
- terminal_trade_allowed، mql_trade_allowed و account_trade_allowed در آخرین status همگی true بودند.
- آخرین retcode مربوط به replacement: `10018 market closed`.

---

## 4. سیر اقدامات و نتایج

### 4.1 Stage131 — MT5 runtime heartbeat

هدف: تشخیص اینکه آیا MT5 می‌تواند در مسیر MQL5/Files فایل تازه بنویسد یا خیر.

نتیجه:

- MT5 runtime heartbeat تازه تولید شد.
- مشکل اصلی در آن مقطع stale telemetry writer بود، نه ناتوانی MT5 در نوشتن فایل.
- تصمیم: به‌جای observerهای پراکنده، telemetry writer یکپارچه لازم است.

فایل‌ها/خروجی‌ها:

```text
xauusd_stage131_runtime_heartbeat...
```

---

### 4.2 Stage132 و Stage133 — Unified Observer telemetry

هدف Stage132:

- افزودن heartbeat/telemetry writer به Unified Observer EA.

هدف Stage133:

- افزودن rule-state telemetry برای ruleهای observer.

نتیجه:

- Stage132 telemetry تازه تولید کرد.
- Stage133 rule-state برای ۷ rule observer تولید کرد.
- Stage133B delimiter hotfix برای CSVها اضافه شد.
- این مسیر ثابت کرد MT5 telemetry قابل اتکاست، اما هنوز order اجرا نمی‌شد.

فایل‌های کلیدی:

```text
xauusd_stage132_unified_observer_ea_heartbeat_kv.csv
xauusd_stage133_unified_observer_rule_state_kv.csv
xauusd_stage133_unified_observer_rule_state_latest.csv
xauusd_stage133_unified_observer_rule_state_history.csv
```

تست‌ها:

```text
Stage132: pytest 4 passed
Stage133: pytest 4 passed
Stage133B: pytest 6 passed
```

---

### 4.3 Stage134 — Demo Executor Pilot

هدف:

- ساخت EA order-capable ولی demo-only.
- جلوگیری از real/live account.
- fixed lot = 0.01
- SL/TP/time-exit
- duplicate guard با `feature_date|rule_id`
- spread guard
- max open positions
- state/status/trade log output

نتیجه:

- Stage134 موفق شد order demo بزند.
- trade_log واقعی تولید شد.
- retcodeهای عملی دیده شد:
  - 10009: order done
  - 10018: market closed
- Stage134B collector اصلاح شد تا trade_log را بر status stale اولویت دهد.

فایل‌های کلیدی:

```text
MQL5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5
xauusd_stage134_demo_executor_status_kv.csv
xauusd_stage134_demo_executor_trade_log.csv
xauusd_stage134_demo_executor_state_kv.csv
```

تست‌ها:

```text
Stage134: pytest 4 passed
Stage134B: pytest 3 passed
Stage146C static tests: 4 passed
```

---

### 4.4 Stage135 تا Stage137 — تلاش‌های discovery schema-based

هدف:

- یافتن rule demo-probe از خروجی‌های قبلی Stage117/live schema.

نتیجه:

- Stage135 به‌خاطر عدم bind مشخص با schema Stage117 ناکام شد.
- Stage135B نشان داد latest feature stale/historical است.
- Stage136 live broad discovery به‌خاطر نبود numeric common features بین live و historical موفق نشد.
- Stage137 نشان داد live signal عملاً numeric keys کافی ندارد.
- تصمیم: به‌جای ادامه schema repair، broker technical discovery مستقیم از AMarkets/MT5 bars ساخته شود.

جمع‌بندی:

```text
این مسیر برای execution عملی مفید نبود و کنار گذاشته شد.
```

---

### 4.5 Stage138 و Stage138B — Broker Technical Demo Discovery

هدف:

- ساخت rule-state قابل استفاده برای Stage134 از روی broker H1 bars.
- بدون order.
- تولید KV سازگار با Stage134.

Stage138B:

- parser برای MT5 export اصلاح شد:
  - tab/comma/semicolon
  - `<DATE>`, `<TIME>`
  - headers مختلف

نتیجه اولیه:

- rule فعالی انتخاب شد و Stage134 توانست با آن order demo بزند.
- در ادامه چند rule از خانواده `D138C_ret_48h_bps_GEQ65...` فعال شدند.

فایل‌های کلیدی:

```text
app/stage138_broker_technical_demo_discovery.py
reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json
reports/stage138_broker_technical_demo_discovery/stage138_candidate_scores.csv
data/demo_execution/xauusd_stage138_technical_rule_state_kv.csv
data/demo_execution/xauusd_stage138_technical_rule_state_latest.csv
MQL5/Files/xauusd_stage138_technical_rule_state_kv.csv
MQL5/Files/xauusd_stage138_technical_rule_state_latest.csv
```

تست‌ها:

```text
Stage138B: pytest 3 passed
```

---

### 4.6 Stage139، Stage140، Stage141 — Outcome monitoring and ledger

Stage139:

- monitor پوزیشن باز demo.
- read-only.

Stage140:

- closed deal monitor.
- Stage140B برای MQL5 compatibility اصلاح شد.

Stage141:

- outcome ledger اولیه.
- بعداً مشخص شد raw ledger در شمارش rows ناسازگار می‌شود.

نتیجه:

- deal history قابل دریافت بود.
- اولین دو معامله با TP و سود بسته شدند.
- اما Stage141 ledger در مواردی duplicate/mismatch داشت و برای تصمیم تجاری کنار گذاشته شد.

فایل‌های کلیدی:

```text
xauusd_stage140_demo_deals_history.csv
data/demo_execution/stage141_demo_execution_outcome_ledger.csv
reports/stage141_demo_execution_outcome_ledger/stage141_demo_execution_outcome_ledger_summary.json
```

تست‌ها:

```text
Stage139: pytest 3 passed
Stage140B: pytest 3 passed
Stage141: pytest 3 passed
```

---

### 4.7 Stage142 و Stage142B — Demo loop supervisor

هدف:

- اجرای زنجیره‌ی monitoring:
  - Stage134 collector
  - Stage139
  - Stage140
  - Stage141
- Stage142 اولیه به‌خاطر اجرای Stage138 refresh در loop کند/timeout-prone شد.
- Stage142B fast loop ساخته شد که Stage138 refresh را از loop سریع حذف کرد.

نتیجه:

- loop execution/monitoring پایدارتر شد.
- Stage138 refresh جداگانه و کندتر/۱۵ دقیقه‌ای مدیریت شد.

فایل‌های کلیدی:

```text
app/stage142_demo_loop_supervisor.py
reports/stage142_demo_loop_supervisor/stage142_demo_loop_supervisor_summary.json
logs/stage142_demo_loop.out.log
logs/stage142_demo_loop.err.log
```

تست‌ها:

```text
Stage142B: pytest 4 passed
```

---

### 4.8 Stage143 — Live H1 bar exporter

هدف:

- جایگزینی فایل H1 stale با export زنده از MT5.

نتیجه:

- ۳۰٬۰۰۰ کندل H1 از MT5 صادر شد.
- Stage138 از فایل live H1 استفاده کرد.

فایل‌های کلیدی:

```text
MQL5/Indicators/Stage143_LiveH1BarExporter.mq5
app/stage143_live_h1_bar_exporter_collector.py
MQL5/Files/xauusd_stage143_live_h1_bars.csv
MQL5/Files/xauusd_stage143_live_h1_bar_exporter_kv.csv
reports/stage143_live_h1_bar_exporter/stage143_live_h1_bar_exporter_summary.json
```

تست‌ها:

```text
Stage143: pytest 3 passed
```

نکته فنی:

- در برخی گزارش‌ها اختلاف برچسب UTC/MT5 server time دیده شد. هنوز برای demo execution blocker نبود، ولی برای audit نهایی باید timezone mapping دقیق‌تر شود.

---

### 4.9 Stage144، Stage144B، Stage144C — Demo execution ledger audit

Stage144 هدف:

- reconcile کردن:
  - Stage134 trade_log
  - Stage140 deals_history
  - Stage141 raw ledger
- ساخت clean ledger قابل اعتماد.

Stage144 اولیه:

- ledger_count_mismatch را درست تشخیص داد.
- اما در موارد open/unmatched هنوز کامل نبود.

Stage144B:

- برای رفع reconciliation ساخته شد.
- ولی عملیاتی خراب‌تر کرد:
  - closed_trade_count را صفر کرد.
  - همه attempts را open/unmatched زد.
- Stage144B کنار گذاشته شد.

Stage144C:

- parser و pairing اصلاح شد.
- TIME_EXIT rowها را attempt حساب نکرد.
- headerless/deal-history rows و position_id pairing را بهتر مدیریت کرد.
- خروجی معتبر فعلی را تولید کرد.

خروجی معتبر Stage144C:

```text
successful_buy_attempts: 7
unique_trade_attempts: 7
closed_trade_count: 7
open_or_unmatched_count: 0
profit_count: 4
loss_count: 3
total_net_profit: 17.10
mean_net_profit: 2.44
total_bps: 43.83
mean_bps: 6.26
win_rate: 0.5714
```

فایل‌های کلیدی:

```text
app/stage144_demo_execution_ledger_audit.py
configs/stage144_demo_execution_ledger_audit.json
configs/stage144b_demo_execution_ledger_reconciliation.json
configs/stage144c_demo_execution_ledger_reconciliation.json
docs/stage144_demo_execution_ledger_audit.md
docs/stage144b_demo_execution_ledger_reconciliation.md
docs/stage144c_demo_execution_ledger_reconciliation.md
tests/test_stage144_demo_execution_ledger_audit.py
tests/test_stage144b_demo_execution_ledger_reconciliation.py
tests/test_stage144c_demo_execution_ledger_reconciliation.py
data/demo_execution/stage144_clean_demo_execution_ledger.csv
reports/stage144_demo_execution_ledger_audit/stage144_clean_demo_execution_ledger.csv
reports/stage144_demo_execution_ledger_audit/stage144_demo_execution_ledger_audit_summary.json
reports/stage144_demo_execution_ledger_audit/stage144_risk_manifest.csv
```

تست‌ها:

```text
Stage144: pytest 3 passed
Stage144B: pytest 2 passed, ولی operationally failed
Stage144C: pytest 2 passed و operationally validated
```

---

### 4.10 Stage145 — Clean Ledger Performance Gate

هدف:

- خواندن clean ledger Stage144.
- تصمیم:
  - continue small-N
  - continue positive
  - freeze/repair loss streak
  - freeze/repair negative expectancy

نتیجه:

- Stage145 روی Stage144C وضعیت فعلی را چنین می‌بیند:

```text
closed_trade_count: 7
profit_count: 4
loss_count: 3
win_rate: 0.5714
total_net_profit: 17.10
mean_net_profit: 2.44
mean_bps: 6.26
max_consecutive_losses: 2
gate_decision: STAGE145_CONTINUE_DEMO_ACCUMULATION_SMALL_N
recommended_action: CONTINUE_DEMO_LOOP_NO_LIVE_PROMOTION
```

نکته مهم:

- Stage145 هنوز aggregate است و per-rule-family decision ندارد.
- در عمل decision دستی سختگیرانه‌تر اعمال شد:
  - family ضعیف قبلی frozen شد.
  - ادامه wildcard روی آن مجاز نیست.

فایل‌های کلیدی:

```text
app/stage145_clean_ledger_performance_gate.py
configs/stage145_clean_ledger_performance_gate.json
docs/stage145_clean_ledger_performance_gate.md
tests/test_stage145_clean_ledger_performance_gate.py
reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json
reports/stage145_clean_ledger_performance_gate/stage145_latest_performance_gate_snapshot.csv
data/demo_execution/stage145_clean_ledger_performance_gate_snapshots.csv
```

تست‌ها:

```text
Stage145: pytest 4 passed
```

---

### 4.11 Stage146C — Demo frequency unblocker

مشکل:

- بعد از مدتی ۱۲ ساعت تقریباً trade جدید نداشتیم.
- علت اصلی:
  - Stage134 با `InpAllowedRules` ایستا بود.
  - Stage138 rule جدید می‌داد ولی Stage134 فقط rule دستی قبلی را قبول می‌کرد.

اصلاح:

- Stage146C در Stage134:
  - `InpAllowedRules=*` را مجاز کرد.
  - blank/ANY/ALL هم به wildcard interpretation نزدیک شدند.
  - duplicate guard همچنان براساس `feature_date|rule_id` حفظ شد.
  - demo-only guard، max positions، spread guard، SL/TP حفظ شد.

نتیجه:

- frequency unblock شد.
- بعد از آن چند order پشت سر هم وارد demo execution شد.
- همین باعث شد کیفیت واقعی rule-family آشکار شود.

فایل‌های کلیدی:

```text
MQL5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5
configs/stage146c_demo_frequency_unblocker_stage134c.json
docs/stage146c_demo_frequency_unblocker_stage134c.md
tests/test_stage146c_static_mql_patch.py
```

تست‌ها:

```text
Stage146C static MQL tests: 4 passed
```

نکته:

- MaxOpenPositions ابتدا برای افزایش داده گسترش یافت، ولی بعداً برای کنترل ریسک demo به 1 برگشت.
- MaxHoldMinutes برای time-boxing کاهش یافت و در نهایت روی 60 دقیقه برای replacement پیشنهاد شد.

---

### 4.12 Freeze خانواده قبلی

خانواده قبلی:

```text
D138C_ret_48h_bps_GEQ65...
```

دلایل freeze:

- بعد از باز شدن فرکانس، کیفیت افت کرد.
- تعداد losses به ۳ رسید.
- دو loss متوالی دیده شد.
- سود کل شکننده شد.
- با یک loss دیگر تقریباً expectancy عملیاتی از بین می‌رفت.

وضعیت نهایی آن خانواده در clean ledger:

```text
closed trades total: 7
profit: 4
loss: 3
net: +17.10
win rate: 57.14%
mean bps: +6.26
max consecutive losses: 2
```

تصمیم:

```text
ادامه wildcard روی این family مجاز نیست.
```

---

### 4.13 Stage138C — Filtered Replacement Selector

هدف:

- ادامه demo execution بدون برگشت به observer-only.
- exclude کردن family ضعیف قبلی.
- انتخاب replacement current-active با validation/tail بهتر.
- بدون order و بدون position modification.

اجرای Stage138C:

```text
excluded_rule_substrings:
D138C_ret_48h_bps_GEQ65
```

خروجی انتخاب‌شده:

```text
selected_rule_id:
D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65

selected_label:
ret_3h_bps >= q65 AND ret_48h_bps >= q65

current_active:
true

validation_events:
1317

validation_mean_bps:
23.6651

validation_hit_rate:
0.6059

tail_events:
1396

tail_mean_bps:
10.6789

tail_hit_rate:
0.5552
```

هشدار:

```text
selection_mean_bps: -0.9699
selection_hit_rate: 0.4989
```

تفسیر:

- این candidate در validation/tail خوب است اما در کل selection window ضعیف بوده.
- بنابراین فقط demo-probe مجاز است، نه اعتماد تجاری.

فایل‌های کلیدی:

```text
app/stage138_broker_technical_demo_discovery.py
configs/stage138c_filtered_replacement_selector.json
docs/stage138c_filtered_replacement_selector.md
tests/test_stage138c_filtered_replacement_selector.py
reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json
reports/stage138_broker_technical_demo_discovery/stage138_candidate_scores.csv
MQL5/Files/xauusd_stage138_technical_rule_state_kv.csv
MQL5/Files/xauusd_stage138_technical_rule_state_latest.csv
```

تست‌ها:

```text
Stage138C: py_compile passed
Stage138C: pytest 3 passed
```

---

## 5. معاملات واقعی demo ثبت‌شده

بر اساس trade_log و deal_history، ۷ معامله demo بسته شده‌اند.

| # | Signal key / rule | Entry | Exit | Reason | Net |
|---|---|---:|---:|---|---:|
| 1 | `2026-07-01T11:00:00Z | D138C_trend_20_50_bps_LEQ35__range_pos_24_LEQ35` | 3997.84 | 4015.88 | TP | +18.04 |
| 2 | `2026-07-01T23:00:00Z | D138C_ret_48h_bps_GEQ50__trend_50_100_bps_LEQ50` | 4040.92 | 4059.02 | TP | +18.10 |
| 3 | `2026-07-02T15:00:00Z | D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50` | 4131.31 | 4119.17 | SL | -12.14 |
| 4 | `2026-07-02T17:00:00Z | D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50` | 4116.03 | 4118.08 | TIME_EXIT/CLOSE | +2.05 |
| 5 | `2026-07-02T18:00:00Z | D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50` | 4118.49 | 4106.34 | SL | -12.15 |
| 6 | `2026-07-02T19:00:00Z | D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65` | 4116.29 | 4108.32 | TIME_EXIT/CLOSE | -7.97 |
| 7 | `2026-07-02T20:00:00Z | D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65` | 4108.68 | 4119.85 | CLOSE | +11.17 |

جمع:

```text
Net total: +17.10
Closed trades: 7
Profit/Loss: 4/3
Win rate: 57.14%
Mean net: +2.44
Mean bps: +6.26
```

---

## 6. وضعیت فعلی دقیق قبل از باز شدن بازار

Stage138C replacement KV:

```text
stage: Stage138C_FILTERED_REPLACEMENT_TECHNICAL_DEMO_DISCOVERY
selected_rule_id: D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65
feature_date: 2026-07-03T19:00:00Z
any_signal_active: true
active_rule_count: 1
execution_allowed: false
order_send: false
```

Stage134 status:

```text
stage: Stage134_DEMO_EXECUTOR_PILOT
decision: HOLD_RETRY_COOLDOWN
reason: same signal attempted recently
selected_rule_id: D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65
allowed_rules: *
any_signal_active: true
signal_fresh: true
spread_ok: true
open_positions: 0
max_open_positions: 1
last_retcode: 10018
last_retcode_description: market closed
```

آخرین attempt replacement:

```text
time_local: 2026.07.04 11:41:03
event_type: DEMO_BUY_ATTEMPT
signal_key: 2026-07-03T19:00:00Z|D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65
ok: false
retcode: 10018
retcode_description: market closed
```

تفسیر:

```text
Discovery درست است.
Stage134 از freeze خارج شده است.
Signal فعال و تازه است.
Spread و account/trade permissions درست هستند.
مشکل فعلی فقط market closed است.
```

ریسک احتمالی بعد از باز شدن بازار:

- اگر Stage134 failed attempt با retcode=10018 را به‌عنوان duplicate/retry blocker طولانی نگه دارد، ممکن است بعد از باز شدن بازار هم order نزند.
- اگر چنین شد، patch لازم فقط باید Stage134 retry logic را اصلاح کند:
  - failed retcode 10018 نباید مثل successful duplicate signal تلقی شود.
  - retry بعد از market open باید مجاز باشد.

---

## 7. فایل‌های مرتبط و درگیر

### 7.1 MT5 / MQL5 Experts و Indicators

```text
MQL5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5
MQL5/Indicators/Stage143_LiveH1BarExporter.mq5
Unified_ObserverOnly_EA.mq5
```

### 7.2 فایل‌های runtime در MQL5/Files

```text
xauusd_stage134_demo_executor_status_kv.csv
xauusd_stage134_demo_executor_trade_log.csv
xauusd_stage134_demo_executor_state_kv.csv

xauusd_stage138_technical_rule_state_kv.csv
xauusd_stage138_technical_rule_state_latest.csv

xauusd_stage140_demo_deals_history.csv

xauusd_stage143_live_h1_bars.csv
xauusd_stage143_live_h1_bar_exporter_kv.csv

xauusd_stage133_unified_observer_rule_state_kv.csv
xauusd_stage133_unified_observer_rule_state_latest.csv
xauusd_stage133_unified_observer_rule_state_history.csv
```

### 7.3 Python app files

```text
app/stage138_broker_technical_demo_discovery.py
app/stage142_demo_loop_supervisor.py
app/stage143_live_h1_bar_exporter_collector.py
app/stage144_demo_execution_ledger_audit.py
app/stage145_clean_ledger_performance_gate.py
```

فایل‌های app مرتبط قبلی یا بسته‌های قبلی که باید در repo بررسی شوند:

```text
app/stage134_demo_executor_collector.py
app/stage139_demo_position_outcome_monitor_collector.py
app/stage140_demo_closed_deal_outcome_monitor_collector.py
app/stage141_demo_execution_outcome_ledger.py
```

### 7.4 Config files

```text
configs/stage138c_filtered_replacement_selector.json
configs/stage144_demo_execution_ledger_audit.json
configs/stage144b_demo_execution_ledger_reconciliation.json
configs/stage144c_demo_execution_ledger_reconciliation.json
configs/stage145_clean_ledger_performance_gate.json
configs/stage146c_demo_frequency_unblocker_stage134c.json
```

### 7.5 Docs

```text
docs/stage138c_filtered_replacement_selector.md
docs/stage144_demo_execution_ledger_audit.md
docs/stage144b_demo_execution_ledger_reconciliation.md
docs/stage144c_demo_execution_ledger_reconciliation.md
docs/stage145_clean_ledger_performance_gate.md
docs/stage146c_demo_frequency_unblocker_stage134c.md
```

### 7.6 Tests

```text
tests/test_stage138c_filtered_replacement_selector.py
tests/test_stage144_demo_execution_ledger_audit.py
tests/test_stage144b_demo_execution_ledger_reconciliation.py
tests/test_stage144c_demo_execution_ledger_reconciliation.py
tests/test_stage145_clean_ledger_performance_gate.py
tests/test_stage146c_static_mql_patch.py
```

### 7.7 Reports and data outputs

```text
reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json
reports/stage138_broker_technical_demo_discovery/stage138_candidate_scores.csv

reports/stage144_demo_execution_ledger_audit/stage144_demo_execution_ledger_audit_summary.json
reports/stage144_demo_execution_ledger_audit/stage144_clean_demo_execution_ledger.csv
reports/stage144_demo_execution_ledger_audit/stage144_risk_manifest.csv

reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json
reports/stage145_clean_ledger_performance_gate/stage145_latest_performance_gate_snapshot.csv
reports/stage145_clean_ledger_performance_gate/stage145_risk_manifest.csv

data/demo_execution/stage144_clean_demo_execution_ledger.csv
data/demo_execution/stage145_clean_ledger_performance_gate_snapshots.csv
data/demo_execution/xauusd_stage138_technical_rule_state_kv.csv
data/demo_execution/xauusd_stage138_technical_rule_state_latest.csv
```

### 7.8 Patch packages ساخته‌شده در این دوره

```text
stage134_demo_executor_pilot_package.zip
stage134b_trade_log_priority_collector_hotfix_package.zip
stage138_broker_technical_demo_discovery_package.zip
stage138b_mt5_export_parser_hotfix_package.zip
stage139_demo_position_outcome_monitor_package.zip
stage140b_mql5_compat_closed_deal_monitor_package.zip
stage141_demo_execution_outcome_ledger_package.zip
stage142b_fast_demo_loop_supervisor_package.zip
stage143_live_h1_bar_exporter_package.zip
stage144_demo_execution_ledger_audit_package.zip
stage145_clean_ledger_performance_gate_package.zip
stage146c_demo_frequency_unblocker_stage134c_package.zip
stage144b_demo_execution_ledger_reconciliation_hotfix_package.zip
stage144c_demo_execution_ledger_reconciliation_hotfix_package.zip
stage138c_filtered_replacement_selector_package.zip
```

---

## 8. ارزیابی انتقادی

### نقاط مثبت

1. **اجرای واقعی demo انجام شده است**  
   دیگر فقط observer یا historical replay نیست. order واقعی demo با retcode و deal history ثبت شده است.

2. **MT5 runtime و فایل‌نویسی تأیید شده‌اند**  
   مسیر MQL5/Files قابل استفاده است.

3. **Stage134 توانسته order بزند و time-exit اجرا کند**  
   پس execution harness به‌صورت عملی کار کرده است.

4. **Stage144C clean ledger قابل اتکا شده است**  
   بعد از شکست Stage144B، نسخه C با داده واقعی validate شد.

5. **freeze discipline اعمال شد**  
   family ضعیف بدون تعارف متوقف شد.

6. **replacement selector با exclusion ساخته شد**  
   یعنی به‌جای ادامه امیدی روی family ضعیف، selector جدید با filter فعال شد.

### نقاط منفی / ریسک‌ها

1. **تعداد stageها زیاد و مسیر پر اصطکاک شد**  
   چند patch و audit برای رسیدن به ledger قابل اتکا لازم شد. این از منظر time-to-market هزینه‌بر بوده است.

2. **Stage145 هنوز aggregate است، نه per-family**  
   نتیجه کل ۷ معامله را می‌بیند، ولی برای تصمیم rule replacement باید per-rule-family یا per-generation performance داشته باشیم.

3. **H1 ruleها frequency و responsiveness محدود دارند**  
   اگر replacement بعد از باز شدن بازار هم کم‌فرکانس باشد، باید سریعاً به M15/M5 execution feed رفت.

4. **Candidate جدید در selection window ضعیف بوده**  
   `selection_mean_bps=-0.9699` و `selection_hit_rate=0.4989` هشدار جدی است. validation/tail بهتر هستند، اما ممکن است selection به regime اخیر overfit شده باشد.

5. **time-exit و immediate re-entry باعث risk clustering شد**  
   چند بار time-exit و entry بعدی در فاصله خیلی کوتاه رخ داد. باید cooldown بعد از exit نیز بررسی شود، نه فقط cooldown بعد از attempt.

6. **market closed retcode ممکن است duplicate/retry را آلوده کند**  
   failed attempt با retcode 10018 نباید بعد از باز شدن بازار مانع retry شود.

7. **هنوز news/session/exogenous filters وارد execution نشده‌اند**  
   gold نسبت به news، DXY، yields، session و spread حساس است. فعلاً Stage138C purely technical است.

8. **live-real هنوز به هیچ وجه مجاز نیست**  
   sample کم، family instability، و فقدان per-family audit مانع promotion هستند.

---

## 9. پرسش‌های پیشنهادی برای ارزیاب خارجی

1. با توجه به clean ledger فعلی، آیا freeze family قبلی درست بوده است؟
2. آیا replacement candidate با وجود selection_mean منفی، ارزش demo-probe دارد؟
3. آیا باید H1 replacement ادامه یابد یا فوراً به M15/M5 execution feed برویم؟
4. thresholdهای Stage138C برای replacement مناسب هستند یا باید سخت‌تر شوند؟
5. آیا Stage145 باید فوراً per-family شود یا برای سرعت عملیاتی aggregate کافی است؟
6. آیا failed market-closed attempt باید در Stage134 retry/duplicate logic کاملاً نادیده گرفته شود؟
7. آیا MaxHoldMinutes=60 برای XAUUSD H1 signal منطقی است یا با horizon 24H تناقض دارد؟
8. آیا باید TP/SL فعلی نسبت به ATR/volatility dynamic شود؟
9. آیا ادامه demo با purely technical rule بدون news/session filter قابل دفاع است؟
10. معیار عملیاتی توقف replacement چه باشد:
    - دو loss متوالی؟
    - total_net <= 0 بعد از ۴ trade؟
    - mean_bps < 2 بعد از ۶ trade؟
    - یا معیار دیگر؟

---

## 10. پیشنهاد عملیاتی فعلی برای بعد از باز شدن بازار

### حالت A: بازار باز شد و replacement order با retcode 10009 پذیرفته شد

اقدام:

```text
اجازه بده یک closed outcome کامل شود.
بعد Stage144C و Stage145 را اجرا کن.
اگر replacement trade اول loss شد، هنوز freeze فوری نکن؛ مگر loss دوم پشت سرش بیاید.
```

### حالت B: بازار باز شد اما Stage134 هنوز order نزد

اگر status چنین بود:

```text
any_signal_active: true
signal_fresh: true
spread_ok: true
open_positions: 0
last_retcode: 10018
decision: HOLD_RETRY_COOLDOWN
```

اقدام:

```text
Stage134 retry logic باید patch شود.
retcode=10018 نباید last_attempt_signal_key را برای duplicate/retry blocking دائمی معتبر کند.
```

### حالت C: replacement پس از ۴ closed trade منفی شد

اقدام:

```text
Freeze replacement.
H1 Stage138C مسیر کافی نیست.
به M15/M5 execution feed برو.
```

### حالت D: replacement ۳ تا ۵ outcome مثبت/قابل قبول داد

اقدام:

```text
ادامه demo تا حداقل 10 closed outcomes.
همچنان live-real ممنوع.
بعد از 10 outcome، per-family performance review.
```

---

## 11. جمع‌بندی نهایی برای متخصص

این پروژه اکنون از نظر فنی به مرحله‌ی واقعی demo execution رسیده است، اما از نظر strategy هنوز اثبات نشده است. مهم‌ترین دستاورد این دوره، نه سود کوچک ledger، بلکه کشف این بود که:

```text
۱) execution واقعی کار می‌کند.
۲) frequency را می‌توان unblock کرد.
۳) quality بعضی rule-familyها سریع فرسوده می‌شود.
۴) clean reconciliation حیاتی است و Stage144C فعلاً معیار معتبر است.
۵) replacement selection با exclusion ممکن شده است.
```

و مهم‌ترین خطر فعلی:

```text
با وجود اجرای واقعی، ممکن است همچنان روی ruleهای technical/H1 کم‌دوام و regime-sensitive بچرخیم.
اگر replacement جدید سریع شکست بخورد، باید بدون ساخت auditهای بیشتر مسیر execution feed را به M15/M5 یا family جدید منتقل کنیم.
```
