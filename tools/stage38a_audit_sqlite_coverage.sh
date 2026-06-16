#!/usr/bin/env bash
set -u

cd "${1:-$HOME/Desktop/xauusd-trader}" || {
  echo "ERROR: repo path not found. Usage: bash stage38a_audit_sqlite_coverage.sh /path/to/xauusd-trader"
  exit 1
}

OUT_DIR="data/reports/stage38a_local_data_audit"
OUT_FILE="$OUT_DIR/sqlite_coverage_audit.txt"
mkdir -p "$OUT_DIR"

{
  echo "STAGE38A SQLITE COVERAGE AUDIT"
  echo "REPO=$(pwd)"
  echo "GENERATED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "==== 1) LOCAL STORE: bars coverage + spread population ===="
  if [ -f "data/local/xauusd_local_store.sqlite" ]; then
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select source, symbol, timeframe,
       count(*) as rows,
       min(utc_time) as min_utc,
       max(utc_time) as max_utc,
       sum(case when spread is not null then 1 else 0 end) as spread_rows,
       round(100.0 * sum(case when spread is not null then 1 else 0 end) / count(*), 2) as spread_pct
from bars
group by source, symbol, timeframe
order by symbol, timeframe, source;
"
  else
    echo "MISSING: data/local/xauusd_local_store.sqlite"
  fi
  echo

  echo "==== 2) LOCAL STORE: spread distribution ===="
  if [ -f "data/local/xauusd_local_store.sqlite" ]; then
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select source, symbol, timeframe,
       min(spread) as min_spread,
       round(avg(spread), 6) as avg_spread,
       max(spread) as max_spread,
       count(spread) as spread_rows
from bars
where spread is not null
group by source, symbol, timeframe
order by symbol, timeframe, source;
"
  fi
  echo

  echo "==== 3) PERSISTENT STORE: OHLC coverage ===="
  if [ -f "data/store/xauusd.sqlite" ]; then
    for t in candles_i_1min candles_i_5min candles_i_15min candles_i_1h; do
      echo "---- $t ----"
      sqlite3 -header -column data/store/xauusd.sqlite "
select symbol, interval, provider,
       count(*) as rows,
       min(time_utc) as min_utc,
       max(time_utc) as max_utc
from $t
group by symbol, interval, provider;
"
    done
  else
    echo "MISSING: data/store/xauusd.sqlite"
  fi
  echo

  echo "==== 4) MACRO DAILY REGIME coverage ===="
  if [ -f "data/local/xauusd_local_store.sqlite" ]; then
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select count(*) as rows,
       min(obs_date) as min_date,
       max(obs_date) as max_date
from macro_daily_regime;
"
    echo
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select macro_regime, count(*) as rows
from macro_daily_regime
group by macro_regime
order by rows desc;
"
  fi
  echo

  echo "==== 5) MACRO CONTEXT H1 coverage ===="
  if [ -f "data/local/xauusd_local_store.sqlite" ]; then
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select count(*) as rows,
       min(utc_time) as min_utc,
       max(utc_time) as max_utc
from macro_context_h1;
"
    echo
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select macro_regime, count(*) as rows
from macro_context_h1
group by macro_regime
order by rows desc;
"
  fi
  echo

  echo "==== 6) EVENT REACTION coverage ===="
  if [ -f "data/local/xauusd_local_store.sqlite" ]; then
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select count(*) as rows,
       min(event_time_utc) as min_event_utc,
       max(event_time_utc) as max_event_utc
from news_event_reactions;
"
    echo
    sqlite3 -header -column data/local/xauusd_local_store.sqlite "
select event_class, event_channel, count(*) as rows
from news_event_reactions
group by event_class, event_channel
order by rows desc
limit 30;
"
  fi
  echo

  echo "==== 7) Existing Stage33D cost-aware report preview ===="
  if [ -d "data/reports/stage33d_strict_cost_aware_pre_paper_gate" ]; then
    for f in data/reports/stage33d_strict_cost_aware_pre_paper_gate/*.csv; do
      echo "---- $f ----"
      head -5 "$f"
      echo
    done
  else
    echo "MISSING: data/reports/stage33d_strict_cost_aware_pre_paper_gate"
  fi

  echo "DONE"
} | tee "$OUT_FILE"

echo
echo "Audit written to: $OUT_FILE"
