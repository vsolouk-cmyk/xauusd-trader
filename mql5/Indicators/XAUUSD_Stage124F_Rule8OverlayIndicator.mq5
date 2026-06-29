//+------------------------------------------------------------------+
//| XAUUSD Stage124F Rule8 Overlay Indicator                         |
//| Fixed-pixel bottom-left dashboard. No trade calls.               |
//+------------------------------------------------------------------+
#property strict
#property indicator_chart_window
#property indicator_plots 0

input string InpKvFile = "xauusd_stage124f_rule8_overlay_kv.csv";
input int    InpTimerSeconds = 20;
input int    InpCorner = CORNER_LEFT_LOWER;
input int    InpX = 10;
input int    InpY = 230;
input int    InpLineHeight = 20;
input color  InpTextColor = clrDeepSkyBlue;
input int    InpFontSize = 5;
input string InpFont = "Arial";
input bool   InpBottomAnchored = true;

string PREFIX = "XAUUSD_STAGE124F_RULE8_OVERLAY_";
int LINE_COUNT = 4;

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

int YDistanceForLine(int idx)
{
   if(InpBottomAnchored)
      return InpY + (LINE_COUNT - 1 - idx) * InpLineHeight;
   return InpY + idx * InpLineHeight;
}

void DeleteOverlay()
{
   long chart = ChartID();
   for(int i = 0; i < 20; ++i)
      ObjectDelete(chart, PREFIX + IntegerToString(i));
}

void PutLabel(int idx, string text)
{
   long chart = ChartID();
   string name = PREFIX + IntegerToString(idx);
   if(ObjectFind(chart, name) < 0)
      ObjectCreate(chart, name, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(chart, name, OBJPROP_CORNER, InpCorner);
   ObjectSetInteger(chart, name, OBJPROP_ANCHOR, InpBottomAnchored ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
   ObjectSetInteger(chart, name, OBJPROP_XDISTANCE, InpX);
   ObjectSetInteger(chart, name, OBJPROP_YDISTANCE, YDistanceForLine(idx));
   ObjectSetInteger(chart, name, OBJPROP_COLOR, InpTextColor);
   ObjectSetInteger(chart, name, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetInteger(chart, name, OBJPROP_BACK, false);
   ObjectSetInteger(chart, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(chart, name, OBJPROP_SELECTED, false);
   ObjectSetInteger(chart, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(chart, name, OBJPROP_ZORDER, 1000);
   ObjectSetString(chart, name, OBJPROP_FONT, InpFont);
   ObjectSetString(chart, name, OBJPROP_TEXT, text);
}

void RefreshOverlay(bool verbose=true)
{
   string keys[], vals[], fmt;
   int cnt = ReadKvFlexible(InpKvFile, keys, vals, fmt);
   DeleteOverlay();
   if(cnt < 0)
   {
      PutLabel(0, "08. Stage124 SPDR | waiting for CSV | NO ORDER");
      PutLabel(1, "file=" + InpKvFile + " err=" + IntegerToString(GetLastError()));
      PutLabel(2, "bottom-anchored overlay; 7-rule EA stays active");
      PutLabel(3, "");
      return;
   }

   string rid = GetValue(keys, vals, "rule_id", "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN");
   string status = GetValue(keys, vals, "rule_status", GetValue(keys, vals, "status", "UNKNOWN"));
   string allow = GetValue(keys, vals, "allow_trading", "false");
   string cost = GetValue(keys, vals, "cost10_mean_bps", "");
   string hit = GetValue(keys, vals, "cost10_hit_rate", "");
   string last = GetValue(keys, vals, "last_signal_time_utc", "");
   string disc = GetValue(keys, vals, "selected_for_stage125_count", "0");

   PutLabel(0, "08 Stage124 SPDR | " + status + " | allow=" + allow + " | NO ORDER");
   PutLabel(1, "rule=" + rid);
   PutLabel(2, "cost10=" + cost + "bps | hit=" + hit + " | last=" + last);
   PutLabel(3, "Stage125 selected=" + disc + " | fmt=" + fmt + " | indicator only");

   if(verbose)
      Print("Stage124F fixed dashboard read complete. kv_count=", cnt,
            " format=", fmt,
            " status=", status,
            " allow_trading=", allow,
            " cost10_mean_bps=", cost,
            " cost10_hit_rate=", hit,
            " Trading remains disabled. No orders are sent.");
}

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "Stage124F Rule8 Fixed Dashboard NO ORDER");
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("Stage124F fixed dashboard initialized. File=", InpKvFile,
         " Indicator overlay only; keep the 7-rule EA running. This indicator cannot send orders.");
   RefreshOverlay(true);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteOverlay();
   Print("Stage124F fixed dashboard deinitialized. reason=", reason);
}

void OnTimer() { RefreshOverlay(true); }

void OnChartEvent(const int id,
                  const long &lparam,
                  const double &dparam,
                  const string &sparam)
{
   if(id == CHARTEVENT_CHART_CHANGE)
      RefreshOverlay(false);
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
