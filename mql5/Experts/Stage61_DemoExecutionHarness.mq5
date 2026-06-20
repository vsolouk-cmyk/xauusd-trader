//+------------------------------------------------------------------+
//| Stage61 Demo Execution Harness                                   |
//| Demo-only MT5 EA for operational plumbing tests.                 |
//| Not a live EA. Not an edge validator.                            |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Stage61 demo-only execution harness. Refuses non-demo accounts by default."

#include <Trade/Trade.mqh>

CTrade trade;

input string SignalFileName = "stage61_demo_signals.csv";
input string ProcessedFileName = "stage61_demo_processed.csv";
input string SymbolName = "XAUUSD";
input long   MagicNumber = 610058;
input double FixedLot = 0.01;
input int    MaxSpreadPoints = 60;
input int    StopLossPoints = 500;
input int    TakeProfitPoints = 500;
input int    MaxOpenPositions = 1;
input int    MaxOrdersPerDay = 3;
input int    MaxHoldMinutes = 180;
input int    PollSeconds = 15;
input bool   RequireDemoAccount = true;
input bool   AllowTrading = false; // keep false until you explicitly enable demo sandbox

string processed_ids[];

bool IsDemoAccount()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   return (mode == ACCOUNT_TRADE_MODE_DEMO);
}

void AddProcessed(const string id)
{
   int n = ArraySize(processed_ids);
   ArrayResize(processed_ids, n + 1);
   processed_ids[n] = id;
}

bool IsProcessed(const string id)
{
   for(int i = 0; i < ArraySize(processed_ids); i++)
   {
      if(processed_ids[i] == id)
         return true;
   }
   return false;
}

void LoadProcessed()
{
   ArrayResize(processed_ids, 0);
   int h = FileOpen(ProcessedFileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
      return;
   while(!FileIsEnding(h))
   {
      string id = FileReadString(h);
      if(StringLen(id) > 0 && id != "signal_id")
         AddProcessed(id);
   }
   FileClose(h);
}

void SaveProcessed(const string id)
{
   int h = FileOpen(ProcessedFileName, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
      h = FileOpen(ProcessedFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
      return;
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, id);
   FileClose(h);
}

int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == SymbolName && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         count++;
   }
   return count;
}

int CountTodayOrders()
{
   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime day_start = StructToTime(dt);
   HistorySelect(day_start, now);
   int count = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) == SymbolName && HistoryDealGetInteger(ticket, DEAL_MAGIC) == MagicNumber)
         count++;
   }
   return count;
}

bool SpreadOK(const string sym, const int max_spread_points)
{
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(ask <= 0 || bid <= 0 || point <= 0)
      return false;
   double spread = (ask - bid) / point;
   return (spread <= max_spread_points);
}

void ManageMaxHold()
{
   datetime now = TimeCurrent();
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != SymbolName || PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if(now - opened >= MaxHoldMinutes * 60)
      {
         trade.PositionClose(ticket);
      }
   }
}

bool OpenDemoOrder(const string signal_id, const string side, const double lot, const int sl_points, const int tp_points, const int max_spread, const string comment)
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
   if(SymbolName == "" || !SymbolSelect(SymbolName, true))
   {
      Print("Stage61: symbol unavailable: ", SymbolName);
      return false;
   }
   if(CountOpenPositions() >= MaxOpenPositions)
   {
      Print("Stage61: max open positions reached.");
      return false;
   }
   if(CountTodayOrders() >= MaxOrdersPerDay)
   {
      Print("Stage61: max daily orders reached.");
      return false;
   }
   if(!SpreadOK(SymbolName, max_spread))
   {
      Print("Stage61: spread gate blocked signal: ", signal_id);
      return false;
   }

   double ask = SymbolInfoDouble(SymbolName, SYMBOL_ASK);
   double bid = SymbolInfoDouble(SymbolName, SYMBOL_BID);
   double point = SymbolInfoDouble(SymbolName, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(SymbolName, SYMBOL_DIGITS);
   double use_lot = MathMin(lot, FixedLot);
   trade.SetExpertMagicNumber(MagicNumber);

   if(side == "BUY")
   {
      double sl = NormalizeDouble(ask - sl_points * point, digits);
      double tp = NormalizeDouble(ask + tp_points * point, digits);
      return trade.Buy(use_lot, SymbolName, ask, sl, tp, comment);
   }
   if(side == "SELL")
   {
      double sl = NormalizeDouble(bid + sl_points * point, digits);
      double tp = NormalizeDouble(bid - tp_points * point, digits);
      return trade.Sell(use_lot, SymbolName, bid, sl, tp, comment);
   }
   return false;
}

void PollSignals()
{
   int h = FileOpen(SignalFileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
      return;

   // header
   if(!FileIsEnding(h))
   {
      for(int i = 0; i < 16 && !FileIsLineEnding(h) && !FileIsEnding(h); i++)
         FileReadString(h);
   }

   while(!FileIsEnding(h))
   {
      string signal_id = FileReadString(h);
      string candidate_id = FileReadString(h);
      string base_candidate_id = FileReadString(h);
      string context_tag = FileReadString(h);
      string signal_time_utc = FileReadString(h);
      string entry_time_utc = FileReadString(h);
      string sym = FileReadString(h);
      string side = FileReadString(h);
      string lot_s = FileReadString(h);
      string sl_s = FileReadString(h);
      string tp_s = FileReadString(h);
      string max_spread_s = FileReadString(h);
      string max_hold_s = FileReadString(h);
      string expiry_utc = FileReadString(h);
      string magic_s = FileReadString(h);
      string comment = FileReadString(h);

      if(StringLen(signal_id) == 0 || signal_id == "signal_id")
         continue;
      if(IsProcessed(signal_id))
         continue;
      if(sym != SymbolName)
         continue;

      double lot = StringToDouble(lot_s);
      int sl_points = (int)StringToInteger(sl_s);
      int tp_points = (int)StringToInteger(tp_s);
      int max_spread = (int)StringToInteger(max_spread_s);

      bool sent = OpenDemoOrder(signal_id, side, lot, sl_points, tp_points, max_spread, comment);
      if(sent)
      {
         AddProcessed(signal_id);
         SaveProcessed(signal_id);
         Print("Stage61 demo order sent for signal: ", signal_id);
      }
   }
   FileClose(h);
}

int OnInit()
{
   if(RequireDemoAccount && !IsDemoAccount())
   {
      Print("Stage61 hard block: this EA is demo-only. Remove from chart or use a demo account.");
      return INIT_FAILED;
   }
   LoadProcessed();
   EventSetTimer(PollSeconds);
   Print("Stage61 Demo Execution Harness initialized. AllowTrading=", AllowTrading);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ManageMaxHold();
   PollSignals();
}
