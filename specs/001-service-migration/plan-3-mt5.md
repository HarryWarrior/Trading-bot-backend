# 001 · Plan 3 of 4 — `mt5` service (attach to the open terminal)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The operator links the MT5 account that is open and logged in on the host terminal, syncs its real history into `journal`, and gets real candles — nothing simulated, no broker password ever asked or stored.

**Architecture:** Hexagonal `services/mt5` (port 8004, `mt5_db`) from `services/_template`. Port `BrokerTerminal` (adapter: `MetaTrader5TerminalAdapter`, attaches with `MetaTrader5.initialize()` without credentials; calls run in one worker thread behind a lock). Port `JournalGateway` (adapter: HTTP client to journal `/ingest/mt5`, forwarding the user's verified JWT plus a service key). Pure domain builds round-trip trades from deals by `position_id`.

**Tech Stack:** Python 3.12 (Windows only for the adapter), FastAPI 0.104.1, motor 3.7.1, httpx 0.25.2, `MetaTrader5==5.0.6231` (Windows marker), pytest.

**Spec:** `specs/001-service-migration/design.md` §5.6, §5.11-4 (admin links), -5 (UTC via server offset); ADR 0002. Plans 1–2 are done (auth, journal, analytics); their conventions apply (`trading_shared.auth`, envelope, error mapping, settings with `jwt_secret_key` ≥ 32, lazy `app`, throwaway-DB integration tests, root pytest config).

## Global Constraints

- Branch `feat/001-real-data`; one commit per task; never push without the owner.
- **Nothing simulated:** no fallback balances, no random candles, no fake "connected". When the terminal is not running / not logged in / on another account, the API says so with an error code; tests use a fake `BrokerTerminal` defined in tests only.
- **No credentials:** no endpoint accepts a login password; nothing stores one. The account is whatever the running terminal reports.
- Linking, syncing and unlinking require role `admin` (`require_role`); listing/status of own accounts: any authenticated owner; `/rates`: any authenticated user.
- One terminal account (`login@server`) can be linked to only one user (unique index); same user re-linking the same account is idempotent (200 with the existing link).
- Times: MT5 deal/candle times are broker server time; convert to UTC with the server offset `offset = round_to_30min(latest_tick_time_server - utc_now)`; store/return tz-aware UTC.
- `account_ref` sent to journal = `f"{login}@{server}"` (same as MT5 reports, so report imports and syncs dedupe by `position_id`).
- Journal `/ingest/mt5` additionally requires header `X-Service-Key` equal to journal setting `ingest_service_key` (≥ 32 chars, required); the mt5 service holds the same key. Missing/wrong key → 403 `FORBIDDEN`.
- Error codes: `TERMINAL_NOT_AVAILABLE` 409 (not running / not logged in / package missing), `TERMINAL_ACCOUNT_MISMATCH` 409, `ACCOUNT_ALREADY_LINKED` 409 (other user), `NOT_FOUND` 404, `SYMBOL_NOT_FOUND` 404, `INVALID_TIMEFRAME` 422, `JOURNAL_UNAVAILABLE` 503, `FORBIDDEN` 403.
- Timeframes: `M1, M5, M15, M30, H1, H4, D1`; max 1000 candles per request.
- Sync reads the full deal history each time (MT5 history is local and fast; journal upserts are idempotent); only CLOSED positions become trades; open positions are reported as `open_positions` count, not sent.

## Review Focus

1. Terminal closed, logged out, or switched to another account between link and sync → 409 with the right code, nothing written to journal. (Tasks 1, 4)
2. A position closed in several partial exits → one trade: entry volume, volume-weighted close price, last exit time, summed profit/commission/swap. (Task 1)
3. Re-syncing (twice, or after importing the MT5 report of the same account) → no duplicates in journal. (Tasks 1, 5)
4. A non-admin user cannot link/sync/unlink and cannot see another user's linked accounts. (Task 4)
5. Broker server at UTC+2/+3 → stored times are UTC (e.g. server 15:00 at +3 → 12:00Z), candles and deals alike. (Tasks 1, 2)

---

### Task 1: `mt5` domain and use cases

**Files:** create `services/mt5/` from the template (package `mt5_service`, prefix `/api/v1/mt5`, ruff first-party); `src/mt5_service/domain/{account.py, deals.py, trades.py, time.py, errors.py}`, `application/ports/{terminal.py, journal.py, repositories.py, clock.py, ids.py}`, `application/use_cases/{link_account.py, sync_account.py, get_status.py, list_accounts.py, unlink_account.py, get_rates.py}`; tests `tests/conftest.py` (FakeTerminal, FakeJournalGateway, fake repo, clock), `tests/unit/test_trade_builder.py`, `tests/unit/test_use_cases.py`, architecture test.

**Interfaces — Produces:**
- `TerminalAccount(login: int, server: str, name: str, currency: str, balance: Decimal, equity: Decimal, trade_mode: "demo"|"real"|"contest", company: str)`.
- `Deal(ticket: int, position_id: int, time_server: datetime(naive), type: DealType, entry: DealEntry, symbol: str, volume: Decimal, price: Decimal, commission: Decimal, swap: Decimal, fee: Decimal, profit: Decimal, comment: str)`; `DealType(IntEnum)`: BUY=0, SELL=1, BALANCE=2, CREDIT=3, CHARGE=4, CORRECTION=5, BONUS=6, COMMISSION=7…(MT5 values); `DealEntry(IntEnum)`: IN=0, OUT=1, INOUT=2, OUT_BY=3.
- `Candle(time: datetime UTC, open, high, low, close: Decimal, tick_volume: int)`.
- `server_offset(latest_tick_server: datetime, utc_now: datetime) -> timedelta` (rounded to nearest 30 min) and `to_utc(server_time, offset) -> datetime`.
- `build_trades(deals, offset) -> BuildResult(trades: list[TradeOut], balance_events: list[BalanceEventOut], open_positions: int)` — trades grouped by `position_id` (IN deals: open time/price/side/volume; OUT/OUT_BY/INOUT: close time = last exit, close price = volume-weighted, profit/commission/swap/fee summed across all deals; `position_id` as string); only positions whose exit volume equals entry volume; balance-type deals → `BalanceEventOut(kind, amount, time, source_ref=str(ticket), comment)` with BALANCE → deposit/withdrawal by sign, CREDIT → credit, CHARGE/CORRECTION/BONUS/COMMISSION/… → adjustment. `TradeOut`/`BalanceEventOut` match journal's `/ingest/mt5` JSON.
- Ports: `BrokerTerminal` (`current_account() -> TerminalAccount` raising `TerminalNotAvailable`; `history_deals() -> list[Deal]`; `latest_tick_time(symbol | None) -> datetime`; `rates(symbol, timeframe, count) -> list[Candle(server time)]` raising `SymbolNotFound`); `JournalGateway.ingest(token, account_ref, trades, balance_events) -> IngestResult(created, updated, balance_events)` raising `JournalUnavailable`; `LinkedAccountRepository` (`add`, `get(user_id, id)`, `find_by_ref(account_ref)`, `list(user_id)`, `delete(user_id, id)`, `mark_synced(id, at, result)`).
- `LinkedAccount(id, user_id, account_ref, login, server, name, currency, trade_mode, company, linked_at, last_sync_at | None, last_sync_result | None)`.
- Use cases: `LinkAccount.execute(user_id) -> LinkedAccount` (reads terminal; other user → `AccountAlreadyLinked`; same user → existing); `SyncAccount.execute(user_id, account_id, token) -> SyncResult(created, updated, balance_events, open_positions)` (terminal must report the same `login@server` → else `TerminalAccountMismatch`; nothing sent on mismatch); `GetStatus.execute(user_id, account_id) -> AccountStatus(connected: bool, balance | None, equity | None, as_of, last_sync_at)` (connected only if the terminal reports this account now; balance/equity None when not connected — never stored defaults); `ListAccounts`, `UnlinkAccount`; `GetRates.execute(symbol, timeframe, count) -> list[Candle UTC]`.

- [ ] **Step 1:** Failing tests: `test_offset_rounds_to_30_minutes` (server tick 15:00:07, utc 12:00:00 → +3h); `test_to_utc_converts_server_time`; `test_single_entry_exit_builds_trade` (buy 1.0 @1.1000, sell out @1.1050, profit 50, commission -2 each side → net 46, times converted with +2h); `test_partial_exits_aggregate` (in 1.0 @1.1000; out 0.4 @1.1100 at t1; out 0.6 @1.1200 at t2 → close_price 1.1160, close_time t2, profits summed); `test_open_position_not_sent_and_counted`; `test_balance_deals_map_to_events` (deposit, withdrawal, credit, correction → adjustment); `test_link_uses_terminal_account_and_never_credentials`; `test_link_when_terminal_unavailable_raises`; `test_link_other_users_account_raises_already_linked`; `test_relink_same_user_is_idempotent`; `test_sync_mismatch_sends_nothing`; `test_sync_sends_trades_and_records_result`; `test_status_disconnected_has_no_balance`; `test_users_cannot_see_each_others_accounts`.
- [ ] **Step 2–4:** RED → implement → `pytest services/mt5/tests -q -W error` green.
- [ ] **Step 5:** Commit `feat(mt5): add mt5 domain and use cases`

### Task 2: `MetaTrader5TerminalAdapter`

**Files:** `adapters/outbound/mt5_terminal.py`, `services/mt5/pyproject.toml` (+ `MetaTrader5==5.0.6231; sys_platform == "win32"`), tests `tests/unit/test_mt5_terminal_mapping.py` (fake `mt5` module object injected — mapping of namedtuples `AccountInfo`, `TradeDeal`, rates arrays → domain types), `tests/live/test_live_terminal.py` (`@pytest.mark.live`, deselected by default like `private`; register marker in root and service config).

**Interfaces:** `MetaTrader5TerminalAdapter(module=None, executor=None)` implements `BrokerTerminal`; lazy `import MetaTrader5` inside (ImportError → `TerminalNotAvailable("MetaTrader5 package not installed")`); `initialize()` with NO credentials; `account_info() is None` → `TerminalNotAvailable("terminal not logged in")`; every call runs on a single-thread executor under a lock and is awaited via `asyncio.get_running_loop().run_in_executor`; `history_deals()` uses `history_deals_get(datetime(2000,1,1), now + 1 day)`; `rates()` uses `symbol_select` + `copy_rates_from_pos(symbol, TIMEFRAME, 0, count)`; unknown symbol → `SymbolNotFound`; `latest_tick_time(symbol)` from `symbol_info_tick` (time is server-time epoch); when no symbol is given, use the symbol of the most recent deal, else the first symbol in Market Watch (`symbols_get()` with `visible`) that has a tick — **no hard-coded symbol**; none → `TerminalNotAvailable("no market data to derive server time")`.

- [ ] **Step 1:** Mapping tests with a fake module (namedtuples with MT5 field names: `login, server, name, currency, balance, equity, trade_mode, company`; deals `ticket, position_id, time, type, entry, symbol, volume, price, commission, swap, fee, profit, comment`; rates structured array `time, open, high, low, close, tick_volume`): not-installed → unavailable; `initialize()` false → unavailable; `account_info()` None → unavailable; `initialize` never receives login/password/server arguments (assert call args); floats → Decimal via `str`.
- [ ] **Step 2–4:** RED → implement → green. Install the wheel into the shared venv; `pytest -m live services/mt5/tests` documented (runs only with a logged-in terminal).
- [ ] **Step 5:** Commit `feat(mt5): add MetaTrader5 terminal adapter`

### Task 3: Persistence, journal gateway, journal service key

**Files:** mt5: `adapters/outbound/{mongo_accounts.py, journal_gateway.py, system_clock.py, uuid_ids.py}`; journal: `settings.py` (+ `ingest_service_key: SecretStr` required ≥ 32), router `/ingest/mt5` checks `X-Service-Key` (constant-time compare) → 403 `FORBIDDEN`, `.env.example`, README, tests; tests mt5 `tests/integration/{test_mongo_accounts.py, test_journal_gateway.py}`.

**Interfaces:** `MongoLinkedAccountRepository(db)` with unique `account_ref` index and `(user_id)` index; `JournalHttpGateway(base_url, service_key, transport=None, timeout=30.0)` POSTs `/api/v1/journal/ingest/mt5` with `Authorization: Bearer <token>` and `X-Service-Key`; non-2xx/connection error → `JournalUnavailable` (401 → `Unauthenticated`); never logs token or key.

- [ ] **Step 1:** Tests: unique `account_ref` across users; list/get scoped by user; journal ingest without/with wrong `X-Service-Key` → 403, with the right key → 200 (update journal's existing ingest tests); gateway against the real journal app via `httpx.ASGITransport` (throwaway DB) → trades land, second ingest `created == 0`.
- [ ] **Step 2–4:** RED → implement → `pytest services/mt5/tests services/journal/tests -q -W error` green.
- [ ] **Step 5:** Commit `feat(mt5): add account persistence and journal gateway; journal ingest requires service key`

### Task 4: `mt5` HTTP API and wiring

**Files:** `settings.py` (`Mt5Settings`: `service_name="mt5"`, `mongodb_url`, `database_name="mt5_db"`, `jwt_secret_key` ≥ 32, `journal_url="http://localhost:8002"`, `ingest_service_key` ≥ 32, `cors_origins`), `bootstrap.py`, `main.py`, router/schemas, `.env.example`, README; tests `tests/integration/test_http.py` (FakeTerminal + fake/ASGI journal).

**Routes (prefix `/api/v1/mt5`, Bearer):** `POST /accounts/link` (admin) → 201 new / 200 existing `{account}` · `GET /accounts` · `GET /accounts/{id}/status` · `POST /accounts/{id}/sync` (admin) → `{result: {created, updated, balance_events, open_positions}}` · `DELETE /accounts/{id}` (admin) → 200 · `GET /rates?symbol=&timeframe=&count=` → `{symbol, timeframe, candles: [{time, open, high, low, close, tick_volume}]}`.

- [ ] **Step 1:** Tests: non-admin link/sync/unlink → 403; admin link with terminal unavailable → 409 `TERMINAL_NOT_AVAILABLE`; link → 201, again → 200 same id; other admin linking same account → 409 `ACCOUNT_ALREADY_LINKED`; sync after terminal switched account → 409 `TERMINAL_ACCOUNT_MISMATCH` and fake journal received nothing; sync OK → counts; status disconnected → `connected: false`, `balance: null`; user B lists 0 and gets 404 on A's id; rates invalid timeframe → 422 `INVALID_TIMEFRAME`; unknown symbol → 404; `count > 1000` → 422; journal down on sync → 503; request body with a `password` field is rejected or ignored (no field exists; assert schema has no credential fields).
- [ ] **Step 2–4:** RED → implement → green (`-W error`).
- [ ] **Step 5:** Commit `feat(mt5): add HTTP API, settings and wiring`

### Task 5: Dev runner, docs, live smoke

**Files:** `scripts/dev.ps1` (+ mt5 8004; also check `INGEST_SERVICE_KEY` equal in journal and mt5 `.env`, case-sensitive, never printed), `docs/services-catalog.md` (mt5 in-progress; note the legacy `/api/v1/mt5` of `app/` is superseded), `docs/adr/0004-mt5-terminal-adapter.md` (attach to open terminal; Windows host; first adapter of the broker port; EA bridge = spec 002), `AGENTS.md`, `docs/CHANGELOG.md`.

- [ ] **Step 1:** Full run `pytest libs/shared/tests services tests -q -rs` → 0 failed, 0 skipped.
- [ ] **Step 2:** Ruff clean.
- [ ] **Step 3:** Smoke without terminal: `dev.ps1` with 4 services; promote a throwaway user to admin (`promote_admin.py`), `POST /accounts/link` → 409 `TERMINAL_NOT_AVAILABLE`; `GET /rates` → 409. Clean up the throwaway user.
- [ ] **Step 4 (owner present):** with the owner's MT5 terminal open and logged in (demo account recommended): link → account shown matches the terminal; sync → trades appear in journal; analytics summary reflects them; re-sync → `created == 0`; `GET /rates?symbol=<a symbol from the account>&timeframe=H1&count=50` → real candles. Then unlink if the owner wants. Never print balances or account numbers in logs committed to git.
- [ ] **Step 5:** Commit `docs: document mt5 service and terminal adapter`
