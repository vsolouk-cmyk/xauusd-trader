#!/usr/bin/env python3
"""Stage126B indicator visibility and overlay layout hotfix.

Writes status-only MQL5 indicators for Stage124F rule-8 and Stage126 rule-9 to
both the repository and the user's MT5 Indicators locations. It does not create
orders, does not change any EA, and does not touch broker/order surfaces.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

STAGE = "Stage126B_INDICATOR_VISIBILITY_AND_OVERLAY_LAYOUT_HOTFIX"
STATUS_OK = "STAGE126B_COMPLETE_INDICATOR_VISIBILITY_LAYOUT_HOTFIX_READY_NO_ORDER"
DECISION_OK = "STAGE126B_RULE8_RULE9_INDICATORS_WRITTEN_NO_ORDER"

DEFAULT_MT5_ROOT = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5")
DEFAULT_MT5_FILES = DEFAULT_MT5_ROOT / "Files"
DEFAULT_MT5_INDICATORS_ROOT = DEFAULT_MT5_ROOT / "Indicators"
DEFAULT_MT5_INDICATORS_NESTED = DEFAULT_MT5_INDICATORS_ROOT / "Advisors" / "XAUUSD"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE126B",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE126B",
    "NO_EA_REPLACEMENT",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

RULE8_INDICATOR = r'''
//+------------------------------------------------------------------+
//| XAUUSD Stage124F Rule8 Overlay Indicator                         |
//| Same-chart visual overlay. No trade calls.                       |
//+------------------------------------------------------------------+
#property strict
#property indicator_chart_window
#property indicator_plots 0

input string InpKvFile = "xauusd_stage124f_rule8_overlay_kv.csv";
input int    InpTimerSeconds = 20;
input int    InpCorner = CORNER_LEFT_UPPER;
input int    InpX = 12;
input int    InpY = 360;
input int    InpLineHeight = 16;
input color  InpTextColor = clrDeepSkyBlue;
input int    InpFontSize = 9;
input string InpFont = "Arial";

string PREFIX = "XAUUSD_STAGE124F_RULE8_OVERLAY_";

string TrimBoth(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

void DeleteOverlay()
{
   long chart = ChartID();
   for(int i = 0; i < 12; ++i)
      ObjectDelete(chart, PREFIX + IntegerToString(i));
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
   ResetLastError();
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
      PutLabel(0, "08. Stage124 SPDR rule | waiting for status CSV | NO ORDER");
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
   PutLabel(3, "Stage125 selected=" + disc + " | keep 7-rule EA running; indicator only");

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

RULE9_INDICATOR = r'''
//+------------------------------------------------------------------+
//| XAUUSD Stage126 Rule9 Frontier Overlay Indicator                 |
//| Status-only indicator. No trading functions.                     |
//+------------------------------------------------------------------+
#property strict
#property indicator_chart_window
#property indicator_plots 0

input string InpStatusFile = "xauusd_stage126_rule9_frontier_status_kv.csv";
input int    InpTimerSeconds = 20;
input int    InpCorner = CORNER_LEFT_UPPER;
input int    InpX = 12;
input int    InpY = 450;
input int    InpLineHeight = 16;
input color  InpColor = clrGold;
input int    InpFontSize = 9;
input string InpFont = "Arial";

string PREFIX = "XAUUSD_STAGE126_RULE9_FRONTIER_OVERLAY_";

string Trim(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

void DeleteOverlay()
{
   long chart = ChartID();
   for(int i = 0; i < 12; ++i)
      ObjectDelete(chart, PREFIX + IntegerToString(i));
}

string GetValue(string &keys[], string &vals[], int n, string key, string fallback="")
{
   for(int i=0; i<n; i++)
      if(keys[i] == key)
         return vals[i];
   return fallback;
}

int ReadKv(string &keys[], string &vals[])
{
   ArrayResize(keys, 0);
   ArrayResize(vals, 0);
   ResetLastError();
   int h = FileOpen(InpStatusFile, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
      return -1;
   int n = 0;
   while(!FileIsEnding(h))
   {
      string k = Trim(FileReadString(h));
      if(FileIsEnding(h) && StringLen(k) == 0) break;
      string v = "";
      if(!FileIsLineEnding(h))
         v = Trim(FileReadString(h));
      while(!FileIsLineEnding(h) && !FileIsEnding(h))
         FileReadString(h);
      if(k == "") continue;
      ArrayResize(keys, n + 1);
      ArrayResize(vals, n + 1);
      keys[n] = k;
      vals[n] = v;
      n++;
   }
   FileClose(h);
   return n;
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
   ObjectSetInteger(chart, name, OBJPROP_COLOR, InpColor);
   ObjectSetInteger(chart, name, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetString(chart, name, OBJPROP_FONT, InpFont);
   ObjectSetString(chart, name, OBJPROP_TEXT, text);
}

void RefreshOverlay()
{
   string keys[], vals[];
   int n = ReadKv(keys, vals);
   DeleteOverlay();
   if(n < 0)
   {
      PutLabel(0, "09. Stage126 frontier | waiting for status CSV | NO ORDER");
      PutLabel(1, "file=" + InpStatusFile + " err=" + IntegerToString(GetLastError()));
      Print("Stage126 status CSV not readable yet. Trading remains disabled.");
      return;
   }

   string rule = GetValue(keys, vals, n, "rule_id", "S126_RULE9");
   string st = GetValue(keys, vals, n, "candidate_status", GetValue(keys, vals, n, "rule_status", "UNKNOWN"));
   string allow = GetValue(keys, vals, n, "allow_trading", "false");
   string cmean = GetValue(keys, vals, n, "cost10_mean_bps", "");
   string chit = GetValue(keys, vals, n, "cost10_hit_rate", "");
   string tail = GetValue(keys, vals, n, "tail_cost10_mean_bps", "");
   string nonov = GetValue(keys, vals, n, "nonoverlap_events_h120", "");
   string reasons = GetValue(keys, vals, n, "reasons", "");

   PutLabel(0, "09. Stage126 frontier shadow | " + st + " | allow_trading=" + allow + " | NO ORDER");
   PutLabel(1, rule);
   PutLabel(2, "cost10=" + cmean + "bps | hit=" + chit + " | tail=" + tail + "bps | nonoverlap=" + nonov);
   PutLabel(3, "reasons=" + reasons);
   Print("Stage126 Rule9 status read complete. kv_count=", n, " status=", st, " allow_trading=", allow, " cost10_mean_bps=", cmean, ". No orders are sent.");
}

int OnInit()
{
   EventSetTimer(MathMax(5, InpTimerSeconds));
   Print("Stage126 Rule9FrontierOverlay initialized. File=", InpStatusFile, " Status-only; no orders.");
   RefreshOverlay();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteOverlay();
   Print("Stage126 Rule9FrontierOverlay deinitialized. reason=", reason);
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
   return(rates_total);
}
'''.strip() + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_indicator_pair(target_dir: Path) -> Dict[str, str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    r8 = target_dir / "XAUUSD_Stage124F_Rule8OverlayIndicator.mq5"
    r9 = target_dir / "XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5"
    safe_write(r8, RULE8_INDICATOR)
    safe_write(r9, RULE9_INDICATOR)
    return {"rule8": str(r8), "rule9": str(r9)}


def run(root: Path, mt5_files: Path, mt5_indicators_root: Path, mt5_indicators_nested: Path, write_mt5: bool) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    out_dir = root / "reports" / "stage126b_indicator_visibility_and_overlay_layout_hotfix"
    out_dir.mkdir(parents=True, exist_ok=True)

    repo_paths = write_indicator_pair(root / "mql5" / "Indicators")
    report_paths = write_indicator_pair(out_dir / "mql5" / "Indicators")

    mt5_root_paths: Dict[str, str] = {}
    mt5_nested_paths: Dict[str, str] = {}
    if write_mt5:
        mt5_root_paths = write_indicator_pair(mt5_indicators_root.expanduser())
        mt5_nested_paths = write_indicator_pair(mt5_indicators_nested.expanduser())

    rule8_file = mt5_files.expanduser() / "xauusd_stage124f_rule8_overlay_kv.csv"
    rule9_file = mt5_files.expanduser() / "xauusd_stage126_rule9_frontier_status_kv.csv"

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS_OK,
        "decision": DECISION_OK,
        "classification": "INDICATOR_VISIBILITY_AND_LAYOUT_HOTFIX_ONLY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "repo_rule8_indicator": repo_paths["rule8"],
        "repo_rule9_indicator": repo_paths["rule9"],
        "report_rule8_indicator": report_paths["rule8"],
        "report_rule9_indicator": report_paths["rule9"],
        "mt5_indicators_written": bool(write_mt5),
        "mt5_root_rule8_indicator": mt5_root_paths.get("rule8", ""),
        "mt5_root_rule9_indicator": mt5_root_paths.get("rule9", ""),
        "mt5_nested_rule8_indicator": mt5_nested_paths.get("rule8", ""),
        "mt5_nested_rule9_indicator": mt5_nested_paths.get("rule9", ""),
        "rule8_default_y": 360,
        "rule9_default_y": 450,
        "rule8_status_file_expected": str(rule8_file),
        "rule9_status_file_expected": str(rule9_file),
        "rule8_status_file_exists": rule8_file.exists(),
        "rule9_status_file_exists": rule9_file.exists(),
        "mt5_usage": [
            "Keep Unified_ObserverOnly_EA on the chart.",
            "Remove Stage124E EA from the chart.",
            "Compile XAUUSD_Stage124F_Rule8OverlayIndicator.mq5 and attach it as an indicator.",
            "Compile XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5 and attach it as an indicator.",
            "If an indicator is not visible in Navigator, open the .mq5 from the written MT5 root/nested path in MetaEditor, compile it, then refresh Navigator."
        ],
    }
    safe_write(out_dir / "stage126b_indicator_visibility_and_overlay_layout_hotfix_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
    safe_write(out_dir / "stage126b_indicator_visibility_and_overlay_layout_hotfix_report.md", f"# {STAGE}\n\nStatus: {STATUS_OK}\nDecision: {DECISION_OK}\n\nRule8 default Y=360, Rule9 default Y=450. Indicator-only; no order surface.\n")
    print(json.dumps({"status": summary["status"], "rule8_status_file_exists": summary["rule8_status_file_exists"], "rule9_status_file_exists": summary["rule9_status_file_exists"], "mt5_indicators_written": summary["mt5_indicators_written"]}, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    ap.add_argument("--mt5-indicators-root", default=str(DEFAULT_MT5_INDICATORS_ROOT))
    ap.add_argument("--mt5-indicators-nested", default=str(DEFAULT_MT5_INDICATORS_NESTED))
    ap.add_argument("--write-mt5-indicators", action="store_true")
    args = ap.parse_args()
    run(Path(args.root), Path(args.mt5_files), Path(args.mt5_indicators_root), Path(args.mt5_indicators_nested), args.write_mt5_indicators)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
