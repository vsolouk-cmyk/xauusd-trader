# Stage38A — T1 Read-only Implementation Plan

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Implementation plan for a future read-only T1 test script  
**Generated UTC:** 2026-06-16T12:34:08Z  
**Status:** Implementation planning only; no strategy code yet  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO  
**Cost policy:** FREE-FIRST ONLY

---

چپ‌چین ادامه می‌دهم.

این سند برنامه پیاده‌سازی آینده برای تست read-only thesis اول است:

```text
T1_REGIME_FILTERED_STRUCTURE_CONTINUATION
```

این سند هنوز کد نیست. هدف این است که قبل از ساخت اسکریپت، نام فایل، ورودی‌ها، خروجی‌ها، validation checks، variant matrix، report schema، و kill/pass logic دقیق شود.

بعد از این سند، اگر همه چیز روشن ماند، گام بعدی می‌تواند ساخت یک اسکریپت read-only باشد. آن اسکریپت هم فقط report تولید می‌کند و هیچ ارتباطی با EA، paper-live، order یا Stage39 عملیاتی ندارد.

---

## 1. Executive Decision

Current status:

```text
T1_READ_ONLY_TEST_DESIGN = CREATED
T1_IMPLEMENTATION_PLAN_READ_ONLY = CREATED
T1_READ_ONLY_SCRIPT = ALLOWED_NEXT_AFTER_REVIEW
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

این سند اجازه اجرای strategy code نمی‌دهد، اما اجازه می‌دهد در گام بعدی یک اسکریپت read-only ساخته شود که فقط داده را بخواند، setupها را طبق قواعد قفل‌شده ارزیابی کند، و گزارش خروجی بسازد.

---

## 2. Future Script Name

If approved, the future read-only script should be:

```text
app/stage38a_t1_read_only_test.py
```

The script must be read-only.

Allowed:

```text
read SQLite data
derive H4/D1 bars
join macro regime
generate candidate trades
apply fixed variant rules
apply fixed cost cases
write CSV/JSON/MD reports under data/reports
```

Forbidden:

```text
modify input tables
write signals into live/dryrun tables
create orders
touch EA/MQL files
change scheduler
connect to broker
send Telegram trade alerts
write paper/live instructions
```

---

## 3. Output Directory

Future script output path:

```text
data/reports/stage38a_t1_read_only_test/
```

Required output files:

```text
stage38a_t1_summary.json
stage38a_t1_variant_metrics.csv
stage38a_t1_trade_ledger.csv
stage38a_t1_regime_split.csv
stage38a_t1_cost_sensitivity.csv
stage38a_t1_diagnostics.csv
stage38a_t1_read_only_test.md
```

Optional diagnostic files:

```text
stage38a_t1_yearly_metrics.csv
stage38a_t1_monthly_metrics.csv
stage38a_t1_skip_reasons.csv
stage38a_t1_level_diagnostics.csv
stage38a_t1_entry_diagnostics.csv
```

---

## 4. Primary Inputs

### 4.1 Price Input

Primary DB:

```text
data/local/xauusd_local_store.sqlite
```

Primary table:

```text
bars
```

Price filter:

```text
source = 'amarkets_mt5'
symbol = 'XAUUSD'
timeframe = '1h'
```

Required columns:

```text
utc_time
open
high
low
close
spread
source
symbol
timeframe
```

Minimum coverage already observed:

```text
2022-05-01T23:00:00Z to 2026-06-16T12:00:00Z
```

The script must verify this at runtime.

### 4.2 Macro Input

Macro table:

```text
macro_daily_regime
```

Required columns:

```text
obs_date
macro_regime
macro_score_long_gold
d_real_yield_20d
d_usd_20d_pct
rate_pressure_score
usd_pressure_score
regime_reason
```

Do not use:

```text
macro_context_h1.macro_regime
```

Reason:

```text
Audit showed macro_context_h1 labels are all neutral.
```

### 4.3 Event Input

Optional for guard only:

```text
macro_events
news_events
event_pipeline_staging
```

But v0 may use only a simple event guard if reliable scheduled events exist.

If event guard quality is uncertain:

```text
use Sunday/Monday open block only
record event_guard_status = limited
```

---

## 5. Runtime Validation Checks

Before any candidate generation, the future script must run preflight checks.

### 5.1 DB Existence

```text
[ ] data/local/xauusd_local_store.sqlite exists
```

### 5.2 Price Table Check

```text
[ ] bars table exists
[ ] required OHLC columns exist
[ ] rows for amarkets_mt5 / XAUUSD / 1h exist
[ ] timestamps parse as UTC
[ ] no severe duplicate timestamps after filtering
```

### 5.3 Coverage Check

Required minimum:

```text
min_start <= 2022-06-01
max_end >= 2026-06-01
rows >= 20,000
```

If not:

```text
abort with status DATA_COVERAGE_FAIL
```

### 5.4 Macro Check

```text
[ ] macro_daily_regime exists
[ ] required macro columns exist
[ ] macro coverage overlaps price coverage
[ ] macro_regime contains at least supportive/hostile/neutral/mixed or equivalent
```

If macro labels are missing:

```text
abort with status MACRO_REGIME_FAIL
```

### 5.5 Cost Model Check

The script must hard-code or read these fixed Stage38A levels:

```text
BASE_SPREAD_POINTS = 37
NORMAL_STRESS_SPREAD_POINTS = 43
DEFAULT_COST_STRESS_SPREAD_POINTS = 49
HIGH_STRESS_SPREAD_POINTS = 51
TAIL_STRESS_SPREAD_POINTS = 70
```

It must not invent new cost thresholds.

### 5.6 Unit Conversion Check

If point-to-price conversion is not known:

```text
cost is reported separately in spread_points
do not convert to USD
do not claim monetary P/L
```

If conversion is later provided:

```text
record conversion source
record symbol point
record digits
record tick size/value
```

---

## 6. Data Preparation Pipeline

Future script should follow this order:

```text
1. Load H1 AMarkets bars.
2. Sort by utc_time.
3. Remove duplicate timestamps if any, keeping latest imported_utc if available.
4. Compute ATR_H1_14.
5. Derive UTC date.
6. Derive H4 bars from H1 using UTC 4-hour boundaries.
7. Derive D1 bars from H1 using UTC day boundaries.
8. Compute D1_MA50 and H4_MA50.
9. Compute previous_day_high.
10. Compute rolling_48h_high.
11. Join macro_daily_regime by UTC date with max 5-day forward fill.
12. Generate setup candidates.
13. Apply entry variant logic.
14. Apply stop/target/time-stop logic.
15. Apply blocked windows.
16. Apply cost scenarios.
17. Generate reports.
```

No optimization loop is allowed.

---

## 7. SQL Extraction Sketch

The future script should use a simple SQL read:

```sql
select
    utc_time,
    open,
    high,
    low,
    close,
    spread,
    source,
    symbol,
    timeframe
from bars
where source = 'amarkets_mt5'
  and symbol = 'XAUUSD'
  and timeframe = '1h'
order by utc_time;
```

Macro SQL:

```sql
select
    obs_date,
    macro_regime,
    macro_score_long_gold,
    d_real_yield_20d,
    d_usd_20d_pct,
    rate_pressure_score,
    usd_pressure_score,
    regime_reason
from macro_daily_regime
order by obs_date;
```

These are read-only queries.

---

## 8. H4/D1 Derivation Details

### 8.1 H4

Use UTC floor:

```text
h4_start = floor utc_time to 4-hour UTC block
```

Aggregate:

```text
open = first open
high = max high
low = min low
close = last close
```

A derived H4 bar is valid only if it has enough H1 bars.

Initial rule:

```text
valid_h4 if H1_count >= 3
```

### 8.2 D1

Use UTC date:

```text
d1_date = date(utc_time)
```

Aggregate:

```text
open = first open
high = max high
low = min low
close = last close
```

A derived D1 bar is valid only if it has enough H1 bars.

Initial rule:

```text
valid_d1 if H1_count >= 18
```

This avoids incomplete/holiday days without overengineering.

---

## 9. Indicators

### 9.1 ATR_H1_14

Formula:

```text
TR = max(
    high - low,
    abs(high - previous_close),
    abs(low - previous_close)
)

ATR_H1_14 = rolling mean of TR over 14 completed H1 bars
```

Warmup:

```text
skip rows with missing ATR_H1_14
```

### 9.2 D1_MA50

```text
D1_MA50 = rolling mean of D1 close over 50 completed D1 bars
```

Use last completed D1 value for H1 bars of current day.

### 9.3 H4_MA50

```text
H4_MA50 = rolling mean of H4 close over 50 completed H4 bars
```

Use last completed H4 value for current H1 bar.

---

## 10. Macro Regime Logic

### 10.1 Join

For each H1 bar:

```text
bar_date = UTC date of utc_time
join to macro_daily_regime.obs_date
```

If missing, forward-fill up to:

```text
max_ffill_days = 5
```

If still missing:

```text
macro_status = missing_macro
skip candidate
```

### 10.2 Permitted Macro Regime

Allowed for T1 long:

```text
macro_regime = supportive
```

or:

```text
macro_regime = neutral
AND macro_score_long_gold >= 0
AND (
    d_real_yield_20d <= 0
    OR d_usd_20d_pct <= 0
)
```

### 10.3 Forbidden Macro Regime

```text
hostile
mixed
missing_macro
```

This is intentionally strict.

---

## 11. Structure Filter

For first implementation plan:

```text
D1_close > D1_MA50
AND H4_close > H4_MA50
```

Use latest completed D1 and H4 values before the signal bar.

Do not use current incomplete H4/D1 bars.

If MA values missing:

```text
skip candidate
```

No swing-high structure in v0.

---

## 12. Level Definitions

Only two levels:

```text
LEVEL_A = previous_day_high
LEVEL_B = rolling_48h_high
```

### 12.1 Previous Day High

```text
previous_day_high = high of prior completed UTC day
```

### 12.2 Rolling 48h High

```text
rolling_48h_high = max high over 48 completed H1 bars before signal bar
```

Exclude current signal bar.

---

## 13. Signal Candidate Logic

For each H1 bar after warmup:

```text
for each allowed level:
    if H1_high > level:
        sweep_distance = H1_high - level
        if sweep_distance >= 0.10 * ATR_H1_14:
            candidate exists
```

Skip candidate if:

```text
H1_range > 2.0 * ATR_H1_14
macro regime not permitted
D1/H4 structure not aligned
blocked window
ATR missing
level missing
```

---

## 14. Entry Variant Implementation

### 14.1 V1_CLOSE_ACCEPTANCE

Candidate becomes trade if:

```text
signal_bar_close > level
(close - low) / (high - low) >= 0.50
```

Entry:

```text
next H1 open
```

If next H1 bar missing:

```text
skip
```

### 14.2 V2_RETEST_CONFIRMATION

Candidate becomes trade if:

```text
bar_0 closes above level
within next 3 H1 bars:
    low <= level + 0.15 * ATR_H1_14
    close > level
```

Entry:

```text
next H1 open after retest confirmation bar
```

No perfect limit fill.

### 14.3 V3_STRICT_NEXT_BAR_HOLD

Candidate becomes trade if:

```text
bar_0 closes above level
bar_1 close >= level
```

Entry:

```text
bar_2 open
```

---

## 15. Stop and Target

### 15.1 Stop by Variant

V1:

```text
stop = signal_bar_low - 0.10 * ATR_H1_14
```

V2:

```text
stop = retest_bar_low - 0.10 * ATR_H1_14
```

V3:

```text
stop = min(bar_0_low, bar_1_low) - 0.10 * ATR_H1_14
```

### 15.2 Stop Validity

```text
stop_distance = entry_price - stop
```

Valid if:

```text
0.50 * ATR_H1_14 <= stop_distance <= 2.50 * ATR_H1_14
```

### 15.3 Targets

Two target variants:

```text
TP_1R:
    target = entry_price + 1.0 * stop_distance

TP_1_5R:
    target = entry_price + 1.5 * stop_distance
```

No partial exits.

No TP2.

---

## 16. Time Stop

Only one time stop in v0:

```text
TIME_5H:
    exit at close of fifth H1 bar after entry if TP/SL not hit first.
```

TIME_B is not implemented in first read-only version to keep variant count at 12.

---

## 17. Variant Matrix

Authorized 12 variants:

```text
V1_CLOSE_ACCEPTANCE + previous_day_high + TP_1R + TIME_5H
V1_CLOSE_ACCEPTANCE + previous_day_high + TP_1_5R + TIME_5H
V2_RETEST_CONFIRMATION + previous_day_high + TP_1R + TIME_5H
V2_RETEST_CONFIRMATION + previous_day_high + TP_1_5R + TIME_5H
V3_STRICT_NEXT_BAR_HOLD + previous_day_high + TP_1R + TIME_5H
V3_STRICT_NEXT_BAR_HOLD + previous_day_high + TP_1_5R + TIME_5H

V1_CLOSE_ACCEPTANCE + rolling_48h_high + TP_1R + TIME_5H
V1_CLOSE_ACCEPTANCE + rolling_48h_high + TP_1_5R + TIME_5H
V2_RETEST_CONFIRMATION + rolling_48h_high + TP_1R + TIME_5H
V2_RETEST_CONFIRMATION + rolling_48h_high + TP_1_5R + TIME_5H
V3_STRICT_NEXT_BAR_HOLD + rolling_48h_high + TP_1R + TIME_5H
V3_STRICT_NEXT_BAR_HOLD + rolling_48h_high + TP_1_5R + TIME_5H
```

No additional variants.

---

## 18. Exit Simulation Priority

Within each H1 bar after entry, OHLC ordering is unknown.

Conservative rule:

```text
If both TP and SL are touched in the same H1 bar:
    count SL first
```

This is conservative.

Optional diagnostic using 1m data may later resolve sequence, but first read-only script may use conservative H1 assumption.

For a long trade:

```text
SL touched if low <= stop
TP touched if high >= target
```

If neither touched before 5 H1 bars:

```text
exit at close of fifth H1 bar
```

---

## 19. Cost Scenarios

For each trade, compute R outcome under:

```text
RAW_NO_COST
BASE_COST_P50_37
NORMAL_STRESS_P75_43
DEFAULT_STRESS_P90_49
HIGH_STRESS_P95_51
TAIL_STRESS_P99_70
```

Because point conversion is not confirmed, future implementation must do one of two things:

### Option A — If conversion known

```text
convert spread_points to price distance
deduct cost from entry/exit outcome
report net R
```

### Option B — If conversion unknown

```text
report gross R
report cost sensitivity in spread_points
do not claim final net R
mark COST_UNIT_UNRESOLVED = true
```

Preferred before implementation:

```text
Add symbol spec audit before cost conversion.
```

But if user wants speed:

```text
Start with Option B as diagnostic only.
```

No candidate can pass commercially under Option B. It can only pass research feasibility.

---

## 20. Blocked Windows

### 20.1 Sunday/Monday Open

No entries:

```text
Sunday 22:00-23:59 UTC
Monday 00:00-01:59 UTC
```

### 20.2 Weekend Hold

No holding through weekend in v0.

If entry would require holding beyond Friday market close:

```text
skip or force time-stop before close
```

### 20.3 Event Guard

If reliable scheduled high-impact events are available:

```text
guard_before = 60 minutes
guard_after = 30 minutes
```

If not reliable:

```text
event_guard_status = limited
do not claim event-safe execution
```

---

## 21. Trade Ledger Schema

Required columns for `stage38a_t1_trade_ledger.csv`:

```text
trade_id
variant_id
entry_variant
level_variant
target_variant
time_variant
signal_utc
entry_utc
exit_utc
source
symbol
timeframe
macro_regime
macro_score_long_gold
d_real_yield_20d
d_usd_20d_pct
d1_close
d1_ma50
h4_close
h4_ma50
atr_h1_14
reference_level
sweep_distance
entry_price
stop_price
target_price
stop_distance
exit_reason
exit_price_raw
r_gross
r_base_p50
r_stress_p90
r_high_p95
r_tail_p99
blocked_window_flag
event_guard_flag
signal_range_atr_ratio
stop_distance_atr_ratio
notes
```

---

## 22. Variant Metrics Schema

Required columns for `stage38a_t1_variant_metrics.csv`:

```text
variant_id
entry_variant
level_variant
target_variant
time_variant
trade_count
gross_pf
base_p50_pf
stress_p90_pf
high_p95_pf
tail_p99_pf
avg_R_gross
avg_R_p90
win_rate_gross
win_rate_p90
max_drawdown_R_p90
median_R_p90
p10_R_p90
p90_R_p90
cost_sensitivity_ratio
supportive_trades
neutral_non_hostile_trades
hostile_trades
mixed_trades
missing_macro_trades
blocked_window_skipped
event_guard_skipped
invalid_stop_skipped
large_signal_skipped
status
decision
```

---

## 23. Summary JSON Schema

Required fields:

```json
{
  "stage": "Stage38A",
  "script": "stage38a_t1_read_only_test.py",
  "generated_utc": "...",
  "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
  "stage39_status": "NO_GO",
  "input_db": "data/local/xauusd_local_store.sqlite",
  "price_source": "amarkets_mt5",
  "symbol": "XAUUSD",
  "timeframe": "1h",
  "variant_count": 12,
  "trade_count_total": 0,
  "best_variant_by_stress_p90": null,
  "pass_count": 0,
  "kill_count": 0,
  "cost_unit": "spread_points",
  "cost_unit_resolved": false,
  "decision": "RESEARCH_ONLY"
}
```

---

## 24. Pass / Watch / Kill Logic

### PASS_RESEARCH_INTEREST

All required:

```text
trade_count >= 50
stress_p90_pf >= 1.10
avg_R_p90 > 0
cost_sensitivity_ratio >= 0.70
permitted_regime_trades >= 90% of trades
no blocked-window dependency
no single-month/year dependency
```

### WATCHLIST

Any:

```text
trade_count between 25 and 49
stress_p90_pf between 1.00 and 1.10
avg_R_p90 slightly positive
cost sensitivity acceptable but drawdown unclear
```

### KILL

Any:

```text
stress_p90_pf < 1.00
avg_R_p90 <= 0
raw PF positive but p90 PF fails
most trades outside permitted regimes
performance concentrated in one short period
blocked-window dependency
unit conversion blocks meaningful cost assessment
```

---

## 25. Markdown Report Structure

`stage38a_t1_read_only_test.md` must include:

```text
1. Executive decision
2. Data coverage
3. Macro coverage
4. Cost model used
5. Variant table
6. Best/worst variants
7. Regime split
8. Cost sensitivity
9. Year/month concentration
10. Failure diagnostics
11. Pass/watch/kill decision
12. Stage39 decision
```

The report must explicitly state:

```text
NO EA
NO PAPER LIVE
NO LIVE ORDER
NO STAGE39 PROMOTION
```

unless a future separate decision document changes that status.

---

## 26. Safety and Repository Boundaries

The future script may write only under:

```text
data/reports/stage38a_t1_read_only_test/
```

It must not write to:

```text
dryrun_signals
dryrun_outcomes
orders
positions
EA files
MQL5 files
scheduler files
GitHub workflows
```

It must not call broker APIs.

It must not send Telegram order-like messages.

---

## 27. Expected Command for Future Script

When implemented later, expected command should be:

```bash
python3 -m app.stage38a_t1_read_only_test
```

Optional flags later:

```bash
python3 -m app.stage38a_t1_read_only_test --db data/local/xauusd_local_store.sqlite --out data/reports/stage38a_t1_read_only_test
```

But flags are optional. Default paths should work.

---

## 28. Implementation Acceptance Checklist

Before coding the script, confirm this plan has:

```text
[ ] fixed data source
[ ] fixed macro join
[ ] fixed structure filter
[ ] fixed two level definitions
[ ] fixed three entry variants
[ ] fixed two target variants
[ ] fixed one time-stop
[ ] fixed 12 variants
[ ] fixed cost scenarios
[ ] fixed blocked windows
[ ] fixed output schemas
[ ] fixed pass/watch/kill rules
```

If any item is changed later, the document must be updated before code.

---

## 29. Gate Status After This Document

```text
T1_IMPLEMENTATION_PLAN_READ_ONLY = CREATED
T1_READ_ONLY_SCRIPT = ALLOWED_NEXT_IF_USER_APPROVES
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

Important:

```text
The future script will still be Stage38A read-only, not Stage39.
```

---

## 30. Recommended Commit

After placing this file in the repo:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs
mv ~/Downloads/STAGE38A_T1_IMPLEMENTATION_PLAN_READ_ONLY.md docs/STAGE38A_T1_IMPLEMENTATION_PLAN_READ_ONLY.md
git status --short
git add -A
git commit -m "Add Stage38A T1 read-only implementation plan"
git pull --rebase origin main
git push
```

---

## 31. Practical Next Step

If this document is accepted, the next artifact can be:

```text
app/stage38a_t1_read_only_test.py
```

with an accompanying report output under:

```text
data/reports/stage38a_t1_read_only_test/
```

The script must be read-only and must not authorize Stage39/paper/live.
