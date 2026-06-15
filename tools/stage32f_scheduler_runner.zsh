#!/bin/zsh
# XAUUSD Stage32F Mac scheduler runner
# Purpose: lightweight preflight first; run heavy Stage32F wrapper only when useful.
# Safe default: skip RUN_BUT_LOW_SAMPLE_PROBABILITY to avoid wasting 10-15 minutes.

set -u

REPO_DIR="${XAUUSD_REPO_DIR:-$HOME/Desktop/xauusd-trader}"
CSV_DIR="${XAUUSD_CSV_DIR:-$HOME/Downloads}"
RUN_LOW_PROB="${XAUUSD_RUN_LOW_PROB:-0}"
PYTHON_BIN="${XAUUSD_PYTHON_BIN:-python3}"

REPORT_DIR="$REPO_DIR/data/reports/stage32f_mac_scheduler"
LOCK_DIR="$REPO_DIR/data/.stage32f_scheduler.lock"
mkdir -p "$REPORT_DIR"

TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$REPORT_DIR/scheduler_${TS_UTC}.log"
STATE_FILE="$REPORT_DIR/latest_scheduler_state.env"

log() {
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "$LOG_FILE"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "DECISION=SKIP_ALREADY_RUNNING"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

if [[ ! -d "$REPO_DIR" ]]; then
  log "DECISION=ERROR_REPO_NOT_FOUND"
  log "REPO_DIR=$REPO_DIR"
  exit 2
fi

cd "$REPO_DIR" || exit 2

log "REPO_DIR=$REPO_DIR"
log "CSV_DIR=$CSV_DIR"
log "RUN_LOW_PROB=$RUN_LOW_PROB"

PREFLIGHT_OUT="$REPORT_DIR/preflight_${TS_UTC}.out"
log "Running preflight..."

set +e
$PYTHON_BIN -m app.stage32f_amarkets_csv_preflight --csv-dir "$CSV_DIR" > "$PREFLIGHT_OUT" 2>&1
PREFLIGHT_RC=$?
set -e

cat "$PREFLIGHT_OUT" >> "$LOG_FILE"

if [[ "$PREFLIGHT_RC" -ne 0 ]]; then
  log "DECISION=ERROR_PREFLIGHT_FAILED"
  log "PREFLIGHT_RC=$PREFLIGHT_RC"
  exit "$PREFLIGHT_RC"
fi

DECISION="$(grep -E '^DECISION=' "$PREFLIGHT_OUT" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
WRAPPER_RECOMMENDED="$(grep -E '^WRAPPER_RECOMMENDED=' "$PREFLIGHT_OUT" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
H1_CSV_MAX="$(grep -E '^H1_CSV_MAX=' "$PREFLIGHT_OUT" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
H1_DB_MAX="$(grep -E '^H1_DB_MAX=' "$PREFLIGHT_OUT" | tail -n 1 | cut -d= -f2- | tr -d '\r')"
CROSSED_TARGET_HOURS="$(grep -E '^CROSSED_TARGET_HOURS=' "$PREFLIGHT_OUT" | tail -n 1 | cut -d= -f2- | tr -d '\r')"

cat > "$STATE_FILE" <<STATE
TS_UTC=$TS_UTC
DECISION=$DECISION
WRAPPER_RECOMMENDED=$WRAPPER_RECOMMENDED
H1_CSV_MAX=$H1_CSV_MAX
H1_DB_MAX=$H1_DB_MAX
CROSSED_TARGET_HOURS=$CROSSED_TARGET_HOURS
LOG_FILE=$LOG_FILE
STATE

log "PREFLIGHT_DECISION=$DECISION"
log "H1_CSV_MAX=$H1_CSV_MAX"
log "H1_DB_MAX=$H1_DB_MAX"
log "CROSSED_TARGET_HOURS=$CROSSED_TARGET_HOURS"

RUN_WRAPPER=0
case "$DECISION" in
  RUN_WRAPPER_RECOMMENDED)
    RUN_WRAPPER=1
    ;;
  RUN_BUT_LOW_SAMPLE_PROBABILITY)
    if [[ "$RUN_LOW_PROB" == "1" ]]; then
      RUN_WRAPPER=1
      log "LOW_PROB_OVERRIDE=1"
    else
      RUN_WRAPPER=0
      log "LOW_PROB_SKIP=1"
    fi
    ;;
  *)
    RUN_WRAPPER=0
    ;;
esac

if [[ "$RUN_WRAPPER" -ne 1 ]]; then
  log "FINAL_DECISION=SKIP_WRAPPER"
  exit 0
fi

log "FINAL_DECISION=RUN_STAGE32F_WRAPPER"
WRAPPER_OUT="$REPORT_DIR/stage32f_wrapper_${TS_UTC}.out"

set +e
$PYTHON_BIN -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper > "$WRAPPER_OUT" 2>&1
WRAPPER_RC=$?
set -e

cat "$WRAPPER_OUT" >> "$LOG_FILE"
log "WRAPPER_RC=$WRAPPER_RC"

SUMMARY_JSON="$REPO_DIR/data/reports/stage32f_extended_shadow_refresh_cycle/stage32f_summary.json"
if [[ -f "$SUMMARY_JSON" ]]; then
  $PYTHON_BIN - <<PY >> "$LOG_FILE" 2>/dev/null
import json
from pathlib import Path
p=Path("$SUMMARY_JSON")
d=json.loads(p.read_text())
for k in ["decision","leading_candidate","leading_remaining_to_extended_min","ledger_rows","pre_commercial_robustness_queue_rows","required_module_errors","commercial_transition_authorized"]:
    print(f"STAGE32F_{k.upper()}={d.get(k)}")
PY
fi

if [[ "$WRAPPER_RC" -ne 0 ]]; then
  osascript -e 'display notification "Stage32F wrapper failed. Check scheduler logs." with title "XAUUSD Stage32F"' >/dev/null 2>&1 || true
  exit "$WRAPPER_RC"
fi

# Notify only when a robustness candidate appears or errors are nonzero.
if [[ -f "$SUMMARY_JSON" ]]; then
  SHOULD_NOTIFY="$($PYTHON_BIN - <<PY
import json
from pathlib import Path
p=Path("$SUMMARY_JSON")
d=json.loads(p.read_text())
if int(d.get("pre_commercial_robustness_queue_rows") or 0) > 0 or int(d.get("required_module_errors") or 0) > 0:
    print("1")
else:
    print("0")
PY
)"
  if [[ "$SHOULD_NOTIFY" == "1" ]]; then
    osascript -e 'display notification "Stage32F needs review. Check latest report." with title "XAUUSD Stage32F"' >/dev/null 2>&1 || true
  fi
fi

log "DONE"
exit 0
