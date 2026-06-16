#!/bin/zsh
set -u

REPO_DIR="${XAUUSD_REPO_DIR:-/Users/vahid/Desktop/xauusd-trader}"
CSV_DIR="${XAUUSD_CSV_DIR:-/Users/vahid/Downloads}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REPORT_DIR="$REPO_DIR/data/reports/stage32f_mac_scheduler"
STATE_FILE="$REPORT_DIR/latest_scheduler_state.env"
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$REPORT_DIR/scheduler_${TS_UTC}.log"
LOCK_DIR="$REPORT_DIR/stage32f_scheduler.lock.d"
LEGACY_LOCK_FILE="$REPORT_DIR/stage32f_scheduler.lock"
RUN_LOW_PROB="${STAGE32F_RUN_LOW_PROB:-0}"


PIPELINE_REPORT_DIR="$REPO_DIR/data/reports/stage35c_stage36a_scheduler"
PIPELINE_STATE_FILE="$PIPELINE_REPORT_DIR/latest_pipeline_state.env"

extract_key_from_text() {
  local text="$1"
  local key="$2"
  echo "$text" | awk -F= -v k="$key" '$1==k {print substr($0, index($0,"=")+1); exit}'
}

run_stage35c_stage36a_pipeline_checks() {
  local context="$1"
  mkdir -p "$PIPELINE_REPORT_DIR"
  local stage35c_out=""
  local stage35c_rc="NA"
  local stage35c_decision="MODULE_MISSING"
  local stage35c_new="NA"
  local stage35c_min="NA"
  local stage36a_out=""
  local stage36a_rc="NA"
  local stage36a_decision="NOT_RUN"
  local stage36a_executed="False"
  local stage36b_out=""
  local stage36b_rc="NA"
  local stage36b_decision="NOT_RUN"
  local stage36b_executed="False"
  local today_utc
  today_utc="$(date -u +%Y-%m-%d)"
  local stage36a_daily_marker="$PIPELINE_REPORT_DIR/stage36a_last_run_date_utc.txt"
  local stage36b_daily_marker="$PIPELINE_REPORT_DIR/stage36b_last_run_date_utc.txt"
  local last_stage36a_date=""
  local last_stage36b_date=""
  [[ -f "$stage36a_daily_marker" ]] && last_stage36a_date="$(cat "$stage36a_daily_marker" 2>/dev/null || true)"
  [[ -f "$stage36b_daily_marker" ]] && last_stage36b_date="$(cat "$stage36b_daily_marker" 2>/dev/null || true)"

  if [[ -f "$REPO_DIR/app/stage35c_forward_confirmation_trigger_queue_pruner.py" ]]; then
    stage35c_out="$($PYTHON_BIN -m app.stage35c_forward_confirmation_trigger_queue_pruner 2>&1)"
    stage35c_rc=$?
    stage35c_decision="$(extract_key_from_text "$stage35c_out" DECISION)"
    stage35c_new="$(extract_key_from_text "$stage35c_out" NEW_SIGNAL_COUNT)"
    stage35c_min="$(extract_key_from_text "$stage35c_out" MIN_NEW_EVENTS)"
    [[ -n "$stage35c_decision" ]] || stage35c_decision="UNKNOWN"
    [[ -n "$stage35c_new" ]] || stage35c_new="NA"
    [[ -n "$stage35c_min" ]] || stage35c_min="NA"
  fi

  if [[ -f "$REPO_DIR/app/stage36a_new_thesis_parallel_intake.py" ]]; then
    if [[ "${STAGE36A_FORCE_RUN:-0}" == "1" || "$last_stage36a_date" != "$today_utc" ]]; then
      stage36a_out="$($PYTHON_BIN -m app.stage36a_new_thesis_parallel_intake 2>&1)"
      stage36a_rc=$?
      stage36a_decision="$(extract_key_from_text "$stage36a_out" DECISION)"
      [[ -n "$stage36a_decision" ]] || stage36a_decision="UNKNOWN"
      stage36a_executed="True"
      echo "$today_utc" > "$stage36a_daily_marker"
    else
      stage36a_decision="SKIP_ALREADY_RAN_TODAY"
      stage36a_executed="False"
    fi
  else
    stage36a_decision="MODULE_MISSING"
  fi

  if [[ -f "$REPO_DIR/app/stage36b_session_regime_baseline_scout.py" ]]; then
    if [[ "${STAGE36B_FORCE_RUN:-0}" == "1" || "$last_stage36b_date" != "$today_utc" ]]; then
      stage36b_out="$($PYTHON_BIN -m app.stage36b_session_regime_baseline_scout 2>&1)"
      stage36b_rc=$?
      stage36b_decision="$(extract_key_from_text "$stage36b_out" DECISION)"
      [[ -n "$stage36b_decision" ]] || stage36b_decision="UNKNOWN"
      stage36b_executed="True"
      echo "$today_utc" > "$stage36b_daily_marker"
    else
      stage36b_decision="SKIP_ALREADY_RAN_TODAY"
      stage36b_executed="False"
    fi
  else
    stage36b_decision="MODULE_MISSING"
  fi

  {
    echo "--- STAGE35C/STAGE36A/STAGE36B PIPELINE CHECK context=$context ---"
    echo "STAGE35C_RC=$stage35c_rc"
    echo "$stage35c_out"
    echo "STAGE36A_RC=$stage36a_rc"
    echo "$stage36a_out"
    echo "STAGE36B_RC=$stage36b_rc"
    echo "$stage36b_out"
  } >> "$LOG_FILE"

  cat > "$PIPELINE_STATE_FILE" <<PIPELINE_STATE_EOF
TS_UTC=$TS_UTC
CONTEXT=$context
STAGE35C_DECISION=$stage35c_decision
STAGE35C_RC=$stage35c_rc
STAGE35C_NEW_SIGNAL_COUNT=$stage35c_new
STAGE35C_MIN_NEW_EVENTS=$stage35c_min
STAGE36A_DECISION=$stage36a_decision
STAGE36A_EXECUTED=$stage36a_executed
STAGE36A_RC=$stage36a_rc
STAGE36B_DECISION=$stage36b_decision
STAGE36B_EXECUTED=$stage36b_executed
STAGE36B_RC=$stage36b_rc
LOG_FILE=$LOG_FILE
PIPELINE_STATE_EOF
}

mkdir -p "$REPORT_DIR"

write_state() {
  local decision="$1"
  local final_decision="$2"
  local wrapper_recommended="$3"
  local wrapper_executed="$4"
  local wrapper_rc="$5"
  local reason="$6"
  local h1_csv_max="${7:-NA}"
  local h1_db_max="${8:-NA}"
  local crossed="${9:-NA}"
  local running_pid="${10:-NA}"
  local lock_kind="${11:-NA}"
  local lock_path="${12:-NA}"
  cat > "$STATE_FILE" <<STATE_EOF
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
RUNNING_PID=$running_pid
LOCK_KIND=$lock_kind
LOCK_PATH=$lock_path
LOG_FILE=$LOG_FILE
STATE_EOF
}

pid_is_alive() {
  local pid="$1"
  [[ -n "$pid" && "$pid" != "NA" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

other_stage32f_pids() {
  local pids=""
  local patterns=(
    "stage32f_scheduler_runner.zsh"
    "python3 -m app.stage32f_extended_shadow_refresh_cycle"
    "python3 -m app.run_active_shadow_suite_with_exogenous_watchlist"
    "python3 -m app.stage32c_dense_forward_shadow_tracker"
  )
  for pat in "${patterns[@]}"; do
    local found
    found="$(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ' || true)"
    for pid in ${(z)found}; do
      [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
      if [[ -n "$pid" ]]; then
        pids="$pids$pid,"
      fi
    done
  done
  echo "${pids%,}"
}

# Handle HF2/HF3 lock directory.
if [[ -d "$LOCK_DIR" ]]; then
  existing_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  existing_ts="$(cat "$LOCK_DIR/ts_utc" 2>/dev/null || true)"
  if pid_is_alive "$existing_pid"; then
    echo "Another scheduler instance is running: pid=$existing_pid lock_ts=$existing_ts" > "$LOG_FILE"
    write_state "SKIP_ALREADY_RUNNING" "SKIP_ALREADY_RUNNING" "False" "False" "NA" "another_scheduler_instance_is_running_pid_${existing_pid}" "NA" "NA" "NA" "$existing_pid" "pid_lock_dir" "$LOCK_DIR"
    exit 0
  fi
  echo "Removed stale lock dir pid=${existing_pid:-NA} lock_ts=${existing_ts:-NA}" > "$LOG_FILE"
  rm -rf "$LOCK_DIR"
fi

# Handle legacy file locks left by HF1/older runner. If PID is absent, use process scan.
legacy_locks=()
if [[ -f "$LEGACY_LOCK_FILE" ]]; then
  legacy_locks+=("$LEGACY_LOCK_FILE")
fi
for lf in "$REPORT_DIR"/*.lock(N); do
  [[ -f "$lf" ]] && legacy_locks+=("$lf")
done

if (( ${#legacy_locks[@]} > 0 )); then
  for lf in "${legacy_locks[@]}"; do
    lock_text="$(cat "$lf" 2>/dev/null || true)"
    lock_pid="$(echo "$lock_text" | awk -F= '/^PID=|^pid=/{print $2; exit}' | tr -d ' ')"
    if [[ -n "$lock_pid" ]] && pid_is_alive "$lock_pid"; then
      echo "Legacy lock is active: file=$lf pid=$lock_pid" > "$LOG_FILE"
      write_state "SKIP_ALREADY_RUNNING" "SKIP_ALREADY_RUNNING" "False" "False" "NA" "another_scheduler_instance_is_running_pid_${lock_pid}" "NA" "NA" "NA" "$lock_pid" "legacy_pid_file_lock" "$lf"
      exit 0
    fi
  done
  active_pids="$(other_stage32f_pids)"
  if [[ -n "$active_pids" ]]; then
    echo "Legacy lock exists and matching process is active: pids=$active_pids locks=${legacy_locks[*]}" > "$LOG_FILE"
    write_state "SKIP_ALREADY_RUNNING" "SKIP_ALREADY_RUNNING" "False" "False" "NA" "another_scheduler_instance_is_running_pids_${active_pids}" "NA" "NA" "NA" "$active_pids" "legacy_lock_without_pid_process_scan" "${legacy_locks[1]}"
    exit 0
  fi
  echo "Removed stale legacy locks: ${legacy_locks[*]}" > "$LOG_FILE"
  rm -f "${legacy_locks[@]}"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  existing_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  echo "Failed to acquire lock. existing_pid=${existing_pid:-NA}" > "$LOG_FILE"
  write_state "SKIP_ALREADY_RUNNING" "SKIP_ALREADY_RUNNING" "False" "False" "NA" "lock_acquire_failed_existing_pid_${existing_pid:-NA}" "NA" "NA" "NA" "${existing_pid:-NA}" "pid_lock_dir" "$LOCK_DIR"
  exit 0
fi

echo "$$" > "$LOCK_DIR/pid"
echo "$TS_UTC" > "$LOCK_DIR/ts_utc"
echo "$LOG_FILE" > "$LOCK_DIR/log_file"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

{
  echo "TS_UTC=$TS_UTC"
  echo "REPO_DIR=$REPO_DIR"
  echo "CSV_DIR=$CSV_DIR"
  echo "RUN_LOW_PROB=$RUN_LOW_PROB"
  echo "LOCK_DIR=$LOCK_DIR"
  echo "RUNNER_PID=$$"
} >> "$LOG_FILE"

cd "$REPO_DIR" || {
  echo "ERROR: cannot cd to $REPO_DIR" >> "$LOG_FILE"
  write_state "ERROR" "RUNNER_FAILED" "False" "False" "NA" "cannot_cd_to_repo" "NA" "NA" "NA" "$$" "pid_lock_dir" "$LOCK_DIR"
  exit 2
}

preflight_out="$($PYTHON_BIN -m app.stage32f_amarkets_csv_preflight --csv-dir "$CSV_DIR" 2>&1)"
preflight_rc=$?
{
  echo "--- PREFLIGHT RC=$preflight_rc ---"
  echo "$preflight_out"
} >> "$LOG_FILE"

extract_value() {
  local key="$1"
  echo "$preflight_out" | awk -F= -v k="$key" '$1==k {print substr($0, index($0,"=")+1); exit}'
}

pre_decision="$(extract_value DECISION)"
pre_wrapper="$(extract_value WRAPPER_RECOMMENDED)"
h1_csv_max="$(extract_value H1_CSV_MAX)"
h1_db_max="$(extract_value H1_DB_MAX)"
crossed="$(extract_value CROSSED_TARGET_HOURS)"

[[ -n "$pre_decision" ]] || pre_decision="UNKNOWN_PREFLIGHT_DECISION"
[[ -n "$pre_wrapper" ]] || pre_wrapper="False"
[[ -n "$h1_csv_max" ]] || h1_csv_max="NA"
[[ -n "$h1_db_max" ]] || h1_db_max="NA"
[[ -n "$crossed" ]] || crossed="NA"

if [[ "$preflight_rc" != "0" ]]; then
  run_stage35c_stage36a_pipeline_checks "preflight_failed"
  write_state "$pre_decision" "PREFLIGHT_FAILED" "$pre_wrapper" "False" "NA" "preflight_returncode_${preflight_rc}" "$h1_csv_max" "$h1_db_max" "$crossed" "$$" "pid_lock_dir" "$LOCK_DIR"
  exit $preflight_rc
fi

should_run="0"
run_reason=""
if [[ "$pre_decision" == "RUN_WRAPPER_RECOMMENDED" ]]; then
  should_run="1"
  run_reason="strict_preflight_recommended"
elif [[ "$pre_decision" == "RUN_BUT_LOW_SAMPLE_PROBABILITY" && "$RUN_LOW_PROB" == "1" ]]; then
  should_run="1"
  run_reason="low_probability_allowed_by_env"
else
  run_stage35c_stage36a_pipeline_checks "skip_wrapper"
  write_state "$pre_decision" "SKIP_WRAPPER" "$pre_wrapper" "False" "NA" "preflight_decision_${pre_decision}" "$h1_csv_max" "$h1_db_max" "$crossed" "$$" "pid_lock_dir" "$LOCK_DIR"
  exit 0
fi

write_state "$pre_decision" "WRAPPER_RUNNING" "$pre_wrapper" "True" "RUNNING" "$run_reason" "$h1_csv_max" "$h1_db_max" "$crossed" "$$" "pid_lock_dir" "$LOCK_DIR"
{
  echo "--- WRAPPER START reason=$run_reason ---"
  date -u
} >> "$LOG_FILE"

$PYTHON_BIN -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper >> "$LOG_FILE" 2>&1
wrapper_rc=$?
{
  echo "--- WRAPPER END rc=$wrapper_rc ---"
  date -u
} >> "$LOG_FILE"

run_stage35c_stage36a_pipeline_checks "after_wrapper"

if [[ "$wrapper_rc" == "0" ]]; then
  write_state "$pre_decision" "WRAPPER_COMPLETED" "$pre_wrapper" "True" "$wrapper_rc" "$run_reason" "$h1_csv_max" "$h1_db_max" "$crossed" "$$" "pid_lock_dir" "$LOCK_DIR"
else
  write_state "$pre_decision" "WRAPPER_FAILED" "$pre_wrapper" "True" "$wrapper_rc" "wrapper_returncode_${wrapper_rc}" "$h1_csv_max" "$h1_db_max" "$crossed" "$$" "pid_lock_dir" "$LOCK_DIR"
fi

exit $wrapper_rc
