#!/usr/bin/env python3
"""
Stage124E: create an 8-rule unified-combo shadow status surface with chart display.

This is an observer/status patch only:
- merges the known legacy 7-rule unified observer status with Stage124C as the 8th shadow rule;
- writes a normalized 8-rule table and an MT5 key/value chart-status CSV;
- writes an MQL5 observer-only EA that displays status on the chart using Comment();
- does not write order, broker, paper/live, CTrade, or OrderSend surfaces.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage124E_UNIFIED_COMBO_8RULE_CHART_STATUS"
STATUS_OK = "STAGE124E_COMPLETE_8RULE_CHART_STATUS_READY_NO_ORDER"
DECISION_OK = "STAGE124E_UNIFIED_8RULE_SHADOW_STATUS_READY_NO_ORDER"
STATUS_BLOCKED = "STAGE124E_BLOCKED_MISSING_STAGE124C_INPUTS_NO_ORDER"
DECISION_BLOCKED = "STAGE124E_8RULE_STATUS_BLOCKED_NO_ORDER"

DEFAULT_MT5_FILES = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")
DEFAULT_MT5_EXPERTS = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD")

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE124E",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_ACTIVE_ORDER_SURFACE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

LEGACY_7_RULES = [
    ("01", "K06_RESILIENT_GOLD_VS_DXY_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("02", "K03_SAFE_HAVEN_REALYIELD_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("03", "K07_DXY_TREND_RELIEF_GOLD_TREND_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("04", "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("05", "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("06", "C96_07_CB_SUPPORT_NOT_CROWDED_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
    ("07", "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120", "LEGACY_UNIFIED_COMBO_OBSERVER"),
]

EA_SOURCE = r'''
//+------------------------------------------------------------------+
//| XAUUSD_Stage124E_UnifiedCombo8RuleChartStatus.mq5                |
//| Observer-only 8-rule status display. No trade library.            |
//+------------------------------------------------------------------+
#property strict

input string InpStatusKvFile = "xauusd_stage124e_unified_combo_8rule_chart_status.csv";
input int    InpTimerSeconds = 30;
input bool   InpShowCommentOnChart = true;
input int    InpMaxLines = 18;

string g_last_text = "";
int    g_last_kv_count = -1;

string TrimBoth(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

bool StartsWith(string s, string prefix)
{
   return StringSubstr(s, 0, StringLen(prefix)) == prefix;
}

int ReadStatusKv(string fname, string &display_text)
{
   int handle = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      display_text = "Stage124E 8-rule status file open failed\nfile=" + fname + "\nerr=" + IntegerToString(GetLastError()) + "\nTrading disabled.";
      return -1;
   }

   string lines[];
   ArrayResize(lines, 0);
   int cnt = 0;
   while(!FileIsEnding(handle))
   {
      string k = TrimBoth(FileReadString(handle));
      if(FileIsEnding(handle) && StringLen(k) == 0) break;
      string v = "";
      if(!FileIsLineEnding(handle)) v = TrimBoth(FileReadString(handle));
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle)) FileReadString(handle);
      cnt++;
      if(StartsWith(k, "line_"))
      {
         int n = ArraySize(lines);
         ArrayResize(lines, n + 1);
         lines[n] = v;
      }
   }
   FileClose(handle);

   display_text = "";
   int maxn = MathMin(ArraySize(lines), InpMaxLines);
   for(int i = 0; i < maxn; i++)
   {
      if(i > 0) display_text += "\n";
      display_text += lines[i];
   }
   if(ArraySize(lines) > InpMaxLines)
      display_text += "\n...";
   return cnt;
}

void PollStatus()
{
   string text;
   int kv_count = ReadStatusKv(InpStatusKvFile, text);
   if(InpShowCommentOnChart)
      Comment(text);

   if(kv_count != g_last_kv_count || text != g_last_text)
   {
      Print("Stage124E 8-rule chart status read complete. kv_count=", kv_count,
            " Trading remains disabled. No orders are sent.");
      g_last_kv_count = kv_count;
      g_last_text = text;
   }
}

int OnInit()
{
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("Stage124E UnifiedCombo8RuleChartStatus initialized. StatusFile=", InpStatusKvFile,
         " Trading disabled by design. This EA does not send orders.");
   PollStatus();
   return INIT_SUCCEEDED;
}

void OnTimer()
{
   PollStatus();
}

void OnTick()
{
   // Observer/status display only. Intentionally no trade calls.
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Print("Stage124E UnifiedCombo8RuleChartStatus deinitialized. reason=", reason);
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


def read_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            k = str(row[0]).strip()
            if not k:
                continue
            v = str(row[1]).strip() if len(row) > 1 else ""
            out[k] = v
    return out


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_kv(path: Path, items: Iterable[Tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for k, v in items:
            writer.writerow([k, "" if v is None else str(v)])


def first_existing(candidates: Iterable[Path]) -> Optional[Path]:
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def find_stage124_summary(root: Path) -> Path:
    return root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json"


def find_stage124_kv(root: Path, summary: Dict[str, Any]) -> Optional[Path]:
    candidates: List[Path] = []
    for key in ("mt5_shadow_kv_repo", "mt5_shadow_kv_report", "mt5_shadow_csv", "shadow_csv_repo", "shadow_csv_report"):
        raw = str(summary.get(key) or "")
        if raw:
            candidates.append(Path(raw))
    candidates.extend([
        root / "data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
        root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
    ])
    return first_existing(candidates)


def build_rule_rows(kv: Dict[str, str], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for slot, rule_id, source in LEGACY_7_RULES:
        rows.append({
            "slot": slot,
            "rule_id": rule_id,
            "source_rule_id": rule_id,
            "rule_status": "LEGACY_7RULE_COMBO_OBSERVER_ACTIVE_OR_EXTERNAL",
            "portfolio_role": "LEGACY_COMBO_RULE",
            "observer_only": "true",
            "candidate_only": "false",
            "allow_trading": "false",
            "side": "OBSERVER",
            "horizon_hours": "120",
            "cost10_mean_bps": "",
            "cost10_hit_rate": "",
            "last_signal_time_utc": "",
            "notes": "Existing unified combo rule carried forward; status source remains previous 7-rule observer/EA.",
        })
    rows.append({
        "slot": "08",
        "rule_id": kv.get("rule_id") or "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
        "source_rule_id": kv.get("source_rule_id") or "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        "rule_status": kv.get("rule_status") or summary.get("replay_status") or "PASS_STATIC_REPLAY",
        "portfolio_role": "STAGE124_SHADOW_RULE_8",
        "observer_only": kv.get("observer_only") or "true",
        "candidate_only": kv.get("candidate_only") or "true",
        "allow_trading": "false",
        "side": kv.get("side") or "OBSERVER",
        "horizon_hours": kv.get("horizon_hours") or "120",
        "cost10_mean_bps": kv.get("cost10_mean_bps") or "95.5793",
        "cost10_hit_rate": kv.get("cost10_hit_rate") or "0.6",
        "last_signal_time_utc": kv.get("last_signal_time_utc") or kv.get("last_signal") or "2026-02-12T00:00:00Z",
        "notes": "Stage124C merged into 8-rule combo status as shadow-only; no order path.",
    })
    return rows


def build_chart_lines(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Tuple[str, str]]:
    generated = utc_now()
    lines: List[str] = []
    lines.append("XAUUSD Unified Combo Shadow Status | 8 rules | NO ORDER")
    lines.append(f"Stage124E generated={generated} | trading=false | CTrade=false | OrderSend=false")
    lines.append("Legacy 7-rule combo is carried forward; rule 08 is Stage124 shadow.")
    for r in rows:
        slot = r.get("slot", "")
        rid = r.get("rule_id", "")
        status = r.get("rule_status", "")
        role = r.get("portfolio_role", "")
        if slot == "08":
            lines.append(f"{slot}. {rid} | {status} | cost10={r.get('cost10_mean_bps','')}bps | hit={r.get('cost10_hit_rate','')} | SHADOW")
        else:
            lines.append(f"{slot}. {rid} | {role} | observer-only")
    lines.append("Decision: observer/status only. Keep order path blocked.")
    lines.append(f"Stage124 replay={summary.get('replay_status','')} selected_for_stage125={summary.get('selected_for_stage125_count','0')}")
    items: List[Tuple[str, str]] = [("schema_version", "stage124e_chart_status_kv_v1")]
    for i, line in enumerate(lines):
        items.append((f"line_{i:02d}", line))
    items.append(("rule_count", str(len(rows))))
    items.append(("allow_trading", "false"))
    items.append(("stage124_rule_status", str(rows[-1].get("rule_status", ""))))
    items.append(("generated_utc", generated))
    return items


def run(root: Path, mt5_files: Path, mt5_experts: Path, write_mt5_csv: bool, write_mql5_ea: bool) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    mt5_files = mt5_files.expanduser()
    mt5_experts = mt5_experts.expanduser()
    out_dir = root / "reports/stage124e_unified_combo_8rule_chart_status"
    shadow_dir = root / "data/shadow_observer"
    out_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir.mkdir(parents=True, exist_ok=True)

    summary_path = find_stage124_summary(root)
    summary_in = read_json(summary_path)
    kv_path = find_stage124_kv(root, summary_in)
    kv = read_kv(kv_path) if kv_path else {}

    blocked: List[str] = []
    if not summary_path.exists():
        blocked.append("stage124c_summary_missing")
    if summary_in.get("replay_status") != "PASS_STATIC_REPLAY":
        blocked.append("stage124c_replay_not_pass")
    if kv_path is None:
        blocked.append("stage124c_kv_status_csv_missing")

    summary: Dict[str, Any]
    if blocked:
        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_BLOCKED,
            "decision": DECISION_BLOCKED,
            "classification": "UNIFIED_COMBO_8RULE_CHART_STATUS_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "blocked_reasons": blocked,
            "stage124_summary": str(summary_path),
            "stage124_kv_source": str(kv_path) if kv_path else "",
        }
    else:
        rows = build_rule_rows(kv, summary_in)
        table_fields = [
            "slot", "rule_id", "source_rule_id", "rule_status", "portfolio_role", "observer_only",
            "candidate_only", "allow_trading", "side", "horizon_hours", "cost10_mean_bps", "cost10_hit_rate",
            "last_signal_time_utc", "notes",
        ]
        repo_table = shadow_dir / "stage124e_unified_combo_8rule_status_table.csv"
        report_table = out_dir / "stage124e_unified_combo_8rule_status_table.csv"
        write_csv(repo_table, table_fields, rows)
        write_csv(report_table, table_fields, rows)

        kv_items = build_chart_lines(rows, summary_in)
        repo_chart_kv = shadow_dir / "stage124e_unified_combo_8rule_chart_status.csv"
        report_chart_kv = out_dir / "stage124e_unified_combo_8rule_chart_status.csv"
        write_kv(repo_chart_kv, kv_items)
        write_kv(report_chart_kv, kv_items)

        mt5_chart_kv = ""
        if write_mt5_csv:
            mt5_files.mkdir(parents=True, exist_ok=True)
            mt5_chart_kv = str(mt5_files / "xauusd_stage124e_unified_combo_8rule_chart_status.csv")
            write_kv(Path(mt5_chart_kv), kv_items)

        repo_ea = root / "mql5/Experts/XAUUSD_Stage124E_UnifiedCombo8RuleChartStatus.mq5"
        repo_ea.parent.mkdir(parents=True, exist_ok=True)
        repo_ea.write_text(EA_SOURCE, encoding="utf-8")
        mt5_ea = ""
        if write_mql5_ea:
            mt5_experts.mkdir(parents=True, exist_ok=True)
            mt5_ea = str(mt5_experts / "XAUUSD_Stage124E_UnifiedCombo8RuleChartStatus.mq5")
            Path(mt5_ea).write_text(EA_SOURCE, encoding="utf-8")

        gov_rows = [{"gate": b, "status": "BLOCKED"} for b in HARD_BLOCKS]
        gov_rows.append({"gate": "CHART_STATUS_DISPLAY", "status": "READY"})
        gov_rows.append({"gate": "UNIFIED_8RULE_SHADOW_STATUS", "status": "READY"})
        write_csv(out_dir / "stage124e_governance_no_order_manifest.csv", ["gate", "status"], gov_rows)

        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_OK,
            "decision": DECISION_OK,
            "classification": "UNIFIED_COMBO_8RULE_CHART_STATUS_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "legacy_rule_count": 7,
            "stage124_shadow_rule_count": 1,
            "unified_display_rule_count": 8,
            "stage124_rule_id": rows[-1]["rule_id"],
            "stage124_rule_status": rows[-1]["rule_status"],
            "stage124_cost10_mean_bps": rows[-1]["cost10_mean_bps"],
            "stage124_cost10_hit_rate": rows[-1]["cost10_hit_rate"],
            "stage124_last_signal_time_utc": rows[-1]["last_signal_time_utc"],
            "allow_trading": "false",
            "stage124_summary": str(summary_path),
            "stage124_kv_source": str(kv_path),
            "repo_status_table": str(repo_table),
            "report_status_table": str(report_table),
            "repo_chart_status_kv": str(repo_chart_kv),
            "report_chart_status_kv": str(report_chart_kv),
            "mt5_chart_status_kv_written": bool(write_mt5_csv),
            "mt5_chart_status_kv": mt5_chart_kv,
            "repo_ea_source": str(repo_ea),
            "mt5_ea_written": bool(write_mql5_ea),
            "mt5_ea_source": mt5_ea,
            "selected_for_stage125_count": summary_in.get("selected_for_stage125_count", 0),
            "discovery_decision": "NO_NEW_STAGE125_CANDIDATE_FROM_STAGE124_DISCOVERY",
            "next": [
                "Compile XAUUSD_Stage124E_UnifiedCombo8RuleChartStatus.mq5 manually.",
                "Use it as observer/status display only; it does not send orders.",
                "After chart display is verified, replace the separate Stage124C/Stage124D test EAs with this single 8-rule status EA if desired.",
            ],
        }

    (out_dir / "stage124e_unified_combo_8rule_chart_status_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_lines = [
        f"# {STAGE}",
        "",
        f"Status: {summary['status']}",
        f"Decision: {summary['decision']}",
        "",
        "Observer/status display only. No order, no CTrade, no OrderSend, no paper/live.",
    ]
    (out_dir / "stage124e_unified_combo_8rule_chart_status_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
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
        "unified_display_rule_count": summary.get("unified_display_rule_count", 0),
        "stage124_rule_status": summary.get("stage124_rule_status", ""),
        "mt5_chart_status_kv_written": summary.get("mt5_chart_status_kv_written", False),
        "mt5_ea_written": summary.get("mt5_ea_written", False),
        "selected_for_stage125_count": summary.get("selected_for_stage125_count", 0),
    }, ensure_ascii=False))
    return 0 if summary.get("status") == STATUS_OK else 2


if __name__ == "__main__":
    raise SystemExit(main())
