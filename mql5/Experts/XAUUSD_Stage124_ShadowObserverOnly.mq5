//+------------------------------------------------------------------+
//| XAUUSD Stage124C Shadow Observer Only EA                         |
//| Reports-only EA. No trade library and never sends orders.        |
//+------------------------------------------------------------------+
#property strict
#property version   "1.243"
#property description "Stage124C shadow observer only; no trading actions."

input string InpShadowCsvFile = "xauusd_stage124_shadow_observer_signal.csv";
input int    InpTimerSeconds = 60;
input bool   InpPrintAllKeys = false;

string g_rule_id = "";
string g_status = "";
string g_allow_trading = "";
string g_last_signal_time = "";
string g_cost10_mean_bps = "";
string g_cost10_hit_rate = "";
string g_combo_mode = "";

int OnInit()
{
   EventSetTimer(InpTimerSeconds);
   Print("Stage124C ShadowObserverOnly initialized. File=", InpShadowCsvFile,
         " Trading disabled by design. This EA does not send orders.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("Stage124C ShadowObserverOnly deinitialized. reason=", reason);
}

void OnTick()
{
   // Intentionally empty. Shadow observer runs on timer only and never trades.
}

void ResetState()
{
   g_rule_id = "";
   g_status = "";
   g_allow_trading = "";
   g_last_signal_time = "";
   g_cost10_mean_bps = "";
   g_cost10_hit_rate = "";
   g_combo_mode = "";
}

void CaptureKeyValue(const string key, const string value)
{
   if(key == "rule_id") g_rule_id = value;
   else if(key == "rule_status") g_status = value;
   else if(key == "allow_trading") g_allow_trading = value;
   else if(key == "last_signal_time_utc") g_last_signal_time = value;
   else if(key == "cost10_mean_bps") g_cost10_mean_bps = value;
   else if(key == "cost10_hit_rate") g_cost10_hit_rate = value;
   else if(key == "combo_integration_mode") g_combo_mode = value;
}

void OnTimer()
{
   int handle = FileOpen(InpShadowCsvFile, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Stage124C shadow key-value CSV not found in MQL5/Files: ", InpShadowCsvFile,
            " error=", GetLastError());
      return;
   }

   ResetState();
   int kv_count = 0;
   while(!FileIsEnding(handle))
   {
      string key = FileReadString(handle);
      if(FileIsEnding(handle) && key == "")
         break;
      string value = FileReadString(handle);
      if(key != "")
      {
         CaptureKeyValue(key, value);
         kv_count++;
         if(InpPrintAllKeys)
            Print("Stage124C shadow kv: ", key, "=", value);
      }
   }
   FileClose(handle);

   Print("Stage124C shadow CSV read complete. kv_count=", kv_count,
         " rule=", g_rule_id,
         " status=", g_status,
         " allow_trading=", g_allow_trading,
         " cost10_mean_bps=", g_cost10_mean_bps,
         " cost10_hit_rate=", g_cost10_hit_rate,
         " last_signal=", g_last_signal_time,
         " combo_mode=", g_combo_mode,
         ". Trading remains disabled.");
}
