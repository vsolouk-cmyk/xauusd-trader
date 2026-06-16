#!/bin/zsh
# XAUUSD Stage35C Minimal Monitor Runner
# Purpose: keep only the surviving h13/h14 forward-confirmation monitor alive.
# Explicitly does NOT run Stage36/Stage37 discovery or variant-mining branches.

set -u

REPO_DIR="${XAUUSD_REPO_DIR:-$HOME/Desktop/xauusd-trader}"
PYTHON_BIN="${XAUUSD_PYTHON:-python3}"
LOG_DIR="$REPO_DIR/data/reports/stage35c_minimal_monitor"
LOCK_DIR="$REPO_DIR/data/.stage35c_minimal_monitor.lock"
STATE_FILE="$LOG_DIR/latest_minimal_monitor_state.env"
RUN_LOG="$LOG_DIR/stage35c_minimal_monitor.log"
AUTO_RERUN_GATES="${XAUUSD_STAGE35C_AUTO_RERUN_GATES:-0}"

mkdir -p "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  {
    echo "RUN_STATUS=LOCKED"
    echo "MESSAGE=another_minimal_monitor_run_is_active"
    echo "GENERATED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$STATE_FILE"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$REPO_DIR" || {
  echo "RUN_STATUS=FAILED_REPO_DIR" > "$STATE_FILE"
  exit 2
}

run_module() {
  local name="$1"
  local module="$2"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] RUN $name: $PYTHON_BIN -m $module" >> "$RUN_LOG"
  "$PYTHON_BIN" -m "$module" >> "$RUN_LOG" 2>&1
  local rc=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE $name rc=$rc" >> "$RUN_LOG"
  return $rc
}

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PREFLIGHT_RC=0
REFRESH_RC=0
STAGE35C_RC=0
STRICT_RERUN_RC=0
AUTO_RERUN_EXECUTED=0

run_module "stage32f_amarkets_csv_preflight" "app.stage32f_amarkets_csv_preflight"
PREFLIGHT_RC=$?

# Keep the old refresh cycle only as data refresh. Do not call any Stage36/37 branch here.
run_module "stage32f_extended_shadow_refresh_cycle" "app.stage32f_extended_shadow_refresh_cycle"
REFRESH_RC=$?

run_module "stage35c_forward_confirmation_trigger_queue_pruner" "app.stage35c_forward_confirmation_trigger_queue_pruner"
STAGE35C_RC=$?

SUMMARY_JSON="$REPO_DIR/data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_summary.json"
PARSED="$($PYTHON_BIN - <<'PY' "$SUMMARY_JSON"
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
def emit(k, v):
    s = str(v).replace(' ', '_')
    print(f'{k}={s}')
if not p.exists():
    emit('STAGE35C_SUMMARY_FOUND', 'false')
    emit('STAGE35C_DECISION', 'missing_summary')
    emit('STAGE35C_NEW_SIGNAL_COUNT', 0)
    emit('STAGE35C_MIN_NEW_EVENTS', 5)
    emit('STAGE35C_ACTION_REQUIRED', 'false')
    sys.exit(0)
try:
    d = json.loads(p.read_text())
except Exception as e:
    emit('STAGE35C_SUMMARY_FOUND', 'false')
    emit('STAGE35C_DECISION', f'json_error_{type(e).__name__}')
    emit('STAGE35C_NEW_SIGNAL_COUNT', 0)
    emit('STAGE35C_MIN_NEW_EVENTS', 5)
    emit('STAGE35C_ACTION_REQUIRED', 'false')
    sys.exit(0)
new_count = int(d.get('new_signal_count') or d.get('new_events') or 0)
min_events = int(d.get('min_new_events') or d.get('required_new_events') or 5)
decision = d.get('decision', 'unknown')
action = new_count >= min_events
emit('STAGE35C_SUMMARY_FOUND', 'true')
emit('STAGE35C_DECISION', decision)
emit('STAGE35C_NEW_SIGNAL_COUNT', new_count)
emit('STAGE35C_MIN_NEW_EVENTS', min_events)
emit('STAGE35C_ACTION_REQUIRED', str(action).lower())
PY
)"

eval "$PARSED"

# By default do NOT rerun strict gates automatically. This preserves minimal monitoring.
# Set XAUUSD_STAGE35C_AUTO_RERUN_GATES=1 only if manual review accepts automatic rerun.
if [ "${STAGE35C_ACTION_REQUIRED:-false}" = "true" ] && [ "$AUTO_RERUN_GATES" = "1" ]; then
  AUTO_RERUN_EXECUTED=1
  run_module "stage33d_strict_cost_aware_pre_paper_gate" "app.stage33d_strict_cost_aware_pre_paper_gate" || STRICT_RERUN_RC=$?
  run_module "stage33e_short_confirmation_recency_filter" "app.stage33e_short_confirmation_recency_filter" || STRICT_RERUN_RC=$?
  run_module "stage35b_strict_variant_backtest_queue_evaluator" "app.stage35b_strict_variant_backtest_queue_evaluator" || STRICT_RERUN_RC=$?
  run_module "stage35c_forward_confirmation_trigger_queue_pruner_after_gate_rerun" "app.stage35c_forward_confirmation_trigger_queue_pruner" || STRICT_RERUN_RC=$?
fi

END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_STATUS="OK"
if [ "$PREFLIGHT_RC" -ne 0 ] || [ "$REFRESH_RC" -ne 0 ] || [ "$STAGE35C_RC" -ne 0 ]; then
  RUN_STATUS="PARTIAL_FAILURE"
fi

{
  echo "RUN_STATUS=$RUN_STATUS"
  echo "START_UTC=$START_UTC"
  echo "END_UTC=$END_UTC"
  echo "REPO_DIR=$REPO_DIR"
  echo "PREFLIGHT_RC=$PREFLIGHT_RC"
  echo "REFRESH_RC=$REFRESH_RC"
  echo "STAGE35C_RC=$STAGE35C_RC"
  echo "AUTO_RERUN_GATES=$AUTO_RERUN_GATES"
  echo "AUTO_RERUN_EXECUTED=$AUTO_RERUN_EXECUTED"
  echo "STRICT_RERUN_RC=$STRICT_RERUN_RC"
  echo "$PARSED"
  echo "NO_STAGE36=true"
  echo "NO_STAGE37=true"
  echo "NO_DISCOVERY=true"
  echo "NO_VARIANT_MINING=true"
  echo "NO_EA_CHANGE=true"
  echo "NO_PAPER_LIVE=true"
  echo "NO_ORDER_AUTHORIZATION=true"
  echo "LOG_FILE=$RUN_LOG"
} > "$STATE_FILE"

cat "$STATE_FILE"
