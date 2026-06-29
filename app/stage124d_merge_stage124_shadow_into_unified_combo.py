#!/usr/bin/env python3
"""
Stage124D: merge Stage124C shadow observer into unified combo as an 8th shadow rule.

Report/observer-only. This script does not send orders, does not enable trading,
and does not write any active broker/order surface. It writes a merged shadow combo
CSV and a no-order MQL5 source for observation.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage124D_MERGE_STAGE124_SHADOW_INTO_UNIFIED_COMBO"
STATUS_OK = "STAGE124D_COMPLETE_COMBO_SHADOW_MERGE_READY_NO_ORDER"
DECISION_OK = "STAGE124D_UNIFIED_COMBO_PLUS_STAGE124_SHADOW_READY_NO_ORDER"
STATUS_BLOCKED = "STAGE124D_BLOCKED_MISSING_STAGE124C_INPUTS_NO_ORDER"
DECISION_BLOCKED = "STAGE124D_COMBO_SHADOW_MERGE_BLOCKED_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE124D",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")
DEFAULT_MT5_EXPERTS = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD")

EA_SOURCE = r'''
//+------------------------------------------------------------------+
//| XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5                      |
//| Observer-only unified combo reader. No trade library.         |
//+------------------------------------------------------------------+
#property strict

input string InpMergedComboFile = "xauusd_stage124d_unified_combo_plus_stage124_shadow.csv";
input string InpStage124KvFile  = "xauusd_stage124_shadow_observer_signal.csv";
input int    InpTimerSeconds    = 60;
input int    InpMaxRowsToPrint  = 6;

int g_last_combo_rows = -1;
int g_last_kv_count = -1;

string TrimBoth(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

int ReadComboCsv(string fname)
{
   int handle = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Stage124D combo file open failed. file=", fname, " err=", GetLastError(), ". Trading remains disabled.");
      return -1;
   }

   int rows = 0;
   while(!FileIsEnding(handle))
   {
      string a = FileReadString(handle);
      if(FileIsEnding(handle) && StringLen(a) == 0) break;
      string b = "";
      string c = "";
      string d = "";
      string e = "";
      if(!FileIsLineEnding(handle)) b = FileReadString(handle);
      if(!FileIsLineEnding(handle)) c = FileReadString(handle);
      if(!FileIsLineEnding(handle)) d = FileReadString(handle);
      if(!FileIsLineEnding(handle)) e = FileReadString(handle);
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle)) FileReadString(handle);
      if(rows < InpMaxRowsToPrint)
         Print("Stage124D combo row ", rows, ": ", a, " | ", b, " | ", c, " | ", d, " | ", e);
      rows++;
   }
   FileClose(handle);
   return rows;
}

int ReadKvCsv(string fname, string &rule, string &status, string &allow, string &combo_mode)
{
   int handle = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Stage124D Stage124 KV file open failed. file=", fname, " err=", GetLastError(), ". Trading remains disabled.");
      return -1;
   }
   int cnt = 0;
   rule = ""; status = ""; allow = ""; combo_mode = "";
   while(!FileIsEnding(handle))
   {
      string k = TrimBoth(FileReadString(handle));
      if(FileIsEnding(handle) && StringLen(k) == 0) break;
      string v = "";
      if(!FileIsLineEnding(handle)) v = TrimBoth(FileReadString(handle));
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle)) FileReadString(handle);
      if(k == "rule_id") rule = v;
      if(k == "rule_status") status = v;
      if(k == "allow_trading") allow = v;
      if(k == "combo_mode") combo_mode = v;
      cnt++;
   }
   FileClose(handle);
   return cnt;
}

void PollFiles()
{
   string rule, status, allow, combo_mode;
   int combo_rows = ReadComboCsv(InpMergedComboFile);
   int kv_count = ReadKvCsv(InpStage124KvFile, rule, status, allow, combo_mode);
   if(combo_rows != g_last_combo_rows || kv_count != g_last_kv_count)
   {
      Print("Stage124D unified combo shadow read complete. combo_rows=", combo_rows,
            " kv_count=", kv_count,
            " stage124_rule=", rule,
            " stage124_status=", status,
            " allow_trading=", allow,
            " combo_mode=", combo_mode,
            ". Trading remains disabled. No orders are sent.");
      g_last_combo_rows = combo_rows;
      g_last_kv_count = kv_count;
   }
}

int OnInit()
{
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("Stage124D UnifiedComboShadowOnly initialized. ComboFile=", InpMergedComboFile,
         " Stage124KvFile=", InpStage124KvFile,
         " Trading disabled by design. This EA does not send orders.");
   return INIT_SUCCEEDED;
}

void OnTimer()
{
   PollFiles();
}

void OnTick()
{
   // Observer only. Intentionally no trade calls.
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("Stage124D UnifiedComboShadowOnly deinitialized. reason=", reason);
}
'''.strip() + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return [], []
        return list(reader.fieldnames), [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_kv_csv(path: Path, items: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for k, v in items.items():
            writer.writerow([k, "" if v is None else str(v)])


def find_stage124_summary(root: Path) -> Path:
    candidates = [
        root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json",
        root / "reports/stage124c_consolidated_shadow_csv_ea_and_frontier_discovery/stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def find_overlay_source(root: Path, summary: Dict[str, Any]) -> Optional[Path]:
    raw = str(summary.get("combo_overlay_preview_repo") or summary.get("combo_overlay_preview_report") or "")
    candidates: List[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.extend([
        root / "data/shadow_observer/stage124c_unified_observer_signal_overlay_preview.csv",
        root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124c_unified_observer_signal_overlay_preview.csv",
        root / "data/shadow_observer/unified_observer_signal.csv",
        root / "data/shadow_observer/xauusd_unified_observer_signal.csv",
        root / "data/observer/unified_observer_signal.csv",
    ])
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def find_stage124_kv(root: Path, summary: Dict[str, Any]) -> Optional[Path]:
    candidates = []
    for key in ("mt5_shadow_kv_repo", "mt5_shadow_kv_report", "shadow_csv_repo", "shadow_csv_report"):
        raw = str(summary.get(key) or "")
        if raw:
            candidates.append(Path(raw))
    candidates.extend([
        root / "data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
        root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
        root / "data/shadow_observer/stage124_xauusd_shadow_observer_signal.csv",
    ])
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def row_contains_stage124(row: Dict[str, str]) -> bool:
    text = " ".join(str(v) for v in row.values())
    return ("S117_06" in text) or ("S120_01" in text) or ("SPDR_FLOW_SUPPORT" in text) or ("Stage124" in text)


def estimate_rule_count(rows: List[Dict[str, str]]) -> int:
    candidates = ["rule_id", "RuleID", "rule", "id", "source_rule_id"]
    seen = set()
    for row in rows:
        for c in candidates:
            v = str(row.get(c, "")).strip()
            if v and v.lower() not in {"nan", "none"}:
                seen.add(v)
                break
    if seen:
        return len(seen)
    return len(rows)


def ensure_stage124_row(fieldnames: List[str], rows: List[Dict[str, str]], summary: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]], bool]:
    if any(row_contains_stage124(r) for r in rows):
        return fieldnames, rows, True
    if not fieldnames:
        fieldnames = ["rule_id", "source_rule_id", "rule_status", "allow_trading", "observer_only", "candidate_only", "stage", "notes"]
    needed = ["rule_id", "source_rule_id", "rule_status", "allow_trading", "observer_only", "candidate_only", "stage", "notes"]
    for c in needed:
        if c not in fieldnames:
            fieldnames.append(c)
    new_row = {c: "" for c in fieldnames}
    new_row.update({
        "rule_id": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
        "source_rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        "rule_status": "PASS_STATIC_REPLAY",
        "allow_trading": "false",
        "observer_only": "true",
        "candidate_only": "true",
        "stage": STAGE,
        "notes": "Stage124C merged as 8th shadow rule only; no order; no trade library; no paper/live.",
    })
    rows.append(new_row)
    return fieldnames, rows, False


def run(root: Path, mt5_files: Path, mt5_experts: Path, write_mt5_csv: bool, write_mql5_ea: bool) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    mt5_files = mt5_files.expanduser()
    mt5_experts = mt5_experts.expanduser()
    out_dir = root / "reports/stage124d_merge_stage124_shadow_into_unified_combo"
    repo_shadow_dir = root / "data/shadow_observer"
    out_dir.mkdir(parents=True, exist_ok=True)
    repo_shadow_dir.mkdir(parents=True, exist_ok=True)

    summary_path = find_stage124_summary(root)
    stage124_summary = read_json(summary_path)
    stage124_ok = stage124_summary.get("replay_status") == "PASS_STATIC_REPLAY"
    overlay_source = find_overlay_source(root, stage124_summary)
    kv_source = find_stage124_kv(root, stage124_summary)

    blocked = []
    if not summary_path.exists():
        blocked.append("stage124c_summary_missing")
    if not stage124_ok:
        blocked.append("stage124c_replay_not_pass")
    if overlay_source is None:
        blocked.append("combo_overlay_or_source_missing")
    if kv_source is None:
        blocked.append("stage124_kv_or_shadow_csv_missing")

    summary: Dict[str, Any]
    if blocked:
        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_BLOCKED,
            "decision": DECISION_BLOCKED,
            "classification": "COMBO_SHADOW_MERGE_ONLY_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "blocked_reasons": blocked,
            "stage124_summary": str(summary_path),
            "overlay_source": str(overlay_source) if overlay_source else "",
            "stage124_kv_source": str(kv_source) if kv_source else "",
            "next": [
                "Run Stage124C successfully first, then rerun Stage124D.",
                "Do not update paper/live/order surfaces.",
            ],
        }
    else:
        assert overlay_source is not None
        fieldnames, rows = read_csv_rows(overlay_source)
        fieldnames, rows, already_had_stage124 = ensure_stage124_row(fieldnames, rows, stage124_summary)
        rule_count = estimate_rule_count(rows)
        merged_repo = repo_shadow_dir / "stage124d_unified_combo_plus_stage124_shadow.csv"
        merged_report = out_dir / "stage124d_unified_combo_plus_stage124_shadow.csv"
        write_csv(merged_repo, fieldnames, rows)
        write_csv(merged_report, fieldnames, rows)

        manifest_rows = [{
            "artifact": "merged_unified_combo_shadow_csv",
            "path": str(merged_repo),
            "reports_only_or_observer_only": "true",
            "allow_trading": "false",
            "order_surface": "false",
        }, {
            "artifact": "stage124_kv_csv_source",
            "path": str(kv_source),
            "reports_only_or_observer_only": "true",
            "allow_trading": "false",
            "order_surface": "false",
        }]
        write_csv(out_dir / "stage124d_combo_merge_manifest.csv", list(manifest_rows[0].keys()), manifest_rows)

        governance = [{"gate": b, "status": "BLOCKED"} for b in HARD_BLOCKS]
        governance.append({"gate": "STAGE124_AS_8TH_RULE", "status": "SHADOW_ONLY_READY"})
        governance.append({"gate": "ACTIVE_ORDER_PERMISSION", "status": "BLOCKED"})
        write_csv(out_dir / "stage124d_governance_no_order_manifest.csv", ["gate", "status"], governance)

        mt5_combo_path = ""
        if write_mt5_csv:
            mt5_files.mkdir(parents=True, exist_ok=True)
            mt5_combo_path = str(mt5_files / "xauusd_stage124d_unified_combo_plus_stage124_shadow.csv")
            write_csv(Path(mt5_combo_path), fieldnames, rows)

        repo_ea_path = root / "mql5/Experts/XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5"
        repo_ea_path.parent.mkdir(parents=True, exist_ok=True)
        repo_ea_path.write_text(EA_SOURCE, encoding="utf-8")
        mt5_ea_path = ""
        if write_mql5_ea:
            mt5_experts.mkdir(parents=True, exist_ok=True)
            mt5_ea_path = str(mt5_experts / "XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5")
            Path(mt5_ea_path).write_text(EA_SOURCE, encoding="utf-8")

        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_OK,
            "decision": DECISION_OK,
            "classification": "UNIFIED_COMBO_SHADOW_MERGE_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "stage124_summary": str(summary_path),
            "stage124_replay_status": stage124_summary.get("replay_status", ""),
            "stage124_rule_status": "PASS_STATIC_REPLAY",
            "stage124_rule_added_to_combo_shadow": True,
            "stage124_already_present_in_overlay_source": already_had_stage124,
            "overlay_source": str(overlay_source),
            "merged_combo_shadow_repo": str(merged_repo),
            "merged_combo_shadow_report": str(merged_report),
            "merged_combo_estimated_rule_count": rule_count,
            "mt5_combo_csv_written": bool(write_mt5_csv),
            "mt5_combo_csv": mt5_combo_path,
            "stage124_kv_source": str(kv_source),
            "repo_ea_source": str(repo_ea_path),
            "mt5_ea_written": bool(write_mql5_ea),
            "mt5_ea_source": mt5_ea_path,
            "selected_for_stage125_count": stage124_summary.get("selected_for_stage125_count", 0),
            "discovery_decision": "NO_NEW_STAGE125_CANDIDATE_FROM_STAGE124_DISCOVERY",
            "next": [
                "Compile XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5 manually in MetaEditor.",
                "Attach it only as observer-only combo shadow if needed; no order path is enabled.",
                "Keep the previous 7-rule combo running until the old combo EA is intentionally replaced or patched.",
            ],
        }

    summary_path_out = out_dir / "stage124d_merge_stage124_shadow_into_unified_combo_summary.json"
    summary_path_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report = [
        f"# {STAGE}",
        "",
        f"Status: {summary['status']}",
        f"Decision: {summary['decision']}",
        "",
        "This is observer-only. No orders, no trade library, no paper/live.",
    ]
    (out_dir / "stage124d_merge_stage124_shadow_into_unified_combo_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    ap.add_argument("--mt5-experts", default=str(DEFAULT_MT5_EXPERTS))
    ap.add_argument("--write-mt5-csv", action="store_true")
    ap.add_argument("--write-mql5-ea", action="store_true")
    args = ap.parse_args(argv)
    summary = run(Path(args.root), Path(args.mt5_files), Path(args.mt5_experts), args.write_mt5_csv, args.write_mql5_ea)
    print(json.dumps({
        "stage": summary.get("stage"),
        "status": summary.get("status"),
        "decision": summary.get("decision"),
        "stage124_rule_added_to_combo_shadow": summary.get("stage124_rule_added_to_combo_shadow", False),
        "merged_combo_estimated_rule_count": summary.get("merged_combo_estimated_rule_count", 0),
        "mt5_combo_csv_written": summary.get("mt5_combo_csv_written", False),
        "mt5_ea_written": summary.get("mt5_ea_written", False),
        "selected_for_stage125_count": summary.get("selected_for_stage125_count", 0),
    }, ensure_ascii=False))
    return 0 if summary.get("status") == STATUS_OK else 2

if __name__ == "__main__":
    raise SystemExit(main())
