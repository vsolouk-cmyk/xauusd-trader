#property strict
#property version   "1.10"
#property description "XAUUSD bounded demo bridge. Disabled by default. Demo accounts only."

#include <Trade/Trade.mqh>

input bool   InpArmed                         = false;
input long   InpAllowedDemoLogin              = 0;
input string InpExpectedSymbol                = "XAUUSD";
input ulong  InpMagicNumber                   = 1782401;
input string InpBridgeFolder                  = "XAUUSD_DEMO_BRIDGE";
input string InpArmingPermitFile               = "arming_permit.txt";
input int    InpPollSeconds                    = 1;
input int    InpMaximumSlippagePoints          = 50;
input double InpNotionalToEquity               = 0.03925991017190415;
input double InpValidatedMaximumNotionalRatio  = 0.1570396406876166;
input double InpSpreadGuardBps                 = 3.0764778059487488;
input int    InpDailyNewPositionsCap           = 1;
input double InpWeeklyLossPausePct             = 2.0;
input double InpHardDrawdownKillPct            = 8.0;
input int    InpMaximumResolvedPositions       = 10;
input int    InpMaximumCalendarDays            = 30;
input int    InpDiagnosticLogSeconds           = 30;
input bool   InpShowChartStatus                = true;

const string EA_PROGRAM = "XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING";
const string CANDIDATE_SCHEMA = "XAUUSD_DEMO_CANDIDATE_V1";

CTrade g_trade;
datetime g_last_diagnostic_log=0;
string g_last_runtime_status="";

struct Candidate
{
   string schema_version;
   string intent_id;
   long   created_epoch;
   long   expires_epoch;
   string symbol;
   string side;
   double probability_up;
   long   signal_epoch;
   long   target_entry_epoch;
   long   target_exit_epoch;
   string entry_semantics;
   string exit_semantics;
   int    exit_after_h1_bars;
   double notional_to_equity;
   bool   event_guard_pass;
   string event_guard_reason;
   double spread_guard_bps;
   string bounded_preflight_sha256;
   ulong  magic_number;
   string execution_mode;
   bool   requires_runtime_authorization;
   bool   python_order_authorized;
};

string JoinPath(const string left,const string right)
{
   if(StringLen(left)==0)
      return right;
   return left+"\\"+right;
}

string CandidatePath()
{
   return JoinPath(InpBridgeFolder,"demo_candidate.txt");
}

string HeartbeatPath()
{
   return JoinPath(InpBridgeFolder,"bridge_heartbeat.txt");
}

string RuntimeLogPath()
{
   return JoinPath(InpBridgeFolder,"bridge_runtime.log");
}

string ArmingPermitPath()
{
   return JoinPath(InpBridgeFolder,InpArmingPermitFile);
}

string ActiveStatePath()
{
   return JoinPath(InpBridgeFolder,"active_position.txt");
}

string ReceiptFolder()
{
   return JoinPath(InpBridgeFolder,"receipts");
}

string SafeIntentId(string value)
{
   string result="";
   for(int i=0;i<StringLen(value);i++)
   {
      ushort ch=StringGetCharacter(value,i);
      bool ok=((ch>='0' && ch<='9') || (ch>='A' && ch<='Z') || (ch>='a' && ch<='z') || ch=='_' || ch=='-');
      result+=ok ? StringSubstr(value,i,1) : "_";
   }
   return result;
}

string ReceiptPath(const string intent_id)
{
   return JoinPath(ReceiptFolder(),SafeIntentId(intent_id)+".txt");
}

bool ReceiptExists(const string intent_id)
{
   return FileIsExist(ReceiptPath(intent_id));
}

string TradeModeName()
{
   long mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode==ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode==ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   if(mode==ACCOUNT_TRADE_MODE_REAL)
      return "REAL";
   return "UNKNOWN";
}

bool WriteKeyValueFile(const string path,const string &keys[],const string &values[])
{
   int handle=FileOpen(path,FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE)
      return false;
   int total=ArraySize(keys);
   for(int i=0;i<total;i++)
      FileWriteString(handle,keys[i]+"="+values[i]+"\n");
   FileFlush(handle);
   FileClose(handle);
   return true;
}

struct VolumeDiagnostic
{
   double bid;
   double ask;
   double mid;
   double equity;
   double contract_size;
   double volume_min;
   double volume_max;
   double volume_step;
   double minimum_notional;
   double minimum_ratio;
   double raw_target_volume;
   double floored_target_volume;
   double actual_executable_ratio;
   double required_equity_ceiling;
   double required_equity_target;
   double equity_multiplier_ceiling;
   double equity_multiplier_target;
   bool   minimum_within_ceiling;
   bool   target_executable;
   string decision;
};

int DiagnosticVolumeDigits(double step)
{
   int digits=0;
   while(digits<8 && MathAbs(step-NormalizeDouble(step,digits))>1e-12)
      digits++;
   return digits;
}

void ComputeVolumeDiagnostic(VolumeDiagnostic &diag)
{
   diag.bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   diag.ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   diag.mid=(diag.bid+diag.ask)/2.0;
   diag.equity=AccountInfoDouble(ACCOUNT_EQUITY);
   diag.contract_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE);
   diag.volume_min=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   diag.volume_max=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   diag.volume_step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   diag.minimum_notional=-1.0;
   diag.minimum_ratio=-1.0;
   diag.raw_target_volume=-1.0;
   diag.floored_target_volume=-1.0;
   diag.actual_executable_ratio=-1.0;
   diag.required_equity_ceiling=-1.0;
   diag.required_equity_target=-1.0;
   diag.equity_multiplier_ceiling=-1.0;
   diag.equity_multiplier_target=-1.0;
   diag.minimum_within_ceiling=false;
   diag.target_executable=false;
   diag.decision="INVALID_SYMBOL_OR_ACCOUNT_VOLUME_CONTRACT";

   if(diag.mid<=0.0 || diag.equity<=0.0 || diag.contract_size<=0.0 ||
      diag.volume_min<=0.0 || diag.volume_step<=0.0 ||
      InpNotionalToEquity<=0.0 || InpValidatedMaximumNotionalRatio<=0.0)
      return;

   diag.minimum_notional=diag.volume_min*diag.contract_size*diag.mid;
   diag.minimum_ratio=diag.minimum_notional/diag.equity;
   diag.raw_target_volume=(diag.equity*InpNotionalToEquity)/(diag.contract_size*diag.mid);
   double floored=MathFloor(diag.raw_target_volume/diag.volume_step+1e-12)*diag.volume_step;
   diag.floored_target_volume=NormalizeDouble(MathMin(floored,diag.volume_max),DiagnosticVolumeDigits(diag.volume_step));
   if(diag.floored_target_volume>=diag.volume_min-1e-12)
      diag.actual_executable_ratio=(diag.floored_target_volume*diag.contract_size*diag.mid)/diag.equity;

   diag.required_equity_ceiling=diag.minimum_notional/InpValidatedMaximumNotionalRatio;
   diag.required_equity_target=diag.minimum_notional/InpNotionalToEquity;
   diag.equity_multiplier_ceiling=diag.required_equity_ceiling/diag.equity;
   diag.equity_multiplier_target=diag.required_equity_target/diag.equity;
   diag.minimum_within_ceiling=(diag.minimum_ratio<=InpValidatedMaximumNotionalRatio+1e-12);
   diag.target_executable=(diag.floored_target_volume>=diag.volume_min-1e-12 &&
                           diag.actual_executable_ratio>0.0 &&
                           diag.actual_executable_ratio<=InpNotionalToEquity+1e-10);

   if(!diag.minimum_within_ceiling)
      diag.decision="BLOCK_ARMING_MINIMUM_LOT_EXCEEDS_VALIDATED_CEILING";
   else if(!diag.target_executable)
      diag.decision="BLOCK_ARMING_MINIMUM_LOT_EXCEEDS_INITIAL_TARGET";
   else
      diag.decision="READY_UNDER_LOCKED_VOLUME_CONTRACT";
}

bool AppendRuntimeLog(const string line)
{
   int handle=FileOpen(RuntimeLogPath(),FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(handle==INVALID_HANDLE)
      handle=FileOpen(RuntimeLogPath(),FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ);
   if(handle==INVALID_HANDLE)
      return false;
   FileSeek(handle,0,SEEK_END);
   FileWriteString(handle,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+" "+line+"\n");
   FileFlush(handle);
   FileClose(handle);
   return true;
}

void UpdateChartStatus(const string status,const VolumeDiagnostic &diag)
{
   if(!InpShowChartStatus)
      return;
   string text=EA_PROGRAM+"\n"+
      "status="+status+" armed="+(InpArmed ? "true" : "false")+" account="+TradeModeName()+"\n"+
      "equity="+DoubleToString(diag.equity,2)+
      " minLot="+DoubleToString(diag.volume_min,4)+
      " minRatio="+DoubleToString(diag.minimum_ratio,6)+"\n"+
      "targetRatio="+DoubleToString(InpNotionalToEquity,6)+
      " maxRatio="+DoubleToString(InpValidatedMaximumNotionalRatio,6)+"\n"+
      "volumeDecision="+diag.decision;
   Comment(text);
}

void LogRuntimeStatus(const string status,const bool force=false)
{
   VolumeDiagnostic diag;
   ComputeVolumeDiagnostic(diag);
   UpdateChartStatus(status,diag);
   datetime now=TimeCurrent();
   int interval=(int)MathMax(10,InpDiagnosticLogSeconds);
   bool due=(force || g_last_diagnostic_log==0 || status!=g_last_runtime_status || now-g_last_diagnostic_log>=interval);
   if(!due)
      return;

   string line=StringFormat(
      "%s status=%s armed=%s mode=%s login=%I64d symbol=%s equity=%.2f bid=%.5f ask=%.5f contract=%.4f minLot=%.6f step=%.6f minRatio=%.12f targetRatio=%.12f maxRatio=%.12f rawTargetLot=%.8f flooredLot=%.8f requiredEquityTarget=%.2f requiredEquityCeiling=%.2f multiplierTarget=%.6f multiplierCeiling=%.6f volumeDecision=%s",
      EA_PROGRAM,status,(InpArmed ? "true" : "false"),TradeModeName(),
      (long)AccountInfoInteger(ACCOUNT_LOGIN),_Symbol,diag.equity,diag.bid,diag.ask,
      diag.contract_size,diag.volume_min,diag.volume_step,diag.minimum_ratio,
      InpNotionalToEquity,InpValidatedMaximumNotionalRatio,diag.raw_target_volume,
      diag.floored_target_volume,diag.required_equity_target,diag.required_equity_ceiling,
      diag.equity_multiplier_target,diag.equity_multiplier_ceiling,diag.decision
   );
   Print(line);
   if(!AppendRuntimeLog(line))
      Print(EA_PROGRAM," runtime file log write failed error=",GetLastError());
   g_last_diagnostic_log=now;
   g_last_runtime_status=status;
}

void WriteHeartbeat(const string status)
{
   VolumeDiagnostic diag;
   ComputeVolumeDiagnostic(diag);

   string keys[];
   string values[];
   ArrayResize(keys,35);
   ArrayResize(values,35);
   keys[0]="program"; values[0]=EA_PROGRAM;
   keys[1]="generated_server_time"; values[1]=TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS);
   keys[2]="status"; values[2]=status;
   keys[3]="armed"; values[3]=InpArmed ? "true" : "false";
   keys[4]="account_trade_mode"; values[4]=TradeModeName();
   keys[5]="account_login"; values[5]=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
   keys[6]="symbol"; values[6]=_Symbol;
   keys[7]="magic_number"; values[7]=IntegerToString((long)InpMagicNumber);
   keys[8]="live_fallback_allowed"; values[8]="false";
   keys[9]="spread_guard_bps"; values[9]=DoubleToString(InpSpreadGuardBps,12);
   keys[10]="notional_to_equity"; values[10]=DoubleToString(InpNotionalToEquity,12);
   keys[11]="validated_maximum_notional_ratio"; values[11]=DoubleToString(InpValidatedMaximumNotionalRatio,12);
   keys[12]="account_equity"; values[12]=DoubleToString(diag.equity,12);
   keys[13]="symbol_bid"; values[13]=DoubleToString(diag.bid,12);
   keys[14]="symbol_ask"; values[14]=DoubleToString(diag.ask,12);
   keys[15]="symbol_mid_price"; values[15]=DoubleToString(diag.mid,12);
   keys[16]="trade_contract_size"; values[16]=DoubleToString(diag.contract_size,12);
   keys[17]="volume_min"; values[17]=DoubleToString(diag.volume_min,12);
   keys[18]="volume_max"; values[18]=DoubleToString(diag.volume_max,12);
   keys[19]="volume_step"; values[19]=DoubleToString(diag.volume_step,12);
   keys[20]="minimum_volume_notional"; values[20]=DoubleToString(diag.minimum_notional,12);
   keys[21]="minimum_volume_ratio"; values[21]=DoubleToString(diag.minimum_ratio,12);
   keys[22]="raw_target_volume"; values[22]=DoubleToString(diag.raw_target_volume,12);
   keys[23]="floored_target_volume"; values[23]=DoubleToString(diag.floored_target_volume,12);
   keys[24]="actual_executable_ratio"; values[24]=DoubleToString(diag.actual_executable_ratio,12);
   keys[25]="minimum_volume_within_validated_ceiling"; values[25]=diag.minimum_within_ceiling ? "true" : "false";
   keys[26]="target_volume_executable"; values[26]=diag.target_executable ? "true" : "false";
   keys[27]="required_equity_for_validated_ceiling"; values[27]=DoubleToString(diag.required_equity_ceiling,12);
   keys[28]="required_equity_for_initial_target"; values[28]=DoubleToString(diag.required_equity_target,12);
   keys[29]="equity_multiplier_to_validated_ceiling"; values[29]=DoubleToString(diag.equity_multiplier_ceiling,12);
   keys[30]="equity_multiplier_to_initial_target"; values[30]=DoubleToString(diag.equity_multiplier_target,12);
   keys[31]="volume_contract_decision"; values[31]=diag.decision;
   keys[32]="allowed_demo_login"; values[32]=IntegerToString(InpAllowedDemoLogin);
   keys[33]="arming_permit_present"; values[33]=FileIsExist(ArmingPermitPath()) ? "true" : "false";
   keys[34]="runtime_log_file"; values[34]=RuntimeLogPath();
   if(!WriteKeyValueFile(HeartbeatPath(),keys,values))
      Print(EA_PROGRAM," heartbeat write failed error=",GetLastError());
}


bool ParseBool(const string value)
{
   string normalized=value;
   StringToLower(normalized);
   return normalized=="1" || normalized=="true" || normalized=="yes";
}

bool LoadCandidate(Candidate &candidate,string &error)
{
   int handle=FileOpen(CandidatePath(),FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE)
   {
      error="CANDIDATE_FILE_NOT_FOUND";
      return false;
   }

   while(!FileIsEnding(handle))
   {
      string line=FileReadString(handle);
      int pos=StringFind(line,"=");
      if(pos<=0)
         continue;
      string key=StringSubstr(line,0,pos);
      string value=StringSubstr(line,pos+1);
      if(key=="schema_version") candidate.schema_version=value;
      else if(key=="intent_id") candidate.intent_id=value;
      else if(key=="created_epoch") candidate.created_epoch=(long)StringToInteger(value);
      else if(key=="expires_epoch") candidate.expires_epoch=(long)StringToInteger(value);
      else if(key=="symbol") candidate.symbol=value;
      else if(key=="side") candidate.side=value;
      else if(key=="probability_up") candidate.probability_up=StringToDouble(value);
      else if(key=="signal_epoch") candidate.signal_epoch=(long)StringToInteger(value);
      else if(key=="target_entry_epoch") candidate.target_entry_epoch=(long)StringToInteger(value);
      else if(key=="target_exit_epoch") candidate.target_exit_epoch=(long)StringToInteger(value);
      else if(key=="entry_semantics") candidate.entry_semantics=value;
      else if(key=="exit_semantics") candidate.exit_semantics=value;
      else if(key=="exit_after_h1_bars") candidate.exit_after_h1_bars=(int)StringToInteger(value);
      else if(key=="notional_to_equity") candidate.notional_to_equity=StringToDouble(value);
      else if(key=="event_guard_pass") candidate.event_guard_pass=ParseBool(value);
      else if(key=="event_guard_reason") candidate.event_guard_reason=value;
      else if(key=="spread_guard_bps") candidate.spread_guard_bps=StringToDouble(value);
      else if(key=="bounded_preflight_sha256") candidate.bounded_preflight_sha256=value;
      else if(key=="magic_number") candidate.magic_number=(ulong)StringToInteger(value);
      else if(key=="execution_mode") candidate.execution_mode=value;
      else if(key=="requires_mt5_runtime_authorization") candidate.requires_runtime_authorization=ParseBool(value);
      else if(key=="python_order_authorized") candidate.python_order_authorized=ParseBool(value);
   }
   FileClose(handle);

   if(candidate.schema_version!=CANDIDATE_SCHEMA)
      error="CANDIDATE_SCHEMA_MISMATCH";
   else if(StringLen(candidate.intent_id)<1)
      error="CANDIDATE_INTENT_ID_MISSING";
   else if(candidate.symbol!=InpExpectedSymbol || _Symbol!=InpExpectedSymbol)
      error="SYMBOL_MISMATCH";
   else if(candidate.side!="LONG" && candidate.side!="SHORT")
      error="SIDE_INVALID";
   else if(candidate.entry_semantics!="OPEN_OF_ALIGNED_H1_ROW_I_PLUS_1")
      error="ENTRY_SEMANTICS_MISMATCH";
   else if(candidate.exit_semantics!="CLOSE_OF_ALIGNED_H1_ROW_I_PLUS_24" || candidate.exit_after_h1_bars!=24)
      error="EXIT_SEMANTICS_MISMATCH";
   else if(candidate.execution_mode!="DEMO_ONLY")
      error="EXECUTION_MODE_NOT_DEMO_ONLY";
   else if(!candidate.requires_runtime_authorization)
      error="RUNTIME_AUTHORIZATION_NOT_REQUIRED";
   else if(candidate.python_order_authorized)
      error="PYTHON_ORDER_AUTHORIZATION_MUST_BE_FALSE";
   else if(!candidate.event_guard_pass || candidate.event_guard_reason!="EVENT_CONTEXT_PRESENT_NO_BLOCK")
      error="EVENT_GUARD_NOT_PASSED";
   else if(candidate.magic_number!=InpMagicNumber)
      error="MAGIC_NUMBER_MISMATCH";
   else if(MathAbs(candidate.notional_to_equity-InpNotionalToEquity)>1e-12)
      error="NOTIONAL_CONTRACT_MISMATCH";
   else if(MathAbs(candidate.spread_guard_bps-InpSpreadGuardBps)>1e-10)
      error="SPREAD_GUARD_CONTRACT_MISMATCH";
   else
      return true;
   return false;
}

bool LoadArmingPermit(const Candidate &candidate,string &reason)
{
   int handle=FileOpen(ArmingPermitPath(),FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE)
   {
      reason="ARMING_PERMIT_MISSING";
      return false;
   }
   string schema="";
   bool authorized=false;
   long allowed_login=0;
   ulong magic=0;
   long expires_epoch=0;
   string bounded_hash="";
   while(!FileIsEnding(handle))
   {
      string line=FileReadString(handle);
      int pos=StringFind(line,"=");
      if(pos<=0)
         continue;
      string key=StringSubstr(line,0,pos);
      string value=StringSubstr(line,pos+1);
      if(key=="schema_version") schema=value;
      else if(key=="authorized") authorized=ParseBool(value);
      else if(key=="allowed_demo_login") allowed_login=(long)StringToInteger(value);
      else if(key=="magic_number") magic=(ulong)StringToInteger(value);
      else if(key=="expires_epoch") expires_epoch=(long)StringToInteger(value);
      else if(key=="bounded_preflight_sha256") bounded_hash=value;
   }
   FileClose(handle);
   datetime now_utc=TimeGMT();
   if(schema!="XAUUSD_DEMO_ARMING_PERMIT_V1") reason="ARMING_PERMIT_SCHEMA_MISMATCH";
   else if(!authorized) reason="ARMING_PERMIT_NOT_AUTHORIZED";
   else if(allowed_login<=0 || allowed_login!=InpAllowedDemoLogin || allowed_login!=AccountInfoInteger(ACCOUNT_LOGIN)) reason="ARMING_PERMIT_LOGIN_MISMATCH";
   else if(magic!=InpMagicNumber) reason="ARMING_PERMIT_MAGIC_MISMATCH";
   else if(bounded_hash!=candidate.bounded_preflight_sha256) reason="ARMING_PERMIT_PREFLIGHT_HASH_MISMATCH";
   else if(now_utc<=0 || expires_epoch<now_utc) reason="ARMING_PERMIT_EXPIRED";
   else return true;
   return false;
}

void WriteReceipt(const string intent_id,const string status,const string reason,const ulong order_ticket,const ulong deal_ticket,const double requested_price,const double fill_price,const double volume,const double spread_bps,const long exit_epoch)
{
   FolderCreate(ReceiptFolder());
   string keys[];
   string values[];
   ArrayResize(keys,17);
   ArrayResize(values,17);
   keys[0]="program"; values[0]=EA_PROGRAM;
   keys[1]="intent_id"; values[1]=intent_id;
   keys[2]="status"; values[2]=status;
   keys[3]="reason"; values[3]=reason;
   keys[4]="server_time"; values[4]=TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS);
   keys[5]="account_trade_mode"; values[5]=TradeModeName();
   keys[6]="account_login"; values[6]=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
   keys[7]="symbol"; values[7]=_Symbol;
   keys[8]="order_ticket"; values[8]=IntegerToString((long)order_ticket);
   keys[9]="deal_ticket"; values[9]=IntegerToString((long)deal_ticket);
   keys[10]="requested_price"; values[10]=DoubleToString(requested_price,_Digits);
   keys[11]="fill_price"; values[11]=DoubleToString(fill_price,_Digits);
   keys[12]="volume"; values[12]=DoubleToString(volume,8);
   keys[13]="spread_bps"; values[13]=DoubleToString(spread_bps,12);
   keys[14]="retcode"; values[14]=IntegerToString((long)g_trade.ResultRetcode());
   keys[15]="retcode_description"; values[15]=g_trade.ResultRetcodeDescription();
   keys[16]="target_exit_epoch"; values[16]=IntegerToString(exit_epoch);
   WriteKeyValueFile(ReceiptPath(intent_id),keys,values);
}

bool HasBridgePosition(ulong &ticket)
{
   ticket=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong current=PositionGetTicket(i);
      if(current==0 || !PositionSelectByTicket(current))
         continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol && (ulong)PositionGetInteger(POSITION_MAGIC)==InpMagicNumber)
      {
         ticket=current;
         return true;
      }
   }
   return false;
}

datetime DayStart(datetime when)
{
   MqlDateTime value;
   TimeToStruct(when,value);
   value.hour=0;
   value.min=0;
   value.sec=0;
   return StructToTime(value);
}

datetime WeekStart(datetime when)
{
   datetime day=DayStart(when);
   MqlDateTime value;
   TimeToStruct(day,value);
   int days_since_monday=(value.day_of_week+6)%7;
   return day-days_since_monday*86400;
}

int CountEntryDeals(datetime from_time)
{
   if(!HistorySelect(from_time,TimeCurrent()))
      return 0;
   int count=0;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0)
         continue;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=InpMagicNumber)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY)==DEAL_ENTRY_IN)
         count++;
   }
   return count;
}

int CountExitDeals(datetime from_time)
{
   if(!HistorySelect(from_time,TimeCurrent()))
      return 0;
   int count=0;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0)
         continue;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=_Symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)!=InpMagicNumber)
         continue;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY)
         count++;
   }
   return count;
}

string StateKey(const string suffix)
{
   return "XAUUSD_BD_"+IntegerToString((long)InpMagicNumber)+"_"+IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))+"_"+suffix;
}

void InitializeRiskState()
{
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(!GlobalVariableCheck(StateKey("START_TIME")))
      GlobalVariableSet(StateKey("START_TIME"),(double)TimeCurrent());
   if(!GlobalVariableCheck(StateKey("PEAK_EQUITY")))
      GlobalVariableSet(StateKey("PEAK_EQUITY"),equity);
   if(!GlobalVariableCheck(StateKey("WEEK_START")))
      GlobalVariableSet(StateKey("WEEK_START"),(double)WeekStart(TimeCurrent()));
   if(!GlobalVariableCheck(StateKey("WEEK_EQUITY")))
      GlobalVariableSet(StateKey("WEEK_EQUITY"),equity);
   if(!GlobalVariableCheck(StateKey("HARD_KILL")))
      GlobalVariableSet(StateKey("HARD_KILL"),0.0);
}

bool QualificationBoundReached(string &reason)
{
   InitializeRiskState();
   datetime start=(datetime)GlobalVariableGet(StateKey("START_TIME"));
   if(TimeCurrent()>=start+InpMaximumCalendarDays*86400)
   {
      reason="QUALIFICATION_BOUND_REACHED_CALENDAR_DAYS";
      return true;
   }
   if(CountExitDeals(start)>=InpMaximumResolvedPositions)
   {
      reason="QUALIFICATION_BOUND_REACHED_RESOLVED_POSITIONS";
      return true;
   }
   return false;
}

bool RiskPauseOrKill(string &reason)
{
   InitializeRiskState();
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double peak=GlobalVariableGet(StateKey("PEAK_EQUITY"));
   if(equity>peak)
   {
      peak=equity;
      GlobalVariableSet(StateKey("PEAK_EQUITY"),peak);
   }
   double drawdown=(peak>0.0 ? (peak-equity)/peak*100.0 : 0.0);
   if(GlobalVariableGet(StateKey("HARD_KILL"))>0.5 || drawdown>=InpHardDrawdownKillPct)
   {
      GlobalVariableSet(StateKey("HARD_KILL"),1.0);
      reason="HARD_DRAWDOWN_KILL";
      return true;
   }

   datetime current_week=WeekStart(TimeCurrent());
   datetime stored_week=(datetime)GlobalVariableGet(StateKey("WEEK_START"));
   if(current_week!=stored_week)
   {
      GlobalVariableSet(StateKey("WEEK_START"),(double)current_week);
      GlobalVariableSet(StateKey("WEEK_EQUITY"),equity);
   }
   double week_equity=GlobalVariableGet(StateKey("WEEK_EQUITY"));
   double week_loss=(week_equity>0.0 ? (week_equity-equity)/week_equity*100.0 : 0.0);
   if(week_loss>=InpWeeklyLossPausePct)
   {
      reason="WEEKLY_LOSS_PAUSE";
      return true;
   }
   return false;
}

bool CloseBridgePosition(const string reason)
{
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   {
      Print(EA_PROGRAM," close blocked: account is not DEMO reason=",reason);
      return false;
   }
   ulong ticket=0;
   if(!HasBridgePosition(ticket))
      return true;
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpMaximumSlippagePoints);
   bool ok=g_trade.PositionClose(ticket);
   if(!ok)
      Print(EA_PROGRAM," close failed reason=",reason," retcode=",g_trade.ResultRetcode()," ",g_trade.ResultRetcodeDescription());
   return ok;
}

double SpreadBps()
{
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double mid=(bid+ask)/2.0;
   if(bid<=0.0 || ask<=0.0 || mid<=0.0 || ask<bid)
      return -1.0;
   return (ask-bid)/mid*10000.0;
}

int VolumeDigits(double step)
{
   int digits=0;
   while(digits<8 && MathAbs(step-NormalizeDouble(step,digits))>1e-12)
      digits++;
   return digits;
}

bool ComputeTargetVolume(const Candidate &candidate,const double price,double &volume,double &actual_ratio,string &reason)
{
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double contract_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE);
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(equity<=0.0 || contract_size<=0.0 || price<=0.0 || minimum<=0.0 || step<=0.0)
   {
      reason="SYMBOL_VOLUME_CONTRACT_INVALID";
      return false;
   }
   double raw=(equity*candidate.notional_to_equity)/(contract_size*price);
   double floored=MathFloor(raw/step+1e-12)*step;
   volume=NormalizeDouble(MathMin(floored,maximum),VolumeDigits(step));
   if(volume<minimum-1e-12)
   {
      reason="TARGET_BELOW_MINIMUM_VOLUME";
      return false;
   }
   actual_ratio=(volume*contract_size*price)/equity;
   if(actual_ratio>candidate.notional_to_equity+1e-10)
   {
      reason="VOLUME_ROUNDING_WOULD_INCREASE_TARGET_RISK";
      return false;
   }
   if(actual_ratio>InpValidatedMaximumNotionalRatio+1e-10)
   {
      reason="VOLUME_EXCEEDS_VALIDATED_MAXIMUM";
      return false;
   }
   return true;
}

bool SaveActiveState(const Candidate &candidate,const ulong position_ticket,const long entry_h1_server_epoch)
{
   string keys[];
   string values[];
   ArrayResize(keys,6);
   ArrayResize(values,6);
   keys[0]="intent_id"; values[0]=candidate.intent_id;
   keys[1]="position_ticket"; values[1]=IntegerToString((long)position_ticket);
   keys[2]="target_exit_epoch"; values[2]=IntegerToString(candidate.target_exit_epoch);
   keys[3]="side"; values[3]=candidate.side;
   keys[4]="entry_h1_epoch"; values[4]=IntegerToString(entry_h1_server_epoch);
   keys[5]="exit_after_h1_bars"; values[5]=IntegerToString(candidate.exit_after_h1_bars);
   return WriteKeyValueFile(ActiveStatePath(),keys,values);
}

bool LoadActiveState(string &intent_id,ulong &ticket,long &exit_epoch,long &entry_h1_epoch,int &exit_after_h1_bars)
{
   int handle=FileOpen(ActiveStatePath(),FILE_READ|FILE_TXT|FILE_ANSI);
   if(handle==INVALID_HANDLE)
      return false;
   while(!FileIsEnding(handle))
   {
      string line=FileReadString(handle);
      int pos=StringFind(line,"=");
      if(pos<=0)
         continue;
      string key=StringSubstr(line,0,pos);
      string value=StringSubstr(line,pos+1);
      if(key=="intent_id") intent_id=value;
      else if(key=="position_ticket") ticket=(ulong)StringToInteger(value);
      else if(key=="target_exit_epoch") exit_epoch=(long)StringToInteger(value);
      else if(key=="entry_h1_epoch") entry_h1_epoch=(long)StringToInteger(value);
      else if(key=="exit_after_h1_bars") exit_after_h1_bars=(int)StringToInteger(value);
   }
   FileClose(handle);
   return StringLen(intent_id)>0;
}

void ProcessActivePosition()
{
   string intent_id="";
   ulong ticket=0;
   long exit_epoch=0;
   long entry_h1_epoch=0;
   int exit_after_h1_bars=24;
   if(!LoadActiveState(intent_id,ticket,exit_epoch,entry_h1_epoch,exit_after_h1_bars))
      return;

   string risk_reason="";
   if(RiskPauseOrKill(risk_reason) && risk_reason=="HARD_DRAWDOWN_KILL")
   {
      if(CloseBridgePosition(risk_reason))
      {
         WriteReceipt(intent_id,"EMERGENCY_FLAT",risk_reason,0,0,0.0,g_trade.ResultPrice(),0.0,SpreadBps(),exit_epoch);
         FileDelete(ActiveStatePath());
      }
      return;
   }

   int entry_shift=iBarShift(_Symbol,PERIOD_H1,(datetime)entry_h1_epoch,true);
   bool bar_horizon_reached=(entry_shift>=exit_after_h1_bars);
   if(bar_horizon_reached)
   {
      if(CloseBridgePosition("TIME_EXIT_I_PLUS_24"))
      {
         WriteReceipt(intent_id,"RESOLVED","TIME_EXIT_I_PLUS_24",0,0,0.0,g_trade.ResultPrice(),0.0,SpreadBps(),exit_epoch);
         FileDelete(ActiveStatePath());
      }
   }
}

void RejectCandidate(const Candidate &candidate,const string reason,const double spread_bps)
{
   if(StringLen(candidate.intent_id)>0 && !ReceiptExists(candidate.intent_id))
      WriteReceipt(candidate.intent_id,"REJECTED",reason,0,0,0.0,0.0,0.0,spread_bps,candidate.target_exit_epoch);
   Print(EA_PROGRAM," candidate rejected intent=",candidate.intent_id," reason=",reason);
}

void ProcessCandidate()
{
   Candidate candidate;
   ZeroMemory(candidate);
   string error="";
   if(!LoadCandidate(candidate,error))
   {
      if(error!="CANDIDATE_FILE_NOT_FOUND")
         RejectCandidate(candidate,error,-1.0);
      return;
   }
   if(ReceiptExists(candidate.intent_id))
      return;
   if(!InpArmed)
      return;
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   {
      RejectCandidate(candidate,"ACCOUNT_NOT_DEMO",-1.0);
      return;
   }
   if(InpAllowedDemoLogin<=0 || AccountInfoInteger(ACCOUNT_LOGIN)!=InpAllowedDemoLogin)
   {
      RejectCandidate(candidate,"DEMO_LOGIN_NOT_EXPLICITLY_BOUND",-1.0);
      return;
   }
   string permit_reason="";
   if(!LoadArmingPermit(candidate,permit_reason))
   {
      RejectCandidate(candidate,permit_reason,-1.0);
      return;
   }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      RejectCandidate(candidate,"TERMINAL_OR_ACCOUNT_TRADING_DISABLED",-1.0);
      return;
   }
   datetime now_utc=TimeGMT();
   if(now_utc<=0)
   {
      RejectCandidate(candidate,"UTC_CLOCK_UNAVAILABLE",-1.0);
      return;
   }
   if(now_utc>candidate.expires_epoch || now_utc>candidate.target_entry_epoch+60)
   {
      RejectCandidate(candidate,"CANDIDATE_EXPIRED_OR_ENTRY_WINDOW_MISSED",-1.0);
      return;
   }
   if(now_utc<candidate.target_entry_epoch)
      return;

   string bound_reason="";
   if(QualificationBoundReached(bound_reason))
   {
      RejectCandidate(candidate,"QUALIFICATION_BOUND_REACHED",-1.0);
      return;
   }
   string risk_reason="";
   if(RiskPauseOrKill(risk_reason))
   {
      RejectCandidate(candidate,risk_reason,-1.0);
      return;
   }
   ulong existing_ticket=0;
   if(HasBridgePosition(existing_ticket))
   {
      RejectCandidate(candidate,"MAX_CONCURRENT_POSITION_GUARD",-1.0);
      return;
   }
   if(CountEntryDeals(DayStart(TimeCurrent()))>=InpDailyNewPositionsCap)
   {
      RejectCandidate(candidate,"DAILY_NEW_POSITION_CAP",-1.0);
      return;
   }

   double spread_bps=SpreadBps();
   if(spread_bps<0.0)
   {
      RejectCandidate(candidate,"LIVE_SPREAD_UNAVAILABLE",spread_bps);
      return;
   }
   if(spread_bps>candidate.spread_guard_bps+1e-10)
   {
      RejectCandidate(candidate,"LIVE_SPREAD_GUARD",spread_bps);
      return;
   }

   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double requested_price=(candidate.side=="LONG" ? ask : bid);
   double volume=0.0;
   double actual_ratio=0.0;
   string volume_reason="";
   if(!ComputeTargetVolume(candidate,requested_price,volume,actual_ratio,volume_reason))
   {
      RejectCandidate(candidate,volume_reason,spread_bps);
      return;
   }

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpMaximumSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   string comment="XAUUSD_BD_"+StringSubstr(candidate.intent_id,0,18);
   bool ok=(candidate.side=="LONG")
      ? g_trade.Buy(volume,_Symbol,0.0,0.0,0.0,comment)
      : g_trade.Sell(volume,_Symbol,0.0,0.0,0.0,comment);
   if(!ok)
   {
      WriteReceipt(candidate.intent_id,"REJECTED","ORDER_SEND_FAILED",g_trade.ResultOrder(),g_trade.ResultDeal(),requested_price,g_trade.ResultPrice(),volume,spread_bps,candidate.target_exit_epoch);
      return;
   }

   ulong position_ticket=0;
   HasBridgePosition(position_ticket);
   long entry_h1_server_epoch=(long)iTime(_Symbol,PERIOD_H1,0);
   if(entry_h1_server_epoch<=0)
   {
      CloseBridgePosition("ENTRY_H1_SERVER_TIME_UNAVAILABLE");
      WriteReceipt(candidate.intent_id,"EMERGENCY_FLAT","ENTRY_H1_SERVER_TIME_UNAVAILABLE",g_trade.ResultOrder(),g_trade.ResultDeal(),requested_price,g_trade.ResultPrice(),volume,spread_bps,candidate.target_exit_epoch);
      return;
   }
   SaveActiveState(candidate,position_ticket,entry_h1_server_epoch);
   WriteReceipt(candidate.intent_id,"OPEN_FILLED","RUNTIME_GUARDS_PASSED",g_trade.ResultOrder(),g_trade.ResultDeal(),requested_price,g_trade.ResultPrice(),volume,spread_bps,candidate.target_exit_epoch);
}

int OnInit()
{
   ResetLastError();
   if(!FolderCreate(InpBridgeFolder) && GetLastError()!=0)
      Print(EA_PROGRAM," bridge folder create warning error=",GetLastError());
   ResetLastError();
   if(!FolderCreate(ReceiptFolder()) && GetLastError()!=0)
      Print(EA_PROGRAM," receipt folder create warning error=",GetLastError());
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   EventSetTimer((int)MathMax(1,InpPollSeconds));
   if(InpArmed)
      InitializeRiskState();
   string status=InpArmed ? "ARMED_RUNTIME_GUARDS_REQUIRED" : "DISABLED_DEFAULT_NO_ORDER";
   WriteHeartbeat(status);
   LogRuntimeStatus(status,true);
   if(!InpArmed)
      Print(EA_PROGRAM," DISABLED: no order can be sent. Set arming only after login-bound permit and arming preflight.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteHeartbeat("STOPPED_NO_ORDER");
   LogRuntimeStatus("STOPPED_NO_ORDER",true);
   Comment("");
   Print(EA_PROGRAM," deinitialized reason=",reason);
}

void OnTimer()
{
   string status=InpArmed ? "ARMED_RUNTIME_GUARDS_REQUIRED" : "DISABLED_DEFAULT_NO_ORDER";
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)
   {
      status="BLOCKED_ACCOUNT_NOT_DEMO";
      WriteHeartbeat(status);
      LogRuntimeStatus(status,false);
      return;
   }
   WriteHeartbeat(status);
   LogRuntimeStatus(status,false);
   ProcessActivePosition();
   ProcessCandidate();
}
