//+------------------------------------------------------------------+
//| TradingJournalBridge.mq5                                         |
//| Pushes raw MT5 deals and a heartbeat to the mt5-bridge API.      |
//|                                                                  |
//| Written from scratch on native WebRequest (no DLL). See          |
//| docs/integrations/README.md (spec 002, Task 1 verdict).          |
//|                                                                  |
//| REQUIRED USER STEP: add the ApiUrl origin (for example           |
//| https://api.example.com) to Tools > Options > Expert Advisors >  |
//| "Allow WebRequest for listed URL". Without it every request      |
//| fails with "URL not allowed" and the EA shows an Alert.          |
//|                                                                  |
//| Contract (kept in sync by tests/unit/test_ea_contract.py):       |
//|  POST /api/v1/mt5-bridge/ingest/heartbeat  (sent first in OnInit |
//|       and every 60 s; only the heartbeat creates the account)    |
//|  POST /api/v1/mt5-bridge/ingest/deals      (<= 200 raw deals)    |
//|  Headers: Content-Type: application/json, Authorization: Bearer  |
//|  Times: UTC ISO "YYYY-MM-DDTHH:MM:SSZ"; decimals as JSON strings |
//|  Answers: 2xx done; 401 stop and ask for a new token;            |
//|  503/5xx/408/429/network: keep queued, retry with exponential    |
//|  backoff capped at 5 min; any other 4xx: drop the batch and log. |
//|                                                                  |
//| The token is never printed, alerted, commented or written to a   |
//| file. It only travels in the request header.                     |
//+------------------------------------------------------------------+
#property copyright   "Trading Journal"
#property version     "1.00"
#property description "Sends your MT5 deals to your Trading Journal account (spec 002)."

//--- inputs
input string ApiUrl                 = "";    // API origin only, e.g. https://api.example.com (no path)
input string IngestToken            = "";    // Ingest token created in the web app (shown once)
input bool   AutoServerOffset       = true;  // Detect broker server time offset to UTC
input int    ServerUtcOffsetMinutes = 0;     // Used only when AutoServerOffset = false

//--- contract constants (must match the bridge; checked by test_ea_contract.py)
#define DEALS_PATH            "/api/v1/mt5-bridge/ingest/deals"
#define HEARTBEAT_PATH        "/api/v1/mt5-bridge/ingest/heartbeat"
#define BATCH_SIZE            200
#define HEARTBEAT_SECONDS     60

//--- local tuning
#define HTTP_TIMEOUT_MS       15000      // per request
#define BACKOFF_BASE_SECONDS  60         // first retry delay; doubles per failure
#define BACKOFF_CAP_SECONDS   300        // 5 minutes
#define MAX_BATCHES_PER_FLUSH 25         // keeps one flush short; the rest goes on the next timer
#define STATE_FOLDER          "TradingJournalBridge"   // under <data folder>\MQL5\Files
#define OFFSET_STEP_SECONDS   1800       // broker offsets are whole or half hours
#define SCAN_OVERLAP_SECONDS  300        // re-read the last 5 min of history on every scan
#define STARTUP_RESCAN_SECONDS 259200    // 3 days re-read on every start (duplicates are harmless)
#define MAX_COMMENT_CHARS     256        // bridge DealIn.comment max_length
#define MAX_SYMBOL_CHARS      64         // bridge DealIn.symbol max_length

enum SendOutcome
  {
   SEND_OK,            // accepted
   SEND_RETRY,         // keep the data and retry later
   SEND_DROP,          // can never be accepted: drop it
   SEND_UNAUTHORIZED   // token unknown or revoked: stop
  };

//--- state (reset in OnInit: globals survive a parameter change)
string   g_base_url = "";
string   g_headers = "";          // holds the token: never print, alert, comment or persist it
long     g_login = 0;
string   g_server = "";
string   g_queue_file = "";
string   g_hwm_name = "";
bool     g_started = false;
bool     g_stopped = false;
bool     g_url_alerted = false;
int      g_failures = 0;
datetime g_next_retry = 0;        // local PC time
datetime g_hwm_time = 0;          // newest queued deal time (broker server time)
ulong    g_recent_tickets[];      // tickets queued within the scan overlap window
datetime g_recent_times[];
int      g_recent_count = 0;

//+------------------------------------------------------------------+
//| Small string helpers                                             |
//+------------------------------------------------------------------+
string TrimText(const string text)
  {
   int start = 0;
   int end = StringLen(text);
   while(start < end)
     {
      ushort c = StringGetCharacter(text, start);
      if(c > 32 && c != 0xFEFF)
         break;
      start++;
     }
   while(end > start && StringGetCharacter(text, end - 1) <= 32)
      end--;
   return StringSubstr(text, start, end - start);
  }

bool HasControlOrSpace(const string text)
  {
   int n = StringLen(text);
   for(int i = 0; i < n; i++)
      if(StringGetCharacter(text, i) <= 32)
         return true;
   return false;
  }

// Characters safe in a file name and a terminal global variable name.
string SanitizeName(const string text, const int max_chars)
  {
   string out = "";
   int n = StringLen(text);
   for(int i = 0; i < n && StringLen(out) < max_chars; i++)
     {
      ushort c = StringGetCharacter(text, i);
      bool ok = (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c == 45 || c == 46;
      out += ok ? ShortToString(c) : "_";
     }
   return out;
  }

//+------------------------------------------------------------------+
//| Minimal JSON serializer (flat payloads only)                     |
//+------------------------------------------------------------------+
string JsonEscape(const string text)
  {
   string out = "";
   int n = StringLen(text);
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(text, i);
      if(c == 34)
         out += "\\\"";
      else if(c == 92)
         out += "\\\\";
      else if(c == 10)
         out += "\\n";
      else if(c == 13)
         out += "\\r";
      else if(c == 9)
         out += "\\t";
      else if(c < 32)
         out += StringFormat("\\u%04X", (int)c);
      else
         out += ShortToString(c);
     }
   return out;
  }

string JsonString(const string text)
  {
   return "\"" + JsonEscape(text) + "\"";
  }

// Decimal as a plain string with up to 8 decimals, trailing zeros removed ("0.5", "-1.75", "100").
string Num(const double value)
  {
   string s = DoubleToString(value, 8);
   int len = StringLen(s);
   if(StringFind(s, ".") >= 0)
     {
      while(len > 0 && StringGetCharacter(s, len - 1) == '0')
         len--;
      if(len > 0 && StringGetCharacter(s, len - 1) == '.')
         len--;
      s = StringSubstr(s, 0, len);
     }
   if(s == "" || s == "-0")
      s = "0";
   return s;
  }

// JSON string with the decimal, or null for 0 (MT5 reports "no SL/TP" as 0).
string OptNum(const double value)
  {
   if(value == 0.0)
      return "null";
   return "\"" + Num(value) + "\"";
  }

//+------------------------------------------------------------------+
//| Broker server time -> UTC                                        |
//| MT5 deal times are broker SERVER time. Like the mt5 service      |
//| (services/mt5 domain/time.py), the offset is                      |
//| TimeTradeServer() - TimeGMT() rounded to the nearest 30 minutes  |
//| and must be a plausible broker offset (-12h..+14h). One offset   |
//| (the current one) is applied to every deal; historical deals on  |
//| the other side of a DST change are shifted by one hour. Set      |
//| AutoServerOffset = false and ServerUtcOffsetMinutes to force it. |
//+------------------------------------------------------------------+
bool ServerOffsetSeconds(int &offset)
  {
   if(!AutoServerOffset)
     {
      offset = ServerUtcOffsetMinutes * 60;
      return true;
     }
   long diff = (long)TimeTradeServer() - (long)TimeGMT();
   long rounded = (long)MathRound((double)diff / OFFSET_STEP_SECONDS) * OFFSET_STEP_SECONDS;
   long residual = diff - rounded;
   if(residual < 0)
      residual = -residual;
   if(rounded < -12 * 3600 || rounded > 14 * 3600 || residual > 600)
     {
      Print("TradingJournalBridge: cannot determine the broker server UTC offset (", diff,
            " s); deals are not queued until it is known. Set AutoServerOffset=false to force it.");
      return false;
     }
   offset = (int)rounded;
   return true;
  }

string UtcIso(const datetime server_time, const int offset_seconds)
  {
   MqlDateTime st;
   TimeToStruct((datetime)((long)server_time - offset_seconds), st);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", st.year, st.mon, st.day, st.hour, st.min, st.sec);
  }

//+------------------------------------------------------------------+
//| HTTP                                                             |
//+------------------------------------------------------------------+
string ErrorCodeOf(const string reply)
  {
   string key = "\"code\":\"";
   int start = StringFind(reply, key);
   if(start < 0)
      return "";
   start += StringLen(key);
   int end = StringFind(reply, "\"", start);
   if(end < 0)
      return "";
   return StringSubstr(reply, start, end - start);
  }

// Returns the HTTP status, or -1 when the request did not reach the server.
int Post(const string path, const string body, string &reply)
  {
   char data[];
   char result[];
   string result_headers = "";
   reply = "";
   int size = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(size > 0 && data[size - 1] == 0)
      ArrayResize(data, size - 1);   // drop the terminating zero: it is not part of the JSON
   ResetLastError();
   int status = WebRequest("POST", g_base_url + path, g_headers, HTTP_TIMEOUT_MS, data, result, result_headers);
   int received = ArraySize(result);
   if(received > 0)
      reply = CharArrayToString(result, 0, received > 400 ? 400 : received, CP_UTF8);
   if(status == -1)
     {
      int error = GetLastError();
      // 4014 (function not allowed) is what MT5 documents for a URL missing from the
      // WebRequest list; 4060 is the code commonly reported for the same case. Both handled.
      if(error == 4014 || error == 4060)
        {
         string message = "TradingJournalBridge: WebRequest is not allowed for " + g_base_url +
                          ". Add it in Tools > Options > Expert Advisors > Allow WebRequest for listed URL.";
         if(!g_url_alerted)
           {
            Alert(message);
            Comment(message);
            g_url_alerted = true;
           }
         Print(message, " (error ", error, ")");
        }
      else
         Print("TradingJournalBridge: request to ", path, " failed (network error ", error, "); will retry.");
     }
   return status;
  }

SendOutcome Classify(const int status)
  {
   if(status >= 200 && status < 300)
      return SEND_OK;
   if(status == 401)
      return SEND_UNAUTHORIZED;
   if(status == -1 || status == 408 || status == 429 || status >= 500)
      return SEND_RETRY;
   if(status >= 400)
      return SEND_DROP;
   return SEND_RETRY;   // unexpected 1xx/3xx: keep the data
  }

void StopUnauthorized()
  {
   if(g_stopped)
      return;
   g_stopped = true;
   string message = "TradingJournalBridge: the ingest token was rejected (unknown or revoked). "
                    "Sending stopped. Create a new token in the web app and set it in the EA inputs.";
   Alert(message);
   Comment(message);
   Print(message);
  }

void ScheduleRetry(const int status)
  {
   g_failures++;
   int delay = BACKOFF_BASE_SECONDS;
   for(int i = 1; i < g_failures && delay < BACKOFF_CAP_SECONDS; i++)
      delay *= 2;
   if(delay > BACKOFF_CAP_SECONDS)
      delay = BACKOFF_CAP_SECONDS;
   g_next_retry = TimeLocal() + delay;
   Print("TradingJournalBridge: deals kept in the queue (HTTP ", status, "); retry in ", delay, " s.");
  }

//+------------------------------------------------------------------+
//| File queue: one deal JSON object per line                        |
//| <terminal data folder>\MQL5\Files\TradingJournalBridge\          |
//|   queue_<login>_<server>.jsonl                                   |
//+------------------------------------------------------------------+
// Defensive: tolerates a BOM, \r\r\n line ends and a torn last line after a crash.
string CleanLine(const string raw)
  {
   string line = TrimText(raw);
   int len = StringLen(line);
   if(len == 0)
      return "";
   if(StringGetCharacter(line, 0) != '{' || StringGetCharacter(line, len - 1) != '}')
     {
      Print("TradingJournalBridge: skipping a corrupt queue line (", len, " chars).");
      return "";
     }
   return line;
  }

bool AppendToQueue(const string &lines[], const int count)
  {
   int handle = FileOpen(g_queue_file, FILE_READ | FILE_WRITE | FILE_TXT | FILE_UNICODE);
   if(handle == INVALID_HANDLE)
     {
      Print("TradingJournalBridge: cannot open the queue file ", g_queue_file, " (error ", GetLastError(), ").");
      return false;
     }
   FileSeek(handle, 0, SEEK_END);
   for(int i = 0; i < count; i++)
      FileWriteString(handle, lines[i] + "\r\n");
   FileClose(handle);
   return true;
  }

int ReadQueue(string &lines[])
  {
   ArrayResize(lines, 0);
   if(!FileIsExist(g_queue_file))
      return 0;
   int handle = FileOpen(g_queue_file, FILE_READ | FILE_TXT | FILE_UNICODE);
   if(handle == INVALID_HANDLE)
     {
      Print("TradingJournalBridge: cannot read the queue file ", g_queue_file, " (error ", GetLastError(), ").");
      return 0;
     }
   int count = 0;
   while(!FileIsEnding(handle))
     {
      string line = CleanLine(FileReadString(handle));
      if(line == "")
         continue;
      ArrayResize(lines, count + 1, 1024);
      lines[count] = line;
      count++;
     }
   FileClose(handle);
   return count;
  }

// Keeps lines[from..total-1]; written to a temp file first so a crash never truncates the queue.
void RewriteQueue(const string &lines[], const int from, const int total)
  {
   if(from >= total)
     {
      FileDelete(g_queue_file);
      return;
     }
   string temp = g_queue_file + ".tmp";
   int handle = FileOpen(temp, FILE_WRITE | FILE_TXT | FILE_UNICODE);
   if(handle == INVALID_HANDLE)
     {
      Print("TradingJournalBridge: cannot rewrite the queue (error ", GetLastError(), "); sent deals may be resent.");
      return;
     }
   for(int i = from; i < total; i++)
      FileWriteString(handle, lines[i] + "\r\n");
   FileClose(handle);
   if(!FileMove(temp, 0, g_queue_file, FILE_REWRITE))
      Print("TradingJournalBridge: cannot replace the queue file (error ", GetLastError(), ").");
  }

string BatchJson(const string &lines[], const int start, const int count)
  {
   string body = "{\"account_login\":" + IntegerToString(g_login) +
                 ",\"server\":" + JsonString(g_server) + ",\"deals\":[";
   for(int i = 0; i < count; i++)
     {
      if(i > 0)
         body += ",";
      body += lines[start + i];
     }
   body += "]}";
   return body;
  }

void FlushQueue()
  {
   if(!g_started || g_stopped)
      return;
   if(g_next_retry > 0 && TimeLocal() < g_next_retry)
      return;
   string lines[];
   int total = ReadQueue(lines);
   if(total <= 0)
      return;
   int done = 0;
   int batches = 0;
   while(done < total && batches < MAX_BATCHES_PER_FLUSH)
     {
      int count = total - done;
      if(count > BATCH_SIZE)
         count = BATCH_SIZE;
      string reply = "";
      int status = Post(DEALS_PATH, BatchJson(lines, done, count), reply);
      SendOutcome outcome = Classify(status);
      if(outcome == SEND_OK)
        {
         g_failures = 0;
         g_next_retry = 0;
         done += count;
         batches++;
         continue;
        }
      if(outcome == SEND_DROP)
        {
         Print("TradingJournalBridge: dropped a batch of ", count, " deals that the server can never accept (HTTP ",
               status, " ", ErrorCodeOf(reply), "): ", reply);
         done += count;
         batches++;
         continue;
        }
      if(outcome == SEND_UNAUTHORIZED)
         StopUnauthorized();
      else
         ScheduleRetry(status);
      break;
     }
   if(done > 0)
      RewriteQueue(lines, done, total);
  }

//+------------------------------------------------------------------+
//| Deals: history scan -> queue                                     |
//| A high-water mark (newest queued deal time, broker server time)  |
//| is kept in a terminal global variable so a restart only re-reads |
//| the last STARTUP_RESCAN_SECONDS. Resending is safe: the server   |
//| is idempotent by (user, account, ticket).                        |
//+------------------------------------------------------------------+
bool RecentlyQueued(const ulong ticket)
  {
   for(int i = 0; i < g_recent_count; i++)
      if(g_recent_tickets[i] == ticket)
         return true;
   return false;
  }

void RememberQueued(const ulong ticket, const datetime queued_time)
  {
   ArrayResize(g_recent_tickets, g_recent_count + 1, 256);
   ArrayResize(g_recent_times, g_recent_count + 1, 256);
   g_recent_tickets[g_recent_count] = ticket;
   g_recent_times[g_recent_count] = queued_time;
   g_recent_count++;
  }

void PruneRecent()
  {
   datetime oldest = (datetime)((long)g_hwm_time - SCAN_OVERLAP_SECONDS);
   int kept = 0;
   for(int i = 0; i < g_recent_count; i++)
     {
      if(g_recent_times[i] < oldest)
         continue;
      g_recent_tickets[kept] = g_recent_tickets[i];
      g_recent_times[kept] = g_recent_times[i];
      kept++;
     }
   g_recent_count = kept;
   ArrayResize(g_recent_tickets, kept, 256);
   ArrayResize(g_recent_times, kept, 256);
  }

string DealJson(const ulong ticket, const int offset)
  {
   string symbol = StringSubstr(HistoryDealGetString(ticket, DEAL_SYMBOL), 0, MAX_SYMBOL_CHARS);
   string comment = StringSubstr(HistoryDealGetString(ticket, DEAL_COMMENT), 0, MAX_COMMENT_CHARS);
   datetime deal_time = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
   string json = "{\"ticket\":" + IntegerToString((long)ticket);
   json += ",\"position_id\":" + IntegerToString(HistoryDealGetInteger(ticket, DEAL_POSITION_ID));
   json += ",\"time\":\"" + UtcIso(deal_time, offset) + "\"";
   json += ",\"type\":" + IntegerToString(HistoryDealGetInteger(ticket, DEAL_TYPE));
   json += ",\"entry\":" + IntegerToString(HistoryDealGetInteger(ticket, DEAL_ENTRY));
   json += ",\"symbol\":" + JsonString(symbol);
   json += ",\"volume\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_VOLUME)) + "\"";
   json += ",\"price\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_PRICE)) + "\"";
   json += ",\"commission\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_COMMISSION)) + "\"";
   json += ",\"swap\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_SWAP)) + "\"";
   json += ",\"fee\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_FEE)) + "\"";
   json += ",\"profit\":\"" + Num(HistoryDealGetDouble(ticket, DEAL_PROFIT)) + "\"";
   json += ",\"sl\":" + OptNum(HistoryDealGetDouble(ticket, DEAL_SL));
   json += ",\"tp\":" + OptNum(HistoryDealGetDouble(ticket, DEAL_TP));
   json += ",\"comment\":" + JsonString(comment);
   json += "}";
   return json;
  }

// Queues every deal with time >= from that was not queued in this session's overlap window.
void CollectNewDeals(const datetime from)
  {
   if(!g_started || g_stopped)
      return;
   int offset = 0;
   if(!ServerOffsetSeconds(offset))
      return;
   if(!HistorySelect(from, TimeCurrent() + 86400))
     {
      Print("TradingJournalBridge: HistorySelect failed (error ", GetLastError(), ").");
      return;
     }
   int total = HistoryDealsTotal();
   string lines[];
   ulong tickets[];
   datetime times[];
   int count = 0;
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      datetime deal_time = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(deal_time < from || RecentlyQueued(ticket))
         continue;
      long type = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if((type == DEAL_TYPE_BUY || type == DEAL_TYPE_SELL) && HistoryDealGetDouble(ticket, DEAL_VOLUME) <= 0.0)
        {
         // The bridge rejects the whole batch for such a deal; skip it instead.
         Print("TradingJournalBridge: skipping deal ", ticket, " (buy/sell with zero volume).");
         continue;
        }
      ArrayResize(lines, count + 1, 1024);
      ArrayResize(tickets, count + 1, 1024);
      ArrayResize(times, count + 1, 1024);
      lines[count] = DealJson(ticket, offset);
      tickets[count] = ticket;
      times[count] = deal_time;
      count++;
     }
   if(count == 0)
      return;
   if(!AppendToQueue(lines, count))
      return;   // nothing remembered: the next scan queues them again
   for(int i = 0; i < count; i++)
     {
      RememberQueued(tickets[i], times[i]);
      if(times[i] > g_hwm_time)
         g_hwm_time = times[i];
     }
   PruneRecent();
   GlobalVariableSet(g_hwm_name, (double)(long)g_hwm_time);
   GlobalVariablesFlush();
  }

datetime OverlapStart(const long window)
  {
   long start = (long)g_hwm_time - window;
   return start > 0 ? (datetime)start : 0;
  }

//+------------------------------------------------------------------+
//| Heartbeat                                                        |
//+------------------------------------------------------------------+
void SendHeartbeat()
  {
   if(!g_started || g_stopped)
      return;
   string body = "{\"account_login\":" + IntegerToString(g_login) +
                 ",\"server\":" + JsonString(g_server) +
                 ",\"balance\":\"" + Num(AccountInfoDouble(ACCOUNT_BALANCE)) + "\"" +
                 ",\"equity\":\"" + Num(AccountInfoDouble(ACCOUNT_EQUITY)) + "\"" +
                 ",\"terminal_build\":" + IntegerToString(TerminalInfoInteger(TERMINAL_BUILD)) + "}";
   string reply = "";
   int status = Post(HEARTBEAT_PATH, body, reply);
   SendOutcome outcome = Classify(status);
   if(outcome == SEND_OK)
      Comment("TradingJournalBridge: connected (", g_login, " @ ", g_server, "), last heartbeat ",
              TimeToString(TimeLocal(), TIME_DATE | TIME_MINUTES));
   else if(outcome == SEND_UNAUTHORIZED)
      StopUnauthorized();
   else if(status != -1)
      Print("TradingJournalBridge: heartbeat answered HTTP ", status, " ", ErrorCodeOf(reply));
  }

//+------------------------------------------------------------------+
//| Startup                                                          |
//+------------------------------------------------------------------+
void ResetState()
  {
   g_base_url = "";
   g_headers = "";
   g_login = 0;
   g_server = "";
   g_queue_file = "";
   g_hwm_name = "";
   g_started = false;
   g_stopped = false;
   g_url_alerted = false;
   g_failures = 0;
   g_next_retry = 0;
   g_hwm_time = 0;
   g_recent_count = 0;
   ArrayResize(g_recent_tickets, 0);
   ArrayResize(g_recent_times, 0);
  }

bool ValidateInputs()
  {
   string url = TrimText(ApiUrl);
   while(StringLen(url) > 0 && StringGetCharacter(url, StringLen(url) - 1) == '/')
      url = StringSubstr(url, 0, StringLen(url) - 1);
   string lower = url;
   StringToLower(lower);
   int scheme = 0;
   if(StringFind(lower, "https://") == 0)
      scheme = 8;
   else if(StringFind(lower, "http://") == 0)
      scheme = 7;
   if(scheme == 0 || StringLen(url) <= scheme || HasControlOrSpace(url) || StringFind(url, "/", scheme) >= 0)
     {
      Print("TradingJournalBridge: ApiUrl must be an origin like https://api.example.com (no path).");
      return false;
     }
   string token = TrimText(IngestToken);
   if(token == "" || HasControlOrSpace(token))
     {
      Print("TradingJournalBridge: the token input is empty or contains spaces. Paste the token from the web app.");
      return false;
     }
   g_base_url = url;
   g_headers = "Content-Type: application/json\r\nAuthorization: Bearer " + token + "\r\n";
   return true;
  }

// Runs once the terminal is connected to an account: heartbeat FIRST (only the heartbeat
// creates the account, deals only touch last_deal_at of an existing one), then backfill.
bool Startup()
  {
   if(g_started)
      return true;
   if(TerminalInfoInteger(TERMINAL_CONNECTED) == 0)
      return false;
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   if(login <= 0 || server == "")
      return false;
   g_login = login;
   g_server = server;
   string key = IntegerToString(login) + "_" + SanitizeName(server, 30);
   FolderCreate(STATE_FOLDER);
   g_queue_file = STATE_FOLDER + "\\queue_" + key + ".jsonl";
   g_hwm_name = "TJB_" + key + "_hwm";
   g_hwm_time = 0;
   if(GlobalVariableCheck(g_hwm_name))
      g_hwm_time = (datetime)(long)GlobalVariableGet(g_hwm_name);
   g_started = true;
   Print("TradingJournalBridge: started for account ", g_login, " @ ", g_server, ", queue file MQL5\\Files\\",
         g_queue_file);
   SendHeartbeat();
   if(g_stopped)
      return true;
   CollectNewDeals(OverlapStart(STARTUP_RESCAN_SECONDS));
   FlushQueue();
   return true;
  }

//+------------------------------------------------------------------+
//| Event handlers                                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   ResetState();
   if(!ValidateInputs())
      return INIT_PARAMETERS_INCORRECT;
   if(!EventSetTimer(HEARTBEAT_SECONDS))
     {
      Print("TradingJournalBridge: cannot start the timer (error ", GetLastError(), ").");
      return INIT_FAILED;
     }
   if(!Startup())
      Print("TradingJournalBridge: waiting for the terminal to connect to a trade account (retry every ",
            HEARTBEAT_SECONDS, " s).");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
  }

void OnTimer()
  {
   if(g_stopped)
      return;
   if(g_started && AccountInfoInteger(ACCOUNT_LOGIN) != g_login)
     {
      // Another account: start over with its own queue file and high-water mark.
      g_started = false;
      g_recent_count = 0;
      ArrayResize(g_recent_tickets, 0);
      ArrayResize(g_recent_times, 0);
     }
   if(!g_started)
     {
      Startup();
      return;
     }
   SendHeartbeat();
   // Also catches deals whose DEAL_ADD event arrived before the history had them.
   CollectNewDeals(OverlapStart(SCAN_OVERLAP_SECONDS));
   FlushQueue();
  }

// A new deal: re-scan the history from the high-water mark (the scan reads the deal's fields
// through HistorySelect/HistoryDealGet*), queue it in the file first, then try to send.
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!g_started || g_stopped)
      return;
   CollectNewDeals(OverlapStart(SCAN_OVERLAP_SECONDS));
   FlushQueue();
  }
//+------------------------------------------------------------------+
