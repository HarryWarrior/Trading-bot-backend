# Integrations research log

Before building a tool from scratch, look for a proven open-source project or API. Record every
evaluation here (accepted or rejected) so nobody repeats it.

**Criteria:** license compatible with SaaS use · maintained (recent releases, issues answered) ·
fits our stack (Python service or language-agnostic API) · works multi-user · cost · security.

## Evaluated

| Name | URL | License | Purpose | Verdict | Spec | Date |
|---|---|---|---|---|---|---|
| dingmaotu/mql-zmq | https://github.com/dingmaotu/mql-zmq | Apache-2.0 | ZeroMQ binding for MQL5 (transport) | Not adopted: needs libzmq DLLs and "Allow DLL imports", a broker/prop-firm blocker, plus a listener on our side; WebRequest is simpler. Last push 2023-12-19; no JSON, no queue | 002 | 2026-11-24 |
| dennislwm/MQL5-JSON-API (fork of luciotato/MQL5-JSON-API) | https://github.com/dennislwm/MQL5-JSON-API | GPL-3.0 | ZeroMQ + `Json.mqh` EA to drive MT5 from Python | Not adopted: GPL-3.0 is incompatible with distributing our EA; ZeroMQ/DLL; fork last push 2020-10-22 (upstream 2019-05-26) | 002 | 2026-11-24 |
| vdemydiuk/mtapi | https://github.com/vdemydiuk/mtapi | MIT | .NET/WebSocket bridge MT4/MT5 for C# clients | Not adopted: needs DLL + Windows .NET host per terminal; wrong direction (client drives MT5). Active (last push 2026-11-24) | 002 | 2026-11-24 |
| DevRico003/mt5-rest-api | https://github.com/DevRico003/mt5-rest-api | None declared (all rights reserved) | REST server via C++ DLL | Not adopted: no license, DLL, runs server-side per terminal. Last push 2025-12-03 | 002 | 2026-11-24 |
| mikha-dev/mt5-rest, cyrus13/rest-mql | https://www.github.com/mikha-dev/mt5-rest, https://github.com/cyrus13/rest-mql | unknown (not checked) | REST wrappers (DLL/C# based) | Not adopted: DLL-based; rest-mql per its description does no JSON handling | 002 | 2026-11-24 |
| MQL5 JSON Library (ding9736), CodeBase 62735 | https://www.mql5.com/en/code/62735 | unknown: no license stated (MQL5 site terms only) | JSON parse/build in MQL5 | Not adopted for copying: license unclear. Reference only. Published 2025-08-17, updated 2026-09-15 | 002 | 2026-11-24 |
| Connexus (joaopedrodev), MQL5 article 15795 | https://www.mql5.com/en/articles/15795 | unknown; "all rights reserved by MetaQuotes" | WebRequest wrapper library (article series) | Not adopted: no license, no retry/queue, JSON built by hand. 2024-09-20 | 002 | 2026-11-24 |
| MetaApi (metaapi.cloud) | https://metaapi.cloud/ ; SDK https://github.com/metaapi/metaapi-python-sdk | SDK license: NOASSERTION per GitHub (unknown); service is paid (docs: free tier for testing/personal use; homepage listed $30/month, pricing marked unavailable) | Cloud MT5 access, needs investor/broker password | Not adopted now: stores broker credentials (violates ADR 0002) and costs per account. Kept as a future fallback adapter behind the same port. SDK last push 2026-05-12 | 002 | 2026-11-24 |

### MT5 EA bridge research summary (spec 002, task 1)

- No maintained, permissively licensed open-source MQL5 EA that pushes deals to a REST API with
  retry/queue was found. All REST/ZeroMQ bridges found need a DLL or a server-side process, or
  use GPL or no license. Nothing is adopted as a dependency.
- Decision: Task 7 writes the EA from scratch on native `WebRequest` (no DLL, so no
  "Allow DLL imports"), with its own small JSON serializer (the payload is flat: deals and
  heartbeat, so string building plus escaping suffices) and a file queue with exponential backoff.
- **Reusable snippets for Task 7: none.** Do not copy code from the GPL-3.0 repo, nor from
  repos/pages with no stated license (DevRico003/mt5-rest-api, MQL5 CodeBase 62735, Connexus). Only
  Apache-2.0 (mql-zmq) and MIT (mtapi) code could be reused with attribution, and neither is
  relevant to a WebRequest EA. MQL5 documentation examples of `WebRequest`, `HistorySelect` and
  `OnTradeTransaction` are used as API reference only.
- Caveats: `WebRequest` needs the URL whitelisted in terminal options, is synchronous and
  unavailable in indicators/some tester modes; the POST body must be passed as a `char[]` with an
  explicit `Content-Type: application/json` header.
- Not verified: licenses of mikha-dev/mt5-rest and cyrus13/rest-mql; the full pricing of MetaApi.

## Candidates to evaluate

| Area | Candidates | Spec |
|---|---|---|
| MT5 EA bridge and MetaApi | Researched 2026-11-24, see Evaluated | 002 |
| Backtesting engines | backtesting.py, vectorbt, backtrader, NautilusTrader, QuantConnect Lean | 003 |
| Live execution | NautilusTrader adapters, Interactive Brokers API (`ib_async`) | 003 |
| Market data | Broker feeds via EA, free/paid data vendors | 003 |
| AI journaling | MCP Python SDK, Claude API | 004 |
