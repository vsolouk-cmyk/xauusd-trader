#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

STAGE = "Stage128B_COMPACT_DASHBOARD_INDICATOR_WRITE_HOTFIX"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators"
)

INDICATOR_NAME = "XAUUSD_Stage128_CompactShadowDashboardIndicator.mq5"

INDICATOR_CODE = r"""#property indicator_chart_window
#property indicator_plots 0
#property strict

input string InpStage128KvFile = "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv";
input int InpCorner = CORNER_RIGHT_LOWER;
input int InpX = 12;
input int InpY = 48;
input int InpFontSize = 6;
input int InpLineHeight = 16;
input color InpColor = clrSilver;
input int InpTimerSeconds = 20;

string PREFIX = "XAU_STAGE128_COMPACT_DASH_";

void DeleteObjects()
{
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, -1, -1);
      if(StringFind(name, PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

void DrawLine(int idx, string text, color c)
{
   string name = PREFIX + IntegerToString(idx);
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, InpCorner);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, InpX);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, InpY + idx * InpLineHeight);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
   ObjectSetInteger(0, name, OBJPROP_COLOR, c);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
}

string Trim(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

string GetKV(string &keys[], string &vals[], int n, string key)
{
   for(int i=0; i<n; i++)
      if(keys[i] == key) return vals[i];
   return "";
}

int ReadKV(string fileName, string &keys[], string &vals[])
{
   ArrayResize(keys, 0);
   ArrayResize(vals, 0);
   int h = FileOpen(fileName, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return -1;
   int n = 0;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      if(line == "") continue;
      int p = StringFind(line, "|");
      if(p < 0) p = StringFind(line, ",");
      if(p < 0) continue;
      string k = Trim(StringSubstr(line, 0, p));
      string v = Trim(StringSubstr(line, p + 1));
      ArrayResize(keys, n+1);
      ArrayResize(vals, n+1);
      keys[n] = k;
      vals[n] = v;
      n++;
   }
   FileClose(h);
   return n;
}

void Render()
{
   string keys[], vals[];
   int n = ReadKV(InpStage128KvFile, keys, vals);
   DeleteObjects();
   if(n < 0)
   {
      DrawLine(0, "Stage128 dashboard: KV file not found", clrTomato);
      return;
   }

   string decision = GetKV(keys, vals, n, "decision");
   string selected = GetKV(keys, vals, n, "selected_for_stage129_count");
   string watch = GetKV(keys, vals, n, "watch_or_reject_count");
   string rule8 = GetKV(keys, vals, n, "rule8_seen");
   string rule9 = GetKV(keys, vals, n, "rule9_seen");
   string s127 = GetKV(keys, vals, n, "stage127_status");
   string allow = GetKV(keys, vals, n, "allow_trading");

   DrawLine(0, "Stage128 shadow dashboard | NO ORDER", InpColor);
   DrawLine(1, "Rule8=" + rule8 + " | Rule9=" + rule9 + " | allow=" + allow, InpColor);
   DrawLine(2, "Stage127=" + s127, InpColor);
   DrawLine(3, "Selected129=" + selected + " | watch/reject=" + watch, (selected == "0" ? clrSilver : clrAqua));
   DrawLine(4, decision, InpColor);
}

int OnInit()
{
   EventSetTimer(MathMax(5, InpTimerSeconds));
   Render();
   Print("Stage128B CompactShadowDashboard initialized. No orders are sent.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteObjects();
   Print("Stage128B CompactShadowDashboard deinitialized. reason=", reason);
}

void OnTimer()
{
   Render();
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_CHART_CHANGE)
      Render();
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[],
                const double &close[], const long &tick_volume[], const long &volume[],
                const int &spread[])
{
   return(rates_total);
}
"""

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def write_text_atomic(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def write_kv_atomic(path: Path, kv: dict) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{v}\n")
    tmp.replace(path)

def read_stage128_summary(root: Path) -> dict:
    p = root / "reports/stage128_market_open_forward_shadow_and_frontier_megascan/stage128_market_open_forward_shadow_and_frontier_megascan_summary.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def install_indicator(root: Path, mt5_indicators: Path) -> list[str]:
    repo_path = root / "mql5/Indicators" / INDICATOR_NAME
    write_text_atomic(repo_path, INDICATOR_CODE)
    dests = [
        mt5_indicators / INDICATOR_NAME,
        mt5_indicators / "Advisors/XAUUSD" / INDICATOR_NAME,
    ]
    written = [str(repo_path)]
    for d in dests:
        write_text_atomic(d, INDICATOR_CODE)
        written.append(str(d))
    return written

def run(root: Path, mt5_files: Path, mt5_indicators: Path) -> dict:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()
    out_dir = ensure_dir(root / "reports/stage128b_compact_dashboard_indicator_write_hotfix")

    s = read_stage128_summary(root)
    kv = {
        "stage": STAGE,
        "generated_utc": now_utc(),
        "allow_trading": "false",
        "order_send": "false",
        "decision": s.get("decision", "STAGE128B_INDICATOR_HOTFIX_ONLY_NO_ORDER"),
        "selected_for_stage129_count": s.get("selected_for_stage129_count", 0),
        "watch_or_reject_count": s.get("watch_or_reject_count", 0),
        "rule8_seen": s.get("telemetry_health", {}).get("rule8_seen", ""),
        "rule9_seen": s.get("telemetry_health", {}).get("rule9_seen", ""),
        "stage127_status": "WATCH_FORWARD_SHADOW_DECONCENTRATION_REQUIRED",
        "runtime_mode": s.get("market_open_runtime_mode", ""),
    }
    repo_kv = root / "data/shadow_observer/stage128_forward_shadow_and_megascan_status_kv.csv"
    report_kv = out_dir / "stage128_forward_shadow_and_megascan_status_kv.csv"
    mt5_kv = mt5_files / "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv"
    write_kv_atomic(repo_kv, kv)
    write_kv_atomic(report_kv, kv)
    write_kv_atomic(mt5_kv, kv)

    written = install_indicator(root, mt5_indicators)

    summary = {
        "stage": STAGE,
        "generated_utc": now_utc(),
        "status": "STAGE128B_COMPLETE_INDICATOR_WRITTEN_NO_ORDER",
        "decision": "STAGE128B_COMPACT_DASHBOARD_INDICATOR_READY_NO_ORDER",
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_TRADE_REQUEST_FROM_STAGE128B",
            "NO_ORDER_SEND",
            "NO_CTRADE_USAGE",
            "NO_MT5_EA_CHANGE_FROM_STAGE128B",
            "NO_PAPER_LIVE",
            "NO_LIVE",
        ],
        "root": str(root),
        "mt5_status_kv": str(mt5_kv),
        "indicator_written": written,
        "summary_json": str(out_dir / "stage128b_compact_dashboard_indicator_write_hotfix_summary.json"),
        "next": [
            "Compile XAUUSD_Stage128_CompactShadowDashboardIndicator.mq5 in MetaEditor.",
            "Attach it only if a compact dashboard is useful; it is optional and no-order.",
            "Do not change Unified_ObserverOnly_EA trading logic."
        ]
    }
    write_text_atomic(out_dir / "stage128b_compact_dashboard_indicator_write_hotfix_summary.json", json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-indicators", default=DEFAULT_MT5_INDICATORS)
    args = ap.parse_args()
    run(Path(args.root), Path(args.mt5_files), Path(args.mt5_indicators))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
