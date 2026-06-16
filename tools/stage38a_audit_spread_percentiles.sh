#!/usr/bin/env bash
set -u

cd "${1:-$HOME/Desktop/xauusd-trader}" || {
  echo "ERROR: repo path not found. Usage: bash stage38a_audit_spread_percentiles.sh /path/to/xauusd-trader"
  exit 1
}

DB="data/local/xauusd_local_store.sqlite"
OUT_DIR="data/reports/stage38a_local_data_audit"
OUT_FILE="$OUT_DIR/spread_percentile_audit.txt"
mkdir -p "$OUT_DIR"

if [ ! -f "$DB" ]; then
  echo "ERROR: missing $DB"
  exit 1
fi

{
  echo "STAGE38A SPREAD PERCENTILE AUDIT"
  echo "REPO=$(pwd)"
  echo "DB=$DB"
  echo "GENERATED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "==== 1) Spread non-null coverage window ===="
  sqlite3 -header -column "$DB" "
select source, symbol, timeframe,
       count(*) as spread_rows,
       min(utc_time) as min_spread_utc,
       max(utc_time) as max_spread_utc
from bars
where spread is not null
group by source, symbol, timeframe
order by symbol, timeframe, source;
"
  echo

  echo "==== 2) Spread percentiles by source/symbol/timeframe ===="
  sqlite3 -header -column "$DB" "
with ranked as (
  select source, symbol, timeframe, spread,
         percent_rank() over (
           partition by source, symbol, timeframe
           order by spread
         ) as pr
  from bars
  where spread is not null
),
agg as (
  select source, symbol, timeframe,
         count(*) as n,
         min(spread) as min_spread,
         avg(spread) as avg_spread,
         max(spread) as max_spread,
         min(case when pr >= 0.50 then spread end) as p50,
         min(case when pr >= 0.75 then spread end) as p75,
         min(case when pr >= 0.90 then spread end) as p90,
         min(case when pr >= 0.95 then spread end) as p95,
         min(case when pr >= 0.99 then spread end) as p99
  from ranked
  group by source, symbol, timeframe
)
select source, symbol, timeframe, n,
       min_spread,
       round(avg_spread, 6) as avg_spread,
       p50, p75, p90, p95, p99,
       max_spread
from agg
order by symbol, timeframe, source;
"
  echo

  echo "==== 3) Spread by UTC hour ===="
  sqlite3 -header -column "$DB" "
with base as (
  select source, symbol, timeframe,
         cast(strftime('%H', utc_time) as integer) as utc_hour,
         spread
  from bars
  where spread is not null
),
ranked as (
  select source, symbol, timeframe, utc_hour, spread,
         percent_rank() over (
           partition by source, symbol, timeframe, utc_hour
           order by spread
         ) as pr
  from base
)
select source, symbol, timeframe, utc_hour,
       count(*) as n,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       min(case when pr >= 0.50 then spread end) as p50,
       min(case when pr >= 0.90 then spread end) as p90,
       min(case when pr >= 0.95 then spread end) as p95,
       max(spread) as max_spread
from ranked
group by source, symbol, timeframe, utc_hour
order by symbol, timeframe, utc_hour, source;
"
  echo

  echo "==== 4) Spread by session_utc ===="
  sqlite3 -header -column "$DB" "
with base as (
  select source, symbol, timeframe,
         coalesce(session_utc, 'UNKNOWN') as session_utc,
         spread
  from bars
  where spread is not null
),
ranked as (
  select source, symbol, timeframe, session_utc, spread,
         percent_rank() over (
           partition by source, symbol, timeframe, session_utc
           order by spread
         ) as pr
  from base
)
select source, symbol, timeframe, session_utc,
       count(*) as n,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       min(case when pr >= 0.50 then spread end) as p50,
       min(case when pr >= 0.90 then spread end) as p90,
       min(case when pr >= 0.95 then spread end) as p95,
       max(spread) as max_spread
from ranked
group by source, symbol, timeframe, session_utc
order by symbol, timeframe, session_utc, source;
"
  echo

  echo "==== 5) Spread by weekday ===="
  sqlite3 -header -column "$DB" "
with base as (
  select source, symbol, timeframe,
         strftime('%w', utc_time) as weekday_utc,
         spread
  from bars
  where spread is not null
),
ranked as (
  select source, symbol, timeframe, weekday_utc, spread,
         percent_rank() over (
           partition by source, symbol, timeframe, weekday_utc
           order by spread
         ) as pr
  from base
)
select source, symbol, timeframe, weekday_utc,
       count(*) as n,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       min(case when pr >= 0.50 then spread end) as p50,
       min(case when pr >= 0.90 then spread end) as p90,
       min(case when pr >= 0.95 then spread end) as p95,
       max(spread) as max_spread
from ranked
group by source, symbol, timeframe, weekday_utc
order by symbol, timeframe, weekday_utc, source;
"
  echo

  echo "==== 6) Spread sample concentration by month ===="
  sqlite3 -header -column "$DB" "
select source, symbol, timeframe,
       substr(utc_time, 1, 7) as yyyy_mm,
       count(*) as spread_rows,
       min(utc_time) as min_utc,
       max(utc_time) as max_utc,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       max(spread) as max_spread
from bars
where spread is not null
group by source, symbol, timeframe, yyyy_mm
order by symbol, timeframe, yyyy_mm, source;
"
  echo

  echo "==== 7) Sunday/Monday open proxy spread ===="
  sqlite3 -header -column "$DB" "
select source, symbol, timeframe,
       strftime('%w', utc_time) as weekday_utc,
       strftime('%H', utc_time) as hour_utc,
       count(*) as n,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       max(spread) as max_spread
from bars
where spread is not null
  and (
    (strftime('%w', utc_time) = '0' and cast(strftime('%H', utc_time) as integer) >= 20)
    or
    (strftime('%w', utc_time) = '1' and cast(strftime('%H', utc_time) as integer) <= 3)
  )
group by source, symbol, timeframe, weekday_utc, hour_utc
order by symbol, timeframe, weekday_utc, hour_utc, source;
"
  echo

  echo "DONE"
} | tee "$OUT_FILE"

echo
echo "Audit written to: $OUT_FILE"
