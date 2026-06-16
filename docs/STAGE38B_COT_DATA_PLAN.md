# STAGE38B COT Data Plan — T3 Gold Positioning Foundation

Project: XAUUSD / Gold Trading System  
Stage: Stage38B  
Sub-thesis: T3 CFTC COT gold positioning foundation  
Status: PLAN_READY  
Generated: 2026-06-16  
Primary output path in repo: `docs/STAGE38B_COT_DATA_PLAN.md`

---

چپ‌چین ادامه می‌دهم.

## 1. Executive decision

Stage38A/T1 is closed as:

```text
LOW_CONFIDENCE_2025_DOMINATED_RESEARCH_CANDIDATE
```

Therefore:

```text
Stage39 = NO-GO
EA = NO-GO
paper-live = NO-GO
live order = NO-GO
active T1 development = paused
```

The next active research step is:

```text
Stage38B / T3 COT data foundation
```

The immediate goal is not to trade. The goal is to build a free, reproducible, auditable CFTC COT data layer for gold positioning, then use it later as a thesis input for read-only T3 research.

---

## 2. Why Stage38B starts with COT

Stage38A showed that a technically positive T1 candidate was too dependent on 2025. That means the system needs a stronger exogenous market-state explanation before any promotion path can reopen.

COT is the right next data foundation because:

```text
1. It is free.
2. It is official CFTC data.
3. It is directly linked to positioning, crowding, squeeze risk, managed-money behavior, and producer/commercial hedging pressure.
4. It can be joined to the existing H1 XAUUSD database without needing live trading.
5. It supports a thesis-first gold model better than blind pattern mining.
```

---

## 3. Official data sources

Use official CFTC sources only for the first implementation.

Primary automated source:

```text
CFTC Public Reporting Environment / Socrata API
Dataset: Disaggregated Futures Only
Resource id: 72hh-3qpy
Base API pattern:
https://publicreporting.cftc.gov/resource/72hh-3qpy.json
```

Primary historical fallback/source-of-truth cross-check:

```text
CFTC Historical Compressed
Report family: Disaggregated Futures Only Reports
Coverage: annual complete files from September 2009 onward
```

Current comma-delimited fallback:

```text
CFTC current Disaggregated Futures-Only comma-delimited file
Example current text endpoint:
https://www.cftc.gov/dea/newcot/f_disagg.txt
```

Gold contract identity to lock:

```text
Market name: GOLD - COMMODITY EXCHANGE INC.
CFTC contract market code: 088691
Contract unit: 100 troy ounces
Exchange family: COMEX / Commodity Exchange Inc.
```

Important exclusion:

```text
Do not use MICRO GOLD - COMMODITY EXCHANGE INC. / code 088695 as the primary XAUUSD positioning proxy.
It may be audited later as a secondary micro-contract sentiment proxy, but it is not the Stage38B baseline.
```

---

## 4. Report type decision

Primary report:

```text
Disaggregated Futures Only
```

Reason:

```text
For physical commodity markets, the disaggregated report gives more useful segmentation than the legacy report:
- Producer/Merchant/Processor/User
- Swap Dealers
- Managed Money
- Other Reportables
```

Secondary later audit:

```text
Disaggregated Futures-and-Options Combined
Legacy Futures Only
Legacy Futures-and-Options Combined
```

These secondary reports are not part of the initial loader unless needed for validation.

---

## 5. Anti-lookahead rule

COT data is weekly. It describes open interest as of Tuesday and is released on Friday afternoon by CFTC.

Therefore, Stage38B must store both dates:

```text
as_of_date              = Tuesday report date
available_from_utc     = first usable timestamp after official Friday release
```

No H1 bar before `available_from_utc` may use the new COT row.

Initial implementation rule:

```text
available_from_utc = Friday 15:30 America/New_York converted to UTC
```

If CFTC holiday/release anomalies appear, keep `as_of_date` intact and mark `available_from_utc` as estimated until release-calendar parsing is added.

Conservative fallback:

```text
If release time is uncertain, delay usability to next Monday 00:00 UTC.
```

This is stricter and avoids lookahead leakage.

---

## 6. Storage layout

Raw downloaded files:

```text
data/cot/cftc/raw/disaggregated_futures_only/
```

Normalized export:

```text
data/cot/cftc/normalized/cot_gold_weekly.csv
```

Audit output:

```text
data/reports/stage38b_cot_audit/
```

SQLite target database:

```text
data/local/xauusd_local_store.sqlite
```

Primary new table:

```text
cot_gold_weekly
```

Optional feature table:

```text
cot_gold_weekly_features
```

---

## 7. SQLite schema draft

```sql
CREATE TABLE IF NOT EXISTS cot_gold_weekly (
    as_of_date TEXT NOT NULL,
    available_from_utc TEXT NOT NULL,
    report_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    market_and_exchange_names TEXT NOT NULL,
    cftc_contract_market_code TEXT NOT NULL,
    cftc_market_code TEXT,
    cftc_commodity_code TEXT,
    open_interest_all REAL,

    prod_merc_long_all REAL,
    prod_merc_short_all REAL,
    swap_long_all REAL,
    swap_short_all REAL,
    swap_spread_all REAL,
    m_money_long_all REAL,
    m_money_short_all REAL,
    m_money_spread_all REAL,
    other_rept_long_all REAL,
    other_rept_short_all REAL,
    other_rept_spread_all REAL,
    tot_rept_long_all REAL,
    tot_rept_short_all REAL,
    nonrept_long_all REAL,
    nonrept_short_all REAL,

    change_open_interest_all REAL,
    change_m_money_long_all REAL,
    change_m_money_short_all REAL,
    change_prod_merc_long_all REAL,
    change_prod_merc_short_all REAL,

    pct_oi_m_money_long_all REAL,
    pct_oi_m_money_short_all REAL,
    pct_oi_prod_merc_long_all REAL,
    pct_oi_prod_merc_short_all REAL,
    pct_oi_swap_long_all REAL,
    pct_oi_swap_short_all REAL,

    traders_total_all REAL,
    contract_units TEXT,
    raw_payload_json TEXT,
    loaded_at_utc TEXT NOT NULL,

    PRIMARY KEY (as_of_date, report_type, cftc_contract_market_code)
);
```

Feature table draft:

```sql
CREATE TABLE IF NOT EXISTS cot_gold_weekly_features (
    as_of_date TEXT PRIMARY KEY,
    available_from_utc TEXT NOT NULL,
    open_interest_all REAL,

    mm_net_all REAL,
    mm_gross_all REAL,
    mm_net_pct_oi REAL,
    mm_long_pct_oi REAL,
    mm_short_pct_oi REAL,
    mm_net_change_1w REAL,
    mm_net_change_4w REAL,
    mm_net_z_52w REAL,
    mm_net_z_156w REAL,
    mm_net_pct_rank_156w REAL,

    prod_merc_net_all REAL,
    prod_merc_net_pct_oi REAL,
    swap_net_all REAL,
    other_rept_net_all REAL,
    nonrept_net_all REAL,

    oi_change_1w REAL,
    oi_z_52w REAL,

    positioning_state TEXT,
    crowding_state TEXT,
    squeeze_risk_state TEXT,
    data_quality_flag TEXT,
    generated_at_utc TEXT NOT NULL
);
```

---

## 8. Minimum derived features

The first feature set must stay small and interpretable.

Managed Money:

```text
mm_net_all = m_money_long_all - m_money_short_all
mm_gross_all = m_money_long_all + m_money_short_all
mm_net_pct_oi = mm_net_all / open_interest_all
mm_long_pct_oi = m_money_long_all / open_interest_all
mm_short_pct_oi = m_money_short_all / open_interest_all
mm_net_change_1w = mm_net_all - mm_net_all.shift(1)
mm_net_change_4w = mm_net_all - mm_net_all.shift(4)
mm_net_z_52w = rolling_zscore(mm_net_all, 52)
mm_net_z_156w = rolling_zscore(mm_net_all, 156)
mm_net_pct_rank_156w = rolling_percentile_rank(mm_net_all, 156)
```

Producer/Merchant:

```text
prod_merc_net_all = prod_merc_long_all - prod_merc_short_all
prod_merc_net_pct_oi = prod_merc_net_all / open_interest_all
```

Swap / other / non-reportable:

```text
swap_net_all = swap_long_all - swap_short_all
other_rept_net_all = other_rept_long_all - other_rept_short_all
nonrept_net_all = nonrept_long_all - nonrept_short_all
```

Open interest:

```text
oi_change_1w = open_interest_all - open_interest_all.shift(1)
oi_z_52w = rolling_zscore(open_interest_all, 52)
```

---

## 9. First positioning labels

These labels are diagnostic only. They are not trade signals.

```text
MM_EXTREME_LONG:
    mm_net_z_156w >= +1.5 or mm_net_pct_rank_156w >= 0.90

MM_EXTREME_SHORT:
    mm_net_z_156w <= -1.5 or mm_net_pct_rank_156w <= 0.10

MM_LONG_BUILD:
    mm_net_change_4w > 0 and mm_net_pct_oi > 0

MM_LONG_UNWIND:
    mm_net_change_4w < 0 and mm_net_pct_oi > 0

MM_SHORT_BUILD:
    mm_net_change_4w < 0 and mm_net_pct_oi < 0

MM_SHORT_COVER:
    mm_net_change_4w > 0 and mm_net_pct_oi < 0

NEUTRAL_POSITIONING:
    none of the above
```

Potential squeeze-risk labels:

```text
UPSIDE_SQUEEZE_RISK:
    mm_net_z_156w <= -1.0 and mm_net_change_4w > 0

LONG_CROWDING_RISK:
    mm_net_z_156w >= +1.5 and mm_net_change_1w < 0
```

These labels are intentionally coarse. They should not be optimized until the audit layer is stable.

---

## 10. Join rule to H1 XAUUSD bars

Existing bar source:

```text
source = amarkets_mt5
symbol = XAUUSD
timeframe = 1h
```

Join logic:

```text
For each H1 bar timestamp:
    use the latest cot_gold_weekly row where available_from_utc <= bar_ts_utc
```

Never join by `as_of_date <= bar_date` directly. That would leak Tuesday COT values into bars before the Friday release.

Initial materialized view/table later:

```text
cot_gold_h1_context
```

Suggested fields:

```text
bar_ts_utc
cot_as_of_date
cot_available_from_utc
mm_net_pct_oi
mm_net_z_156w
mm_net_change_4w
prod_merc_net_pct_oi
oi_z_52w
positioning_state
crowding_state
squeeze_risk_state
```

---

## 11. Audit acceptance criteria

Stage38B data foundation passes only if all conditions below are true.

Coverage:

```text
1. GOLD / CFTC code 088691 rows are present.
2. Weekly rows cover at least the local XAUUSD H1 research range from 2022-05-01 onward.
3. Historical rows before 2022 are also retained when available, because rolling z-scores need lookback history.
4. Latest available COT row is no more than two expected weekly releases behind, unless CFTC itself has a delay.
```

Integrity:

```text
1. No duplicate primary keys.
2. `as_of_date` is weekly and monotonic after sorting.
3. `open_interest_all > 0` for all normal rows.
4. Key positioning fields are numeric.
5. Missing values are reported, not silently filled.
6. Contract code is locked to 088691.
```

Anti-lookahead:

```text
1. `available_from_utc` exists for every row.
2. No H1 bar before release availability can access the new weekly row.
3. Audit report must include a sample around at least three release weeks.
```

Output reproducibility:

```text
1. Downloader can be rerun idempotently.
2. Loader can rebuild tables from raw files.
3. Audit report is regenerated under data/reports/stage38b_cot_audit/.
```

---

## 12. Implementation sequence

### Step 1 — Commit this plan

```text
docs/STAGE38B_COT_DATA_PLAN.md
```

### Step 2 — Build downloader

Target file:

```text
tools/stage38b_download_cftc_cot_gold.py
```

Required behavior:

```text
- Query CFTC PRE/Socrata Disaggregated Futures Only dataset.
- Filter to CFTC contract market code 088691.
- Save raw JSON and normalized CSV.
- Support start/end date arguments.
- Avoid API tokens.
- Include polite pagination and retry logic.
- Write a small metadata JSON with source URL, row count, min/max as_of_date, and generated_at_utc.
```

Expected CLI:

```bash
python3 tools/stage38b_download_cftc_cot_gold.py \
  --start-year 2009 \
  --out-dir data/cot/cftc
```

### Step 3 — Build SQLite loader

Target file:

```text
app/stage38b_cot_gold_loader.py
```

Required behavior:

```text
- Read normalized CSV.
- Create/replace cot_gold_weekly and cot_gold_weekly_features.
- Compute available_from_utc conservatively.
- Compute minimum feature set.
- Produce audit markdown + JSON.
```

Expected CLI:

```bash
python3 app/stage38b_cot_gold_loader.py \
  --db data/local/xauusd_local_store.sqlite \
  --cot-csv data/cot/cftc/normalized/cot_gold_weekly.csv \
  --reports-dir data/reports/stage38b_cot_audit
```

### Step 4 — Audit report

Expected outputs:

```text
data/reports/stage38b_cot_audit/stage38b_cot_gold_audit.md
data/reports/stage38b_cot_audit/stage38b_cot_gold_audit_summary.json
```

Required audit sections:

```text
- Source used
- Contract identity confirmation
- Row count
- Date range
- Latest row
- Missing weeks
- Duplicate keys
- Null field counts
- Feature sanity ranges
- Anti-lookahead release timestamp examples
- SQLite table row counts
- PASS/WATCH/KILL decision
```

### Step 5 — Later T3 research design

Only after Stage38B data audit passes:

```text
docs/STAGE38B_T3_COT_RESEARCH_DESIGN.md
```

No T3 signal test should begin before the COT data foundation is audited.

---

## 13. Kill / watch conditions

Kill conditions:

```text
1. Cannot reliably isolate GOLD / 088691.
2. Data source changes break stable field names and no robust fallback exists.
3. COT rows cannot be joined to H1 bars without lookahead ambiguity.
4. Coverage from 2022-05-01 onward is incomplete and cannot be repaired.
```

Watch conditions:

```text
1. CFTC API rate limits or temporary downtime require fallback to historical compressed files.
2. CFTC release calendar anomalies require conservative delayed availability.
3. Futures-only and futures-options-combined disagree materially; this becomes a later validation issue, not a blocker for baseline loading.
```

Pass conditions:

```text
1. GOLD / 088691 weekly rows loaded.
2. Date coverage is sufficient.
3. Anti-lookahead timestamps exist.
4. Feature table is generated.
5. Audit report is clean or only has explainable warnings.
```

---

## 14. Explicit out-of-scope items

Do not do any of the following in Stage38B foundation:

```text
- No EA.
- No paper-live.
- No live order.
- No Telegram trading alert.
- No Stage39 promotion.
- No strategy optimization.
- No threshold mining on COT labels before data audit passes.
- No paid data vendor.
```

---

## 15. Immediate next artifact

The next artifact after this plan is clear:

```text
tools/stage38b_download_cftc_cot_gold.py
```

It should be delivered with:

```text
1. downloader script
2. syntax check
3. ready-to-run command
4. mv command from Downloads into repo
5. safe git commands
```

