# TradingJournalBridge EA (MQL5)

Expert Advisor that pushes your raw MT5 deals and a heartbeat to the `mt5-bridge` API
(spec 002). Written from scratch on native `WebRequest`: no DLL, so "Allow DLL imports" stays off.

Status: source written, *(awaiting compile and real-account verification, Task 8)*. It has
not been compiled or run yet; see [Limitations](#limitations).

## What it does

1. `OnInit`: validates the inputs, then (once the terminal is connected to an account) sends a
   **heartbeat first** (only the heartbeat creates the broker account on the server), then
   **backfills** the deal history with `HistorySelect` into a local file queue and sends it in
   batches of at most 200 deals. Until one heartbeat has been accepted (API down, 5xx) nothing
   is backfilled or flushed; the 60 s timer retries the heartbeat and the scan starts after it succeeds.
   `OnTimer` and `OnTradeTransaction` act only while the terminal account (login and server) is the one the EA started with.
2. `OnTradeTransaction` (`TRADE_TRANSACTION_DEAL_ADD`): re-scans the history from the high-water
   mark, queues the new deal in the file, then sends it.
3. `OnTimer` every 60 s: heartbeat (login, server, balance, equity, terminal build), a history
   re-scan (catches events missed or arriving before the history had the deal) and a queue flush.

Payloads are exactly the ones in [`sample_payloads/`](sample_payloads) (checked by
`tests/unit/test_ea_contract.py` against the bridge request schemas): times in UTC ISO
(`2026-11-20T09:14:32Z`), decimals as JSON strings, `sl`/`tp` `null` when MT5 reports 0.

Answers of `POST /ingest/deals`:

| Answer | EA behavior |
|---|---|
| 2xx | Batch done, removed from the queue |
| 401 | Stops sending (deals stay queued); Alert + chart comment: create a new token |
| 503, other 5xx, 408, 429, network error / timeout (`WebRequest` returns -1) | Batch stays queued; retry after 60 s, 120 s, 240 s, then every 300 s (cap 5 min) |
| 3xx (redirect, not followed) | Batch stays queued and retried; the log says to set `ApiUrl` to the final https origin |
| any other 4xx (422 `VALIDATION_ERROR`, `INVALID_DEAL_BATCH`, `JOURNAL_REJECTED`) | Batch dropped and logged in the Experts tab |

Resending is always safe: the server is idempotent by (user, account, deal ticket).

## Install

1. In the web app, create an **ingest token** (`POST /api/v1/mt5-bridge/tokens`). It is shown
   only once: copy it.
2. Download the EA (`GET /api/v1/mt5-bridge/ea/download`, `TradingJournalBridge.ex5`), or compile
   it yourself (below).
3. MT5: **File > Open Data Folder**, copy `TradingJournalBridge.ex5` into `MQL5\Experts\`, then
   right-click **Expert Advisors > Refresh** in the Navigator.
4. **Whitelist the API URL (required):** **Tools > Options > Expert Advisors**, tick
   **Allow WebRequest for listed URL** and add the API origin exactly as in `ApiUrl`
   (for example `https://api.example.com`, or `http://localhost:8005` when developing).
5. Drag the EA onto **one** chart (any symbol, any timeframe). Inputs:
   - `ApiUrl`: API origin only, no path and no trailing route (for example
     `https://api.example.com`). The EA appends `/api/v1/mt5-bridge/ingest/...`.
   - `IngestToken`: the token from step 1.
   - `AutoServerOffset` (default `true`) / `ServerUtcOffsetMinutes`: see time handling below.
6. Enable **Algo Trading** in the toolbar. The chart comment shows
   `TradingJournalBridge: connected (...)` after the first heartbeat; the web app lists the account
   as connected.

Attach it to a single chart per terminal: two copies would share the queue file.

## Compile (owner, MetaEditor)

1. Copy `TradingJournalBridge.mq5` into `<MT5 data folder>\MQL5\Experts\`.
2. Open it in MetaEditor (F4 from the terminal) and press **F7** (Compile). It must report
   0 errors; review any warnings.
3. MetaEditor writes `TradingJournalBridge.ex5` next to the source.
4. For `GET /api/v1/mt5-bridge/ea/download` to serve it, copy the `.ex5` to
   `services/mt5-bridge/ea/TradingJournalBridge.ex5` (the default `EA_FILE_PATH` in
   `settings.py`), or point `EA_FILE_PATH` at its location. Until then the endpoint answers 404
   `NOT_FOUND`.
5. **Never commit the `.ex5`** (`*.ex5` is git-ignored): it is a build artifact.

## Time handling (server time to UTC)

MT5 deal times are broker **server** time. Like the `mt5` service
(`services/mt5/src/mt5_service/domain/time.py`), the EA computes the offset as
`TimeTradeServer() - TimeGMT()`, rounds it to the nearest 30 minutes, accepts it only within
-12 h..+14 h (residual at most 10 min), and sends `deal time - offset` with a `Z` suffix. If the
offset cannot be trusted, deals are not queued until it can (nothing is sent with a guessed time).
One offset (the current one) is applied to every deal: during the first backfill, deals from the
other side of a DST change are shifted by one hour. To force a value set
`AutoServerOffset = false` and `ServerUtcOffsetMinutes` (for example `120` for UTC+2).

## Local state

| What | Where |
|---|---|
| Deal queue (one JSON deal per line, survives restarts) | `<MT5 data folder>\MQL5\Files\TradingJournalBridge\queue_<login>_<server>.jsonl` |
| High-water mark (newest queued deal time, server time) | Terminal global variable `TJB_<login>_<server>_hwm` (F3 in the terminal) |

On every start the EA re-reads the last 3 days of history before the high-water mark, and every
scan re-reads the last 5 minutes, so a missed event never loses a deal (duplicates are harmless).
Deleting the global variable makes the next start resend the whole history. Every append starts
on a fresh line and a queue line is used only if it is exactly one JSON object, so a line torn by a
crash is skipped instead of breaking a batch. The queue is rewritten through a `.tmp` file that
replaces it only when every write succeeded; on a write error the old queue is kept. The token is never
stored in these files, printed, alerted or shown on the chart.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Alert "WebRequest is not allowed for ..." (error 4014 or 4060) | Add the exact `ApiUrl` origin to Tools > Options > Expert Advisors > Allow WebRequest for listed URL, then re-attach the EA |
| Alert "the ingest token was rejected" (HTTP 401) | The token was revoked or mistyped. Create a new token in the web app, open the EA inputs (F7 on the chart) and paste it. Queued deals are sent after that |
| EA removed right after attaching (`INIT_PARAMETERS_INCORRECT`) | `ApiUrl` must start with `http://` or `https://` and have no path; the token must not be empty or contain spaces |
| "waiting for the terminal to connect" | The terminal is not logged in; the EA retries every 60 s |
| "cannot determine the broker server UTC offset" | Stale server time (no connection). Set `AutoServerOffset = false` and the offset in minutes |
| Deals never arrive | Check the Experts tab for "dropped a batch" (HTTP 4xx with the error code) or "kept in the queue" (server unreachable; it retries); inspect the queue file above |

## Limitations

- **Backfills that span a DST change are off by one hour.** The EA applies the broker's
  *current* server-to-UTC offset to every deal. New deals (sent as they happen) are right; deals
  backfilled from before the broker's last DST switch are stored one hour early or late. Workaround:
  set `AutoServerOffset = false` and `ServerUtcOffsetMinutes` before the first backfill (it still
  applies one offset to all deals). Proper fix: a per-timestamp server-timezone rule like the `mt5`
  service's `MT5_SERVER_TIMEZONE` *(planned follow-up)*. Accepted for spec 002 (owner-only use).
- `ApiUrl` with plain `http://` is accepted for local development; for any host other than
  `localhost`/`127.0.0.1` the EA prints a warning, because the request (and its token) is unencrypted.

Untested because MQL5 cannot be compiled or run in this repository's CI (no MetaEditor, no terminal):

- The source has never been compiled: syntax or overload errors may remain (Task 8).
- Runtime behavior is unverified on a real account: `WebRequest` from `OnInit`, the URL-not-allowed
  error code (handled as 4014 or 4060), passing `char[]` buffers to
  `StringToCharArray`/`CharArrayToString`, text-file queue read/write (`FILE_TXT | FILE_UNICODE`
  line endings), `FileMove` replacement, `FolderCreate`, `DEAL_FEE`/`DEAL_SL`/`DEAL_TP`
  availability on the owner's build, and the deal being visible to `HistorySelect` at the moment
  `TRADE_TRANSACTION_DEAL_ADD` arrives (the 60 s timer scan is the fallback).
- A batch answered with a 4xx is dropped whole (199 good deals with one bad one are lost); the EA
  skips buy/sell deals with zero volume locally to avoid the only known cause.
- `WebRequest` is synchronous: a long first backfill blocks the chart for a few seconds per
  batch (at most 25 batches per flush; the rest follows on the next timer).
- Prop-firm or broker EA restrictions are not handled (spec 002 non-goal).
