#!/usr/bin/env python3
"""
Stage124F: package Stage124 as a same-chart indicator overlay, not a second EA.

Purpose:
- keep the existing 7-rule Unified_ObserverOnly_EA running on the chart;
- add Stage124/SPDR rule as a visual rule-08 overlay on the same chart via a custom indicator;
- write only MT5 Files CSV + indicator source when explicitly requested;
- no OrderSend, no CTrade, no broker or paper/live surface.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage124F_RULE8_SAME_CHART_INDICATOR_OVERLAY"
STATUS_OK = "STAGE124F_COMPLETE_RULE8_INDICATOR_OVERLAY_READY_NO_ORDER"
DECISION_OK = "STAGE124F_USE_7RULE_EA_PLUS_RULE8_INDICATOR_OVERLAY_NO_ORDER"
STATUS_BLOCKED = "STAGE124F_BLOCKED_MISSING_STAGE124C_INPUTS_NO_ORDER"
DECISION_BLOCKED = "STAGE124F_RULE8_INDICATOR_OVERLAY_BLOCKED_NO_ORDER"

DEFAULT_MT5_FILES = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")
DEFAULT_MT5_INDICATORS = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Indicators/Advisors/XAUUSD")

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE124F",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_EA_REPLACEMENT_REQUIRED",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

INDICATOR_SOURCE = r'''
//+------------------------------------------------------------------+
//| XAUUSD_Stage124F_Rule8OverlayIndicator.mq5                       |
//| Same-chart visual overlay for Stage124 rule 08. No trade calls.   |
//+------------------------------------------------------------------+
#property strict
#property indicator_chart_window
#property indicator_plots 0

input string InpKvFile = "xauusd_stage124f_rule8_overlay_kv.csv";
input int    InpTimerSeconds = 30;
input int    InpCorner = CORNER_LEFT_UPPER;
input int    InpX = 10;
input int    InpY = 220;
input int    InpLineHeight = 16;
input color  InpTextColor = clrDeepSkyBlue;
input int    InpFontSize = 9;
input string InpFont = "Arial";

string PREFIX = "Stage124F_Rule8_";

string TrimBoth(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

void DeleteOverlay()
{
   long chart = ChartID();
   int total = ObjectsTotal(chart, 0, -1);
   for(int i = total - 1; i >= 0; --i)
   {
      string name = ObjectName(chart, i, 0, -1);
      if(StringFind(name, PREFIX) == 0)
         ObjectDelete(chart, name);
   }
}

void PutLabel(int idx, string text)
{
   long chart = ChartID();
   string name = PREFIX + IntegerToString(idx);
   if(ObjectFind(chart, name) < 0)
      ObjectCreate(chart, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(chart, name, OBJPROP_CORNER, InpCorner);
   ObjectSetInteger(chart, name, OBJPROP_XDISTANCE, InpX);
   ObjectSetInteger(chart, name, OBJPROP_YDISTANCE, InpY + idx * InpLineHeight);
   ObjectSetInteger(chart, name, OBJPROP_COLOR, InpTextColor);
   ObjectSetInteger(chart, name, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetString(chart, name, OBJPROP_FONT, InpFont);
   ObjectSetString(chart, name, OBJPROP_TEXT, text);
}

string GetValue(string &keys[], string &vals[], string key, string fallback="")
{
   for(int i = 0; i < ArraySize(keys); ++i)
      if(keys[i] == key)
         return vals[i];
   return fallback;
}

int ReadKv(string fname, string &keys[], string &vals[])
{
   ArrayResize(keys, 0);
   ArrayResize(vals, 0);
   int handle = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
      return -1;

   int cnt = 0;
   while(!FileIsEnding(handle))
   {
      string k = TrimBoth(FileReadString(handle));
      if(FileIsEnding(handle) && StringLen(k) == 0) break;
      string v = "";
      if(!FileIsLineEnding(handle))
         v = TrimBoth(FileReadString(handle));
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle))
         FileReadString(handle);
      if(StringLen(k) > 0)
      {
         int n = ArraySize(keys);
         ArrayResize(keys, n + 1);
         ArrayResize(vals, n + 1);
         keys[n] = k;
         vals[n] = v;
         cnt++;
      }
   }
   FileClose(handle);
   return cnt;
}

void RefreshOverlay()
{
   string keys[], vals[];
   int cnt = ReadKv(InpKvFile, keys, vals);
   DeleteOverlay();

   if(cnt < 0)
   {
      PutLabel(0, "08. Stage124 SPDR rule | overlay file open failed | NO ORDER");
      PutLabel(1, "file=" + InpKvFile + " err=" + IntegerToString(GetLastError()));
      return;
   }

   string rid = GetValue(keys, vals, "rule_id", "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN");
   string status = GetValue(keys, vals, "rule_status", "UNKNOWN");
   string allow = GetValue(keys, vals, "allow_trading", "false");
   string cost = GetValue(keys, vals, "cost10_mean_bps", "");
   string hit = GetValue(keys, vals, "cost10_hit_rate", "");
   string last = GetValue(keys, vals, "last_signal_time_utc", "");
   string disc = GetValue(keys, vals, "selected_for_stage125_count", "0");

   PutLabel(0, "08. Stage124 SPDR shadow | " + status + " | allow_trading=" + allow + " | NO ORDER");
   PutLabel(1, "rule=" + rid);
   PutLabel(2, "cost10_mean=" + cost + "bps | hit=" + hit + " | last=" + last);
   PutLabel(3, "Stage125 selected=" + disc + " | keep 7-rule EA running; this is indicator overlay only");

   Print("Stage124F rule8 overlay read complete. kv_count=", cnt,
         " status=", status,
         " allow_trading=", allow,
         " cost10_mean_bps=", cost,
         " cost10_hit_rate=", hit,
         " Trading remains disabled. No orders are sent.");
}

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "Stage124F Rule8 Overlay NO ORDER");
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("Stage124F Rule8OverlayIndicator initialized. File=", InpKvFile,
         " Indicator overlay only; keep the 7-rule EA running. This indicator cannot send orders.");
   RefreshOverlay();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteOverlay();
   Print("Stage124F Rule8OverlayIndicator deinitialized. reason=", reason);
}

void OnTimer()
{
   RefreshOverlay();
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   return rates_total;
}
'''.strip() + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            key = str(row[0]).strip()
            if not key:
                continue
            out[key] = str(row[1]).strip() if len(row) > 1 else ""
    return out


def write_kv_atomic(path: Path, items: Iterable[Tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for k, v in items:
            writer.writerow([k, "" if v is None else str(v)])
    os.replace(tmp, path)


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def find_stage124_summary(root: Path) -> Path:
    return root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json"


def find_stage124_kv(root: Path, summary: Dict[str, Any]) -> Optional[Path]:
    candidates: List[Path] = []
    for key in ("mt5_shadow_kv_repo", "mt5_shadow_kv_report", "shadow_csv_repo", "shadow_csv_report"):
        raw = str(summary.get(key) or "")
        if raw:
            candidates.append(Path(raw))
    candidates.extend([
        root / "data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
        root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv",
    ])
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def build_rule8_kv(summary: Dict[str, Any], kv: Dict[str, str]) -> List[Tuple[str, Any]]:
    return [
        ("schema_version", "stage124f_rule8_overlay_kv_v1"),
        ("stage", STAGE),
        ("generated_utc", utc_now()),
        ("slot", "08"),
        ("rule_id", kv.get("rule_id") or "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN"),
        ("source_rule_id", kv.get("source_rule_id") or "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF"),
        ("rule_status", kv.get("rule_status") or summary.get("replay_status") or "PASS_STATIC_REPLAY"),
        ("allow_trading", "false"),
        ("observer_only", "true"),
        ("candidate_only", kv.get("candidate_only") or "true"),
        ("side", kv.get("side") or "OBSERVER"),
        ("horizon_hours", kv.get("horizon_hours") or "120"),
        ("cost10_mean_bps", kv.get("cost10_mean_bps") or "95.5793"),
        ("cost10_hit_rate", kv.get("cost10_hit_rate") or "0.6"),
        ("last_signal_time_utc", kv.get("last_signal_time_utc") or kv.get("last_signal") or "2026-02-12T00:00:00Z"),
        ("selected_for_stage125_count", summary.get("selected_for_stage125_count", 0)),
        ("runtime_mode", "KEEP_EXISTING_7RULE_EA_ADD_THIS_INDICATOR_ON_SAME_CHART"),
        ("order_policy", "NO_ORDER_SEND_NO_CTRADE_NO_PAPER_LIVE_NO_LIVE"),
    ]


def run(root: Path, mt5_files: Path, mt5_indicators: Path, write_mt5_csv: bool, write_mql5_indicator: bool) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()
    out_dir = root / "reports/stage124f_rule8_indicator_overlay"
    shadow_dir = root / "data/shadow_observer"
    out_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir.mkdir(parents=True, exist_ok=True)

    summary_path = find_stage124_summary(root)
    stage124_summary = read_json(summary_path)
    kv_path = find_stage124_kv(root, stage124_summary)
    kv = read_kv(kv_path) if kv_path else {}

    blocked: List[str] = []
    if not summary_path.exists():
        blocked.append("stage124c_summary_missing")
    if stage124_summary.get("replay_status") != "PASS_STATIC_REPLAY":
        blocked.append("stage124_replay_not_pass")
    if kv_path is None:
        blocked.append("stage124_rule8_kv_missing")

    if blocked:
        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_BLOCKED,
            "decision": DECISION_BLOCKED,
            "classification": "RULE8_SAME_CHART_INDICATOR_OVERLAY_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "blocked_reasons": blocked,
            "stage124_summary": str(summary_path),
            "stage124_kv_source": str(kv_path) if kv_path else "",
        }
    else:
        kv_items = build_rule8_kv(stage124_summary, kv)
        repo_kv = shadow_dir / "stage124f_rule8_overlay_kv.csv"
        report_kv = out_dir / "stage124f_rule8_overlay_kv.csv"
        write_kv_atomic(repo_kv, kv_items)
        write_kv_atomic(report_kv, kv_items)

        mt5_kv_path = ""
        if write_mt5_csv:
            mt5_files.mkdir(parents=True, exist_ok=True)
            mt5_kv_path = str(mt5_files / "xauusd_stage124f_rule8_overlay_kv.csv")
            write_kv_atomic(Path(mt5_kv_path), kv_items)

        repo_ind = root / "mql5/Indicators/XAUUSD_Stage124F_Rule8OverlayIndicator.mq5"
        repo_ind.parent.mkdir(parents=True, exist_ok=True)
        repo_ind.write_text(INDICATOR_SOURCE, encoding="utf-8")

        mt5_ind_path = ""
        if write_mql5_indicator:
            mt5_indicators.mkdir(parents=True, exist_ok=True)
            mt5_ind_path = str(mt5_indicators / "XAUUSD_Stage124F_Rule8OverlayIndicator.mq5")
            Path(mt5_ind_path).write_text(INDICATOR_SOURCE, encoding="utf-8")

        write_csv(
            out_dir / "stage124f_runtime_decision.csv",
            ["item", "decision"],
            [
                {"item": "existing_7rule_ea", "decision": "KEEP_RUNNING_ON_THE_CHART"},
                {"item": "stage124_rule8", "decision": "ADD_AS_CUSTOM_INDICATOR_OVERLAY_ON_SAME_CHART"},
                {"item": "stage124c_stage124d_stage124e_eas", "decision": "DO_NOT_KEEP_AS_PERMANENT_PARALLEL_EAS"},
                {"item": "active_order_surface", "decision": "BLOCKED"},
            ],
        )
        write_csv(out_dir / "stage124f_governance_no_order_manifest.csv", ["gate", "status"], [{"gate": b, "status": "BLOCKED"} for b in HARD_BLOCKS])

        summary = {
            "stage": STAGE,
            "generated_utc": utc_now(),
            "status": STATUS_OK,
            "decision": DECISION_OK,
            "classification": "RULE8_SAME_CHART_INDICATOR_OVERLAY_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "stage124_summary": str(summary_path),
            "stage124_kv_source": str(kv_path),
            "stage124_rule_id": dict(kv_items).get("rule_id"),
            "stage124_rule_status": dict(kv_items).get("rule_status"),
            "cost10_mean_bps": dict(kv_items).get("cost10_mean_bps"),
            "cost10_hit_rate": dict(kv_items).get("cost10_hit_rate"),
            "selected_for_stage125_count": stage124_summary.get("selected_for_stage125_count", 0),
            "existing_7rule_ea_policy": "KEEP_RUNNING",
            "rule8_runtime_surface": "CUSTOM_INDICATOR_OVERLAY_ON_SAME_CHART",
            "repo_rule8_kv": str(repo_kv),
            "report_rule8_kv": str(report_kv),
            "mt5_rule8_kv_written": bool(write_mt5_csv),
            "mt5_rule8_kv": mt5_kv_path,
            "repo_indicator_source": str(repo_ind),
            "mt5_indicator_written": bool(write_mql5_indicator),
            "mt5_indicator_source": mt5_ind_path,
            "next": [
                "Compile the indicator manually in MetaEditor.",
                "Keep Unified_ObserverOnly_EA attached to the same chart.",
                "Attach XAUUSD_Stage124F_Rule8OverlayIndicator as an indicator, not as a second EA.",
                "Remove Stage124C/D/E test EAs from charts after this overlay is visible.",
            ],
        }

    (out_dir / "stage124f_rule8_indicator_overlay_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage124f_rule8_indicator_overlay_report.md").write_text(
        f"# {STAGE}\n\nStatus: {summary['status']}\nDecision: {summary['decision']}\n\nSame-chart indicator overlay only. No order surface.\n",
        encoding="utf-8",
    )
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    ap.add_argument("--mt5-indicators", default=str(DEFAULT_MT5_INDICATORS))
    ap.add_argument("--write-mt5-csv", action="store_true")
    ap.add_argument("--write-mql5-indicator", action="store_true")
    args = ap.parse_args(argv)
    summary = run(Path(args.root), Path(args.mt5_files), Path(args.mt5_indicators), args.write_mt5_csv, args.write_mql5_indicator)
    print(json.dumps({
        "stage": summary.get("stage"),
        "status": summary.get("status"),
        "decision": summary.get("decision"),
        "rule8_runtime_surface": summary.get("rule8_runtime_surface", ""),
        "stage124_rule_status": summary.get("stage124_rule_status", ""),
        "mt5_rule8_kv_written": summary.get("mt5_rule8_kv_written", False),
        "mt5_indicator_written": summary.get("mt5_indicator_written", False),
    }, ensure_ascii=False))
    return 0 if summary.get("status") == STATUS_OK else 2


if __name__ == "__main__":
    raise SystemExit(main())
