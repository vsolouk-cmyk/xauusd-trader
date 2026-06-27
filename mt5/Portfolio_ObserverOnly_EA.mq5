#property strict
#property description "Expanded portfolio observer display only"

input string InpSignalFile = "portfolio_observer_signal.csv";
input int InpTimerSeconds = 15;
input bool InpAllowExecution = false;

string g_feature_date = "";
string g_mode = "";
string g_any_active = "false";
string g_selected_rule = "";
string g_selected_label = "";
string g_k06_active = "false";
string g_k03_active = "false";
string g_k07_active = "false";
string g_s8314_active = "false";
string g_s8313_active = "false";
string g_k06_failures = "";
string g_k03_failures = "";
string g_k07_failures = "";
string g_s8314_failures = "";
string g_s8313_failures = "";
bool g_loaded = false;

string TrimCopy(string input_value)
{
   string v = input_value;
   StringTrimLeft(v);
   StringTrimRight(v);
   return v;
}

string LowerCopy(string input_value)
{
   string v = input_value;
   StringToLower(v);
   return v;
}

bool TextIsTrue(string input_value)
{
   string v = LowerCopy(TrimCopy(input_value));
   return (v == "true" || v == "1" || v == "yes");
}

void ResetState()
{
   g_feature_date = "";
   g_mode = "";
   g_any_active = "false";
   g_selected_rule = "";
   g_selected_label = "";
   g_k06_active = "false";
   g_k03_active = "false";
   g_k07_active = "false";
   g_s8314_active = "false";
   g_s8313_active = "false";
   g_k06_failures = "";
   g_k03_failures = "";
   g_k07_failures = "";
   g_s8314_failures = "";
   g_s8313_failures = "";
   g_loaded = false;
}

void AssignField(string key, string value)
{
   if(key == "feature_date") g_feature_date = value;
   else if(key == "mode") g_mode = value;
   else if(key == "portfolio_mode" && g_mode == "") g_mode = value;
   else if(key == "any_signal_active") g_any_active = value;
   else if(key == "selected_rule_id") g_selected_rule = value;
   else if(key == "selected_label") g_selected_label = value;
   else if(key == "K06_active") g_k06_active = value;
   else if(key == "K03_active") g_k03_active = value;
   else if(key == "K07_active") g_k07_active = value;
   else if(key == "S83_14_active") g_s8314_active = value;
   else if(key == "S83_13_active") g_s8313_active = value;
   else if(key == "K06_failures") g_k06_failures = value;
   else if(key == "K03_failures") g_k03_failures = value;
   else if(key == "K07_failures") g_k07_failures = value;
   else if(key == "S83_14_failures") g_s8314_failures = value;
   else if(key == "S83_13_failures") g_s8313_failures = value;
   else if(key == "K06_RESILIENT_GOLD_VS_DXY_H120_signal_active") g_k06_active = value;
   else if(key == "K03_SAFE_HAVEN_REALYIELD_H120_signal_active") g_k03_active = value;
   else if(key == "K07_DXY_TREND_RELIEF_GOLD_TREND_H120_signal_active") g_k07_active = value;
   else if(key == "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120_signal_active") g_s8314_active = value;
   else if(key == "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120_signal_active") g_s8313_active = value;
   else if(key == "K06_RESILIENT_GOLD_VS_DXY_H120_failures") g_k06_failures = value;
   else if(key == "K03_SAFE_HAVEN_REALYIELD_H120_failures") g_k03_failures = value;
   else if(key == "K07_DXY_TREND_RELIEF_GOLD_TREND_H120_failures") g_k07_failures = value;
   else if(key == "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120_failures") g_s8314_failures = value;
   else if(key == "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120_failures") g_s8313_failures = value;
}

bool LoadBridgeFile()
{
   ResetState();
   int h = FileOpen(InpSignalFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("Portfolio observer bridge file not found: ", InpSignalFile, " error=", GetLastError());
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
   g_loaded = true;
   return true;
}

void PrintState()
{
   Print("Expanded portfolio observer bridge");
   Print("feature_date=", g_feature_date);
   Print("mode=", g_mode);
   Print("any_signal_active=", g_any_active);
   Print("selected_rule=", g_selected_rule);
   Print("selected_label=", g_selected_label);
   Print("execution_allowed=false");
   Print("K06_active=", g_k06_active, " failures=", g_k06_failures);
   Print("K03_active=", g_k03_active, " failures=", g_k03_failures);
   Print("K07_active=", g_k07_active, " failures=", g_k07_failures);
   Print("S83_14_active=", g_s8314_active, " failures=", g_s8314_failures);
   Print("S83_13_active=", g_s8313_active, " failures=", g_s8313_failures);
}

void DrawState()
{
   string text = "Expanded portfolio observer\n";
   text += "date: " + g_feature_date + "\n";
   text += "mode: " + g_mode + "\n";
   text += "any active: " + g_any_active + "\n";
   text += "selected: " + g_selected_rule + "\n";
   text += "K06: " + g_k06_active + "\n";
   text += "K03: " + g_k03_active + "\n";
   text += "K07: " + g_k07_active + "\n";
   text += "S83_14: " + g_s8314_active + "\n";
   text += "S83_13: " + g_s8313_active + "\n";
   Comment(text);
}

int OnInit()
{
   if(InpAllowExecution)
   {
      Print("Expanded portfolio observer disabled because execution flag is true.");
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
   Print("Expanded portfolio observer deinitialized. Reason=", reason);
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
