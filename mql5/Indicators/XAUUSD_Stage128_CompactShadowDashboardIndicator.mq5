#property indicator_chart_window
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
