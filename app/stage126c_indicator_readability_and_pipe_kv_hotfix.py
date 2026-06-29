#!/usr/bin/env python3
"""Stage126C indicator readability and pipe-KV hotfix.

Writes updated Stage124F/Stage126 status-only indicators. The indicators are
layout-safe for the existing 7-rule EA chart status and read both comma KV and
pipe KV files. No EA, order, broker, CTrade, or OrderSend surface is changed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

STAGE = "Stage126C_INDICATOR_READABILITY_AND_PIPE_KV_HOTFIX"
STATUS_OK = "STAGE126C_COMPLETE_INDICATOR_READABILITY_PIPE_KV_HOTFIX_READY_NO_ORDER"
DECISION_OK = "STAGE126C_RULE8_RULE9_INDICATORS_READABLE_LAYOUT_FIXED_NO_ORDER"

DEFAULT_MT5_ROOT = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5")
DEFAULT_MT5_FILES = DEFAULT_MT5_ROOT / "Files"
DEFAULT_MT5_INDICATORS_ROOT = DEFAULT_MT5_ROOT / "Indicators"
DEFAULT_MT5_INDICATORS_NESTED = DEFAULT_MT5_INDICATORS_ROOT / "Advisors" / "XAUUSD"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE126C",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE126C",
    "NO_EA_REPLACEMENT",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

COMMON_MQL_HELPERS = r'''
string TrimBoth(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

int ReadKvDelimited(string fname, ushort delim, string &keys[], string &vals[])
{
   ArrayResize(keys, 0);
   ArrayResize(vals, 0);
   ResetLastError();
   int h = FileOpen(fname, FILE_READ | FILE_CSV | FILE_ANSI, delim);
   if(h == INVALID_HANDLE)
      return -1;

   int n = 0;
   while(!FileIsEnding(h))
   {
      string k = TrimBoth(FileReadString(h));
      if(FileIsEnding(h) && StringLen(k) == 0) break;
      string v = "";
      if(!FileIsLineEnding(h))
         v = TrimBoth(FileReadString(h));
      while(!FileIsLineEnding(h) && !FileIsEnding(h))
         FileReadString(h);
      if(StringLen(k) > 0)
      {
         ArrayResize(keys, n + 1);
         ArrayResize(vals, n + 1);
         keys[n] = k;
         vals[n] = v;
         n++;
      }
   }
   FileClose(h);
   return n;
}

bool HasUsefulValue(string &vals[])
{
   for(int i = 0; i < ArraySize(vals); ++i)
      if(StringLen(vals[i]) > 0)
         return true;
   return false;
}

int ReadKvFlexible(string fname, string &keys[], string &vals[], string &format_used)
{
   string pk[], pv[];
   int pn = ReadKvDelimited(fname, '|', pk, pv);
   if(pn > 0 && HasUsefulValue(pv))
   {
      ArrayResize(keys, pn);
      ArrayResize(vals, pn);
      for(int i=0; i<pn; ++i) { keys[i] = pk[i]; vals[i] = pv[i]; }
      format_used = "PIPE";
      return pn;
   }

   string ck[], cv[];
   int cn = ReadKvDelimited(fname, ',', ck, cv);
   if(cn > 0 && HasUsefulValue(cv))
   {
      ArrayResize(keys, cn);
      ArrayResize(vals, cn);
      for(int j=0; j<cn; ++j) { keys[j] = ck[j]; vals[j] = cv[j]; }
      format_used = "COMMA";
      return cn;
   }

   if(pn >= 0) { format_used = "PIPE_NO_VALUES"; return pn; }
   format_used = "READ_ERROR";
   return -1;
}

string GetValue(string &keys[], string &vals[], string key, string fallback="")
{
   for(int i = 0; i < ArraySize(keys); ++i)
      if(keys[i] == key)
         return vals[i];
   return fallback;
}
'''

RULE8_INDICATOR = (r'''
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
input int    InpY = 430;
input int    InpLineHeight = 22;
input color  InpTextColor = clrDeepSkyBlue;
input int    InpFontSize = 7;
input string InpFont = "Arial";

string PREFIX = "XAUUSD_STAGE124F_RULE8_OVERLAY_";
''' + COMMON_MQL_HELPERS + r'''

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

void RefreshOverlay()
{
   string keys[], vals[], fmt;
   int cnt = ReadKvFlexible(InpKvFile, keys, vals, fmt);
   DeleteOverlay();
   if(cnt < 0)
   {
      PutLabel(0, "08. Stage124 SPDR rule | waiting for status CSV | NO ORDER");
      PutLabel(1, "file=" + InpKvFile + " err=" + IntegerToString(GetLastError()));
      return;
   }

   string rid = GetValue(keys, vals, "rule_id", "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN");
   string status = GetValue(keys, vals, "rule_status", GetValue(keys, vals, "status", "UNKNOWN"));
   string allow = GetValue(keys, vals, "allow_trading", "false");
   string cost = GetValue(keys, vals, "cost10_mean_bps", "");
   string hit = GetValue(keys, vals, "cost10_hit_rate", "");
   string last = GetValue(keys, vals, "last_signal_time_utc", "");
   string disc = GetValue(keys, vals, "selected_for_stage125_count", "0");

   PutLabel(0, "08. Stage124 SPDR shadow | " + status + " | allow=" + allow + " | NO ORDER");
   PutLabel(1, "rule=" + rid);
   PutLabel(2, "cost10=" + cost + "bps | hit=" + hit + " | last=" + last);
   PutLabel(3, "Stage125 selected=" + disc + " | format=" + fmt + " | indicator only");

   Print("Stage124F rule8 overlay read complete. kv_count=", cnt,
         " format=", fmt,
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

void OnTimer() { RefreshOverlay(); }

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
''').strip() + "\n"

RULE9_INDICATOR = (r'''
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
input int    InpY = 540;
input int    InpLineHeight = 22;
input color  InpColor = clrGold;
input int    InpFontSize = 7;
input string InpFont = "Arial";

string PREFIX = "XAUUSD_STAGE126_RULE9_FRONTIER_OVERLAY_";
''' + COMMON_MQL_HELPERS + r'''

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
   ObjectSetInteger(chart, name, OBJPROP_COLOR, InpColor);
   ObjectSetInteger(chart, name, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetString(chart, name, OBJPROP_FONT, InpFont);
   ObjectSetString(chart, name, OBJPROP_TEXT, text);
}

void RefreshOverlay()
{
   string keys[], vals[], fmt;
   int n = ReadKvFlexible(InpStatusFile, keys, vals, fmt);
   DeleteOverlay();
   if(n < 0)
   {
      PutLabel(0, "09. Stage126 frontier | waiting for status CSV | NO ORDER");
      PutLabel(1, "file=" + InpStatusFile + " err=" + IntegerToString(GetLastError()));
      Print("Stage126 status CSV not readable yet. Trading remains disabled.");
      return;
   }

   string rule = GetValue(keys, vals, "rule_id", GetValue(keys, vals, "candidate_id", "S126_01_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP_SHADOW"));
   string st = GetValue(keys, vals, "candidate_status", GetValue(keys, vals, "rule_status", GetValue(keys, vals, "status", "UNKNOWN")));
   string allow = GetValue(keys, vals, "allow_trading", "false");
   string cmean = GetValue(keys, vals, "cost10_mean_bps", GetValue(keys, vals, "mean_bps", ""));
   string chit = GetValue(keys, vals, "cost10_hit_rate", GetValue(keys, vals, "hit_rate", ""));
   string tail = GetValue(keys, vals, "tail_cost10_mean_bps", "");
   string nonov = GetValue(keys, vals, "nonoverlap_events_h120", GetValue(keys, vals, "nonoverlap_events", ""));
   string reasons = GetValue(keys, vals, "reasons", GetValue(keys, vals, "missing_feature_keys", ""));

   PutLabel(0, "09. Stage126 VIX-dollar shadow | " + st + " | allow=" + allow + " | NO ORDER");
   PutLabel(1, "rule=" + rule);
   PutLabel(2, "cost10=" + cmean + "bps | hit=" + chit + " | tail=" + tail + "bps | nonoverlap=" + nonov);
   PutLabel(3, "reasons=" + reasons + " | format=" + fmt + " | indicator only");

   Print("Stage126 Rule9 status read complete. kv_count=", n,
         " format=", fmt,
         " status=", st,
         " allow_trading=", allow,
         " cost10_mean_bps=", cmean,
         ". No orders are sent.");
}

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "Stage126 Rule9 Frontier Overlay NO ORDER");
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

void OnTimer() { RefreshOverlay(); }

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
''').strip() + "\n"


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
    out_dir = root / "reports" / "stage126c_indicator_readability_and_pipe_kv_hotfix"
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
        "classification": "INDICATOR_READABILITY_AND_PIPE_KV_HOTFIX_ONLY_NO_ORDER",
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
        "rule8_default_y": 430,
        "rule9_default_y": 540,
        "font_size": 7,
        "line_height": 22,
        "kv_format_support": "PIPE_AND_COMMA",
        "rule8_status_file_expected": str(rule8_file),
        "rule9_status_file_expected": str(rule9_file),
        "rule8_status_file_exists": rule8_file.exists(),
        "rule9_status_file_exists": rule9_file.exists(),
        "mt5_usage": [
            "Keep Unified_ObserverOnly_EA on the chart.",
            "Attach/refresh XAUUSD_Stage124F_Rule8OverlayIndicator as an indicator.",
            "Attach/refresh XAUUSD_Stage126_Rule9FrontierOverlayIndicator as an indicator.",
            "Compile both indicators after this hotfix; they support pipe and comma KV status files.",
        ],
    }
    safe_write(out_dir / "stage126c_indicator_readability_and_pipe_kv_hotfix_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
    safe_write(out_dir / "stage126c_indicator_readability_and_pipe_kv_hotfix_report.md", f"# {STAGE}\n\nStatus: {STATUS_OK}\nDecision: {DECISION_OK}\n\nRule8 default Y=430, Rule9 default Y=540. Font size=7, line height=22. Pipe/comma KV support. Indicator-only; no order surface.\n")
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
