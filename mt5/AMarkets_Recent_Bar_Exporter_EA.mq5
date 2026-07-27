#property copyright "XAUUSD project"
#property version   "1.00"
#property strict
#property description "Exports completed recent AMarkets M5/H1 bars only. No trading path."

input string InpSymbol                    = "XAUUSD";
input long   InpAllowedDemoLogin          = 7907958;
input string InpOutputDirectory           = "XAUUSD_DEMO_BRIDGE\\SOURCE";
input int    InpRefreshSeconds            = 60;
input int    InpM5LookbackDays            = 10;
input int    InpH1LookbackDays            = 45;
input int    InpCopyAttempts              = 8;
input int    InpRetryMilliseconds         = 500;
input bool   InpShowChartStatus            = true;

#define EXPORTER_PROGRAM "AMARKETS_RECENT_BAR_EXPORTER_EA_V1"

string g_symbol="";
datetime g_last_exported_m5=0;
int g_last_m5_rows=0;
int g_last_h1_rows=0;
datetime g_last_m5_first=0;
datetime g_last_m5_last=0;
datetime g_last_h1_first=0;
datetime g_last_h1_last=0;

string TradeModeName()
  {
   ENUM_ACCOUNT_TRADE_MODE mode=(ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode==ACCOUNT_TRADE_MODE_DEMO) return "DEMO";
   if(mode==ACCOUNT_TRADE_MODE_REAL) return "REAL";
   if(mode==ACCOUNT_TRADE_MODE_CONTEST) return "CONTEST";
   return "UNKNOWN";
  }

string Dt(const datetime value)
  {
   if(value<=0) return "0";
   return TimeToString(value,TIME_DATE|TIME_SECONDS);
  }

string JoinPath(const string left,const string right)
  {
   if(StringLen(left)==0) return right;
   return left+"\\"+right;
  }

string TfCode(const ENUM_TIMEFRAMES tf)
  {
   if(tf==PERIOD_M5) return "5m";
   if(tf==PERIOD_H1) return "1h";
   return EnumToString(tf);
  }

bool EnsureFolders()
  {
   ResetLastError();
   if(!FolderCreate("XAUUSD_DEMO_BRIDGE") && GetLastError()!=0)
      PrintFormat("[%s] bridge folder warning error=%d",EXPORTER_PROGRAM,GetLastError());
   ResetLastError();
   if(!FolderCreate(InpOutputDirectory) && GetLastError()!=0)
     {
      PrintFormat("[%s] source folder create failed path=%s error=%d",EXPORTER_PROGRAM,InpOutputDirectory,GetLastError());
      return false;
     }
   return true;
  }

int CopyCompletedRates(const ENUM_TIMEFRAMES tf,const int lookback_days,MqlRates &rates[],datetime &last_complete)
  {
   ArrayFree(rates);
   ArraySetAsSeries(rates,false);
   last_complete=iTime(g_symbol,tf,1);
   if(last_complete<=0)
     {
      MqlRates probe[];
      ArraySetAsSeries(probe,false);
      CopyRates(g_symbol,tf,0,4,probe);
      last_complete=iTime(g_symbol,tf,1);
     }
   if(last_complete<=0)
      return -1;

   datetime start=last_complete-(datetime)((long)lookback_days*86400);
   int copied=-1;
   for(int attempt=1;attempt<=MathMax(1,InpCopyAttempts) && !IsStopped();attempt++)
     {
      ResetLastError();
      copied=CopyRates(g_symbol,tf,start,last_complete,rates);
      int err=GetLastError();
      if(copied>0)
         return copied;
      PrintFormat("[%s] CopyRates retry tf=%s attempt=%d/%d copied=%d error=%d",EXPORTER_PROGRAM,TfCode(tf),attempt,InpCopyAttempts,copied,err);
      Sleep((int)MathMax(50,InpRetryMilliseconds));
     }
   return copied;
  }

bool ExportTimeframe(const ENUM_TIMEFRAMES tf,const int lookback_days,const string final_name,int &rows_written,datetime &first_bar,datetime &last_bar,string &error)
  {
   rows_written=0;
   first_bar=0;
   last_bar=0;
   error="";
   MqlRates rates[];
   datetime last_complete=0;
   int copied=CopyCompletedRates(tf,lookback_days,rates,last_complete);
   if(copied<=0)
     {
      error=StringFormat("COPY_RATES_FAILED_%s_%d",TfCode(tf),GetLastError());
      return false;
     }

   string final_path=JoinPath(InpOutputDirectory,final_name);
   string temp_path=final_path+".tmp";
   FileDelete(temp_path);
   int handle=FileOpen(temp_path,FILE_WRITE|FILE_CSV|FILE_ANSI,'\t');
   if(handle==INVALID_HANDLE)
     {
      error=StringFormat("OUTPUT_OPEN_FAILED_%s_%d",TfCode(tf),GetLastError());
      return false;
     }

   FileWrite(handle,"<DATE>","<TIME>","<OPEN>","<HIGH>","<LOW>","<CLOSE>","<TICKVOL>","<SPREAD>","<VOL>");
   int digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);
   if(digits<=0) digits=2;
   datetime previous=0;
   int count=ArraySize(rates);
   bool ok=true;
   for(int i=0;i<count;i++)
     {
      if(rates[i].time<=0 || rates[i].time>last_complete || rates[i].time<=previous)
         continue;
      if(rates[i].high<MathMax(rates[i].open,rates[i].close) || rates[i].low>MathMin(rates[i].open,rates[i].close) || rates[i].high<rates[i].low)
        {
         error=StringFormat("OHLC_INVARIANT_FAILED_%s_%s",TfCode(tf),Dt(rates[i].time));
         ok=false;
         break;
        }
      uint written=FileWrite(handle,
                             TimeToString(rates[i].time,TIME_DATE),
                             TimeToString(rates[i].time,TIME_MINUTES),
                             DoubleToString(rates[i].open,digits),
                             DoubleToString(rates[i].high,digits),
                             DoubleToString(rates[i].low,digits),
                             DoubleToString(rates[i].close,digits),
                             (long)rates[i].tick_volume,
                             (int)rates[i].spread,
                             (long)rates[i].real_volume);
      if(written==0)
        {
         error=StringFormat("OUTPUT_WRITE_FAILED_%s_%d",TfCode(tf),GetLastError());
         ok=false;
         break;
        }
      if(first_bar<=0) first_bar=rates[i].time;
      last_bar=rates[i].time;
      previous=rates[i].time;
      rows_written++;
     }
   FileFlush(handle);
   FileClose(handle);

   if(!ok || rows_written<=0)
     {
      FileDelete(temp_path);
      if(error=="") error=StringFormat("NO_COMPLETED_ROWS_%s",TfCode(tf));
      return false;
     }

   FileDelete(final_path);
   ResetLastError();
   if(!FileMove(temp_path,0,final_path,FILE_REWRITE))
     {
      error=StringFormat("ATOMIC_RENAME_FAILED_%s_%d",TfCode(tf),GetLastError());
      FileDelete(temp_path);
      return false;
     }
   return true;
  }

bool WriteStatus(const string decision,const string detail,const int m5_rows,const int h1_rows,const datetime m5_first,const datetime m5_last,const datetime h1_first,const datetime h1_last)
  {
   string final_path=JoinPath(InpOutputDirectory,"recent_export_status.txt");
   string temp_path=final_path+".tmp";
   FileDelete(temp_path);
   int handle=FileOpen(temp_path,FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE)
      return false;
   string body="program="+EXPORTER_PROGRAM+"\r\n";
   body+="decision="+decision+"\r\n";
   body+="detail="+detail+"\r\n";
   body+="account_login="+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"\r\n";
   body+="account_trade_mode="+TradeModeName()+"\r\n";
   body+="account_server="+AccountInfoString(ACCOUNT_SERVER)+"\r\n";
   body+="symbol="+g_symbol+"\r\n";
   body+="m5_rows="+IntegerToString(m5_rows)+"\r\n";
   body+="h1_rows="+IntegerToString(h1_rows)+"\r\n";
   body+="m5_first="+Dt(m5_first)+"\r\n";
   body+="m5_last="+Dt(m5_last)+"\r\n";
   body+="h1_first="+Dt(h1_first)+"\r\n";
   body+="h1_last="+Dt(h1_last)+"\r\n";
   body+="generated_server_time="+Dt(TimeTradeServer())+"\r\n";
   FileWriteString(handle,body);
   FileFlush(handle);
   FileClose(handle);
   FileDelete(final_path);
   return FileMove(temp_path,0,final_path,FILE_REWRITE);
  }

void RunExport(const bool force)
  {
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
     {
      WriteStatus("FAIL_ACCOUNT_NOT_DEMO","Exporter is bound to a demo account.",0,0,0,0,0,0);
      return;
     }
   if(InpAllowedDemoLogin<=0 || AccountInfoInteger(ACCOUNT_LOGIN)!=InpAllowedDemoLogin)
     {
      WriteStatus("FAIL_LOGIN_MISMATCH","Current login does not match InpAllowedDemoLogin.",0,0,0,0,0,0);
      return;
     }
   datetime latest_m5=iTime(g_symbol,PERIOD_M5,1);
   if(!force && latest_m5>0 && latest_m5==g_last_exported_m5)
     {
      WriteStatus("PASS_RECENT_EXPORT","No new completed M5 bar; existing recent files remain current.",g_last_m5_rows,g_last_h1_rows,g_last_m5_first,g_last_m5_last,g_last_h1_first,g_last_h1_last);
      return;
     }

   int m5_rows=0,h1_rows=0;
   datetime m5_first=0,m5_last=0,h1_first=0,h1_last=0;
   string m5_error="",h1_error="";
   bool m5_ok=ExportTimeframe(PERIOD_M5,MathMax(2,InpM5LookbackDays),"amarkets_xauusd_5m_recent.csv",m5_rows,m5_first,m5_last,m5_error);
   bool h1_ok=ExportTimeframe(PERIOD_H1,MathMax(3,InpH1LookbackDays),"amarkets_xauusd_1h_recent.csv",h1_rows,h1_first,h1_last,h1_error);
   if(!m5_ok || !h1_ok)
     {
      string detail="m5="+m5_error+";h1="+h1_error;
      WriteStatus("FAIL_RECENT_EXPORT",detail,m5_rows,h1_rows,m5_first,m5_last,h1_first,h1_last);
      PrintFormat("[%s] FAIL %s",EXPORTER_PROGRAM,detail);
      return;
     }
   g_last_exported_m5=m5_last;
   g_last_m5_rows=m5_rows;
   g_last_h1_rows=h1_rows;
   g_last_m5_first=m5_first;
   g_last_m5_last=m5_last;
   g_last_h1_first=h1_first;
   g_last_h1_last=h1_last;
   WriteStatus("PASS_RECENT_EXPORT","Completed recent M5/H1 bars exported atomically.",m5_rows,h1_rows,m5_first,m5_last,h1_first,h1_last);
   PrintFormat("[%s] PASS m5_rows=%d m5_last=%s h1_rows=%d h1_last=%s",EXPORTER_PROGRAM,m5_rows,Dt(m5_last),h1_rows,Dt(h1_last));
   if(InpShowChartStatus)
      Comment("AMarkets recent exporter\nlogin=",InpAllowedDemoLogin," DEMO\nM5 last=",Dt(m5_last)," rows=",m5_rows,"\nH1 last=",Dt(h1_last)," rows=",h1_rows,"\nNO TRADING PATH");
  }

int OnInit()
  {
   g_symbol=InpSymbol;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return INIT_FAILED;
   if(!SymbolSelect(g_symbol,true))
      return INIT_FAILED;
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
      return INIT_FAILED;
   if(InpAllowedDemoLogin<=0 || AccountInfoInteger(ACCOUNT_LOGIN)!=InpAllowedDemoLogin)
      return INIT_FAILED;
   if(!EnsureFolders())
      return INIT_FAILED;
   EventSetTimer((int)MathMax(30,InpRefreshSeconds));
   RunExport(true);
   PrintFormat("[%s] initialized login=%I64d symbol=%s NO TRADING PATH",EXPORTER_PROGRAM,AccountInfoInteger(ACCOUNT_LOGIN),g_symbol);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
   PrintFormat("[%s] deinitialized reason=%d",EXPORTER_PROGRAM,reason);
  }

void OnTimer()
  {
   RunExport(false);
  }
