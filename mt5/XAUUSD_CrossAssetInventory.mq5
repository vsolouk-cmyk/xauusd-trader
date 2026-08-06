#property strict
#property script_show_inputs
#property version   "1.20"
#property description "Read-only self-validating atomic AMarkets/MT5 cross-asset inventory. No trading functions."

input string   InpOutputDirectory = "XAUUSD_CROSS_ASSET_INVENTORY";
input datetime InpHistoryStart     = D'2015.01.01 00:00';
input int      InpSyncRetries      = 5;
input int      InpRetryDelayMs     = 400;
input int      InpPublishRetries   = 5;

const string PROGRAM = "XAUUSD_CROSS_ASSET_INTRADAY_READINESS_V1_2_SELF_VALIDATING_CSV_REPAIR";
const int EXPECTED_COLUMNS = 25;

string UpperText(const string value)
{
   string result=value;
   StringToUpper(result);
   return result;
}

bool Contains(const string text,const string token)
{
   return StringFind(text,token)>=0;
}

string ClassifySymbol(const string name,const string description)
{
   string text=UpperText(name+" "+description);
   string classes="";

   if(Contains(text,"DXY") || Contains(text,"USDX") || Contains(text,"DOLLAR INDEX"))
      classes="USD_INDEX";

   if(Contains(text,"EURUSD") || Contains(text,"USDJPY"))
   {
      if(classes!="") classes+="|";
      classes+="USD_FX_PROXY";
   }

   if(Contains(text,"US10Y") || Contains(text,"UST10") || Contains(text,"TNX") ||
      Contains(text,"10Y TREASURY") || Contains(text,"10-YEAR TREASURY") ||
      Contains(text,"10 YEAR TREASURY") || Contains(text,"US 10Y"))
   {
      if(classes!="") classes+="|";
      classes+="US_RATES";
   }

   if(Contains(text,"VIX") || Contains(text,"VOLX") || Contains(text,"VOLATILITY INDEX"))
   {
      if(classes!="") classes+="|";
      classes+="VOLATILITY";
   }

   if(Contains(text,"XAG") || Contains(text,"SILVER"))
   {
      if(classes!="") classes+="|";
      classes+="SILVER";
   }

   if(Contains(text,"US500") || Contains(text,"SPX500") || Contains(text,"S&P 500") || Contains(text,"SP500"))
   {
      if(classes!="") classes+="|";
      classes+="EQUITY_RISK";
   }

   if(Contains(text,"WTI") || Contains(text,"USOIL") || Contains(text,"XTI") || Contains(text,"BRENT") || Contains(text,"XBR"))
   {
      if(classes!="") classes+="|";
      classes+="ENERGY";
   }

   return classes;
}

void TriggerSeries(const string symbol,const ENUM_TIMEFRAMES timeframe)
{
   MqlRates probe[];
   ArraySetAsSeries(probe,true);
   for(int attempt=0; attempt<InpSyncRetries; attempt++)
   {
      ResetLastError();
      int copied=CopyRates(symbol,timeframe,0,2,probe);
      long synchronized=0;
      SeriesInfoInteger(symbol,timeframe,SERIES_SYNCHRONIZED,synchronized);
      if(copied>0 && synchronized!=0)
         return;
      Sleep(InpRetryDelayMs);
   }
}

void ReadTimeframeFields(const string symbol,const ENUM_TIMEFRAMES timeframe,
                         int &bars,long &first_date,long &last_date,long &synchronized)
{
   TriggerSeries(symbol,timeframe);
   first_date=0;
   last_date=0;
   synchronized=0;
   SeriesInfoInteger(symbol,timeframe,SERIES_FIRSTDATE,first_date);
   SeriesInfoInteger(symbol,timeframe,SERIES_LASTBAR_DATE,last_date);
   SeriesInfoInteger(symbol,timeframe,SERIES_SYNCHRONIZED,synchronized);
   bars=Bars(symbol,timeframe,InpHistoryStart,TimeCurrent());
}

string UniqueInventoryPath()
{
   long login=AccountInfoInteger(ACCOUNT_LOGIN);
   long chart_id=ChartID();
   long local_epoch=(long)TimeLocal();
   ulong tick=GetTickCount64();
   return InpOutputDirectory+"\\mt5_cross_asset_inventory_"+
          IntegerToString(login)+"_"+
          IntegerToString(chart_id)+"_"+
          IntegerToString(local_epoch)+"_"+
          IntegerToString((long)tick)+".csv";
}

int CountValidatedRows(const string path)
{
   ResetLastError();
   int handle=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE,',');
   if(handle==INVALID_HANDLE)
   {
      Print("FAIL_SNAPSHOT_VALIDATION_OPEN path=",path," error=",GetLastError());
      return -1;
   }

   int records=0;
   int columns=0;
   string first_field="";

   while(!FileIsEnding(handle))
   {
      string value=FileReadString(handle);
      if(columns==0)
         first_field=value;
      columns++;

      bool line_end=FileIsLineEnding(handle);
      bool file_end=FileIsEnding(handle);
      if(line_end || file_end)
      {
         if(first_field==PROGRAM && columns==EXPECTED_COLUMNS)
            records++;
         columns=0;
         first_field="";
      }
   }

   FileClose(handle);
   return records;
}

void OnStart()
{
   ResetLastError();
   FolderCreate(InpOutputDirectory);

   string canonical_path=InpOutputDirectory+"\\mt5_cross_asset_inventory.csv";
   string snapshot_path=UniqueInventoryPath();

   int handle=FileOpen(snapshot_path,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');
   if(handle==INVALID_HANDLE)
   {
      Print("FAIL_SNAPSHOT_FILE_OPEN path=",snapshot_path," error=",GetLastError());
      return;
   }

   uint header_bytes=FileWrite(handle,
      "program","generated_server_time","symbol","description","categories","selected","trade_mode","digits","point","bid","ask","spread_points","spread_bps",
      "m15_bars","m15_first_epoch","m15_last_epoch","m15_synchronized",
      "h1_bars","h1_first_epoch","h1_last_epoch","h1_synchronized",
      "d1_bars","d1_first_epoch","d1_last_epoch","d1_synchronized");

   if(header_bytes==0)
   {
      int error=GetLastError();
      FileClose(handle);
      Print("FAIL_HEADER_WRITE path=",snapshot_path," error=",error);
      return;
   }

   int total=SymbolsTotal(false);
   int written=0;
   int write_failures=0;

   for(int i=0;i<total;i++)
   {
      string symbol=SymbolName(i,false);
      if(symbol=="") continue;
      string description=SymbolInfoString(symbol,SYMBOL_DESCRIPTION);
      string categories=ClassifySymbol(symbol,description);
      if(categories=="") continue;

      bool selected=SymbolSelect(symbol,true);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
      double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
      double spread_points=(point>0.0 && ask>0.0 && bid>0.0) ? (ask-bid)/point : 0.0;
      double mid=(ask+bid)/2.0;
      double spread_bps=(mid>0.0) ? (ask-bid)/mid*10000.0 : 0.0;
      long trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
      long digits=SymbolInfoInteger(symbol,SYMBOL_DIGITS);

      string safe_description=description;
      StringReplace(safe_description,","," ");
      StringReplace(safe_description,"\r"," ");
      StringReplace(safe_description,"\n"," ");

      int m15_bars=0,h1_bars=0,d1_bars=0;
      long m15_first=0,m15_last=0,m15_sync=0;
      long h1_first=0,h1_last=0,h1_sync=0;
      long d1_first=0,d1_last=0,d1_sync=0;
      ReadTimeframeFields(symbol,PERIOD_M15,m15_bars,m15_first,m15_last,m15_sync);
      ReadTimeframeFields(symbol,PERIOD_H1,h1_bars,h1_first,h1_last,h1_sync);
      ReadTimeframeFields(symbol,PERIOD_D1,d1_bars,d1_first,d1_last,d1_sync);

      ResetLastError();
      uint row_bytes=FileWrite(handle,
         PROGRAM,
         IntegerToString((long)TimeCurrent()),
         symbol,
         safe_description,
         categories,
         IntegerToString((int)selected),
         IntegerToString((int)trade_mode),
         IntegerToString((int)digits),
         DoubleToString(point,10),
         DoubleToString(bid,(int)digits),
         DoubleToString(ask,(int)digits),
         DoubleToString(spread_points,3),
         DoubleToString(spread_bps,6),
         IntegerToString(m15_bars),IntegerToString(m15_first),IntegerToString(m15_last),IntegerToString((int)m15_sync),
         IntegerToString(h1_bars),IntegerToString(h1_first),IntegerToString(h1_last),IntegerToString((int)h1_sync),
         IntegerToString(d1_bars),IntegerToString(d1_first),IntegerToString(d1_last),IntegerToString((int)d1_sync));

      if(row_bytes==0)
      {
         write_failures++;
         Print("FAIL_ROW_WRITE symbol=",symbol," error=",GetLastError());
      }
      else
      {
         written++;
      }
   }

   FileFlush(handle);
   FileClose(handle);

   if(written<=0 || write_failures>0)
   {
      Print("FAIL_INVENTORY_WRITE written=",written," write_failures=",write_failures,
            " snapshot=",snapshot_path);
      return;
   }

   int validated=CountValidatedRows(snapshot_path);
   if(validated!=written)
   {
      Print("FAIL_SNAPSHOT_SELF_VALIDATION written=",written," validated=",validated,
            " snapshot=",snapshot_path);
      return;
   }

   int publish_error=0;
   bool published=false;
   for(int attempt=0; attempt<InpPublishRetries; attempt++)
   {
      ResetLastError();
      if(FileMove(snapshot_path,0,canonical_path,FILE_REWRITE))
      {
         published=true;
         break;
      }
      publish_error=GetLastError();
      Sleep(InpRetryDelayMs);
   }

   if(published)
   {
      Print("PASS_CROSS_ASSET_MT5_INVENTORY_CREATED rows=",written,
            " validated=",validated," file=",canonical_path,
            " publish=ATOMIC_CANONICAL");
   }
   else
   {
      Print("PASS_CROSS_ASSET_MT5_INVENTORY_CREATED rows=",written,
            " validated=",validated," file=",snapshot_path,
            " publish=VALID_SNAPSHOT_FALLBACK canonical_move_error=",publish_error);
   }
}
