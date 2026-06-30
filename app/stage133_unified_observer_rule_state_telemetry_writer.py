#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STAGE = "Stage133_UNIFIED_OBSERVER_RULE_STATE_TELEMETRY_WRITER"
STATUS = "STAGE133_COMPLETE_UNIFIED_OBSERVER_RULE_STATE_TELEMETRY_READY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE133",
    "NO_ORDER_SEND_ADDED",
    "NO_TRADE_CLASS_ADDED",
    "NO_TRADING_LOGIC_CHANGE",
    "NO_SIGNAL_RULE_CHANGE",
    "NO_SELECTED_RULE_CHANGE",
    "NO_INDICATOR_UI_CHANGE_FROM_STAGE133",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_EXPERTS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD"
)

LATEST_CSV = "xauusd_stage133_unified_observer_rule_state_latest.csv"
HISTORY_CSV = "xauusd_stage133_unified_observer_rule_state_history.csv"
KV_FILE = "xauusd_stage133_unified_observer_rule_state_kv.csv"

BLOCK_BEGIN = "// STAGE133_RULE_STATE_TELEMETRY_BLOCK_BEGIN"
BLOCK_END = "// STAGE133_RULE_STATE_TELEMETRY_BLOCK_END"
CALL_LINE = 'Stage133_WriteRuleTelemetryIfDue(keys, vals, n, "DisplaySignal");'

TELEMETRY_BLOCK = """
// STAGE133_RULE_STATE_TELEMETRY_BLOCK_BEGIN
// Rule-state telemetry-only writer. No orders, no trade-class usage, no signal logic change.
input int Stage133RuleTelemetryIntervalSec = 60;
input string Stage133RuleTelemetryLatestFile = "xauusd_stage133_unified_observer_rule_state_latest.csv";
input string Stage133RuleTelemetryHistoryFile = "xauusd_stage133_unified_observer_rule_state_history.csv";
input string Stage133RuleTelemetryKvFile = "xauusd_stage133_unified_observer_rule_state_kv.csv";
datetime g_stage133_last_rule_telemetry_write = 0;

string Stage133_BoolText(bool value)
{
   return(value ? "true" : "false");
}

string Stage133_CleanCell(string value)
{
   StringReplace(value, "\\r", " ");
   StringReplace(value, "\\n", " ");
   if(StringLen(value) > 240)
      value = StringSubstr(value, 0, 237) + "...";
   return(value);
}

bool Stage133_IsActiveText(string value)
{
   string v = value;
   StringToLower(v);
   return(v == "true" || v == "1" || v == "yes" || v == "active");
}

void Stage133_WriteRuleHeader(int handle)
{
   FileWrite(handle,
             "time_local",
             "time_current",
             "time_trade_server",
             "symbol",
             "period",
             "feature_date",
             "mode",
             "any_signal_active",
             "selected_rule_id",
             "selected_label",
             "execution_allowed",
             "order_authorized",
             "rule_id",
             "rule_active",
             "rule_failures",
             "reason",
             "allow_trading",
             "order_send",
             "note");
}

int Stage133_WriteRuleRows(int handle, const string &keys[], const string &vals[], int n, string reason)
{
   string rules[7];
   rules[0] = "K06";
   rules[1] = "K03";
   rules[2] = "K07";
   rules[3] = "S83_14";
   rules[4] = "S83_13";
   rules[5] = "C96_07";
   rules[6] = "S105_03";

   datetime tc = TimeCurrent();
   datetime ts = TimeTradeServer();
   string local_time = TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS);
   string current_time = TimeToString(tc, TIME_DATE|TIME_SECONDS);
   string server_time = TimeToString(ts, TIME_DATE|TIME_SECONDS);

   string feature_date = Stage133_CleanCell(GetValue(keys, vals, n, "feature_date", ""));
   string mode = Stage133_CleanCell(GetValue(keys, vals, n, "mode", ""));
   string any_signal_active = Stage133_CleanCell(GetValue(keys, vals, n, "any_signal_active", ""));
   string selected_rule_id = Stage133_CleanCell(GetValue(keys, vals, n, "selected_rule_id", ""));
   string selected_label = Stage133_CleanCell(GetValue(keys, vals, n, "selected_label", ""));
   string execution_allowed = Stage133_CleanCell(GetValue(keys, vals, n, "execution_allowed", ""));
   string order_authorized = Stage133_CleanCell(GetValue(keys, vals, n, "order_authorized", ""));

   int active_count = 0;
   for(int i=0; i<7; i++)
   {
      string rid = rules[i];
      string active = Stage133_CleanCell(GetValue(keys, vals, n, rid + "_active", ""));
      string failures = Stage133_CleanCell(GetValue(keys, vals, n, rid + "_failures", ""));
      if(Stage133_IsActiveText(active))
         active_count++;

      FileWrite(handle,
                local_time,
                current_time,
                server_time,
                _Symbol,
                IntegerToString(_Period),
                feature_date,
                mode,
                any_signal_active,
                selected_rule_id,
                selected_label,
                execution_allowed,
                order_authorized,
                rid,
                active,
                failures,
                reason,
                "false",
                "false",
                "telemetry_only_rule_state_no_orders_no_signal_change");
   }
   return(active_count);
}

void Stage133_WriteKvSummary(const string &keys[], const string &vals[], int n, string reason, int active_count)
{
   int h = FileOpen(Stage133RuleTelemetryKvFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("Stage133 rule-state KV FileOpen failed. file=", Stage133RuleTelemetryKvFile, " err=", GetLastError(), ". No orders are sent.");
      return;
   }

   datetime tc = TimeCurrent();
   datetime ts = TimeTradeServer();

   FileWriteString(h, "stage|Stage133_UNIFIED_OBSERVER_RULE_STATE_TELEMETRY_WRITER\\n");
   FileWriteString(h, "status|RULE_STATE_TELEMETRY_ALIVE_NO_ORDER\\n");
   FileWriteString(h, "reason|" + reason + "\\n");
   FileWriteString(h, "allow_trading|false\\n");
   FileWriteString(h, "order_send|false\\n");
   FileWriteString(h, "symbol|" + _Symbol + "\\n");
   FileWriteString(h, "period|" + IntegerToString(_Period) + "\\n");
   FileWriteString(h, "time_local|" + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + "\\n");
   FileWriteString(h, "time_current|" + TimeToString(tc, TIME_DATE|TIME_SECONDS) + "\\n");
   FileWriteString(h, "time_trade_server|" + TimeToString(ts, TIME_DATE|TIME_SECONDS) + "\\n");
   FileWriteString(h, "feature_date|" + Stage133_CleanCell(GetValue(keys, vals, n, "feature_date", "")) + "\\n");
   FileWriteString(h, "mode|" + Stage133_CleanCell(GetValue(keys, vals, n, "mode", "")) + "\\n");
   FileWriteString(h, "any_signal_active|" + Stage133_CleanCell(GetValue(keys, vals, n, "any_signal_active", "")) + "\\n");
   FileWriteString(h, "selected_rule_id|" + Stage133_CleanCell(GetValue(keys, vals, n, "selected_rule_id", "")) + "\\n");
   FileWriteString(h, "selected_label|" + Stage133_CleanCell(GetValue(keys, vals, n, "selected_label", "")) + "\\n");
   FileWriteString(h, "execution_allowed|" + Stage133_CleanCell(GetValue(keys, vals, n, "execution_allowed", "")) + "\\n");
   FileWriteString(h, "order_authorized|" + Stage133_CleanCell(GetValue(keys, vals, n, "order_authorized", "")) + "\\n");
   FileWriteString(h, "rule_count|7\\n");
   FileWriteString(h, "active_rule_count|" + IntegerToString(active_count) + "\\n");
   FileWriteString(h, "terminal_trade_allowed|" + Stage133_BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "mql_trade_allowed|" + Stage133_BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "account_trade_allowed|" + Stage133_BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "note|telemetry_only_rule_state_inside_unified_observer_ea_no_orders_no_signal_change\\n");
   FileClose(h);
}

void Stage133_WriteRuleTelemetryNow(const string &keys[], const string &vals[], int n, string reason)
{
   int latest = FileOpen(Stage133RuleTelemetryLatestFile, FILE_WRITE|FILE_CSV|FILE_ANSI);
   if(latest == INVALID_HANDLE)
   {
      Print("Stage133 latest rule-state FileOpen failed. file=", Stage133RuleTelemetryLatestFile, " err=", GetLastError(), ". No orders are sent.");
      return;
   }
   Stage133_WriteRuleHeader(latest);
   int active_count = Stage133_WriteRuleRows(latest, keys, vals, n, reason);
   FileClose(latest);

   int history = FileOpen(Stage133RuleTelemetryHistoryFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI);
   if(history != INVALID_HANDLE)
   {
      if(FileSize(history) == 0)
         Stage133_WriteRuleHeader(history);
      FileSeek(history, 0, SEEK_END);
      Stage133_WriteRuleRows(history, keys, vals, n, reason);
      FileClose(history);
   }
   else
   {
      Print("Stage133 history rule-state FileOpen failed. file=", Stage133RuleTelemetryHistoryFile, " err=", GetLastError(), ". No orders are sent.");
   }

   Stage133_WriteKvSummary(keys, vals, n, reason, active_count);
   g_stage133_last_rule_telemetry_write = TimeLocal();
   Print("Stage133 rule-state telemetry written. active_count=", active_count, " selected=", GetValue(keys, vals, n, "selected_rule_id", ""), ". No orders are sent.");
}

void Stage133_WriteRuleTelemetryIfDue(const string &keys[], const string &vals[], int n, string reason)
{
   datetime now_local = TimeLocal();
   int interval_sec = MathMax(10, Stage133RuleTelemetryIntervalSec);
   if(g_stage133_last_rule_telemetry_write == 0 || (now_local - g_stage133_last_rule_telemetry_write) >= interval_sec)
   {
      Stage133_WriteRuleTelemetryNow(keys, vals, n, reason);
   }
}
// STAGE133_RULE_STATE_TELEMETRY_BLOCK_END
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def locate_observer_sources(root: Path, mt5_experts: Path) -> List[Path]:
    patterns = [
        "**/*Unified*Observer*.mq5",
        "**/*ObserverOnly*.mq5",
        "**/*Unified_ObserverOnly*.mq5",
        "**/*unified*observer*.mq5",
    ]
    roots = [
        root / "mt5",
        root / "mql5",
        root / "MQL5",
        root,
        mt5_experts,
    ]
    found: List[Path] = []
    seen = set()
    for r in roots:
        if not r.exists():
            continue
        for pat in patterns:
            for p in r.glob(pat):
                if p.is_file() and p.suffix.lower() == ".mq5":
                    s = str(p.resolve())
                    if s not in seen:
                        found.append(p)
                        seen.add(s)
    def score(p: Path) -> int:
        n = p.name.lower()
        val = 0
        if n == "unified_observeronly_ea.mq5":
            val += 200
        if "unified" in n and "observer" in n:
            val += 100
        if "ea" in n:
            val += 20
        if "indicator" in n:
            val -= 80
        if "stage124" in n:
            val -= 30
        return val
    found.sort(key=score, reverse=True)
    return found


def forbidden_added_tokens(before: str, after: str) -> List[str]:
    added = after.replace(before, "")
    out = []
    for token in ["OrderSend", "#include <Trade", "CTrade ", ".Buy(", ".Sell(", "PositionOpen", "trade.Buy", "trade.Sell"]:
        if token in added:
            out.append(token)
    return out


def inject_rule_telemetry_call(src: str) -> Tuple[str, bool]:
    if CALL_LINE in src:
        return src, False
    # Preferred exact place in current Unified_ObserverOnly_EA.
    exact = "   UpdateChartComment(keys, vals, n);\n"
    if exact in src:
        return src.replace(exact, exact + "\n   " + CALL_LINE + "\n", 1), True

    # Fallback: after successful ReadSignal guard inside DisplaySignal.
    pat = re.compile(r"(void\s+DisplaySignal\s*\(\s*\)\s*\{.*?if\s*\(!ReadSignal\(keys,\s*vals,\s*n\)\)\s*return;\s*)", re.DOTALL)
    m = pat.search(src)
    if not m:
        return src, False
    insert_at = m.end()
    return src[:insert_at] + "\n\n   " + CALL_LINE + "\n" + src[insert_at:], True


def patch_mql5_source(src: str) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "block_added": False,
        "display_signal_call_added": False,
        "already_patched": BLOCK_BEGIN in src,
    }
    out = src
    if BLOCK_BEGIN not in out:
        out = out.rstrip() + "\n\n" + TELEMETRY_BLOCK.strip() + "\n"
        meta["block_added"] = True
    out, changed = inject_rule_telemetry_call(out)
    meta["display_signal_call_added"] = changed
    meta["forbidden_added_tokens"] = forbidden_added_tokens(src, out)
    return out, meta


def backup_path_for(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_suffix(path.suffix + f".stage133_backup_{stamp}")


def patch_file(path: Path) -> Dict[str, Any]:
    before = path.read_text(encoding="utf-8", errors="replace")
    after, meta = patch_mql5_source(before)
    changed = after != before
    backup = ""
    if changed:
        b = backup_path_for(path)
        shutil.copy2(path, b)
        path.write_text(after, encoding="utf-8")
        backup = str(b)
    return {"source": str(path), "changed": changed, "backup": backup, **meta}


def read_kv(path: Path) -> Tuple[Dict[str, str], str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}, "MISSING_OR_EMPTY"
    kv: Dict[str, str] = {}
    fmt = "UNKNOWN"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            k, v = line.split("|", 1)
            fmt = "PIPE"
        elif "," in line:
            k, v = line.split(",", 1)
            if fmt == "UNKNOWN":
                fmt = "COMMA"
        else:
            continue
        k = k.strip().strip('"').strip("'")
        v = v.strip().strip('"').strip("'")
        if k:
            kv[k] = v
    return kv, fmt


def read_latest_rule_rows(path: Path) -> Tuple[int, int, List[str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return 0, 0, []
    rows = []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(dict(r))
    except Exception:
        return 0, 0, []
    active = 0
    active_ids = []
    for r in rows:
        v = str(r.get("rule_active", "")).lower()
        if v in {"true", "1", "yes", "active"}:
            active += 1
            active_ids.append(str(r.get("rule_id", "")))
    return len(rows), active, active_ids


FIELDS = [
    "snapshot_utc",
    "rule_state_exists",
    "rule_state_fresh",
    "rule_state_age_sec",
    "rule_state_mtime_utc",
    "kv_count",
    "kv_format",
    "status",
    "feature_date",
    "mode",
    "any_signal_active",
    "selected_rule_id",
    "selected_label",
    "execution_allowed",
    "order_authorized",
    "rule_count",
    "active_rule_count",
    "latest_rows",
    "latest_active_rows",
    "latest_active_rule_ids",
    "allow_trading",
    "order_send",
    "decision",
]


def collect_rule_state(root: Path, mt5_files: Path, stale_after_sec: float, decision_hint: str) -> Dict[str, Any]:
    snapshot_utc = utc_now()
    kv_path = mt5_files / KV_FILE
    latest_path = mt5_files / LATEST_CSV
    kv, fmt = read_kv(kv_path)
    exists = kv_path.exists() and kv_path.stat().st_size > 0
    age = max(0.0, time.time() - kv_path.stat().st_mtime) if exists else None
    fresh = bool(exists and age is not None and age <= stale_after_sec)
    latest_rows, latest_active, active_ids = read_latest_rule_rows(latest_path)

    allow = kv.get("allow_trading", "")
    order_send = kv.get("order_send", "")
    no_order_ok = str(allow).lower() not in {"true", "1", "yes"} and str(order_send).lower() not in {"true", "1", "yes"}

    if not exists:
        decision = decision_hint or "STAGE133_RULE_STATE_TELEMETRY_NOT_FOUND_COMPILE_RELOAD_REQUIRED_NO_ORDER"
    elif not fresh:
        decision = "STAGE133_RULE_STATE_TELEMETRY_STALE_RUNTIME_NOT_CONFIRMED_NO_ORDER"
    elif latest_rows < 7:
        decision = "STAGE133_RULE_STATE_LATEST_ROWS_INCOMPLETE_REVIEW_REQUIRED_NO_ORDER"
    elif not no_order_ok:
        decision = "STAGE133_RULE_STATE_ORDER_FLAG_REVIEW_REQUIRED_NO_ORDER"
    else:
        decision = "STAGE133_RULE_STATE_TELEMETRY_CONFIRMED_NO_ORDER"

    return {
        "snapshot_utc": snapshot_utc,
        "rule_state_exists": exists,
        "rule_state_fresh": fresh,
        "rule_state_age_sec": round(age, 2) if age is not None else "",
        "rule_state_mtime_utc": iso_from_epoch(kv_path.stat().st_mtime) if exists else "",
        "kv_count": len(kv),
        "kv_format": fmt,
        "status": kv.get("status", ""),
        "feature_date": kv.get("feature_date", ""),
        "mode": kv.get("mode", ""),
        "any_signal_active": kv.get("any_signal_active", ""),
        "selected_rule_id": kv.get("selected_rule_id", ""),
        "selected_label": kv.get("selected_label", ""),
        "execution_allowed": kv.get("execution_allowed", ""),
        "order_authorized": kv.get("order_authorized", ""),
        "rule_count": kv.get("rule_count", ""),
        "active_rule_count": kv.get("active_rule_count", ""),
        "latest_rows": latest_rows,
        "latest_active_rows": latest_active,
        "latest_active_rule_ids": ";".join(active_ids),
        "allow_trading": allow,
        "order_send": order_send,
        "decision": decision,
    }


def run(root: Path, mt5_files: Path, mt5_experts: Path, source: Optional[str], patch_source: bool, write_mt5_ea: bool, stale_after_sec: float, write_mt5_status_kv: bool) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_experts = mt5_experts.expanduser()

    out = ensure_dir(root / "reports/stage133_unified_observer_rule_state_telemetry_writer")
    data = ensure_dir(root / "data/forward_shadow_telemetry")
    snapshot_utc = utc_now()

    sources = [Path(source).expanduser()] if source else locate_observer_sources(root, mt5_experts)
    sources = [p for p in sources if p.exists() and p.is_file()]
    selected = sources[0] if sources else None

    patch_result: Dict[str, Any] = {}
    mt5_written = ""
    decision_hint = ""
    if patch_source:
        if not selected:
            decision_hint = "STAGE133_NO_UNIFIED_OBSERVER_EA_SOURCE_FOUND_NO_ORDER"
        else:
            patch_result = patch_file(selected)
            if patch_result.get("forbidden_added_tokens"):
                decision_hint = "STAGE133_PATCH_REVIEW_REQUIRED_FORBIDDEN_TOKEN_ADDED_NO_ORDER"
            elif write_mt5_ea:
                ensure_dir(mt5_experts)
                dest = mt5_experts / selected.name
                try:
                    if selected.resolve() != dest.resolve():
                        shutil.copy2(selected, dest)
                    mt5_written = str(dest)
                except shutil.SameFileError:
                    mt5_written = str(dest)
                decision_hint = "STAGE133_RULE_STATE_TELEMETRY_PATCH_WRITTEN_COMPILE_RELOAD_REQUIRED_NO_ORDER"
            else:
                decision_hint = "STAGE133_RULE_STATE_TELEMETRY_PATCH_READY_COMPILE_RELOAD_REQUIRED_NO_ORDER"

    row = collect_rule_state(root, mt5_files, stale_after_sec, decision_hint)

    latest_snapshot = out / "stage133_latest_rule_state_telemetry_snapshot.csv"
    history_snapshot = data / "stage133_rule_state_telemetry_snapshots.csv"
    governance = out / "stage133_governance_no_order_manifest.csv"
    patch_audit = out / "stage133_patch_audit.csv"
    status_kv_repo = data / "stage133_rule_state_telemetry_status_kv.csv"
    status_kv_report = out / "stage133_rule_state_telemetry_status_kv.csv"

    write_rows(latest_snapshot, [row], FIELDS)
    append_rows(history_snapshot, [row], FIELDS)
    write_rows(governance, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS], ["block", "status"])
    patch_fields = ["source", "changed", "backup", "block_added", "display_signal_call_added", "already_patched", "forbidden_added_tokens"]
    write_rows(patch_audit, [patch_result] if patch_result else [], patch_fields)

    status_kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": row["decision"],
        "generated_utc": snapshot_utc,
        "allow_trading": "false",
        "order_send": "false",
        "selected_source": str(selected) if selected else "",
        "patch_source": str(bool(patch_source)).lower(),
        "mt5_ea_written": mt5_written,
        "rule_state_exists": str(row["rule_state_exists"]).lower(),
        "rule_state_fresh": str(row["rule_state_fresh"]).lower(),
        "rule_state_age_sec": row["rule_state_age_sec"],
        "latest_rows": row["latest_rows"],
        "latest_active_rows": row["latest_active_rows"],
        "selected_rule_id": row["selected_rule_id"],
    }
    write_kv(status_kv_repo, status_kv)
    write_kv(status_kv_report, status_kv)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        p = mt5_files / "xauusd_stage133_rule_state_telemetry_status_kv.csv"
        write_kv(p, status_kv)
        mt5_status_kv = str(p)

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot_utc,
        "status": STATUS,
        "decision": row["decision"],
        "classification": "UNIFIED_OBSERVER_RULE_STATE_TELEMETRY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "mt5_experts": str(mt5_experts),
        "candidate_sources": [str(p) for p in sources[:10]],
        "selected_source": str(selected) if selected else "",
        "patch_source_requested": patch_source,
        "write_mt5_ea_requested": write_mt5_ea,
        "patch_result": patch_result,
        "mt5_ea_written": mt5_written,
        **row,
        "rule_state_kv": str(mt5_files / KV_FILE),
        "rule_state_latest_csv": str(mt5_files / LATEST_CSV),
        "rule_state_history_csv": str(mt5_files / HISTORY_CSV),
        "latest_snapshot_csv": str(latest_snapshot),
        "history_snapshot_csv": str(history_snapshot),
        "patch_audit_csv": str(patch_audit),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "governance_no_order_manifest": str(governance),
        "summary_json": str(out / "stage133_unified_observer_rule_state_telemetry_writer_summary.json"),
        "report_md": str(out / "stage133_unified_observer_rule_state_telemetry_writer_report.md"),
        "next": [
            "Compile the patched Unified Observer EA in MetaEditor and reload/reattach it on XAUUSD,H1.",
            "After one to two minutes, run Stage133 without --patch-source to confirm fresh rule-state telemetry.",
            "If rule-state telemetry is fresh, collect market-open snapshots; do not promote from telemetry alone.",
        ],
    }
    write_json(out / "stage133_unified_observer_rule_state_telemetry_writer_summary.json", summary)
    report = [
        f"# {STAGE}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{row['decision']}`",
        "",
        "## Selected source",
        "",
        f"`{str(selected) if selected else ''}`",
        "",
        "## Rule state telemetry",
        "",
        f"- exists: {row['rule_state_exists']}",
        f"- fresh: {row['rule_state_fresh']}",
        f"- latest rows: {row['latest_rows']}",
        f"- active rows: {row['latest_active_rows']}",
        f"- selected rule: `{row['selected_rule_id']}`",
        "",
        "## No-order governance",
        "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
    ]
    (out / "stage133_unified_observer_rule_state_telemetry_writer_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-experts", default=DEFAULT_MT5_EXPERTS)
    ap.add_argument("--source", default="")
    ap.add_argument("--patch-source", action="store_true")
    ap.add_argument("--write-mt5-ea", action="store_true")
    ap.add_argument("--stale-after-sec", type=float, default=180.0)
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    args = ap.parse_args()
    run(
        root=Path(args.root),
        mt5_files=Path(args.mt5_files),
        mt5_experts=Path(args.mt5_experts),
        source=args.source or None,
        patch_source=args.patch_source,
        write_mt5_ea=args.write_mt5_ea,
        stale_after_sec=args.stale_after_sec,
        write_mt5_status_kv=args.write_mt5_status_kv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
