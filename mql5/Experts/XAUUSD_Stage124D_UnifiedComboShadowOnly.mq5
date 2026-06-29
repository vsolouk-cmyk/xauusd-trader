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
