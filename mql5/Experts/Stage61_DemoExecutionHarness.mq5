//+------------------------------------------------------------------+
//| Stage61 Demo Execution Harness                                    |
//| Demo-only MT5 EA for operational plumbing tests.                  |
//| This is NOT a live EA and NOT a statistical edge validator.        |
//+------------------------------------------------------------------+
#property strict
#property version   "1.01"
#property description "Stage61 demo-only execution harness. Refuses non-demo accounts by default."

#include <Trade/Trade.mqh>

CTrade g_trade;

input string SignalFileName       = "stage61_demo_signals.csv";
input string ProcessedFileName    = "stage61_demo_processed.csv";
input string TradeSymbol          = "XAUUSD";
input long   MagicNumber          = 610058;
input double FixedLot             = 0.01;
input int    MaxSpreadPoints      = 60;
input int    StopLossPoints       = 500;
input int    TakeProfitPoints     = 500;
input int    MaxOpenPositions     = 1;
input int    MaxOrdersPerDay      = 3;
input int    MaxHoldMinutes       = 180;
input int    PollSeconds          = 15;
input bool   RequireDemoAccount   = true;
input bool   AllowTrading         = false;

string g_processed_ids[];

bool IsDemoAccount()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   return (mode == ACCOUNT_TRADE_MODE_DEMO);
}

bool IsBlank(const string value)
{
   string tmp = value;
   StringTrimLeft(tmp);
   StringTrimRight(tmp);
   return (StringLen(tmp) <= 0);
}

bool SameText(const string a, const string b)
{
   return (StringCompare(a, b, false) == 0);
}

void AddProcessedId(const string signal_id)
{
   int n = ArraySize(g_processed_ids);
   ArrayResize(g_processed_ids, n + 1);
   g_processed_ids[n] = signal_id;
}

bool IsProcessedId(const string signal_id)
{
   for(int i = 0; i < ArraySize(g_processed_ids); i++)
   {
      if(SameText(g_processed_ids[i], signal_id))
         return true;
   }
   return false;
}

void LoadProcessedIds()
{
   ArrayResize(g_processed_ids, 0);

   int handle = FileOpen(ProcessedFileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
      return;

   while(!FileIsEnding(handle))
   {
      string signal_id = FileReadString(handle);
      if(!IsBlank(signal_id) && !SameText(signal_id, "signal_id"))
         AddProcessedId(signal_id);
   }

   FileClose(handle);
}

void SaveProcessedId(const string signal_id)
{
   int handle = FileOpen(ProcessedFileName, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
      handle = FileOpen(ProcessedFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');

   if(handle == INVALID_HANDLE)
   {
      Print("Stage61: could not open processed file: ", ProcessedFileName);
      return;
   }

   FileSeek(handle, 0, SEEK_END);
   FileWrite(handle, signal_id);
   FileClose(handle);
}

int CountOpenHarnessPositions()
{
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      string pos_symbol = PositionGetString(POSITION_SYMBOL);
      long pos_magic = PositionGetInteger(POSITION_MAGIC);

      if(SameText(pos_symbol, TradeSymbol) && pos_magic == MagicNumber)
         count++;
   }

   return count;
}

int CountTodayHarnessDeals()
{
   datetime now_time = TimeCurrent();
   MqlDateTime date_parts;
   TimeToStruct(now_time, date_parts);
   date_parts.hour = 0;
   date_parts.min = 0;
   date_parts.sec = 0;
   datetime day_start = StructToTime(date_parts);

   if(!HistorySelect(day_start, now_time))
      return 0;

   int count = 0;
   int total = HistoryDealsTotal();

   for(int i = total - 1; i >= 0; i--)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0)
         continue;

      string deal_symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
      long deal_magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);

      if(SameText(deal_symbol, TradeSymbol) && deal_magic == MagicNumber && deal_entry == DEAL_ENTRY_IN)
         count++;
   }

   return count;
}

bool SpreadIsAcceptable(const string symbol_value, const int max_spread_points)
{
   double ask = SymbolInfoDouble(symbol_value, SYMBOL_ASK);
   double bid = SymbolInfoDouble(symbol_value, SYMBOL_BID);
   double point = SymbolInfoDouble(symbol_value, SYMBOL_POINT);

   if(ask <= 0.0 || bid <= 0.0 || point <= 0.0)
      return false;

   double spread_points = (ask - bid) / point;
   return (spread_points <= max_spread_points);
}

void ManageMaxHoldMinutes()
{
   datetime now_time = TimeCurrent();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      string pos_symbol = PositionGetString(POSITION_SYMBOL);
      long pos_magic = PositionGetInteger(POSITION_MAGIC);

      if(!SameText(pos_symbol, TradeSymbol) || pos_magic != MagicNumber)
         continue;

      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if((now_time - opened) >= (MaxHoldMinutes * 60))
      {
         bool closed = g_trade.PositionClose(ticket);
         if(!closed)
            Print("Stage61: PositionClose failed, ticket=", ticket, " retcode=", g_trade.ResultRetcode());
      }
   }
}

bool ValidateRuntimeGates(const string signal_id, const int max_spread_points)
{
   if(!AllowTrading)
   {
      Print("Stage61: AllowTrading=false, signal ignored: ", signal_id);
      return false;
   }

   if(RequireDemoAccount && !IsDemoAccount())
   {
      Print("Stage61 hard block: account is not DEMO.");
      return false;
   }

   if(IsBlank(TradeSymbol) || !SymbolSelect(TradeSymbol, true))
   {
      Print("Stage61: symbol unavailable: ", TradeSymbol);
      return false;
   }

   if(CountOpenHarnessPositions() >= MaxOpenPositions)
   {
      Print("Stage61: max open positions reached.");
      return false;
   }

   if(CountTodayHarnessDeals() >= MaxOrdersPerDay)
   {
      Print("Stage61: max daily orders reached.");
      return false;
   }

   int effective_max_spread = max_spread_points;
   if(effective_max_spread <= 0)
      effective_max_spread = MaxSpreadPoints;

   if(!SpreadIsAcceptable(TradeSymbol, effective_max_spread))
   {
      Print("Stage61: spread gate blocked signal: ", signal_id);
      return false;
   }

   return true;
}

bool OpenDemoOrder(const string signal_id,
                   const string side,
                   const double signal_lot,
                   const int signal_sl_points,
                   const int signal_tp_points,
                   const int signal_max_spread_points,
                   const string order_comment)
{
   if(!ValidateRuntimeGates(signal_id, signal_max_spread_points))
      return false;

   double ask = SymbolInfoDouble(TradeSymbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(TradeSymbol, SYMBOL_BID);
   double point = SymbolInfoDouble(TradeSymbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(TradeSymbol, SYMBOL_DIGITS);

   if(ask <= 0.0 || bid <= 0.0 || point <= 0.0)
      return false;

   int sl_points = signal_sl_points;
   int tp_points = signal_tp_points;
   if(sl_points <= 0)
      sl_points = StopLossPoints;
   if(tp_points <= 0)
      tp_points = TakeProfitPoints;

   double requested_lot = signal_lot;
   if(requested_lot <= 0.0)
      requested_lot = FixedLot;

   double use_lot = MathMin(requested_lot, FixedLot);
   g_trade.SetExpertMagicNumber(MagicNumber);

   if(SameText(side, "BUY"))
   {
      double sl = NormalizeDouble(ask - sl_points * point, digits);
      double tp = NormalizeDouble(ask + tp_points * point, digits);
      bool sent = g_trade.Buy(use_lot, TradeSymbol, ask, sl, tp, order_comment);
      if(!sent)
         Print("Stage61: BUY failed for ", signal_id, " retcode=", g_trade.ResultRetcode());
      return sent;
   }

   if(SameText(side, "SELL"))
   {
      double sl = NormalizeDouble(bid + sl_points * point, digits);
      double tp = NormalizeDouble(bid - tp_points * point, digits);
      bool sent = g_trade.Sell(use_lot, TradeSymbol, bid, sl, tp, order_comment);
      if(!sent)
         Print("Stage61: SELL failed for ", signal_id, " retcode=", g_trade.ResultRetcode());
      return sent;
   }

   Print("Stage61: unsupported side for signal ", signal_id, ": ", side);
   return false;
}

void SkipCsvHeader(const int handle)
{
   if(FileIsEnding(handle))
      return;

   // Exporter currently writes 16 columns. Read one header row defensively.
   for(int i = 0; i < 16 && !FileIsEnding(handle); i++)
   {
      FileReadString(handle);
      if(FileIsLineEnding(handle))
         break;
   }
}

void PollSignals()
{
   int handle = FileOpen(SignalFileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
      return;

   SkipCsvHeader(handle);

   while(!FileIsEnding(handle))
   {
      string signal_id = FileReadString(handle);
      string candidate_id = FileReadString(handle);
      string base_candidate_id = FileReadString(handle);
      string context_tag = FileReadString(handle);
      string signal_time_utc = FileReadString(handle);
      string entry_time_utc = FileReadString(handle);
      string file_symbol = FileReadString(handle);
      string side = FileReadString(handle);
      string lot_s = FileReadString(handle);
      string sl_s = FileReadString(handle);
      string tp_s = FileReadString(handle);
      string max_spread_s = FileReadString(handle);
      string max_hold_s = FileReadString(handle);
      string expiry_utc = FileReadString(handle);
      string magic_s = FileReadString(handle);
      string order_comment = FileReadString(handle);

      if(IsBlank(signal_id) || SameText(signal_id, "signal_id"))
         continue;

      if(IsProcessedId(signal_id))
         continue;

      if(!SameText(file_symbol, TradeSymbol))
         continue;

      double lot = StringToDouble(lot_s);
      int sl_points = (int)StringToInteger(sl_s);
      int tp_points = (int)StringToInteger(tp_s);
      int max_spread = (int)StringToInteger(max_spread_s);

      bool sent = OpenDemoOrder(signal_id, side, lot, sl_points, tp_points, max_spread, order_comment);
      if(sent)
      {
         AddProcessedId(signal_id);
         SaveProcessedId(signal_id);
         Print("Stage61 demo order sent for signal: ", signal_id,
               " candidate=", candidate_id,
               " context=", context_tag,
               " entry_utc=", entry_time_utc);
      }
   }

   FileClose(handle);
}

int OnInit()
{
   if(RequireDemoAccount && !IsDemoAccount())
   {
      Print("Stage61 hard block: this EA is demo-only. Remove from chart or use a demo account.");
      return INIT_FAILED;
   }

   if(IsBlank(TradeSymbol))
   {
      Print("Stage61 hard block: TradeSymbol is empty.");
      return INIT_FAILED;
   }

   LoadProcessedIds();

   int timer_seconds = PollSeconds;
   if(timer_seconds < 1)
      timer_seconds = 15;
   EventSetTimer(timer_seconds);

   Print("Stage61 Demo Execution Harness initialized. TradeSymbol=", TradeSymbol,
         " AllowTrading=", AllowTrading,
         " RequireDemoAccount=", RequireDemoAccount);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ManageMaxHoldMinutes();
   PollSignals();
}
