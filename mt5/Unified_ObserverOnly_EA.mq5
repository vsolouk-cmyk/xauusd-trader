#property strict
#property description "Unified observer-only EA. Reads unified_observer_signal.csv and prints rule status. No execution logic."

input string SignalFileName = "unified_observer_signal.csv";
input int RefreshSeconds = 60;

string GetValue(string key, string &keys[], string &values[], int count)
{
   for(int i = 0; i < count; i++)
   {
      if(keys[i] == key)
         return values[i];
   }
   return "";
}

int LoadSignal(string &keys[], string &values[])
{
   ArrayResize(keys, 0);
   ArrayResize(values, 0);
   int handle = FileOpen(SignalFileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Unified observer bridge file not found: ", SignalFileName, " err=", GetLastError());
      return 0;
   }

   int count = 0;
   bool first = true;
   while(!FileIsEnding(handle))
   {
      string k = FileReadString(handle);
      string v = "";
      if(!FileIsEnding(handle))
         v = FileReadString(handle);

      if(first)
      {
         first = false;
         if(k == "key")
            continue;
      }

      if(StringLen(k) > 0)
      {
         ArrayResize(keys, count + 1);
         ArrayResize(values, count + 1);
         keys[count] = k;
         values[count] = v;
         count++;
      }
   }
   FileClose(handle);
   return count;
}

void PrintSignal()
{
   string keys[];
   string values[];
   int count = LoadSignal(keys, values);
   if(count <= 0)
      return;

   Print("Unified observer bridge");
   Print("feature_date=", GetValue("feature_date", keys, values, count));
   Print("mode=", GetValue("mode", keys, values, count));
   Print("any_signal_active=", GetValue("any_signal_active", keys, values, count));
   Print("selected_rule=", GetValue("selected_rule_id", keys, values, count));
   Print("selected_label=", GetValue("selected_label", keys, values, count));
   Print("execution_allowed=", GetValue("execution_allowed", keys, values, count));
   Print("K06_primary_active=", GetValue("primary_signal_active", keys, values, count), " failures=", GetValue("primary_failures", keys, values, count));
   Print("K06_active=", GetValue("K06_active", keys, values, count), " failures=", GetValue("K06_failures", keys, values, count));
   Print("K03_active=", GetValue("K03_active", keys, values, count), " failures=", GetValue("K03_failures", keys, values, count));
   Print("K07_active=", GetValue("K07_active", keys, values, count), " failures=", GetValue("K07_failures", keys, values, count));
   Print("S83_14_active=", GetValue("S83_14_active", keys, values, count), " failures=", GetValue("S83_14_failures", keys, values, count));
   Print("S83_13_active=", GetValue("S83_13_active", keys, values, count), " failures=", GetValue("S83_13_failures", keys, values, count));
   Print("C96_07_active=", GetValue("C96_07_active", keys, values, count), " failures=", GetValue("C96_07_failures", keys, values, count));
}

int OnInit()
{
   EventSetTimer(RefreshSeconds);
   PrintSignal();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PrintSignal();
}
