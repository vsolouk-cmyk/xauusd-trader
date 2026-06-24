# Stage38A — AMarkets XAUUSD Symbol Spec Extracted from Screenshot

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38A  
**Document type:** Extracted MT5 symbol specification and cost-conversion interpretation  
**Generated UTC:** 2026-06-16T13:07:40Z  
**Status:** Manual screenshot extraction  
**Execution authorization:** NO EA, NO paper-live, NO live order  
**Stage39 authorization:** NO-GO

---

چپ‌چین ادامه می‌دهم.

این سند مشخصات قابل استخراج از اسکرین‌شات MT5 Specification برای نماد XAUUSD در AMarkets را ثبت می‌کند.

---

## 1. Extracted Values

```text
SYMBOL = XAUUSD
DESCRIPTION = Gold vs US Dollar
EXCHANGE = XCCY
SECTOR = Commodities
INDUSTRY = Precious Metals

DIGITS = 2
CONTRACT_SIZE = 100
SPREAD_TYPE = floating
STOPS_LEVEL = 0

MARGIN_CURRENCY = USD
PROFIT_CURRENCY = USD
CALCULATION = CFD Leverage

TICK_SIZE = 0.00
TICK_VALUE = 0

CHART_MODE = By bid price
TRADE_ACCESS = Full access
EXECUTION = Market
GTC_MODE = Good till cancelled
FILLING = Fill or Kill, Immediate or Cancel
ORDERS = All

MINIMAL_VOLUME = 0.01
MAXIMAL_VOLUME = 100
VOLUME_STEP = 0.01

SWAP_TYPE = In points
SWAP_LONG = -64.7
SWAP_SHORT = 34.1
TRIPLE_SWAP_DAY = Wednesday
```

Sessions shown:

```text
Monday to Thursday:
    Quotes = 01:00-23:59
    Trade  = 01:00-23:59

Friday:
    Quotes = 01:00-23:55
    Trade  = 01:00-23:55
```

Margin rates shown:

```text
Market buy:
    Initial = 1.0000000
    Initial USD/lot ≈ 144.91
    Maintenance = 1.0000000
    Maintenance USD/lot ≈ 144.91

Market sell:
    Initial = 1.0000000
    Initial USD/lot ≈ 144.90
    Maintenance = 1.0000000
    Maintenance USD/lot ≈ 144.90
```

---

## 2. Mapping to Our Template

The MT5 screenshot does not show every field using the same names. Mapping:

```text
DIGITS -> DIGITS
Contract size -> CONTRACT_SIZE
Spread floating -> SPREAD_TYPE
Stops level -> STOPS_LEVEL
Margin currency -> MARGIN_CURRENCY
Profit currency -> PROFIT_CURRENCY
Calculation -> CALCULATION_MODE
Tick size -> TICK_SIZE
Tick value -> TICK_VALUE
Minimal volume -> MIN_VOLUME
Maximal volume -> MAX_VOLUME
Volume step -> VOLUME_STEP
Swap type -> SWAP_TYPE
Swap long -> SWAP_LONG
Swap short -> SWAP_SHORT
Swap rates Wednesday=3 -> TRIPLE_SWAP_DAY
Sessions -> TRADING_HOURS_SERVER_TIME / QUOTE_HOURS_SERVER_TIME
```

Fields not shown or unclear:

```text
SERVER
ACCOUNT_TYPE
COMMISSION
COMMISSION_UNIT
COMMISSION_PER_LOT_OR_SIDE
ROLLOVER_TIME_UTC
FREEZE_LEVEL
CURRENT_SPREAD_SHOWN
```

---

## 3. Point Conversion Decision

Since:

```text
DIGITS = 2
```

we can derive:

```text
POINT = 0.01
```

Therefore, for Stage38A v0:

```text
spread_price_distance = spread_points * 0.01
```

Examples:

```text
p50 spread = 37 points -> 0.37 XAUUSD price units
p75 spread = 43 points -> 0.43 XAUUSD price units
p90 spread = 49 points -> 0.49 XAUUSD price units
p95 spread = 51 points -> 0.51 XAUUSD price units
p99 spread = 70 points -> 0.70 XAUUSD price units
max spread = 183 points -> 1.83 XAUUSD price units
```

This is enough for price-distance cost modeling in the T1 read-only test.

---

## 4. Important Limitation

The screenshot shows:

```text
TICK_SIZE = 0.00
TICK_VALUE = 0
```

This is not useful for full monetary conversion. It may be a display/rounding/CFD-spec issue.

Therefore:

```text
Allowed now:
    spread_points -> price_distance
    price_distance -> R impact

Still not fully resolved:
    price_distance -> exact USD P/L per lot
```

For read-only R-based research, this is sufficient.

For any paper/live step, it is not sufficient.

---

## 5. Swap Interpretation

Swap is shown in points:

```text
SWAP_LONG = -64.7
SWAP_SHORT = 34.1
TRIPLE_SWAP_DAY = Wednesday
```

With POINT=0.01, provisional price-distance equivalent:

```text
SWAP_LONG_PRICE_DISTANCE = -0.647
SWAP_SHORT_PRICE_DISTANCE = +0.341
```

But for R-based intraday T1:

```text
Avoid overnight holding in v0.
No weekend hold.
No promotion if profitability depends on overnight exposure.
```

---

## 6. T1 Cost Model Update

The Stage38A execution cost model can now move from unresolved spread_points to provisional price-distance cost:

```text
BASE_SPREAD_POINTS = 37  -> 0.37 price units
P75_SPREAD_POINTS = 43   -> 0.43 price units
P90_SPREAD_POINTS = 49   -> 0.49 price units
P95_SPREAD_POINTS = 51   -> 0.51 price units
P99_SPREAD_POINTS = 70   -> 0.70 price units
MAX_SPREAD_POINTS = 183  -> 1.83 price units
```

T1 read-only script may compute net R as:

```text
cost_R = spread_price_distance / stop_distance
net_R = gross_R - cost_R_adjustment
```

The exact one-way vs round-trip application must be specified in the implementation script. Conservative v0 should apply round-trip cost.

---

## 7. Remaining Missing Items

Still missing:

```text
commission
exact server timezone
exact rollover time UTC
reliable tick value
reliable tick size
account type
```

These do not block T1 read-only R-based test, but they block paper/live readiness.

---

## 8. Gate Decision

```text
POINT_TO_PRICE_CONVERSION = RESOLVED_FOR_V0
USD_PNL_CONVERSION = NOT_FULLY_RESOLVED
SWAP_POINTS = CAPTURED
COMMISSION = NOT_SHOWN
T1_READ_ONLY_SCRIPT = SAFER_TO_BUILD_NEXT
STAGE39 = NO_GO
EA_PAPER_LIVE_ORDER = NO_GO
```

---

## 9. Recommended Manual Spec File

The corresponding manual file is:

```text
data/manual/amarkets_xauusd_symbol_spec_20260616.txt
```

---

## 10. Recommended Commit

```bash
cd ~/Desktop/xauusd-trader
mkdir -p docs data/manual
mv ~/Downloads/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_EXTRACTED.md docs/STAGE38A_AMARKETS_XAUUSD_SYMBOL_SPEC_EXTRACTED.md
mv ~/Downloads/amarkets_xauusd_symbol_spec_20260616.txt data/manual/amarkets_xauusd_symbol_spec_20260616.txt
git status --short
git add -A
git commit -m "Add AMarkets XAUUSD symbol specification extraction"
git pull --rebase origin main
git push
```

---

## 11. Practical Next Step

Next artifact can now be:

```text
app/stage38a_t1_read_only_test.py
```

The script may use:

```text
POINT = 0.01
CONTRACT_SIZE = 100
SWAP_LONG = -64.7 points
SWAP_SHORT = 34.1 points
TRIPLE_SWAP_DAY = Wednesday
```

But it must remain read-only and must not authorize Stage39.
