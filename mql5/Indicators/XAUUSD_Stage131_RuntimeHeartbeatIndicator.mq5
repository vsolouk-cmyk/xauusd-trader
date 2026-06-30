#property indicator_chart_window
#property indicator_plots 0
#property strict

input int InpTimerSeconds = 60;
input string InpHeartbeatKvFile = "xauusd_stage131_runtime_heartbeat_kv.csv";
input string InpHeartbeatHistoryFile = "xauusd_stage131_runtime_heartbeat_history.csv";
input bool InpAppendHistory = true;

datetime g_last_write = 0;

string BoolText(bool v)
{
   return(v ? "true" : "false");
}

void WriteKV()
{
   int h = FileOpen(InpHeartbeatKvFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("Stage131 heartbeat KV FileOpen failed. file=", InpHeartbeatKvFile, " err=", GetLastError());
      return;
   }

   datetime tc = TimeCurrent();
   datetime ts = TimeTradeServer();
   string now_local = TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS);
   string now_current = TimeToString(tc, TIME_DATE|TIME_SECONDS);
   string now_server = TimeToString(ts, TIME_DATE|TIME_SECONDS);

   FileWriteString(h, "stage|Stage131_MT5_RUNTIME_HEARTBEAT_INDICATOR\n");
   FileWriteString(h, "status|HEARTBEAT_ALIVE_NO_ORDER\n");
   FileWriteString(h, "allow_trading|false\n");
   FileWriteString(h, "order_send|false\n");
   FileWriteString(h, "symbol|" + _Symbol + "\n");
   FileWriteString(h, "period|" + IntegerToString(_Period) + "\n");
   FileWriteString(h, "time_local|" + now_local + "\n");
   FileWriteString(h, "time_current|" + now_current + "\n");
   FileWriteString(h, "time_trade_server|" + now_server + "\n");
   FileWriteString(h, "terminal_trade_allowed|" + BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) + "\n");
   FileWriteString(h, "mql_trade_allowed|" + BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)) + "\n");
   FileWriteString(h, "account_trade_allowed|" + BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) + "\n");
   FileWriteString(h, "account_server|" + AccountInfoString(ACCOUNT_SERVER) + "\n");
   FileWriteString(h, "build|" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)) + "\n");
   FileWriteString(h, "note|telemetry_only_indicator_no_orders_no_ea_change\n");
   FileClose(h);

   if(InpAppendHistory)
   {
      bool exists = FileIsExist(InpHeartbeatHistoryFile);
      int hh = FileOpen(InpHeartbeatHistoryFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI);
      if(hh != INVALID_HANDLE)
      {
         if(!exists || FileSize(hh) == 0)
         {
            FileWrite(hh, "time_local", "time_current", "time_trade_server", "symbol", "period", "terminal_trade_allowed", "mql_trade_allowed", "account_trade_allowed", "note");
         }
         FileSeek(hh, 0, SEEK_END);
         FileWrite(hh, now_local, now_current, now_server, _Symbol, IntegerToString(_Period),
                   BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)),
                   BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED)),
                   BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)),
                   "telemetry_only_no_orders");
         FileClose(hh);
      }
      else
      {
         Print("Stage131 heartbeat history FileOpen failed. file=", InpHeartbeatHistoryFile, " err=", GetLastError());
      }
   }

   g_last_write = TimeLocal();
   Print("Stage131 heartbeat written. symbol=", _Symbol, " period=", _Period, " file=", InpHeartbeatKvFile, " No orders are sent.");
}

int OnInit()
{
   EventSetTimer(MathMax(10, InpTimerSeconds));
   WriteKV();
   Print("Stage131 RuntimeHeartbeatIndicator initialized. Telemetry only. No orders are sent.");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteKV();
   Print("Stage131 RuntimeHeartbeatIndicator deinitialized. reason=", reason, ". No orders were sent.");
}

void OnTimer()
{
   WriteKV();
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[],
                const double &open[], const double &high[], const double &low[],
                const double &close[], const long &tick_volume[], const long &volume[],
                const int &spread[])
{
   return(rates_total);
}
