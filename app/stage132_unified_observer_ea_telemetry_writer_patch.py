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

STAGE = "Stage132_UNIFIED_OBSERVER_EA_TELEMETRY_WRITER_PATCH"
STATUS = "STAGE132_COMPLETE_UNIFIED_OBSERVER_EA_TELEMETRY_WRITER_READY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE132",
    "NO_ORDER_SEND_ADDED",
    "NO_CTRADE_ADDED",
    "NO_TRADING_LOGIC_CHANGE",
    "NO_SIGNAL_RULE_CHANGE",
    "NO_INDICATOR_UI_CHANGE_FROM_STAGE132",
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

HEARTBEAT_KV = "xauusd_stage132_unified_observer_ea_heartbeat_kv.csv"
HEARTBEAT_HISTORY = "xauusd_stage132_unified_observer_ea_heartbeat_history.csv"

BLOCK_BEGIN = "// STAGE132_TELEMETRY_BLOCK_BEGIN"
BLOCK_END = "// STAGE132_TELEMETRY_BLOCK_END"
CALL_INIT = "Stage132_WriteTelemetryNow(\"OnInit\");"
CALL_TICK = "Stage132_WriteTelemetryIfDue(\"OnTick\");"
CALL_DEINIT = "Stage132_WriteTelemetryNow(\"OnDeinit\");"

TELEMETRY_BLOCK = """
// STAGE132_TELEMETRY_BLOCK_BEGIN
// Telemetry-only runtime writer. No orders, no trade-class usage, no signal logic change.
input int Stage132TelemetryIntervalSec = 60;
input string Stage132TelemetryKvFile = "xauusd_stage132_unified_observer_ea_heartbeat_kv.csv";
input string Stage132TelemetryHistoryFile = "xauusd_stage132_unified_observer_ea_heartbeat_history.csv";
datetime g_stage132_last_telemetry_write = 0;

string Stage132_BoolText(bool value)
{
   return(value ? "true" : "false");
}

void Stage132_WriteTelemetryNow(string reason)
{
   datetime tc = TimeCurrent();
   datetime ts = TimeTradeServer();
   string local_time = TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS);
   string current_time = TimeToString(tc, TIME_DATE|TIME_SECONDS);
   string server_time = TimeToString(ts, TIME_DATE|TIME_SECONDS);

   int h = FileOpen(Stage132TelemetryKvFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("Stage132 telemetry KV FileOpen failed. file=", Stage132TelemetryKvFile, " err=", GetLastError(), ". No orders are sent.");
      return;
   }

   FileWriteString(h, "stage|Stage132_UNIFIED_OBSERVER_EA_TELEMETRY_WRITER\\n");
   FileWriteString(h, "status|UNIFIED_OBSERVER_EA_RUNTIME_ALIVE_NO_ORDER\\n");
   FileWriteString(h, "reason|" + reason + "\\n");
   FileWriteString(h, "allow_trading|false\\n");
   FileWriteString(h, "order_send|false\\n");
   FileWriteString(h, "symbol|" + _Symbol + "\\n");
   FileWriteString(h, "period|" + IntegerToString(_Period) + "\\n");
   FileWriteString(h, "time_local|" + local_time + "\\n");
   FileWriteString(h, "time_current|" + current_time + "\\n");
   FileWriteString(h, "time_trade_server|" + server_time + "\\n");
   FileWriteString(h, "terminal_trade_allowed|" + Stage132_BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "mql_trade_allowed|" + Stage132_BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "account_trade_allowed|" + Stage132_BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) + "\\n");
   FileWriteString(h, "account_login|" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\\n");
   FileWriteString(h, "account_server|" + AccountInfoString(ACCOUNT_SERVER) + "\\n");
   FileWriteString(h, "terminal_build|" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)) + "\\n");
   FileWriteString(h, "bars|" + IntegerToString(Bars(_Symbol, PERIOD_CURRENT)) + "\\n");
   FileWriteString(h, "note|telemetry_only_inside_unified_observer_ea_no_orders_no_signal_change\\n");
   FileClose(h);

   int hh = FileOpen(Stage132TelemetryHistoryFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI);
   if(hh != INVALID_HANDLE)
   {
      if(FileSize(hh) == 0)
      {
         FileWrite(hh, "time_local", "time_current", "time_trade_server", "symbol", "period", "reason", "terminal_trade_allowed", "mql_trade_allowed", "account_trade_allowed", "note");
      }
      FileSeek(hh, 0, SEEK_END);
      FileWrite(hh, local_time, current_time, server_time, _Symbol, IntegerToString(_Period), reason,
                Stage132_BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)),
                Stage132_BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)),
                Stage132_BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)),
                "telemetry_only_no_orders_no_signal_change");
      FileClose(hh);
   }
   else
   {
      Print("Stage132 telemetry history FileOpen failed. file=", Stage132TelemetryHistoryFile, " err=", GetLastError(), ". No orders are sent.");
   }

   g_stage132_last_telemetry_write = TimeLocal();
   Print("Stage132 unified observer EA telemetry written. reason=", reason, " symbol=", _Symbol, " period=", _Period, ". No orders are sent.");
}

void Stage132_WriteTelemetryIfDue(string reason)
{
   datetime now_local = TimeLocal();
   int interval_sec = MathMax(10, Stage132TelemetryIntervalSec);
   if(g_stage132_last_telemetry_write == 0 || (now_local - g_stage132_last_telemetry_write) >= interval_sec)
   {
      Stage132_WriteTelemetryNow(reason);
   }
}
// STAGE132_TELEMETRY_BLOCK_END
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


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
        root / "mql5",
        root / "MQL5",
        root / "app",
        root,
        mt5_experts,
        mt5_experts.parent if mt5_experts else None,
    ]
    found: List[Path] = []
    seen = set()
    for r in roots:
        if not r or not r.exists():
            continue
        for pat in patterns:
            for p in r.glob(pat):
                if p.is_file() and p.suffix.lower() == ".mq5":
                    s = str(p.resolve())
                    if s not in seen:
                        found.append(p)
                        seen.add(s)
    def score(p: Path) -> int:
        name = p.name.lower()
        val = 0
        if "unified_observeronly" in name or "unified_observer" in name:
            val += 100
        if "observeronly" in name:
            val += 40
        if "ea" in name:
            val += 20
        if "indicator" in name:
            val -= 50
        if "stage124e" in name:
            val -= 30
        return val
    found.sort(key=score, reverse=True)
    return found


def has_forbidden_added_tokens(before: str, after: str) -> List[str]:
    added = after.replace(before, "")
    forbidden = []
    for tok in ["OrderSend", "CTrade", ".Buy(", ".Sell(", "PositionOpen", "trade.Buy", "trade.Sell"]:
        if tok in added:
            forbidden.append(tok)
    return forbidden


def inject_into_function(src: str, func_name: str, call_line: str) -> Tuple[str, bool]:
    if call_line in src:
        return src, False
    pattern = re.compile(r"((?:int|void)\s+" + re.escape(func_name) + r"\s*\([^)]*\)\s*\{)", re.MULTILINE)
    m = pattern.search(src)
    if not m:
        return src, False
    insert_at = m.end()
    return src[:insert_at] + "\n   " + call_line + "\n" + src[insert_at:], True


def add_function_if_missing(src: str, handler_name: str, func_text: str) -> Tuple[str, bool]:
    if re.search(r"(?:int|void)\s+" + re.escape(handler_name) + r"\s*\(", src):
        return src, False
    return src.rstrip() + "\n\n" + func_text.strip() + "\n", True


def patch_mql5_source(src: str) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "block_added": False,
        "oninit_call_added": False,
        "ontick_call_added": False,
        "ondeinit_call_added": False,
        "ontick_handler_added": False,
        "ondeinit_handler_added": False,
        "already_patched": BLOCK_BEGIN in src,
    }

    out = src
    if BLOCK_BEGIN not in out:
        out = out.rstrip() + "\n\n" + TELEMETRY_BLOCK.strip() + "\n"
        meta["block_added"] = True

    out2, changed = inject_into_function(out, "OnInit", CALL_INIT)
    out = out2
    meta["oninit_call_added"] = changed

    out2, changed = inject_into_function(out, "OnTick", CALL_TICK)
    out = out2
    if changed:
        meta["ontick_call_added"] = True
    elif CALL_TICK not in out:
        out, added = add_function_if_missing(out, "OnTick", "void OnTick()\n{\n   " + CALL_TICK + "\n}")
        meta["ontick_handler_added"] = added
        meta["ontick_call_added"] = added

    out2, changed = inject_into_function(out, "OnDeinit", CALL_DEINIT)
    out = out2
    if changed:
        meta["ondeinit_call_added"] = True
    elif CALL_DEINIT not in out:
        out, added = add_function_if_missing(out, "OnDeinit", "void OnDeinit(const int reason)\n{\n   " + CALL_DEINIT + "\n}")
        meta["ondeinit_handler_added"] = added
        meta["ondeinit_call_added"] = added

    meta["forbidden_added_tokens"] = has_forbidden_added_tokens(src, out)
    return out, meta


def backup_path_for(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_suffix(path.suffix + f".stage132_backup_{stamp}")


def patch_file(path: Path) -> Dict[str, Any]:
    before = path.read_text(encoding="utf-8", errors="replace")
    after, meta = patch_mql5_source(before)
    backup = ""
    changed = after != before
    if changed:
        b = backup_path_for(path)
        shutil.copy2(path, b)
        path.write_text(after, encoding="utf-8")
        backup = str(b)
    return {
        "source": str(path),
        "changed": changed,
        "backup": backup,
        **meta,
    }


def read_kv(path: Path) -> Tuple[Dict[str, str], str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}, "MISSING_OR_EMPTY"
    kv: Dict[str, str] = {}
    fmt = "UNKNOWN"
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
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


FIELDS = [
    "snapshot_utc",
    "ea_heartbeat_exists",
    "ea_heartbeat_fresh",
    "ea_heartbeat_age_sec",
    "ea_heartbeat_mtime_utc",
    "kv_count",
    "kv_format",
    "status",
    "reason",
    "symbol",
    "period",
    "time_local",
    "time_current",
    "time_trade_server",
    "terminal_trade_allowed",
    "mql_trade_allowed",
    "account_trade_allowed",
    "allow_trading",
    "order_send",
    "decision",
]


def collect_ea_heartbeat(root: Path, mt5_files: Path, stale_after_sec: float, decision_hint: str) -> Dict[str, Any]:
    snapshot_utc = utc_now()
    hb = mt5_files / HEARTBEAT_KV
    kv, fmt = read_kv(hb)
    exists = hb.exists() and hb.stat().st_size > 0
    age = max(0.0, time.time() - hb.stat().st_mtime) if exists else None
    fresh = bool(exists and age is not None and age <= stale_after_sec)
    allow = kv.get("allow_trading", "")
    order_send = kv.get("order_send", "")
    no_order_ok = str(allow).lower() not in {"true", "1", "yes"} and str(order_send).lower() not in {"true", "1", "yes"}

    if not exists:
        decision = decision_hint or "STAGE132_EA_HEARTBEAT_NOT_FOUND_COMPILE_ATTACH_RELOAD_REQUIRED_NO_ORDER"
    elif not fresh:
        decision = "STAGE132_EA_HEARTBEAT_STALE_RUNTIME_NOT_CONFIRMED_NO_ORDER"
    elif not no_order_ok:
        decision = "STAGE132_EA_HEARTBEAT_ORDER_FLAG_REVIEW_REQUIRED_NO_ORDER"
    else:
        decision = "STAGE132_UNIFIED_OBSERVER_EA_RUNTIME_TELEMETRY_CONFIRMED_NO_ORDER"

    return {
        "snapshot_utc": snapshot_utc,
        "ea_heartbeat_exists": exists,
        "ea_heartbeat_fresh": fresh,
        "ea_heartbeat_age_sec": round(age, 2) if age is not None else "",
        "ea_heartbeat_mtime_utc": iso_from_epoch(hb.stat().st_mtime) if exists else "",
        "kv_count": len(kv),
        "kv_format": fmt,
        "status": kv.get("status", ""),
        "reason": kv.get("reason", ""),
        "symbol": kv.get("symbol", ""),
        "period": kv.get("period", ""),
        "time_local": kv.get("time_local", ""),
        "time_current": kv.get("time_current", ""),
        "time_trade_server": kv.get("time_trade_server", ""),
        "terminal_trade_allowed": kv.get("terminal_trade_allowed", ""),
        "mql_trade_allowed": kv.get("mql_trade_allowed", ""),
        "account_trade_allowed": kv.get("account_trade_allowed", ""),
        "allow_trading": allow,
        "order_send": order_send,
        "decision": decision,
    }


def run(root: Path, mt5_files: Path, mt5_experts: Path, source: Optional[str], patch_source: bool, write_mt5_ea: bool, stale_after_sec: float, write_mt5_status_kv: bool) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_experts = mt5_experts.expanduser()
    out = ensure_dir(root / "reports/stage132_unified_observer_ea_telemetry_writer_patch")
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
            decision_hint = "STAGE132_NO_UNIFIED_OBSERVER_EA_SOURCE_FOUND_NO_ORDER"
        else:
            patch_result = patch_file(selected)
            if patch_result.get("forbidden_added_tokens"):
                decision_hint = "STAGE132_PATCH_REVIEW_REQUIRED_FORBIDDEN_TOKEN_ADDED_NO_ORDER"
            elif write_mt5_ea:
                ensure_dir(mt5_experts)
                dest = mt5_experts / selected.name
                try:
                    if selected.resolve() != dest.resolve():
                        shutil.copy2(selected, dest)
                    mt5_written = str(dest)
                except shutil.SameFileError:
                    mt5_written = str(dest)
                decision_hint = "STAGE132_EA_TELEMETRY_PATCH_WRITTEN_COMPILE_RELOAD_REQUIRED_NO_ORDER"
            else:
                decision_hint = "STAGE132_EA_TELEMETRY_PATCH_READY_COMPILE_RELOAD_REQUIRED_NO_ORDER"

    row = collect_ea_heartbeat(root, mt5_files, stale_after_sec, decision_hint)
    latest_path = out / "stage132_latest_unified_observer_ea_heartbeat_snapshot.csv"
    history_path = data / "stage132_unified_observer_ea_heartbeat_snapshots.csv"
    governance_path = out / "stage132_governance_no_order_manifest.csv"
    patch_audit_path = out / "stage132_patch_audit.csv"
    status_kv_repo = data / "stage132_unified_observer_ea_telemetry_status_kv.csv"
    status_kv_report = out / "stage132_unified_observer_ea_telemetry_status_kv.csv"

    write_rows(latest_path, [row], FIELDS)
    append_rows(history_path, [row], FIELDS)
    write_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS], ["block", "status"])
    patch_fields = ["source", "changed", "backup", "block_added", "oninit_call_added", "ontick_call_added", "ondeinit_call_added", "ontick_handler_added", "ondeinit_handler_added", "already_patched", "forbidden_added_tokens"]
    write_rows(patch_audit_path, [patch_result] if patch_result else [], patch_fields)

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
        "ea_heartbeat_exists": str(row["ea_heartbeat_exists"]).lower(),
        "ea_heartbeat_fresh": str(row["ea_heartbeat_fresh"]).lower(),
        "ea_heartbeat_age_sec": row["ea_heartbeat_age_sec"],
    }
    write_kv(status_kv_repo, status_kv)
    write_kv(status_kv_report, status_kv)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        p = mt5_files / "xauusd_stage132_unified_observer_ea_telemetry_status_kv.csv"
        write_kv(p, status_kv)
        mt5_status_kv = str(p)

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot_utc,
        "status": STATUS,
        "decision": row["decision"],
        "classification": "UNIFIED_OBSERVER_EA_TELEMETRY_WRITER_NO_ORDER",
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
        "heartbeat_kv": str(mt5_files / HEARTBEAT_KV),
        "heartbeat_history": str(mt5_files / HEARTBEAT_HISTORY),
        "latest_snapshot_csv": str(latest_path),
        "history_csv": str(history_path),
        "patch_audit_csv": str(patch_audit_path),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "governance_no_order_manifest": str(governance_path),
        "summary_json": str(out / "stage132_unified_observer_ea_telemetry_writer_patch_summary.json"),
        "report_md": str(out / "stage132_unified_observer_ea_telemetry_writer_patch_report.md"),
        "next": [
            "Compile the patched Unified Observer EA in MetaEditor and reload/reattach it on XAUUSD,H1.",
            "After one to two minutes, run Stage132 collector again without --patch-source to confirm a fresh EA heartbeat.",
            "If EA heartbeat is fresh, continue collecting forward telemetry; do not promote from heartbeat alone.",
        ],
    }
    write_json(out / "stage132_unified_observer_ea_telemetry_writer_patch_summary.json", summary)

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
        "## Heartbeat",
        "",
        f"- exists: {row['ea_heartbeat_exists']}",
        f"- fresh: {row['ea_heartbeat_fresh']}",
        f"- age sec: {row['ea_heartbeat_age_sec']}",
        "",
        "## No-order governance",
        "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
    ]
    (out / "stage132_unified_observer_ea_telemetry_writer_patch_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-experts", default=DEFAULT_MT5_EXPERTS)
    ap.add_argument("--source", default="", help="Optional explicit Unified Observer EA .mq5 path")
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
