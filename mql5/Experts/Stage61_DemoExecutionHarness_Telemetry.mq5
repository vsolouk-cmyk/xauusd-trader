#property strict
#property version   "1.10"
#property description "Stage61 demo-only telemetry harness. Reads stage61_demo_signals.csv and writes stage61_ea_status.csv. No live trading authorization."

input string TradeSymbol = "XAUUSD";
input string SignalFileName = "stage61_demo_signals.csv";
input string StatusFileName = "stage61_ea_status.csv";
input bool RequireDemoAccount = true;
input bool AllowTrading = false;
input double FixedLot = 0.01;
input int MaxOpenPositions = 1;
input int MaxOrdersPerDay = 3;
input int PollSeconds = 5;

string LastStatus = "INIT";
int LastValidRows = 0;
int LastInvalidRows = 0;
string LastMessage = "";

void WriteStatus(const string status, const int valid_rows, const int invalid_rows, const string message)
{
   int h = FileOpen(StatusFileName, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
   {
      Print("Stage61 telemetry: cannot write status file: ", StatusFileName, " error=", GetLastError());
      return;
   }
   FileWrite(h, "key", "value");
   FileWrite(h, "timestamp_server", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   FileWrite(h, "account_login", IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)));
   FileWrite(h, "account_server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(h, "account_trade_mode", IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)));
   FileWrite(h, "require_demo_account", RequireDemoAccount ? "true" : "false");
   FileWrite(h, "allow_trading", AllowTrading ? "true" : "false");
   FileWrite(h, "trade_symbol", TradeSymbol);
   FileWrite(h, "signal_file", SignalFileName);
   FileWrite(h, "status", status);
   FileWrite(h, "valid_rows", IntegerToString(valid_rows));
   FileWrite(h, "invalid_rows", IntegerToString(invalid_rows));
   FileWrite(h, "orders_created", "0");
   FileWrite(h, "message", message);
   FileClose(h);
}

bool IsDemoAccount()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   return (mode == ACCOUNT_TRADE_MODE_DEMO);
}

bool IsSignalHeader(const string line)
{
   return (StringFind(line, "signal_id") >= 0 && StringFind(line, "entry_time_utc") >= 0 && StringFind(line, "direction") >= 0);
}

bool IsValidSignalRow(const string line)
{
   string cells[];
   int n = StringSplit(line, ',', cells);
   if(n < 13)
      return false;
   if(StringLen(cells[0]) <= 0) return false;
   if(StringLen(cells[4]) <= 0) return false;
   if(StringLen(cells[5]) <= 0) return false;
   string dir = cells[5];
   if(StringCompare(dir, "BUY") != 0 && StringCompare(dir, "SELL") != 0 && StringCompare(dir, "LONG") != 0 && StringCompare(dir, "SHORT") != 0)
      return false;
   return true;
}

void ParseSignalsNoOrder()
{
   if(RequireDemoAccount && !IsDemoAccount())
   {
      LastStatus = "BLOCKED_NOT_DEMO";
      LastValidRows = 0;
      LastInvalidRows = 0;
      LastMessage = "RequireDemoAccount=true and current account is not demo";
      WriteStatus(LastStatus, LastValidRows, LastInvalidRows, LastMessage);
      Print("Stage61 telemetry: ", LastStatus, " - ", LastMessage);
      return;
   }

   int h = FileOpen(SignalFileName, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      LastStatus = "SIGNAL_FILE_NOT_FOUND";
      LastValidRows = 0;
      LastInvalidRows = 0;
      LastMessage = "Cannot open signal file in MQL5/Files";
      WriteStatus(LastStatus, LastValidRows, LastInvalidRows, LastMessage);
      Print("Stage61 telemetry: ", LastStatus, " file=", SignalFileName, " error=", GetLastError());
      return;
   }

   bool header_seen = false;
   int valid_rows = 0;
   int invalid_rows = 0;

   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      if(StringLen(line) == 0)
         continue;
      if(!header_seen)
      {
         header_seen = IsSignalHeader(line);
         if(!header_seen)
            invalid_rows++;
         continue;
      }
      if(IsValidSignalRow(line))
         valid_rows++;
      else
         invalid_rows++;
   }
   FileClose(h);

   LastValidRows = valid_rows;
   LastInvalidRows = invalid_rows;

   if(!header_seen)
   {
      LastStatus = "INVALID_HEADER";
      LastMessage = "CSV header did not match expected Stage61 signal schema";
   }
   else if(valid_rows == 0 && invalid_rows == 0)
   {
      LastStatus = "PARSE_OK_EMPTY_NO_ORDER";
      LastMessage = "Header parsed, no signal rows, no orders allowed in telemetry test";
   }
   else if(valid_rows > 0 && !AllowTrading)
   {
      LastStatus = "PARSE_OK_TRADING_DISABLED_NO_ORDER";
      LastMessage = "Valid signal rows parsed; AllowTrading=false so no order is sent";
   }
   else if(valid_rows > 0 && AllowTrading)
   {
      LastStatus = "PARSE_OK_TRADING_FLAG_TRUE_BUT_TELEMETRY_NO_ORDER";
      LastMessage = "This telemetry harness never sends orders; use the execution harness for tiny demo order test";
   }
   else
   {
      LastStatus = "PARSE_NO_VALID_ROWS";
      LastMessage = "Header parsed but no valid signal rows were found";
   }

   WriteStatus(LastStatus, LastValidRows, LastInvalidRows, LastMessage);
   Print("Stage61 telemetry: ", LastStatus, " valid_rows=", valid_rows, " invalid_rows=", invalid_rows, " allow_trading=", (AllowTrading ? "true" : "false"));
}

int OnInit()
{
   EventSetTimer(PollSeconds);
   WriteStatus("INIT", 0, 0, "EA initialized; waiting for timer parse");
   Print("Stage61 telemetry initialized. SignalFile=", SignalFileName, " StatusFile=", StatusFileName, " AllowTrading=", (AllowTrading ? "true" : "false"));
   ParseSignalsNoOrder();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteStatus("DEINIT", LastValidRows, LastInvalidRows, "EA deinitialized");
}

void OnTimer()
{
   ParseSignalsNoOrder();
}
