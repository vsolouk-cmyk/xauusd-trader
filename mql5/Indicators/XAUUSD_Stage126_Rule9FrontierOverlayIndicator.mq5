//+------------------------------------------------------------------+
//| XAUUSD Stage126 Rule9 Frontier Overlay Indicator                 |
//| Fixed-pixel bottom-left dashboard. No trading functions.         |
//+------------------------------------------------------------------+
#property strict
#property indicator_chart_window
#property indicator_plots 0

input string InpStatusFile = "xauusd_stage126_rule9_frontier_status_kv.csv";
input int    InpTimerSeconds = 20;
input int    InpCorner = CORNER_LEFT_LOWER;
input int    InpX = 10;
input int    InpY = 110;
input int    InpLineHeight = 20;
input color  InpColor = clrGold;
input int    InpFontSize = 5;
input string InpFont = "Arial";
input bool   InpBottomAnchored = true;

string PREFIX = "XAUUSD_STAGE126_RULE9_FRONTIER_OVERLAY_";
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
   ObjectSetInteger(chart, name, OBJPROP_COLOR, InpColor);
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
   int n = ReadKvFlexible(InpStatusFile, keys, vals, fmt);
   DeleteOverlay();
   if(n < 0)
   {
      PutLabel(0, "09. Stage126 VIX-dollar | waiting for CSV | NO ORDER");
      PutLabel(1, "file=" + InpStatusFile + " err=" + IntegerToString(GetLastError()));
      PutLabel(2, "fixed bottom dashboard; indicator only");
      PutLabel(3, "");
      if(verbose) Print("Stage126 status CSV not readable yet. Trading remains disabled.");
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

   PutLabel(0, "09 Stage126 VIX-dollar | " + st + " | allow=" + allow + " | NO ORDER");
   PutLabel(1, "rule=" + rule);
   PutLabel(2, "cost10=" + cmean + "bps | hit=" + chit + " | tail=" + tail + "bps | nonov=" + nonov);
   PutLabel(3, "reasons=" + reasons + " | fmt=" + fmt + " | indicator only");

   if(verbose)
      Print("Stage126 fixed dashboard read complete. kv_count=", n,
            " format=", fmt,
            " status=", st,
            " allow_trading=", allow,
            " cost10_mean_bps=", cmean,
            ". No orders are sent.");
}

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "Stage126 Rule9 Fixed Dashboard NO ORDER");
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("Stage126 fixed dashboard initialized. File=", InpStatusFile, " Status-only; no orders.");
   RefreshOverlay(true);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteOverlay();
   Print("Stage126 fixed dashboard deinitialized. reason=", reason);
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
   return(rates_total);
}
