#property strict
#property description "K06 observer bridge display only"

input string InpSignalFile = "k06_observer_signal.csv";
input int InpTimerSeconds = 15;
input bool InpAllowExecution = false;

string g_thesis = "";
string g_feature_date = "";
string g_signal_active = "false";
string g_mode = "";
string g_execution_allowed = "false";
string g_failures = "";

string TrimCopy(string input_value)
{
   string v = input_value;
   StringTrimLeft(v);
   StringTrimRight(v);
   return v;
}

void ResetState()
{
   g_thesis = "";
   g_feature_date = "";
   g_signal_active = "false";
   g_mode = "";
   g_execution_allowed = "false";
   g_failures = "";
}

void AssignField(string key, string value)
{
   if(key == "thesis" || key == "thesis_id") g_thesis = value;
   else if(key == "feature_date") g_feature_date = value;
   else if(key == "latest_feature_date_utc" && g_feature_date == "") g_feature_date = value;
   else if(key == "signal_active") g_signal_active = value;
   else if(key == "mode") g_mode = value;
   else if(key == "ea_mode" && g_mode == "") g_mode = value;
   else if(key == "execution_allowed") g_execution_allowed = value;
   else if(key == "failures" || key == "rule_failures") g_failures = value;
}

bool LoadBridgeFile()
{
   ResetState();
   int h = FileOpen(InpSignalFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("K06 observer bridge file not found: ", InpSignalFile, " error=", GetLastError());
      return false;
   }
   bool first_line = true;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      if(line == "") continue;
      if(first_line)
      {
         first_line = false;
         if(StringFind(line, "key,value") == 0) continue;
      }
      int pos = StringFind(line, ",");
      if(pos <= 0) continue;
      string key = TrimCopy(StringSubstr(line, 0, pos));
      string value = TrimCopy(StringSubstr(line, pos + 1));
      AssignField(key, value);
   }
   FileClose(h);
   return true;
}

void PrintState()
{
   Print("K06 observer bridge");
   Print("thesis=", g_thesis);
   Print("feature_date=", g_feature_date);
   Print("signal_active=", g_signal_active);
   Print("mode=", g_mode);
   Print("execution_allowed=", g_execution_allowed);
   Print("failures=", g_failures);
}

void DrawState()
{
   string text = "K06 observer\n";
   text += "thesis: " + g_thesis + "\n";
   text += "date: " + g_feature_date + "\n";
   text += "active: " + g_signal_active + "\n";
   text += "mode: " + g_mode + "\n";
   text += "failures: " + g_failures + "\n";
   Comment(text);
}

int OnInit()
{
   if(InpAllowExecution)
   {
      Print("K06 observer disabled because execution flag is true.");
      return INIT_FAILED;
   }
   EventSetTimer(InpTimerSeconds);
   LoadBridgeFile();
   PrintState();
   DrawState();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
   Print("K06 observer deinitialized. Reason=", reason);
}

void OnTick()
{
   DrawState();
}

void OnTimer()
{
   if(LoadBridgeFile())
   {
      PrintState();
      DrawState();
   }
}
