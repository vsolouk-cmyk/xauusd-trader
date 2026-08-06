#property strict
#property script_show_inputs
#property version   "1.10"
#property description "Read-only XAUUSD cross-asset M15/H1 history exporter. No trading functions."

input string   InpOutputDirectory = "XAUUSD_CROSS_ASSET_HISTORY";
input datetime InpHistoryStart     = D'2016.01.01 00:00';
input int      InpChunkDays        = 120;
input int      InpSyncRetries      = 8;
input int      InpRetryDelayMs     = 500;
input int      InpPublishRetries   = 5;
input bool     InpRepairOnlyLateHistorySymbols = true;

const string PROGRAM = "XAUUSD_CROSS_ASSET_INTRADAY_PANEL_V1";
const int EXPECTED_COLUMNS = 12;

string SafeName(string value)
{
   StringReplace(value,"&","AND");
   StringReplace(value,".","_");
   StringReplace(value,"/","_");
   StringReplace(value,"\\","_");
   StringReplace(value," ","_");
   StringToLower(value);
   return value;
}

string TimeframeLabel(const ENUM_TIMEFRAMES timeframe)
{
   if(timeframe==PERIOD_M15) return "M15";
   if(timeframe==PERIOD_H1) return "H1";
   return "UNKNOWN";
}

int CountValidatedRows(const string path,const string symbol,const string timeframe)
{
   ResetLastError();
   int handle=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE,',');
   if(handle==INVALID_HANDLE)
   {
      Print("FAIL_EXPORT_VALIDATION_OPEN path=",path," error=",GetLastError());
      return -1;
   }

   int records=0;
   int columns=0;
   string first_field="";
   string row_symbol="";
   string row_timeframe="";

   while(!FileIsEnding(handle))
   {
      string value=FileReadString(handle);
      if(columns==0) first_field=value;
      if(columns==1) row_symbol=value;
      if(columns==2) row_timeframe=value;
      columns++;

      bool line_end=FileIsLineEnding(handle);
      bool file_end=FileIsEnding(handle);
      if(line_end || file_end)
      {
         if(first_field==PROGRAM && row_symbol==symbol && row_timeframe==timeframe && columns==EXPECTED_COLUMNS)
            records++;
         columns=0;
         first_field="";
         row_symbol="";
         row_timeframe="";
      }
   }

   FileClose(handle);
   return records;
}

bool EnsureSeries(const string symbol,const ENUM_TIMEFRAMES timeframe)
{
   MqlRates probe[];
   ArraySetAsSeries(probe,false);
   for(int attempt=0; attempt<InpSyncRetries; attempt++)
   {
      ResetLastError();
      int copied=CopyRates(symbol,timeframe,0,2,probe);
      long synchronized=0;
      SeriesInfoInteger(symbol,timeframe,SERIES_SYNCHRONIZED,synchronized);
      if(copied>0 && synchronized!=0)
         return true;
      Sleep(InpRetryDelayMs);
   }
   return false;
}


bool ResolveEffectiveHistoryStart(const string symbol,
                                  const ENUM_TIMEFRAMES timeframe,
                                  datetime &effective_start,
                                  datetime &series_first,
                                  datetime &server_first)
{
   long series_first_raw=0;
   long server_first_raw=0;

   ResetLastError();
   if(!SeriesInfoInteger(symbol,timeframe,SERIES_FIRSTDATE,series_first_raw) || series_first_raw<=0)
   {
      Print("FAIL_EXPORT_FIRST_DATE symbol=",symbol,
            " timeframe=",TimeframeLabel(timeframe),
            " property=SERIES_FIRSTDATE error=",GetLastError());
      return false;
   }

   ResetLastError();
   if(!SeriesInfoInteger(symbol,timeframe,SERIES_SERVER_FIRSTDATE,server_first_raw))
      server_first_raw=0;

   long start_raw=(long)InpHistoryStart;
   if(server_first_raw>start_raw) start_raw=server_first_raw;
   if(series_first_raw>start_raw) start_raw=series_first_raw;

   series_first=(datetime)series_first_raw;
   server_first=(datetime)server_first_raw;
   effective_start=(datetime)start_raw;

   if(effective_start<=0 || effective_start>TimeCurrent())
   {
      Print("FAIL_EXPORT_EFFECTIVE_START symbol=",symbol,
            " timeframe=",TimeframeLabel(timeframe),
            " requested=",TimeToString(InpHistoryStart,TIME_DATE|TIME_MINUTES),
            " series_first=",TimeToString(series_first,TIME_DATE|TIME_MINUTES),
            " server_first=",TimeToString(server_first,TIME_DATE|TIME_MINUTES),
            " effective=",TimeToString(effective_start,TIME_DATE|TIME_MINUTES));
      return false;
   }
   return true;
}

bool ExportSeries(const string symbol,const ENUM_TIMEFRAMES timeframe)
{
   string tf=TimeframeLabel(timeframe);
   if(tf=="UNKNOWN") return false;

   if(!SymbolSelect(symbol,true))
   {
      Print("FAIL_EXPORT_SYMBOL_SELECT symbol=",symbol," error=",GetLastError());
      return false;
   }
   if(!EnsureSeries(symbol,timeframe))
   {
      Print("FAIL_EXPORT_SERIES_SYNC symbol=",symbol," timeframe=",tf," error=",GetLastError());
      return false;
   }

   FolderCreate(InpOutputDirectory);
   string base=SafeName(symbol)+"__"+SafeName(tf);
   string canonical=InpOutputDirectory+"\\"+base+".csv";
   string snapshot=InpOutputDirectory+"\\"+base+"_"+
                   IntegerToString((long)TimeLocal())+"_"+
                   IntegerToString((long)GetTickCount64())+".csv";

   ResetLastError();
   int handle=FileOpen(snapshot,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');
   if(handle==INVALID_HANDLE)
   {
      Print("FAIL_EXPORT_FILE_OPEN path=",snapshot," error=",GetLastError());
      return false;
   }

   uint header_bytes=FileWrite(handle,
      "program","symbol","timeframe","time_server_epoch","open","high","low","close",
      "tick_volume","spread","real_volume","source");
   if(header_bytes==0)
   {
      int error=GetLastError();
      FileClose(handle);
      Print("FAIL_EXPORT_HEADER_WRITE path=",snapshot," error=",error);
      return false;
   }

   datetime now=TimeCurrent();
   datetime cursor=0;
   datetime series_first=0;
   datetime server_first=0;
   if(!ResolveEffectiveHistoryStart(symbol,timeframe,cursor,series_first,server_first))
   {
      FileClose(handle);
      FileDelete(snapshot);
      return false;
   }

   Print("INFO_EXPORT_EFFECTIVE_START symbol=",symbol,
         " timeframe=",tf,
         " requested=",TimeToString(InpHistoryStart,TIME_DATE|TIME_MINUTES),
         " series_first=",TimeToString(series_first,TIME_DATE|TIME_MINUTES),
         " server_first=",TimeToString(server_first,TIME_DATE|TIME_MINUTES),
         " effective=",TimeToString(cursor,TIME_DATE|TIME_MINUTES));

   long last_written=0;
   int written=0;
   int failures=0;
   int chunk_seconds=MathMax(1,InpChunkDays)*86400;

   while(cursor<=now)
   {
      datetime chunk_end=(datetime)MathMin((long)now,(long)cursor+(long)chunk_seconds);
      MqlRates rates[];
      ArraySetAsSeries(rates,false);
      int copied=-1;
      for(int attempt=0; attempt<InpSyncRetries; attempt++)
      {
         ResetLastError();
         copied=CopyRates(symbol,timeframe,cursor,chunk_end,rates);
         if(copied>=0) break;
         Sleep(InpRetryDelayMs);
      }
      if(copied<0)
      {
         failures++;
         Print("FAIL_EXPORT_COPY_RATES symbol=",symbol," timeframe=",tf,
               " from=",TimeToString(cursor,TIME_DATE|TIME_MINUTES),
               " to=",TimeToString(chunk_end,TIME_DATE|TIME_MINUTES),
               " error=",GetLastError());
         break;
      }

      for(int i=0;i<copied;i++)
      {
         if((long)rates[i].time<=last_written) continue;
         ResetLastError();
         uint row_bytes=FileWrite(handle,
            PROGRAM,
            symbol,
            tf,
            IntegerToString((long)rates[i].time),
            DoubleToString(rates[i].open,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
            DoubleToString(rates[i].high,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
            DoubleToString(rates[i].low,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
            DoubleToString(rates[i].close,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
            IntegerToString((long)rates[i].tick_volume),
            IntegerToString((int)rates[i].spread),
            IntegerToString((long)rates[i].real_volume),
            "AMARKETS_MT5");
         if(row_bytes==0)
         {
            failures++;
            Print("FAIL_EXPORT_ROW_WRITE symbol=",symbol," timeframe=",tf,
                  " time=",IntegerToString((long)rates[i].time)," error=",GetLastError());
            break;
         }
         written++;
         last_written=(long)rates[i].time;
      }
      if(failures>0) break;
      if(chunk_end>=now) break;
      cursor=chunk_end+1;
   }

   FileFlush(handle);
   FileClose(handle);

   if(failures>0 || written<=0)
   {
      Print("FAIL_EXPORT_WRITE symbol=",symbol," timeframe=",tf,
            " rows=",written," failures=",failures," snapshot=",snapshot);
      return false;
   }

   int validated=CountValidatedRows(snapshot,symbol,tf);
   if(validated!=written)
   {
      Print("FAIL_EXPORT_SELF_VALIDATION symbol=",symbol," timeframe=",tf,
            " written=",written," validated=",validated," snapshot=",snapshot);
      return false;
   }

   bool published=false;
   int publish_error=0;
   for(int attempt=0; attempt<InpPublishRetries; attempt++)
   {
      ResetLastError();
      if(FileMove(snapshot,0,canonical,FILE_REWRITE))
      {
         published=true;
         break;
      }
      publish_error=GetLastError();
      Sleep(InpRetryDelayMs);
   }

   if(published)
   {
      Print("PASS_CROSS_ASSET_HISTORY_EXPORT symbol=",symbol," timeframe=",tf,
            " rows=",written," validated=",validated," file=",canonical,
            " publish=ATOMIC_CANONICAL");
   }
   else
   {
      Print("PASS_CROSS_ASSET_HISTORY_EXPORT symbol=",symbol," timeframe=",tf,
            " rows=",written," validated=",validated," file=",snapshot,
            " publish=VALID_SNAPSHOT_FALLBACK canonical_move_error=",publish_error);
   }
   return true;
}

void OnStart()
{
   string symbols[];
   string scope;
   if(InpRepairOnlyLateHistorySymbols)
   {
      ArrayResize(symbols,2);
      symbols[0]="WTI";
      symbols[1]="DXY";
      scope="WTI_DXY_REPAIR_ONLY";
   }
   else
   {
      ArrayResize(symbols,8);
      symbols[0]="XAUUSD";
      symbols[1]="XAGUSD";
      symbols[2]="EURUSD";
      symbols[3]="USDJPY";
      symbols[4]="S&P500";
      symbols[5]="WTI";
      symbols[6]="BRENT";
      symbols[7]="DXY";
      scope="FULL_16_FILE_EXPORT";
   }

   ENUM_TIMEFRAMES timeframes[]={PERIOD_M15,PERIOD_H1};
   int passed=0;
   int failed=0;
   int expected=ArraySize(symbols)*ArraySize(timeframes);

   for(int i=0;i<ArraySize(symbols);i++)
   {
      for(int j=0;j<ArraySize(timeframes);j++)
      {
         if(ExportSeries(symbols[i],timeframes[j])) passed++;
         else failed++;
      }
   }

   if(failed==0 && passed==expected)
      Print("PASS_CROSS_ASSET_HISTORY_EXPORT_COMPLETE files=",passed,
            " scope=",scope," program=",PROGRAM," no_orders=true");
   else
      Print("FAIL_CROSS_ASSET_HISTORY_EXPORT_COMPLETE passed=",passed,
            " failed=",failed," expected=",expected,
            " scope=",scope," program=",PROGRAM);
}
