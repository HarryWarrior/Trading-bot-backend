# mt5 service

Links the account of the MetaTrader 5 terminal running on this machine, syncs its CLOSED trades
and balance events to the `journal` service, and serves real candles. Prefix `/api/v1/mt5`.

Nothing is simulated and no broker password is ever accepted or stored: the account is whatever the
running terminal reports (`login@server`). When the terminal is not running, not logged in or on
another account the API answers with an error code (`TERMINAL_NOT_AVAILABLE`,
`TERMINAL_ACCOUNT_MISMATCH`).

The terminal adapter uses the official `MetaTrader5` Python package, which only exists for
**Windows** and talks to a terminal already running and logged in on the same machine. The package
is imported lazily: the service starts without a terminal (and on other OSes) and only answers
`TERMINAL_NOT_AVAILABLE` on requests that need it.

## Routes (Bearer token required)

| Method | Path | Role | Result |
|---|---|---|---|
| POST | `/accounts/link` | admin | 201 `{account}` (new) or 200 (same user, already linked); no request body |
| GET | `/accounts` | any user | `{accounts: [...]}` (own accounts only) |
| GET | `/accounts/{id}/status` | any user (owner) | `{status: {connected, balance, equity, as_of, last_sync_at}}`; `connected: false` and nulls when the terminal is closed or on another account |
| POST | `/accounts/{id}/sync` | admin | `{result: {created, updated, balance_events, open_positions, skipped_positions}}` |
| DELETE | `/accounts/{id}` | admin | removes the link only (journal trades are kept) |
| GET | `/rates?symbol=&timeframe=&count=` | any user | `{symbol, timeframe, candles: [{time, open, high, low, close, tick_volume}]}`; timeframes `M1 M5 M15 M30 H1 H4 D1`, `count` 1..1000 |

Linking, syncing and unlinking require role `admin`. One terminal account can be linked to only one
user (`ACCOUNT_ALREADY_LINKED` 409 for anyone else). Sync forwards the caller's own access token to
the journal, plus the shared `X-Service-Key`. Error codes: `TERMINAL_NOT_AVAILABLE` 409,
`TERMINAL_ACCOUNT_MISMATCH` 409, `MULTIPLE_TERMINALS` 409, `SERVER_TIMEZONE_MISMATCH` 409, `ACCOUNT_ALREADY_LINKED` 409, `NOT_FOUND` 404,
`SYMBOL_NOT_FOUND` 404, `INVALID_TIMEFRAME` 422, `JOURNAL_UNAVAILABLE` 503, `FORBIDDEN` 403.

## Environment variables

See `.env.example` (copy to the git-ignored `.env`).

| Variable | Notes |
|---|---|
| `JWT_SECRET_KEY` | required, >= 32 chars, same as auth |
| `INGEST_SERVICE_KEY` | required, >= 32 chars, same as the journal service |
| `JOURNAL_URL` | default `http://localhost:8002` |
| `MONGODB_URL`, `DATABASE_NAME` | default `mongodb://localhost:27017`, `mt5_db` |
| `CORS_ORIGINS`, `ENVIRONMENT`, `LOG_LEVEL` | as in the other services |
| `MT5_SERVER_TIMEZONE` | recommended, IANA zone of the broker server clock, e.g. `Europe/Athens` |
| `MT5_SERVER_UTC_OFFSET_MINUTES` | optional, -720..840; ignored when `MT5_SERVER_TIMEZONE` is set |

### Broker server time: `MT5_SERVER_TIMEZONE` (recommended)

MT5 deal and candle times are broker server time, not UTC. Set `MT5_SERVER_TIMEZONE` to the IANA
zone of the broker clock; brokers on EET such as FTMO use `Europe/Athens` (GMT+2 in winter, GMT+3
in summer). Every deal and candle is converted with the offset in force at ITS OWN timestamp, so a
history that spans DST changes is correct, and no market data is needed, so it also works on
weekends. Wall-clock times that happen twice or never at a DST change are resolved with `fold=0`
(first occurrence / offset before the jump).

When a live tick is available the zone is sanity-checked: a tick AHEAD of the zone's current time
by more than 10 minutes cannot be real, and the call answers `SERVER_TIMEZONE_MISMATCH` (409). A
zone set too far ahead of the real broker time looks like a stale tick and is not detected.

Without `MT5_SERVER_TIMEZONE` the offset is detected as
`round_to_30min(latest_tick_server_time - utc_now)` (needs a fresh tick; rejected when the market
is closed) or taken from the fixed `MT5_SERVER_UTC_OFFSET_MINUTES` (e.g. `120`/`180`). Both apply
ONE offset to the whole history, so deals on the other side of a DST change are off by one hour.

## One terminal, never launched

The service attaches to the terminal that is ALREADY open (ADR 0004). `MetaTrader5.initialize()`
would start `terminal64.exe` if none were running, so a process probe (`psutil`) looks first: no
terminal -> `TERMINAL_NOT_AVAILABLE` ("MT5 terminal is not running") without calling initialize;
more than one -> `MULTIPLE_TERMINALS`; exactly one -> `initialize(path=<that terminal>)`. Keep a
single terminal open. A terminal whose executable path the OS hides from this process is ignored.

## Rules implemented in the domain

- Deals are grouped by `position_id`. Side = side of the IN deal, volume = sum of IN volumes, close
  price = volume-weighted exit price, close time = last exit, profit/commission/swap/fee summed
  (fee is folded into commission because journal has no fee field). Only fully closed positions
  become trades; open ones are counted.
- Positions containing an INOUT (reversal) deal are NOT supported yet: they are skipped and reported
  in `skipped_positions` with a reason, never guessed.
- Balance-type deals: BALANCE -> deposit/withdrawal by sign, CREDIT -> credit, every other non-trade
  type -> adjustment (profit + commission + swap + fee). BUY_CANCELED / SELL_CANCELED are ignored.
- Re-syncing reads the full history again; journal upserts by `position_id`, so there are no
  duplicates.

## Run and test

```bash
pip install -e libs/shared -e "services/mt5[dev]"
cd services/mt5 && uvicorn mt5_service.main:app --reload --port 8004   # needs MongoDB; terminal only for link/sync/status/rates
pytest services/mt5/tests -q -W error          # fake terminal, no MetaTrader5 contact; Mongo-backed tests need local MongoDB
pytest -m live services/mt5/tests              # LIVE: needs MetaTrader 5 open and logged in on this machine (read-only calls)
```
