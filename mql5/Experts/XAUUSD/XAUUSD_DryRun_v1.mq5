//+------------------------------------------------------------------+
//| XAUUSD_DryRun_v1.mq5                                             |
//| Stage 5A dry-run logger for XAUUSD locked candidate v1            |
//| HARD RULE: This EA never sends orders.                            |
//+------------------------------------------------------------------+
#property strict
#property version   "1.01"
#property description "XAUUSD dry-run signal logger. No order placement."

// If InpSymbol is AUTO or empty, the EA uses the chart symbol (_Symbol).
input string InpSymbol              = "AUTO";
input int    InpSmaWindow           = 10;
input double InpMinDistanceUSD      = 10.0;
input double InpTakeProfitUSD       = 24.0;
input double InpStopLossUSD         = 15.0;
input int    InpTimeExitH1Bars      = 12;
input bool   InpUseUTCSessionFilter = true;
input bool   InpPrintDebug          = true;
input bool   InpDryRunOnly          = true;

datetime g_lastProcessedClosedH1 = 0;
string   g_logFileName = "XAUUSD_DryRun_v1_signals.csv";
string   g_symbol = "";

string TrimString(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

string ResolveSymbol()
{
   string s = TrimString(InpSymbol);
   if(s == "" || s == "AUTO" || s == "auto" || s == "_Symbol")
      return _Symbol;
   return s;
}

string SessionNameUTC(const int hour_utc)
{
   if(hour_utc >= 0 && hour_utc < 7)   return "asia";
   if(hour_utc >= 7 && hour_utc < 13)  return "london";
   if(hour_utc >= 13 && hour_utc < 17) return "london_ny_overlap";
   if(hour_utc >= 17 && hour_utc < 22) return "new_york";
   return "other";
}

bool IsBlockedSessionUTC(const datetime current_gmt)
{
   MqlDateTime dt;
   TimeToStruct(current_gmt, dt);
   return (dt.hour >= 7 && dt.hour < 13);
}

bool EnsureSymbolReady(const string symbol)
{
   if(symbol == "" || symbol == NULL)
   {
      Print("ERROR: Empty symbol after resolution. Chart symbol=", _Symbol, " input=", InpSymbol);
      return false;
   }

   if(symbol == _Symbol)
   {
      if(InpPrintDebug)
         Print("Using chart symbol: ", symbol);
      return true;
   }

   if(!SymbolSelect(symbol, true))
   {
      Print("ERROR: Could not select symbol: ", symbol, " | chart symbol=", _Symbol, " | input=", InpSymbol, " | err=", GetLastError());
      Print("Fix: set InpSymbol=AUTO or set it exactly to the broker symbol shown in Market Watch.");
      return false;
   }

   if(InpPrintDebug)
      Print("Selected broker symbol: ", symbol);

   return true;
}

double SMAClosedBars(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int shift_start)
{
   if(period <= 0)
      return EMPTY_VALUE;

   double sum = 0.0;
   for(int i = shift_start; i < shift_start + period; i++)
   {
      double c = iClose(symbol, tf, i);
      if(c == 0.0)
         return EMPTY_VALUE;
      sum += c;
   }
   return sum / (double)period;
}

bool FileExistsInCommon(const string file_name)
{
   int h = FileOpen(file_name, FILE_READ | FILE_CSV | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return false;
   FileClose(h);
   return true;
}

void EnsureHeader()
{
   if(FileExistsInCommon(g_logFileName))
      return;

   int h = FileOpen(g_logFileName, FILE_WRITE | FILE_CSV | FILE_COMMON);
   if(h == INVALID_HANDLE)
   {
      Print("ERROR: Cannot create log file: ", g_logFileName, " err=", GetLastError());
      return;
   }

   FileWrite(
      h,
      "logged_at_gmt",
      "symbol",
      "chart_symbol",
      "strategy_id",
      "signal_closed_h1_time_server",
      "signal_closed_h1_time_gmt_now",
      "session_utc",
      "close_h1",
      "sma10",
      "distance_usd",
      "direction",
      "planned_entry_model",
      "tp_usd",
      "sl_usd",
      "time_exit_h1_bars",
      "dry_run_only"
   );

   FileClose(h);
}

void LogSignal(const string symbol, const datetime closed_bar_time, const double close_h1, const double sma10, const double distance)
{
   datetime now_gmt = TimeGMT();

   MqlDateTime dt;
   TimeToStruct(now_gmt, dt);
   string session = SessionNameUTC(dt.hour);

   int h = FileOpen(g_logFileName, FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON);
   if(h == INVALID_HANDLE)
   {
      Print("ERROR: Cannot open log file: ", g_logFileName, " err=", GetLastError());
      return;
   }

   FileSeek(h, 0, SEEK_END);

   FileWrite(
      h,
      TimeToString(now_gmt, TIME_DATE | TIME_SECONDS),
      symbol,
      _Symbol,
      "xauusd_long_tp24_sl15_no_london_v1",
      TimeToString(closed_bar_time, TIME_DATE | TIME_SECONDS),
      TimeToString(now_gmt, TIME_DATE | TIME_SECONDS),
      session,
      DoubleToString(close_h1, 5),
      DoubleToString(sma10, 5),
      DoubleToString(distance, 5),
      "long",
      "next_h1_open",
      DoubleToString(InpTakeProfitUSD, 2),
      DoubleToString(InpStopLossUSD, 2),
      IntegerToString(InpTimeExitH1Bars),
      "true"
   );

   FileClose(h);

   Print(
      "DRY-RUN SIGNAL logged | symbol=", symbol,
      " chart=", _Symbol,
      " close=", DoubleToString(close_h1, 5),
      " sma10=", DoubleToString(sma10, 5),
      " distance=", DoubleToString(distance, 5),
      " session=", session
   );
}

int OnInit()
{
   if(!InpDryRunOnly)
      Print("WARNING: InpDryRunOnly is false, but this EA contains no order code. It will still log only.");

   g_symbol = ResolveSymbol();

   if(!EnsureSymbolReady(g_symbol))
      return INIT_FAILED;

   EnsureHeader();

   Print("XAUUSD_DryRun_v1 initialized. HARD RULE: no order placement.");
   Print("Resolved symbol=", g_symbol, " | chart symbol=", _Symbol, " | input=", InpSymbol);
   Print("Log file in MT5 common files: ", g_logFileName);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Print("XAUUSD_DryRun_v1 deinitialized. reason=", reason);
}

void OnTick()
{
   const string symbol = g_symbol;
   const ENUM_TIMEFRAMES tf = PERIOD_H1;

   datetime closed_h1_time = iTime(symbol, tf, 1);
   if(closed_h1_time <= 0)
   {
      if(InpPrintDebug)
         Print("Dry-run waiting: no closed H1 data for symbol=", symbol);
      return;
   }

   if(closed_h1_time == g_lastProcessedClosedH1)
      return;

   g_lastProcessedClosedH1 = closed_h1_time;

   if(InpUseUTCSessionFilter && IsBlockedSessionUTC(TimeGMT()))
   {
      if(InpPrintDebug)
         Print("Dry-run skip: blocked UTC London session. closed_h1=", TimeToString(closed_h1_time, TIME_DATE | TIME_SECONDS));
      return;
   }

   double close_h1 = iClose(symbol, tf, 1);
   double sma10 = SMAClosedBars(symbol, tf, InpSmaWindow, 1);
   if(close_h1 == 0.0 || sma10 == EMPTY_VALUE)
   {
      Print("Dry-run skip: insufficient H1/SMA data for symbol=", symbol);
      return;
   }

   double distance = close_h1 - sma10;

   if(distance >= InpMinDistanceUSD)
   {
      LogSignal(symbol, closed_h1_time, close_h1, sma10, distance);
   }
   else
   {
      if(InpPrintDebug)
      {
         Print(
            "Dry-run no signal | symbol=", symbol,
            " close=", DoubleToString(close_h1, 5),
            " sma10=", DoubleToString(sma10, 5),
            " distance=", DoubleToString(distance, 5)
         );
      }
   }

   // No OrderSend, no CTrade, no trading functions anywhere in this EA.
}
//+------------------------------------------------------------------+
