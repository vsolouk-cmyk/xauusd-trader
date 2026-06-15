#!/bin/zsh
set -u

REPO_DIR="/Users/vahid/Desktop/xauusd-trader"
REPORT_DIR="$REPO_DIR/data/reports/stage32f_mac_scheduler"
LOCK_DIR="$REPORT_DIR/stage32f_scheduler.lockdir"
STATE_FILE="$REPORT_DIR/latest_scheduler_state.env"
PYTHON_BIN="python3"
RUN_LOW_PROB="${RUN_LOW_PROB:-0}"

mkdir -p "$REPORT_DIR"
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$REPORT_DIR/scheduler_${TS_UTC}.log"

write_state() {
  local decision="$1"
  local wrapper_recommended="$2"
  local final_decision="$3"
  local wrapper_executed="$4"
  local wrapper_rc="$5"
  local reason="$6"
  local h1_csv_max="${7:-NA}"
  local h1_db_max="${8:-NA}"
  local crossed="${9:-NA}"
  cat > "$STATE_FILE" <<STATE
TS_UTC=$TS_UTC
DECISION=$decision
WRAPPER_RECOMMENDED=$wrapper_recommended
FINAL_DECISION=$final_decision
WRAPPER_EXECUTED=$wrapper_executed
WRAPPER_RC=$wrapper_rc
RUN_LOW_PROB=$RUN_LOW_PROB
REASON=$reason
H1_CSV_MAX=$h1_csv_max
H1_DB_MAX=$h1_db_max
CROSSED_TARGET_HOURS=$crossed
LOG_FILE=$LOG_FILE
STATE
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

is_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  [[ "$pid" == <-> ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# Atomic lock acquisition via mkdir. If existing, inspect PID and clear stale lock.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID=""
  LOCK_TS=""
  [[ -f "$LOCK_DIR/pid" ]] && LOCK_PID="$(cat "$LOCK_DIR/pid" 2>/dev/null | tr -d '[:space:]')"
  [[ -f "$LOCK_DIR/ts_utc" ]] && LOCK_TS="$(cat "$LOCK_DIR/ts_utc" 2>/dev/null | tr -d '[:space:]')"

  if is_pid_alive "$LOCK_PID"; then
    echo "SKIP_ALREADY_RUNNING pid=$LOCK_PID ts=$LOCK_TS" > "$LOG_FILE"
    write_state "SKIP_ALREADY_RUNNING" "False" "SKIP_ALREADY_RUNNING" "False" "NA" "another_scheduler_instance_is_running_pid_${LOCK_PID}" "NA" "NA" "NA"
    exit 0
  fi

  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "SKIP_LOCK_RACE" > "$LOG_FILE"
    write_state "SKIP_LOCK_RACE" "False" "SKIP_LOCK_RACE" "False" "NA" "lock_race_after_stale_cleanup" "NA" "NA" "NA"
    exit 0
  fi
  log "Removed stale lock pid=$LOCK_PID ts=$LOCK_TS"
fi

echo $$ > "$LOCK_DIR/pid"
echo "$TS_UTC" > "$LOCK_DIR/ts_utc"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

cd "$REPO_DIR" || {
  write_state "REPO_DIR_ERROR" "False" "REPO_DIR_ERROR" "False" "NA" "cannot_cd_repo_dir" "NA" "NA" "NA"
  exit 2
}

log "Starting Stage32F scheduler HF2"

PREFLIGHT_OUT="$($PYTHON_BIN -m app.stage32f_amarkets_csv_preflight --csv-dir /Users/vahid/Downloads 2>&1)"
PREFLIGHT_RC=$?
echo "$PREFLIGHT_OUT" >> "$LOG_FILE"

if [[ $PREFLIGHT_RC -ne 0 ]]; then
  write_state "PREFLIGHT_FAILED" "False" "PREFLIGHT_FAILED" "False" "$PREFLIGHT_RC" "preflight_returned_nonzero" "NA" "NA" "NA"
  exit $PREFLIGHT_RC
fi

DECISION="$(echo "$PREFLIGHT_OUT" | awk -F= '/^DECISION=/{print $2; exit}')"
WRAPPER_RECOMMENDED="$(echo "$PREFLIGHT_OUT" | awk -F= '/^WRAPPER_RECOMMENDED=/{print $2; exit}')"
REASON_RAW="$(echo "$PREFLIGHT_OUT" | awk -F= '/^REASON=/{print substr($0, index($0,"=")+1); exit}' | tr ' ' '_' | tr -cd '[:alnum:]_.,:-')"
H1_CSV_MAX="$(echo "$PREFLIGHT_OUT" | awk -F= '/^H1_CSV_MAX=/{print substr($0, index($0,"=")+1); exit}')"
H1_DB_MAX="$(echo "$PREFLIGHT_OUT" | awk -F= '/^H1_DB_MAX=/{print substr($0, index($0,"=")+1); exit}')"
CROSSED="$(echo "$PREFLIGHT_OUT" | awk -F= '/^CROSSED_TARGET_HOURS=/{print substr($0, index($0,"=")+1); exit}' | tr ' ' '_')"

[[ -n "$DECISION" ]] || DECISION="UNKNOWN"
[[ -n "$WRAPPER_RECOMMENDED" ]] || WRAPPER_RECOMMENDED="False"
[[ -n "$REASON_RAW" ]] || REASON_RAW="NA"
[[ -n "$H1_CSV_MAX" ]] || H1_CSV_MAX="NA"
[[ -n "$H1_DB_MAX" ]] || H1_DB_MAX="NA"
[[ -n "$CROSSED" ]] || CROSSED="NA"

# Strict default: low-probability runs are skipped unless RUN_LOW_PROB=1.
if [[ "$DECISION" == "RUN_WRAPPER_RECOMMENDED" ]]; then
  log "Preflight recommends wrapper. Running Stage32F wrapper."
  $PYTHON_BIN -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper >> "$LOG_FILE" 2>&1
  WRAP_RC=$?
  if [[ $WRAP_RC -eq 0 ]]; then
    write_state "$DECISION" "$WRAPPER_RECOMMENDED" "WRAPPER_COMPLETED" "True" "0" "strict_preflight_recommended" "$H1_CSV_MAX" "$H1_DB_MAX" "$CROSSED"
    exit 0
  else
    write_state "$DECISION" "$WRAPPER_RECOMMENDED" "WRAPPER_FAILED" "True" "$WRAP_RC" "wrapper_returned_nonzero" "$H1_CSV_MAX" "$H1_DB_MAX" "$CROSSED"
    exit $WRAP_RC
  fi
fi

if [[ "$DECISION" == "RUN_BUT_LOW_SAMPLE_PROBABILITY" && "$RUN_LOW_PROB" == "1" ]]; then
  log "Low-probability run allowed by RUN_LOW_PROB=1. Running wrapper."
  $PYTHON_BIN -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper >> "$LOG_FILE" 2>&1
  WRAP_RC=$?
  if [[ $WRAP_RC -eq 0 ]]; then
    write_state "$DECISION" "$WRAPPER_RECOMMENDED" "WRAPPER_COMPLETED_LOW_PROB" "True" "0" "low_probability_forced_by_env" "$H1_CSV_MAX" "$H1_DB_MAX" "$CROSSED"
    exit 0
  else
    write_state "$DECISION" "$WRAPPER_RECOMMENDED" "WRAPPER_FAILED_LOW_PROB" "True" "$WRAP_RC" "low_probability_wrapper_failed" "$H1_CSV_MAX" "$H1_DB_MAX" "$CROSSED"
    exit $WRAP_RC
  fi
fi

log "Skipping wrapper: decision=$DECISION reason=$REASON_RAW"
write_state "$DECISION" "$WRAPPER_RECOMMENDED" "SKIP_WRAPPER" "False" "NA" "$REASON_RAW" "$H1_CSV_MAX" "$H1_DB_MAX" "$CROSSED"
exit 0
