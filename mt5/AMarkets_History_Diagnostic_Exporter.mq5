#property copyright "XAUUSD project"
#property version   "1.00"
#property strict
#property script_show_inputs

input string          InpSymbol                     = "XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe                  = PERIOD_H1;
input datetime        InpStartDate                  = D'2011.01.01 00:00';
input datetime        InpEndDate                    = 0;
input int             InpChunkDays                  = 0;
input int             InpMaxAttemptsPerChunk        = 45;
input int             InpSleepMilliseconds          = 1000;
input bool            InpClampStartToServerHistory  = true;
input bool            InpExportCsv                  = true;
input string          InpOutputDirectory            = "XAUUSD_HISTORY_EXPORT";

string g_symbol;
ENUM_TIMEFRAMES g_tf;
int g_digits=2;
int g_last_error=0;
string g_last_error_name="ERR_SUCCESS";
long g_server_first=0;
long g_terminal_first=0;
long g_series_first=0;
long g_series_last=0;
long g_total_rows=0;
long g_duplicate_rows_skipped=0;
datetime g_effective_start=0;
datetime g_effective_end=0;
string g_csv_final="";
string g_csv_temp="";
string g_diag_file="";

string ErrorName(const int code)
  {
   switch(code)
     {
      case 0:    return "ERR_SUCCESS";
      case 4004: return "ERR_NOT_ENOUGH_MEMORY";
      case 4301: return "ERR_MARKET_UNKNOWN_SYMBOL";
      case 4302: return "ERR_MARKET_NOT_SELECTED";
      case 4305: return "ERR_MARKET_SELECT_ERROR";
      case 4306: return "ERR_MARKET_SELECT_LIMIT";
      case 4401: return "ERR_HISTORY_NOT_FOUND";
      case 4402: return "ERR_HISTORY_WRONG_PROPERTY";
      case 4403: return "ERR_HISTORY_TIMEOUT";
      case 4404: return "ERR_HISTORY_BARS_LIMIT";
      case 4405: return "ERR_HISTORY_LOAD_ERRORS";
      case 4407: return "ERR_HISTORY_SMALL_BUFFER";
      default:   return "ERR_"+IntegerToString(code);
     }
  }

string TfCode(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return "1m";
      case PERIOD_M2:  return "2m";
      case PERIOD_M3:  return "3m";
      case PERIOD_M4:  return "4m";
      case PERIOD_M5:  return "5m";
      case PERIOD_M6:  return "6m";
      case PERIOD_M10: return "10m";
      case PERIOD_M12: return "12m";
      case PERIOD_M15: return "15m";
      case PERIOD_M20: return "20m";
      case PERIOD_M30: return "30m";
      case PERIOD_H1:  return "1h";
      case PERIOD_H2:  return "2h";
      case PERIOD_H3:  return "3h";
      case PERIOD_H4:  return "4h";
      case PERIOD_H6:  return "6h";
      case PERIOD_H8:  return "8h";
      case PERIOD_H12: return "12h";
      case PERIOD_D1:  return "1d";
      case PERIOD_W1:  return "1w";
      case PERIOD_MN1: return "1mn";
      default:
        {
         string value=EnumToString(tf);
         StringToLower(value);
         return value;
        }
     }
  }

int DefaultChunkDays(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return 7;
      case PERIOD_M2:
      case PERIOD_M3:
      case PERIOD_M4:
      case PERIOD_M5:  return 31;
      case PERIOD_M6:
      case PERIOD_M10:
      case PERIOD_M12:
      case PERIOD_M15: return 92;
      case PERIOD_M20:
      case PERIOD_M30: return 184;
      case PERIOD_H1:
      case PERIOD_H2:
      case PERIOD_H3:
      case PERIOD_H4:  return 366;
      default:         return 3660;
     }
  }

string Dt(const datetime value)
  {
   if(value<=0)
      return "0";
   return TimeToString(value,TIME_DATE|TIME_SECONDS);
  }

string SafeSymbolName(string value)
  {
   StringToLower(value);
   StringReplace(value,".","_");
   StringReplace(value,"/","_");
   StringReplace(value,"\\","_");
   StringReplace(value," ","_");
   return value;
  }

void SetLastErrorInfo(const int code)
  {
   g_last_error=code;
   g_last_error_name=ErrorName(code);
  }

void PrintState(const string prefix)
  {
   long synchronized=SeriesInfoInteger(g_symbol,g_tf,SERIES_SYNCHRONIZED);
   long bars_count=SeriesInfoInteger(g_symbol,g_tf,SERIES_BARS_COUNT);
   long first_date=SeriesInfoInteger(g_symbol,g_tf,SERIES_FIRSTDATE);
   long last_date=SeriesInfoInteger(g_symbol,g_tf,SERIES_LASTBAR_DATE);
   long terminal_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_TERMINAL_FIRSTDATE);
   long server_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_SERVER_FIRSTDATE);

   PrintFormat("[AMARKETS_HISTORY][%s] symbol=%s tf=%s connected=%s synchronized=%s bars=%I64d server_first=%s terminal_first=%s series_first=%s series_last=%s terminal_maxbars=%I64d",
               prefix,
               g_symbol,
               TfCode(g_tf),
               (TerminalInfoInteger(TERMINAL_CONNECTED)?"true":"false"),
               (synchronized?"true":"false"),
               bars_count,
               Dt((datetime)server_first),
               Dt((datetime)terminal_first),
               Dt((datetime)first_date),
               Dt((datetime)last_date),
               TerminalInfoInteger(TERMINAL_MAXBARS));
  }

bool ProbeRecentHistory(const datetime end_time)
  {
   MqlRates probe[];
   ArraySetAsSeries(probe,false);
   datetime start_time=end_time-(datetime)(7*86400);

   for(int attempt=1;attempt<=10 && !IsStopped();attempt++)
     {
      ResetLastError();
      int copied=CopyRates(g_symbol,g_tf,start_time,end_time,probe);
      int err=GetLastError();
      SetLastErrorInfo(err);
      bool synchronized=(bool)SeriesInfoInteger(g_symbol,g_tf,SERIES_SYNCHRONIZED);
      PrintFormat("[AMARKETS_HISTORY][PROBE] attempt=%d/10 copied=%d error=%d(%s) synchronized=%s",
                  attempt,copied,err,ErrorName(err),(synchronized?"true":"false"));
      if(copied>0 && synchronized)
         return true;
      Sleep(1000);
     }
   return false;
  }

int RequestChunk(const datetime from_time,const datetime to_time,MqlRates &rates[])
  {
   ArrayFree(rates);
   ArraySetAsSeries(rates,false);

   int previous_copied=-999999;
   int stable_successes=0;
   int last_copied=-1;

   for(int attempt=1;attempt<=InpMaxAttemptsPerChunk && !IsStopped();attempt++)
     {
      ResetLastError();
      int copied=CopyRates(g_symbol,g_tf,from_time,to_time,rates);
      int err=GetLastError();
      SetLastErrorInfo(err);
      bool synchronized=(bool)SeriesInfoInteger(g_symbol,g_tf,SERIES_SYNCHRONIZED);
      int known_bars=Bars(g_symbol,g_tf,from_time,to_time);

      PrintFormat("[AMARKETS_HISTORY][REQUEST] tf=%s range=%s -> %s attempt=%d/%d copied=%d known_bars=%d synchronized=%s error=%d(%s)",
                  TfCode(g_tf),Dt(from_time),Dt(to_time),attempt,InpMaxAttemptsPerChunk,copied,known_bars,
                  (synchronized?"true":"false"),err,ErrorName(err));

      if(copied==0 && synchronized && known_bars==0)
         return 0;

      if(copied>0 && synchronized && known_bars>0 && copied>=known_bars)
         return copied;

      if(copied>0 && synchronized && copied==previous_copied)
         stable_successes++;
      else
         stable_successes=0;

      if(copied>0 && synchronized && stable_successes>=2)
         return copied;

      previous_copied=copied;
      last_copied=copied;
      Sleep(InpSleepMilliseconds);
     }

   return last_copied;
  }

void WriteDiagnostic(const string decision,const string detail)
  {
   int h=FileOpen(g_diag_file,FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h==INVALID_HANDLE)
     {
      PrintFormat("[AMARKETS_HISTORY][DIAGNOSTIC_WRITE_FAILED] path=%s error=%d(%s)",
                  g_diag_file,GetLastError(),ErrorName(GetLastError()));
      return;
     }

   string body="program=AMARKETS_HISTORY_DIAGNOSTIC_EXPORTER_V1\r\n";
   body+="decision="+decision+"\r\n";
   body+="detail="+detail+"\r\n";
   body+="symbol="+g_symbol+"\r\n";
   body+="timeframe="+TfCode(g_tf)+"\r\n";
   body+="terminal_connected="+(TerminalInfoInteger(TERMINAL_CONNECTED)?"true":"false")+"\r\n";
   body+="account_login="+IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN))+"\r\n";
   body+="account_server="+AccountInfoString(ACCOUNT_SERVER)+"\r\n";
   body+="account_company="+AccountInfoString(ACCOUNT_COMPANY)+"\r\n";
   body+="requested_start="+Dt(InpStartDate)+"\r\n";
   body+="effective_start="+Dt(g_effective_start)+"\r\n";
   body+="effective_end="+Dt(g_effective_end)+"\r\n";
   body+="server_first="+Dt((datetime)g_server_first)+"\r\n";
   body+="terminal_first="+Dt((datetime)g_terminal_first)+"\r\n";
   body+="series_first="+Dt((datetime)g_series_first)+"\r\n";
   body+="series_last="+Dt((datetime)g_series_last)+"\r\n";
   body+="series_synchronized="+(SeriesInfoInteger(g_symbol,g_tf,SERIES_SYNCHRONIZED)?"true":"false")+"\r\n";
   body+="terminal_maxbars="+IntegerToString((int)TerminalInfoInteger(TERMINAL_MAXBARS))+"\r\n";
   body+="rows_written="+IntegerToString((int)g_total_rows)+"\r\n";
   body+="duplicates_skipped="+IntegerToString((int)g_duplicate_rows_skipped)+"\r\n";
   body+="last_error="+IntegerToString(g_last_error)+"\r\n";
   body+="last_error_name="+g_last_error_name+"\r\n";
   body+="csv_file="+g_csv_final+"\r\n";
   body+="generated_server_time="+Dt(TimeTradeServer())+"\r\n";
   FileWriteString(h,body);
   FileClose(h);
  }

bool WriteRates(int handle,const MqlRates &rates[],datetime &last_written)
  {
   int count=ArraySize(rates);
   for(int i=0;i<count;i++)
     {
      if(rates[i].time<=last_written)
        {
         g_duplicate_rows_skipped++;
         continue;
        }

      string d=TimeToString(rates[i].time,TIME_DATE);
      string t=TimeToString(rates[i].time,TIME_MINUTES);
      uint bytes=FileWrite(handle,
                           d,
                           t,
                           DoubleToString(rates[i].open,g_digits),
                           DoubleToString(rates[i].high,g_digits),
                           DoubleToString(rates[i].low,g_digits),
                           DoubleToString(rates[i].close,g_digits),
                           (long)rates[i].tick_volume,
                           (int)rates[i].spread,
                           (long)rates[i].real_volume);
      if(bytes==0)
        {
         int err=GetLastError();
         SetLastErrorInfo(err);
         PrintFormat("[AMARKETS_HISTORY][WRITE_FAILED] time=%s error=%d(%s)",Dt(rates[i].time),err,ErrorName(err));
         return false;
        }
      last_written=rates[i].time;
      g_total_rows++;
     }
   return true;
  }

void OnStart()
  {
   g_symbol=InpSymbol;
   g_tf=InpTimeframe;
   g_effective_end=InpEndDate;
   if(g_effective_end<=0)
     {
      g_effective_end=TimeTradeServer();
      if(g_effective_end<=0)
         g_effective_end=TimeCurrent();
      if(g_effective_end<=0)
         g_effective_end=TimeLocal();
     }
   g_effective_start=InpStartDate;
   g_digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   if(g_digits<=0)
      g_digits=2;

   string base=SafeSymbolName(g_symbol)+"_"+TfCode(g_tf);
   g_csv_final=InpOutputDirectory+"\\amarkets_"+base+".csv";
   g_csv_temp=InpOutputDirectory+"\\amarkets_"+base+".csv.tmp";
   g_diag_file=InpOutputDirectory+"\\amarkets_"+base+"_diagnostic.txt";

   Print("[AMARKETS_HISTORY][START] program=AMARKETS_HISTORY_DIAGNOSTIC_EXPORTER_V1");
   PrintFormat("[AMARKETS_HISTORY][CONFIG] symbol=%s tf=%s start=%s end=%s export=%s output=%s",
               g_symbol,TfCode(g_tf),Dt(g_effective_start),Dt(g_effective_end),(InpExportCsv?"true":"false"),g_csv_final);

   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
     {
      SetLastErrorInfo(0);
      Print("[AMARKETS_HISTORY][FAIL] terminal is not connected to a trade server");
      WriteDiagnostic("FAIL_NOT_CONNECTED","Terminal is not connected to a trade server.");
      return;
     }

   ResetLastError();
   if(!SymbolSelect(g_symbol,true))
     {
      int err=GetLastError();
      SetLastErrorInfo(err);
      PrintFormat("[AMARKETS_HISTORY][FAIL] SymbolSelect failed error=%d(%s)",err,ErrorName(err));
      WriteDiagnostic("FAIL_SYMBOL_SELECT","Unable to select symbol in Market Watch.");
      return;
     }

   PrintState("BEFORE_PROBE");
   ProbeRecentHistory(g_effective_end);
   PrintState("AFTER_PROBE");

   g_server_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_SERVER_FIRSTDATE);
   g_terminal_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_TERMINAL_FIRSTDATE);
   g_series_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_FIRSTDATE);
   g_series_last=SeriesInfoInteger(g_symbol,g_tf,SERIES_LASTBAR_DATE);

   if(g_server_first<=0)
     {
      Print("[AMARKETS_HISTORY][FAIL] server first date is unknown after probe");
      WriteDiagnostic("FAIL_SERVER_HISTORY_UNKNOWN","SERIES_SERVER_FIRSTDATE remained zero after synchronization probe.");
      return;
     }

   if(g_effective_start<(datetime)g_server_first)
     {
      PrintFormat("[AMARKETS_HISTORY][SERVER_LIMIT] requested_start=%s is earlier than server_first=%s account_login=%I64d server=%s",
                  Dt(g_effective_start),Dt((datetime)g_server_first),AccountInfoInteger(ACCOUNT_LOGIN),AccountInfoString(ACCOUNT_SERVER));
      if(InpClampStartToServerHistory)
        {
         g_effective_start=(datetime)g_server_first;
         PrintFormat("[AMARKETS_HISTORY][CLAMP] effective_start=%s",Dt(g_effective_start));
        }
      else
        {
         WriteDiagnostic("FAIL_REQUEST_BEFORE_SERVER_HISTORY","Requested start precedes SERIES_SERVER_FIRSTDATE on the current account server.");
         return;
        }
     }

   if(g_effective_start>=g_effective_end)
     {
      WriteDiagnostic("FAIL_INVALID_RANGE","Effective start is not earlier than effective end.");
      return;
     }

   if(!InpExportCsv)
     {
      WriteDiagnostic("PASS_DIAGNOSTIC_ONLY","Server and terminal history properties were collected; CSV export was disabled.");
      Print("[AMARKETS_HISTORY][PASS] diagnostic-only run complete");
      return;
     }

   FileDelete(g_csv_temp);
   int handle=FileOpen(g_csv_temp,FILE_WRITE|FILE_CSV|FILE_ANSI,'\t');
   if(handle==INVALID_HANDLE)
     {
      int err=GetLastError();
      SetLastErrorInfo(err);
      PrintFormat("[AMARKETS_HISTORY][FAIL] FileOpen failed path=%s error=%d(%s)",g_csv_temp,err,ErrorName(err));
      WriteDiagnostic("FAIL_OUTPUT_OPEN","Unable to open temporary CSV in MQL5 Files sandbox.");
      return;
     }

   FileWrite(handle,"<DATE>","<TIME>","<OPEN>","<HIGH>","<LOW>","<CLOSE>","<TICKVOL>","<SPREAD>","<VOL>");

   int chunk_days=InpChunkDays;
   if(chunk_days<=0)
      chunk_days=DefaultChunkDays(g_tf);

   datetime cursor=g_effective_start;
   datetime last_written=0;
   int chunk_index=0;
   bool failed=false;
   string failure_detail="";

   while(cursor<=g_effective_end && !IsStopped())
     {
      chunk_index++;
      long chunk_seconds=(long)chunk_days*86400;
      datetime chunk_end=cursor+(datetime)chunk_seconds-1;
      if(chunk_end>g_effective_end || chunk_end<cursor)
         chunk_end=g_effective_end;

      MqlRates rates[];
      int copied=RequestChunk(cursor,chunk_end,rates);
      if(copied<0)
        {
         failed=true;
         failure_detail=StringFormat("Chunk request failed: %s -> %s error=%d(%s)",Dt(cursor),Dt(chunk_end),g_last_error,g_last_error_name);
         break;
        }

      if(copied>0 && !WriteRates(handle,rates,last_written))
        {
         failed=true;
         failure_detail=StringFormat("CSV write failed for chunk: %s -> %s",Dt(cursor),Dt(chunk_end));
         break;
        }

      FileFlush(handle);
      double pct=100.0*(double)(chunk_end-g_effective_start)/(double)(g_effective_end-g_effective_start);
      if(pct>100.0)
         pct=100.0;
      PrintFormat("[AMARKETS_HISTORY][PROGRESS] chunk=%d range=%s -> %s copied=%d total_rows=%I64d progress=%.2f%%",
                  chunk_index,Dt(cursor),Dt(chunk_end),copied,g_total_rows,pct);
      Comment(StringFormat("AMarkets history export\n%s %s\n%s -> %s\nrows=%I64d progress=%.2f%%",
                           g_symbol,TfCode(g_tf),Dt(g_effective_start),Dt(g_effective_end),g_total_rows,pct));

      if(chunk_end>=g_effective_end)
         break;
      cursor=chunk_end+1;
     }

   FileClose(handle);
   Comment("");

   if(IsStopped() && !failed)
     {
      failed=true;
      failure_detail="Script was stopped by the user before completion.";
     }

   if(failed)
     {
      FileDelete(g_csv_temp);
      PrintFormat("[AMARKETS_HISTORY][FAIL] %s",failure_detail);
      if(g_last_error==4404)
         Print("[AMARKETS_HISTORY][ACTION] Increase Tools -> Options -> Charts -> Max bars in chart, restart MT5, and retry.");
      if(g_last_error==4401)
         Print("[AMARKETS_HISTORY][ACTION] The current broker server does not provide the requested interval. Test the older AMarkets login/server.");
      if(g_last_error==4403 || g_last_error==4405)
         Print("[AMARKETS_HISTORY][ACTION] Check Journal connectivity/rates-base errors and retry on the same server or old account server.");
      WriteDiagnostic("FAIL_HISTORY_EXPORT",failure_detail);
      return;
     }

   FileDelete(g_csv_final);
   ResetLastError();
   if(!FileMove(g_csv_temp,0,g_csv_final,FILE_REWRITE))
     {
      int err=GetLastError();
      SetLastErrorInfo(err);
      PrintFormat("[AMARKETS_HISTORY][FAIL] atomic rename failed error=%d(%s)",err,ErrorName(err));
      WriteDiagnostic("FAIL_ATOMIC_RENAME","CSV was written but the temporary file could not be renamed atomically.");
      return;
     }

   g_series_first=SeriesInfoInteger(g_symbol,g_tf,SERIES_FIRSTDATE);
   g_series_last=SeriesInfoInteger(g_symbol,g_tf,SERIES_LASTBAR_DATE);
   WriteDiagnostic("PASS_HISTORY_EXPORT","History was requested in bounded chunks and exported successfully.");
   PrintFormat("[AMARKETS_HISTORY][PASS] output=%s rows=%I64d server_first=%s effective_start=%s last_error=%d(%s)",
               g_csv_final,g_total_rows,Dt((datetime)g_server_first),Dt(g_effective_start),g_last_error,g_last_error_name);
  }
