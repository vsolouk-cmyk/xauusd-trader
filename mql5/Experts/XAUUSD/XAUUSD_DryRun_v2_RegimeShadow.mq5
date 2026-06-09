//+------------------------------------------------------------------+
//| XAUUSD_DryRun_v2_RegimeShadow.mq5                                |
//| Stage 8D forward-shadow logger only.                              |
//|                                                                  |
//| Hard rule: NO ORDER CODE. This EA logs candidate signals only.     |
//+------------------------------------------------------------------+
#property strict
#property version   "2.00"
#property description "XAUUSD Stage 8D dry-run logger: H4-up + compression + liquidity-session long candidate."

input string InpStrategyId = "xauusd_h4_up_compression_liquidity_long_v1";
input string InpCsvName = "XAUUSD_DryRun_v2_regime_shadow_signals.csv";
input double InpServerUtcOffsetHours = 2.0;
input int InpH4EmaFast = 20;
input int InpH4EmaSlow = 50;
input int InpH4SlopeBars = 5;
input int InpRangeWindowH1 = 16;
input int InpPercentileLookbackH1 = 240;
input double InpCompressionPctMin = 0.50;
input double InpCompressionPctMax = 0.80;
input int InpEntryHourUtcStartA = 13; // London-NY overlap start
input int InpEntryHourUtcEndA = 17;   // exclusive
input int InpEntryHourUtcStartB = 17; // New York start
input int InpEntryHourUtcEndB = 22;   // exclusive
input int InpTimeExitHours = 12;
input double InpEmergencyStopUsd = 30.0;
input bool InpPrintDebug = true;

datetime g_last_processed_h1_open = 0;

string IsoTime(datetime t)
{
   return TimeToString(t, TIME_DATE|TIME_MINUTES|TIME_SECONDS);
}

datetime ServerToUtc(datetime server_time)
{
   int seconds = (int)MathRound(InpServerUtcOffsetHours * 3600.0);
   return (datetime)(server_time - seconds);
}

string SessionUtc(datetime utc_time)
{
   MqlDateTime dt;
   TimeToStruct(utc_time, dt);
   int h = dt.hour;
   if(h >= 0 && h < 7) return "asia";
   if(h >= 7 && h < 13) return "london";
   if(h >= 13 && h < 17) return "london_ny_overlap";
   if(h >= 17 && h < 22) return "new_york";
   return "other";
}

bool IsAllowedLiquiditySession(datetime planned_entry_utc)
{
   MqlDateTime dt;
   TimeToStruct(planned_entry_utc, dt);
   int h = dt.hour;
   bool a = (h >= InpEntryHourUtcStartA && h < InpEntryHourUtcEndA);
   bool b = (h >= InpEntryHourUtcStartB && h < InpEntryHourUtcEndB);
   return (a || b);
}

bool GetEMA(const ENUM_TIMEFRAMES tf, const int period, const int shift, double &value)
{
   int handle = iMA(_Symbol, tf, period, 0, MODE_EMA, PRICE_CLOSE);
   if(handle == INVALID_HANDLE)
      return false;

   double buffer[];
   ArraySetAsSeries(buffer, true);
   int copied = CopyBuffer(handle, 0, shift, 1, buffer);
   IndicatorRelease(handle);

   if(copied != 1)
      return false;

   value = buffer[0];
   return true;
}

double H1RangeAtShift(const int shift, const int window)
{
   double hh = -DBL_MAX;
   double ll = DBL_MAX;

   for(int j = shift; j < shift + window; j++)
   {
      double h = iHigh(_Symbol, PERIOD_H1, j);
      double l = iLow(_Symbol, PERIOD_H1, j);
      if(h == 0.0 || l == 0.0)
         return -1.0;
      if(h > hh) hh = h;
      if(l < ll) ll = l;
   }
   return hh - ll;
}

bool CompressionPercentile(const int closed_h1_shift, double &range16, double &pct)
{
   int window = InpRangeWindowH1;
   int lookback = InpPercentileLookbackH1;

   range16 = H1RangeAtShift(closed_h1_shift, window);
   if(range16 < 0.0)
      return false;

   int valid = 0;
   int below_or_equal = 0;

   for(int k = closed_h1_shift + 1; k <= closed_h1_shift + lookback; k++)
   {
      double r = H1RangeAtShift(k, window);
      if(r < 0.0)
         continue;
      valid++;
      if(r <= range16)
         below_or_equal++;
   }

   if(valid < lookback * 0.80)
      return false;

   pct = (double)below_or_equal / (double)valid;
   return true;
}

bool H4TrendUp(double &h4_close, double &ema20, double &ema50, double &ema20_prev, double &slope)
{
   // Use last fully closed H4 bar.
   int shift = 1;
   h4_close = iClose(_Symbol, PERIOD_H4, shift);
   if(h4_close == 0.0)
      return false;

   if(!GetEMA(PERIOD_H4, InpH4EmaFast, shift, ema20))
      return false;
   if(!GetEMA(PERIOD_H4, InpH4EmaSlow, shift, ema50))
      return false;
   if(!GetEMA(PERIOD_H4, InpH4EmaFast, shift + InpH4SlopeBars, ema20_prev))
      return false;

   slope = ema20 - ema20_prev;
   return (h4_close > ema20 && ema20 > ema50 && slope > 0.0);
}

void EnsureHeader()
{
   int h = FileOpen(InpCsvName, FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
   {
      Print("Failed to open CSV for header: ", InpCsvName, " err=", GetLastError());
      return;
   }

   if(FileSize(h) == 0)
   {
      FileWrite(
         h,
         "tool_version",
         "strategy_id",
         "logged_at_gmt",
         "symbol",
         "signal_closed_h1_server",
         "signal_closed_h1_utc",
         "planned_entry_utc",
         "session_utc",
         "h1_close",
         "h4_close",
         "h4_ema20",
         "h4_ema50",
         "h4_ema20_slope_5",
         "h1_range16",
         "compression_pct",
         "direction",
         "entry_model",
         "exit_model",
         "time_exit_hours",
         "emergency_stop_usd",
         "dry_run_only"
      );
   }

   FileClose(h);
}

void LogSignal(
   datetime closed_h1_open_server,
   datetime signal_closed_h1_server,
   datetime signal_closed_h1_utc,
   datetime planned_entry_utc,
   string session,
   double h1_close,
   double h4_close,
   double h4_ema20,
   double h4_ema50,
   double h4_slope,
   double range16,
   double compression_pct
)
{
   EnsureHeader();

   int h = FileOpen(InpCsvName, FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
   {
      Print("Failed to open CSV for signal: ", InpCsvName, " err=", GetLastError());
      return;
   }

   FileSeek(h, 0, SEEK_END);

   FileWrite(
      h,
      "stage8d_v1",
      InpStrategyId,
      IsoTime(TimeGMT()),
      _Symbol,
      IsoTime(signal_closed_h1_server),
      IsoTime(signal_closed_h1_utc),
      IsoTime(planned_entry_utc),
      session,
      DoubleToString(h1_close, _Digits),
      DoubleToString(h4_close, _Digits),
      DoubleToString(h4_ema20, _Digits),
      DoubleToString(h4_ema50, _Digits),
      DoubleToString(h4_slope, _Digits),
      DoubleToString(range16, 4),
      DoubleToString(compression_pct, 6),
      "long",
      "next_h1_open_after_signal_close",
      "time_exit_12h_with_emergency_stop",
      IntegerToString(InpTimeExitHours),
      DoubleToString(InpEmergencyStopUsd, 2),
      "true"
   );

   FileClose(h);

   if(InpPrintDebug)
      Print("Stage8D dry-run signal logged: ", InpStrategyId, " closed_h1=", IsoTime(signal_closed_h1_utc), " entry=", IsoTime(planned_entry_utc), " session=", session);
}

int OnInit()
{
   Print("XAUUSD_DryRun_v2_RegimeShadow initialized. NO ORDER CODE. Symbol=", _Symbol);
   EnsureHeader();
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Work from last fully closed H1 bar.
   int closed_shift = 1;
   datetime closed_h1_open_server = iTime(_Symbol, PERIOD_H1, closed_shift);
   if(closed_h1_open_server == 0)
      return;

   if(closed_h1_open_server == g_last_processed_h1_open)
      return;

   g_last_processed_h1_open = closed_h1_open_server;

   datetime signal_closed_h1_server = (datetime)(closed_h1_open_server + 3600);
   datetime signal_closed_h1_utc = ServerToUtc(signal_closed_h1_server);
   datetime planned_entry_utc = signal_closed_h1_utc; // next H1 open equals closed H1 close time.

   string session = SessionUtc(planned_entry_utc);
   if(!IsAllowedLiquiditySession(planned_entry_utc))
   {
      if(InpPrintDebug)
         Print("Stage8D no signal: session not allowed: ", session, " entry_utc=", IsoTime(planned_entry_utc));
      return;
   }

   double h1_close = iClose(_Symbol, PERIOD_H1, closed_shift);
   if(h1_close == 0.0)
      return;

   double h4_close = 0.0, h4_ema20 = 0.0, h4_ema50 = 0.0, h4_ema20_prev = 0.0, h4_slope = 0.0;
   if(!H4TrendUp(h4_close, h4_ema20, h4_ema50, h4_ema20_prev, h4_slope))
   {
      if(InpPrintDebug)
         Print("Stage8D no signal: H4 trend up condition false.");
      return;
   }

   double range16 = 0.0, comp_pct = 0.0;
   if(!CompressionPercentile(closed_shift, range16, comp_pct))
   {
      if(InpPrintDebug)
         Print("Stage8D no signal: compression percentile unavailable.");
      return;
   }

   bool comp_mid_high = (comp_pct > InpCompressionPctMin && comp_pct <= InpCompressionPctMax);
   if(!comp_mid_high)
   {
      if(InpPrintDebug)
         Print("Stage8D no signal: compression pct not mid_high: ", DoubleToString(comp_pct, 6));
      return;
   }

   LogSignal(
      closed_h1_open_server,
      signal_closed_h1_server,
      signal_closed_h1_utc,
      planned_entry_utc,
      session,
      h1_close,
      h4_close,
      h4_ema20,
      h4_ema50,
      h4_slope,
      range16,
      comp_pct
   );
}
//+------------------------------------------------------------------+
