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
