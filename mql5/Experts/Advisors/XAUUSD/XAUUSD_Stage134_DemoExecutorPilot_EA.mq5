#property strict

#include <Trade/Trade.mqh>

input bool InpEnableDemoOrders = false;
input bool InpRequireDemoAccount = true;
input double InpLots = 0.01;
input double InpMaxLots = 0.01;
input int InpMagic = 1340001;
input int InpPollSeconds = 30;
input int InpMaxSignalAgeSec = 7200;
input int InpMinSecondsBetweenOrderAttempts = 60;
input int InpMaxOpenPositions = 1;
input int InpMaxSpreadPoints = 120;
input int InpDeviationPoints = 30;
input int InpStopLossPoints = 1200;
input int InpTakeProfitPoints = 1800;
input int InpMaxHoldMinutes = 240;
input string InpAllowedRules = "*";
input string InpRuleStateKvFile = "xauusd_stage133_unified_observer_rule_state_kv.csv";
input string InpStatusKvFile = "xauusd_stage134_demo_executor_status_kv.csv";
input string InpTradeLogFile = "xauusd_stage134_demo_executor_trade_log.csv";
input string InpStateKvFile = "xauusd_stage134_demo_executor_state_kv.csv";

CTrade g_trade;
datetime g_last_eval = 0;
datetime g_last_order_attempt_time = 0;
string g_last_attempt_signal_key = "";
string g_last_success_signal_key = "";
string g_last_retcode = "";
string g_last_retcode_description = "";

string BoolText(bool v){ return(v ? "true" : "false"); }
string CleanCell(string v){ StringReplace(v,"\r"," "); StringReplace(v,"\n"," "); if(StringLen(v)>240) v=StringSubstr(v,0,237)+"..."; return(v); }
bool IsTrueText(string v){ StringToLower(v); return(v=="true" || v=="1" || v=="yes" || v=="active"); }
string TrimText(string v){ StringTrimLeft(v); StringTrimRight(v); return(v); }


bool IsAcceptedRetcode(string retcode)
{
   string r = TrimText(retcode);
   return(r == "10008" || r == "10009" || r == "10010");
}

bool IsRetryableRetcode(string retcode)
{
   string r = TrimText(retcode);
   return(r == "10018"); // market closed; must not become a duplicate/success blocker
}

string RetryableText(string retcode)
{
   return(IsRetryableRetcode(retcode) ? "true" : "false");
}

string ReadKvValueFromFile(string file_name, string key, string fallback="")
{
   int h = FileOpen(file_name, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return(fallback);
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      int sep = StringFind(line, "|");
      if(sep < 0) sep = StringFind(line, ",");
      if(sep < 0) continue;
      string k = TrimText(StringSubstr(line, 0, sep));
      string v = TrimText(StringSubstr(line, sep + 1));
      if(k == key){ FileClose(h); return(v); }
   }
   FileClose(h);
   return(fallback);
}

datetime FileModifiedTime(string file_name)
{
   if(!FileIsExist(file_name)) return(0);
   long mt = FileGetInteger(file_name, FILE_MODIFY_DATE);
   return((datetime)mt);
}

bool IsDemoAccount(){ return(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO); }
string TradeModeText()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode == ACCOUNT_TRADE_MODE_DEMO) return("DEMO");
   if(mode == ACCOUNT_TRADE_MODE_REAL) return("REAL");
   if(mode == ACCOUNT_TRADE_MODE_CONTEST) return("CONTEST");
   return("UNKNOWN");
}

bool IsRuleAllowed(string rid)
{
   string allowed_raw = TrimText(InpAllowedRules);
   string allowed_lc = allowed_raw;
   StringToLower(allowed_lc);
   if(allowed_raw == "" || allowed_raw == "*" || allowed_lc == "any" || allowed_lc == "all")
      return(true);
   string allowed = "," + allowed_raw + ",";
   string needle = "," + rid + ",";
   return(StringFind(allowed, needle) >= 0);
}

int CountOpenPositions()
{
   int count = 0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic) count++;
   }
   return(count);
}

void AppendTradeLog(string event_type, string signal_key, string rule_id, string feature_date, double lot, double price, double sl, double tp, bool ok, string retcode, string retcode_desc)
{
   bool exists = FileIsExist(InpTradeLogFile);
   int h = FileOpen(InpTradeLogFile, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(h == INVALID_HANDLE) return;
   if(!exists || FileSize(h) == 0)
      FileWrite(h,"time_local","time_current","symbol","event_type","signal_key","rule_id","feature_date","lot","price","sl","tp","ok","retcode","retcode_description","account_mode","demo_required","demo_orders_enabled","note");
   FileSeek(h, 0, SEEK_END);
   FileWrite(h,TimeToString(TimeLocal(),TIME_DATE|TIME_SECONDS),TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),_Symbol,event_type,signal_key,rule_id,feature_date,DoubleToString(lot,2),DoubleToString(price,_Digits),DoubleToString(sl,_Digits),DoubleToString(tp,_Digits),BoolText(ok),retcode,retcode_desc,TradeModeText(),BoolText(InpRequireDemoAccount),BoolText(InpEnableDemoOrders),"stage134_demo_only_execution_pilot");
   FileClose(h);
}

void WriteState()
{
   int h = FileOpen(InpStateKvFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h,"last_attempt_signal_key|"+g_last_attempt_signal_key+"\n");
   FileWriteString(h,"last_success_signal_key|"+g_last_success_signal_key+"\n");
   FileWriteString(h,"last_order_attempt_time|"+TimeToString(g_last_order_attempt_time,TIME_DATE|TIME_SECONDS)+"\n");
   FileClose(h);
}
void LoadState(){ g_last_attempt_signal_key=ReadKvValueFromFile(InpStateKvFile,"last_attempt_signal_key",""); g_last_success_signal_key=ReadKvValueFromFile(InpStateKvFile,"last_success_signal_key",""); }

void CloseExpiredPositions()
{
   if(InpMaxHoldMinutes <= 0) return;
   datetime now = TimeCurrent();
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      datetime open_time = (datetime)PositionGetInteger(POSITION_TIME);
      if((now - open_time) >= InpMaxHoldMinutes*60)
      {
         bool ok = g_trade.PositionClose(ticket, InpDeviationPoints);
         AppendTradeLog("TIME_EXIT", "", "", "", 0, 0, 0, 0, ok, IntegerToString((int)g_trade.ResultRetcode()), g_trade.ResultRetcodeDescription());
      }
   }
}

void WriteStatusKv(string decision, string reason, string selected_rule_id, string feature_date, string any_signal_active, string active_rule_count, bool signal_fresh, int signal_age_sec, bool spread_ok, int spread_points, int open_positions, bool order_attempted)
{
   int h = FileOpen(InpStatusKvFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h,"stage|Stage134_DEMO_EXECUTOR_PILOT\n");
   FileWriteString(h,"status|DEMO_EXECUTOR_RUNTIME_ALIVE\n");
   FileWriteString(h,"decision|"+decision+"\n");
   FileWriteString(h,"reason|"+CleanCell(reason)+"\n");
   FileWriteString(h,"allow_real_account|false\n");
   FileWriteString(h,"demo_orders_enabled|"+BoolText(InpEnableDemoOrders)+"\n");
   FileWriteString(h,"require_demo_account|"+BoolText(InpRequireDemoAccount)+"\n");
   FileWriteString(h,"account_mode|"+TradeModeText()+"\n");
   FileWriteString(h,"demo_account_ok|"+BoolText(IsDemoAccount())+"\n");
   FileWriteString(h,"terminal_trade_allowed|"+BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))+"\n");
   FileWriteString(h,"mql_trade_allowed|"+BoolText((bool)MQLInfoInteger(MQL_TRADE_ALLOWED))+"\n");
   FileWriteString(h,"account_trade_allowed|"+BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"\n");
   FileWriteString(h,"symbol|"+_Symbol+"\n");
   FileWriteString(h,"period|"+IntegerToString(_Period)+"\n");
   FileWriteString(h,"time_local|"+TimeToString(TimeLocal(),TIME_DATE|TIME_SECONDS)+"\n");
   FileWriteString(h,"time_current|"+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\n");
   FileWriteString(h,"selected_rule_id|"+selected_rule_id+"\n");
   FileWriteString(h,"allowed_rules|"+CleanCell(InpAllowedRules)+"\n");
   FileWriteString(h,"feature_date|"+feature_date+"\n");
   FileWriteString(h,"any_signal_active|"+any_signal_active+"\n");
   FileWriteString(h,"active_rule_count|"+active_rule_count+"\n");
   FileWriteString(h,"signal_fresh|"+BoolText(signal_fresh)+"\n");
   FileWriteString(h,"signal_age_sec|"+IntegerToString(signal_age_sec)+"\n");
   FileWriteString(h,"spread_ok|"+BoolText(spread_ok)+"\n");
   FileWriteString(h,"spread_points|"+IntegerToString(spread_points)+"\n");
   FileWriteString(h,"open_positions|"+IntegerToString(open_positions)+"\n");
   FileWriteString(h,"max_open_positions|"+IntegerToString(InpMaxOpenPositions)+"\n");
   FileWriteString(h,"lot|"+DoubleToString(MathMin(InpLots,InpMaxLots),2)+"\n");
   FileWriteString(h,"order_attempted|"+BoolText(order_attempted)+"\n");
   FileWriteString(h,"last_retcode|"+g_last_retcode+"\n");
   FileWriteString(h,"last_retcode_description|"+CleanCell(g_last_retcode_description)+"\n");
   FileWriteString(h,"last_retcode_retryable|"+RetryableText(g_last_retcode)+"\n");
   FileWriteString(h,"last_attempt_signal_key|"+g_last_attempt_signal_key+"\n");
   FileWriteString(h,"last_success_signal_key|"+g_last_success_signal_key+"\n");
   FileClose(h);
}

void EvaluateSignal()
{
   CloseExpiredPositions();
   datetime now = TimeCurrent();
   datetime mt = FileModifiedTime(InpRuleStateKvFile);
   int signal_age_sec = (mt > 0 ? (int)(TimeLocal() - mt) : 999999);
   bool signal_fresh = (mt > 0 && signal_age_sec >= 0 && signal_age_sec <= InpMaxSignalAgeSec);
   string selected_rule_id = CleanCell(ReadKvValueFromFile(InpRuleStateKvFile,"selected_rule_id",""));
   string feature_date = CleanCell(ReadKvValueFromFile(InpRuleStateKvFile,"feature_date",""));
   string any_signal_active = CleanCell(ReadKvValueFromFile(InpRuleStateKvFile,"any_signal_active",""));
   string active_rule_count = CleanCell(ReadKvValueFromFile(InpRuleStateKvFile,"active_rule_count","0"));
   string signal_key = feature_date + "|" + selected_rule_id;
   int spread_points = (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   bool spread_ok = (spread_points > 0 && spread_points <= InpMaxSpreadPoints);
   int open_positions = CountOpenPositions();
   bool order_attempted = false;
   string decision = "HOLD";
   string reason = "no actionable signal";

   if(!InpEnableDemoOrders){ decision="BLOCKED_NOT_ARMED"; reason="InpEnableDemoOrders=false"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(InpRequireDemoAccount && !IsDemoAccount()){ decision="BLOCKED_NOT_DEMO_ACCOUNT"; reason="RequireDemoAccount=true but account is not demo"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)){ decision="BLOCKED_TRADING_NOT_ALLOWED"; reason="terminal/mql/account trading flag is disabled"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(!signal_fresh){ decision="BLOCKED_SIGNAL_STALE"; reason="Stage133 rule-state telemetry is stale or missing"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(!IsTrueText(any_signal_active) || selected_rule_id=="" || !IsRuleAllowed(selected_rule_id)){ decision="HOLD_NO_ACTIVE_ALLOWED_RULE"; reason="no active selected rule"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(!spread_ok){ decision="BLOCKED_SPREAD"; reason="spread above guard"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(open_positions >= InpMaxOpenPositions){ decision="BLOCKED_MAX_OPEN_POSITIONS"; reason="max open positions reached"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(signal_key == g_last_success_signal_key){ decision="HOLD_SIGNAL_ALREADY_EXECUTED"; reason="same feature_date|rule_id already executed successfully"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   if(signal_key == g_last_attempt_signal_key && g_last_order_attempt_time > 0 && (now - g_last_order_attempt_time) < InpMinSecondsBetweenOrderAttempts)
   {
      if(IsRetryableRetcode(g_last_retcode))
      {
         decision="HOLD_RETRYABLE_REJECT_COOLDOWN";
         reason="last attempt was retryable (market closed); will retry after cooldown, not treated as executed";
      }
      else
      {
         decision="HOLD_RETRY_COOLDOWN";
         reason="same signal attempted recently";
      }
      WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted);
      return;
   }

   double lot = MathMin(InpLots, InpMaxLots);
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(lot < min_lot) lot = min_lot;
   if(lot > max_lot) lot = max_lot;
   if(step > 0.0) lot = MathFloor(lot/step)*step;
   lot = NormalizeDouble(lot, 2);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(ask <= 0.0){ decision="BLOCKED_NO_ASK_PRICE"; reason="ask price unavailable"; WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,open_positions,order_attempted); return; }
   double sl = NormalizeDouble(ask - InpStopLossPoints*_Point, _Digits);
   double tp = NormalizeDouble(ask + InpTakeProfitPoints*_Point, _Digits);
   string comment = "Stage134Demo|" + selected_rule_id;
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   order_attempted = true;
   g_last_order_attempt_time = now;
   g_last_attempt_signal_key = signal_key;
   bool ok = g_trade.Buy(lot, _Symbol, ask, sl, tp, comment);
   g_last_retcode = IntegerToString((int)g_trade.ResultRetcode());
   g_last_retcode_description = g_trade.ResultRetcodeDescription();
   bool accepted_retcode = IsAcceptedRetcode(g_last_retcode);
   if(ok && accepted_retcode)
   {
      g_last_success_signal_key=signal_key;
      decision="DEMO_BUY_SENT";
      reason="demo BUY order accepted";
   }
   else if(IsRetryableRetcode(g_last_retcode))
   {
      decision="DEMO_BUY_REJECTED_RETRYABLE_MARKET_CLOSED";
      reason="demo BUY rejected because market is closed; signal is not marked successful and can retry after market opens";
   }
   else
   {
      decision="DEMO_BUY_REJECTED";
      reason="demo BUY order rejected by terminal/broker";
   }
   WriteState();
   AppendTradeLog("DEMO_BUY_ATTEMPT", signal_key, selected_rule_id, feature_date, lot, ask, sl, tp, ok, g_last_retcode, g_last_retcode_description);
   WriteStatusKv(decision,reason,selected_rule_id,feature_date,any_signal_active,active_rule_count,signal_fresh,signal_age_sec,spread_ok,spread_points,CountOpenPositions(),order_attempted);
}

int OnInit(){ LoadState(); EventSetTimer(MathMax(10,InpPollSeconds)); g_trade.SetExpertMagicNumber(InpMagic); EvaluateSignal(); Print("Stage134 DemoExecutorPilot initialized. Demo-only order path. RequireDemoAccount=",BoolText(InpRequireDemoAccount)," EnableDemoOrders=",BoolText(InpEnableDemoOrders)); return(INIT_SUCCEEDED); }
void OnDeinit(const int reason){ EventKillTimer(); WriteState(); Print("Stage134 DemoExecutorPilot deinitialized. reason=",reason); }
void OnTick(){ datetime now=TimeCurrent(); if(g_last_eval==0 || (now-g_last_eval)>=MathMax(10,InpPollSeconds)){ g_last_eval=now; EvaluateSignal(); } }
void OnTimer(){ EvaluateSignal(); }
