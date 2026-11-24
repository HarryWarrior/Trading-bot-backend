# 001 · Plan 2 of 4 — `journal` + `analytics` services

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each user's trades and balance events live in MongoDB (`journal_db`), imported idempotently from MT5 reports and flat CSVs, and `analytics` computes correct, rounded KPIs from that user's data only.

**Architecture:** Two hexagonal services copied from `services/_template`. `journal` (port 8002) owns trades, balance events and imports; report formats are adapters behind a `ReportParser` port. `analytics` (port 8003) is stateless: a `TradeSource` port (adapter: HTTP client to journal forwarding the caller's JWT) feeds pure KPI functions. Both verify JWTs with `trading_shared.auth`.

**Tech Stack:** Python 3.11+, FastAPI 0.104.1, Pydantic 2.5, motor 3.7.1 / pymongo 4.18.0, pandas 2.1.3 + openpyxl 3.1.2 (parsers only), httpx 0.25.2, pytest 7.4.3 + pytest-asyncio 0.21.1.

**Spec:** `specs/001-service-migration/design.md` (§2, §5.4, §5.5, §5.11-2, -3, -5). Plan 1 (`plan-1-auth.md`) is done; its JWT/Mongo helpers and conventions apply.

## Global Constraints

- Branch `feat/001-real-data`; one commit per task; never push without the owner.
- `.agents/rules/` apply; envelope/pagination/errors from `trading_shared` (`Depends(page_params)` for lists); every route except `/health` requires `current_user_dependency`; every query filters by `user_id`.
- **No data in code:** no demo trades/balances/prices; tests build synthetic reports in code or use `data/samples/sample_trades.csv`; real reports in `data/private/` are never committed (an optional `-m private` test may read them when present, skipped otherwise).
- Settings follow plan 1: `jwt_secret_key` required, ≥ 32 chars, same secret as `auth`; `mongodb_url`, `database_name` (`journal_db`); `journal_url` for analytics (default `http://localhost:8002`).
- Money and ratios rounded to 2 decimals at the API edge; percentages in percent units; nothing invented: unknown → `null`.
- Net trade result = `profit + commission + swap` (all KPIs use net).
- Times stored as timezone-aware UTC. Report times without a known broker offset are taken as UTC (offset handling arrives with MT5 linking in plan 3).
- `account_ref`: MT5 report → `"<login>@<server>"` from the report header; flat CSV (and MT5 reports without a parseable Account line) → the stable per-user `"upload"` so row hashes dedupe across overlapping uploads (changed by final-review ruling; was `"upload:<import_id>"`); MT5 ingest → given by caller.
- Natural keys (unique indexes): trades `(user_id, account_ref, position_id)` when `position_id` is known, else `(user_id, account_ref, row_hash)`; balance events `(user_id, account_ref, source_ref)`.
- Uploads: `.csv`, `.xlsx`, `.xls`; ≤ 10 MB; same file (SHA-256) for the same user → 409 `DUPLICATE_IMPORT` with `details.import_id`.
- Error codes: `DUPLICATE_IMPORT` 409, `UNSUPPORTED_FILE` 400, `FILE_TOO_LARGE` 413, `UNREADABLE_REPORT` 400 (with `details.reason`), `NOT_FOUND` 404, `JOURNAL_UNAVAILABLE` 503.

## Review Focus

1. Same MT5 report uploaded under two filenames → second is 409; a *newer* report of the same account (superset of positions) → only new positions created, existing ones updated, none duplicated. (Task 1)
2. User B never sees user A's trades, accounts, imports or KPIs — including by guessing a trade id (→ 404). (Tasks 1, 4, 6)
3. A report where some rows are malformed → import succeeds for the good rows and returns `skipped_rows` with row numbers and reasons; a file with no recognizable table → 400 `UNREADABLE_REPORT`. (Task 2)
4. No balance information → `max_drawdown_pct` and `starting_balance` are `null`, never 0 or a made-up base; with balance events the percentage stays within [-100, 0]. (Task 5)
5. A user with zero trades → summary returns zeros/nulls with 200, not 500; journal down → analytics 503 `JOURNAL_UNAVAILABLE`. (Tasks 5, 6)

---

### Task 1: `journal` domain and use cases

**Files:** create `services/journal/` from `services/_template` (package `journal_service`, prefix `/api/v1/journal`, add to root ruff `known-first-party`); `src/journal_service/domain/{trade.py, balance.py, report_import.py, errors.py, keys.py}`, `application/ports/{repositories.py, parsing.py, clock.py, ids.py}`, `application/use_cases/{import_report.py, ingest_mt5_history.py, list_trades.py, get_trade.py, list_accounts.py, list_imports.py, get_dataset.py}`; tests `tests/conftest.py` (fakes as fixtures), `tests/unit/test_use_cases.py`, architecture test.

**Interfaces — Produces:**
- `Side(StrEnum)`: `BUY`, `SELL`. `Outcome(StrEnum)`: `WIN`, `LOSS`, `BREAKEVEN`.
- `Trade(id, user_id, account_ref, position_id: str | None, row_hash: str | None, source: "report"|"mt5", import_id: str | None, symbol, side, volume: Decimal, open_time, close_time, open_price: Decimal, close_price: Decimal, stop_loss: Decimal | None, take_profit: Decimal | None, commission: Decimal, swap: Decimal, profit: Decimal, comment: str | None)`; properties `net` (`profit + commission + swap`), `outcome`, `duration_minutes`.
- `BalanceEvent(id, user_id, account_ref, kind: "deposit"|"withdrawal"|"credit", amount: Decimal (signed), time, source_ref: str, comment)`.
- `ReportImport(id, user_id, filename, sha256, account_ref, trades_created, trades_updated, balance_events, skipped_rows: list[SkippedRow], created_at)`; `SkippedRow(row: int, reason: str)`.
- `keys.row_hash(account_ref, symbol, side, open_time, close_time, volume, open_price, close_price, profit) -> str` (SHA-256 of a canonical string).
- Parsing port: `ParsedReport(account: ReportAccount | None, trades: list[ParsedTrade], balance_events: list[ParsedBalanceEvent], skipped_rows: list[SkippedRow])`; `ReportAccount(login: str, server: str, currency: str | None)`; `ReportParser.parse(filename: str, content: bytes) -> ParsedReport` (raises `UnreadableReport(reason)`).
- Repository ports: `TradeRepository.upsert_many(user_id, trades) -> tuple[int, int]` (created, updated) · `list(user_id, filters: TradeFilters, page, page_size, sort_by, sort_dir) -> tuple[list[Trade], int]` · `get(user_id, trade_id) -> Trade | None` · `all_for(user_id, account_ref: str | None) -> list[Trade]` · `accounts(user_id) -> list[AccountSummary(account_ref, trades, first_trade_at, last_trade_at)]`; `BalanceRepository.upsert_many(user_id, events) -> int` · `all_for(user_id, account_ref | None)`; `ImportRepository.add`, `find_by_sha(user_id, sha256)`, `list(user_id, page, page_size)`.
- `TradeFilters(symbol, outcome, date_from, date_to, profit_min, profit_max, account_ref, q)`.
- Use cases: `ImportReport(parser, trades, balances, imports, clock, ids).execute(user_id, filename, content) -> ReportImport` (raises `DuplicateImport(import_id)`); `IngestMt5History.execute(user_id, account_ref, trades: list[ParsedTrade], balance_events) -> IngestResult(created, updated, balance_events)`; `ListTrades.execute(user_id, filters, params)`; `GetTrade.execute(user_id, trade_id)` (raises `TradeNotFound`); `ListAccounts`, `ListImports`, `GetDataset.execute(user_id, account_ref | None) -> Dataset(trades, balance_events)`.

- [ ] **Step 1:** Failing tests (fake parser returning canned `ParsedReport`s): `test_import_creates_trades_and_balance_events`; `test_same_file_twice_raises_duplicate_import_with_previous_id`; `test_newer_report_updates_existing_positions_and_adds_new_ones` (positions 1,2 then 1,2,3 → created 1, updated 2); `test_rows_without_position_id_deduplicate_by_row_hash`; `test_flat_csv_import_uses_upload_account_ref` (`account_ref == f"upload:{import.id}"`); `test_mt5_report_uses_login_at_server_account_ref`; `test_skipped_rows_are_recorded`; `test_users_are_isolated` (B lists 0, B `GetTrade` of A's id → `TradeNotFound`); `test_net_includes_commission_and_swap`; `test_outcome_breakeven_when_net_is_zero`; `test_ingest_mt5_history_is_idempotent`.
- [ ] **Step 2:** `pytest services/journal/tests -q` → FAIL.
- [ ] **Step 3:** Implement domain, ports, use cases (Decimal throughout the domain).
- [ ] **Step 4:** `pytest services/journal/tests -q -W error` → pass (architecture test included).
- [ ] **Step 5:** Commit `feat(journal): add journal domain and use cases`

### Task 2: Report parsers

**Files:** `src/journal_service/adapters/outbound/parsers/{mt5_report.py, flat_csv.py, dispatcher.py, encoding.py}`; `services/journal/pyproject.toml` (+ `pandas==2.1.3`, `openpyxl==3.1.2`); tests `tests/unit/test_parsers.py`, `tests/unit/report_builders.py` (builds synthetic MT5 `.xlsx` and `.csv` reports in memory with openpyxl), `tests/private/test_private_reports.py` (`@pytest.mark.private`, skipped unless `data/private/` files exist and `-m private` is given).

**Interfaces:** `DispatchingReportParser(parsers: list[ReportParser])` implements `ReportParser` (first parser whose `accepts(filename, content)` is true; none → `UnreadableReport("unrecognized format")`). `Mt5ReportParser`: MT5 "Trade History Report" (header rows `Account: <login> (<currency>, <server>, …)`; section `Positions` → trades with `position_id` from the `Position` column, duplicate columns Time/Price = open/close, `S / L`, `T / P`, Commission, Swap, Profit; section `Deals` rows with Type `balance`/`credit` → balance events (`source_ref` = Deal ticket; deposit/withdrawal by sign; credit as `credit`)). `FlatCsvParser`: one-table CSV/XLSX with English or Spanish headers (port the legacy header detection and column aliases from `app/services/trade_parser_service.py`, incl. `Ticket` → `position_id` when present); rows that fail to parse → `SkippedRow(row_number, reason)`. `decode_text(content) -> str`: utf-8-sig, then utf-16 (BOM), then cp1252.

- [ ] **Step 1:** Failing tests: `test_mt5_xlsx_positions_and_balance` (synthetic report: header account `12345678 (USD, Demo-Server, demo, Hedge)`, 3 positions, 1 deposit 10000, 1 withdrawal -500 → account `12345678@Demo-Server`, 3 trades with position ids, 2 balance events); `test_mt5_report_ignores_orders_and_results_sections`; `test_sample_csv_parses_10_trades` (`data/samples/sample_trades.csv`: 10 trades, total profit 1450); `test_spanish_headers`; `test_utf16_csv_is_decoded`; `test_malformed_row_is_skipped_with_reason` (row with profit "abc" → skipped, others kept); `test_unrecognized_file_raises_unreadable_report`; `test_ticket_column_becomes_position_id`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** `pytest services/journal/tests -q -W error` → pass; `pytest services/journal/tests -m private -q` → parses every local private report without exceptions (record counts in the report; not committed).
- [ ] **Step 5:** Commit `feat(journal): add MT5 and flat CSV report parsers`

### Task 3: `journal` Mongo adapters

**Files:** `adapters/outbound/{mongo_repositories.py, system_clock.py, uuid_ids.py}`; tests `tests/integration/test_mongo_repositories.py` (throwaway `test_journal_<uuid>`, skip if Mongo unreachable).

**Interfaces:** `MongoTradeRepository(db)`, `MongoBalanceRepository(db)`, `MongoImportRepository(db)`, each `async create_indexes()`. Decimals stored as `Decimal128`; datetimes tz-aware. `upsert_many` uses `bulk_write` of `UpdateOne(natural_key, {"$set": …, "$setOnInsert": {"_id", "created_at"}}, upsert=True)` and returns created/updated from the result. Indexes: unique partial `(user_id, account_ref, position_id)` where `position_id` exists; unique partial `(user_id, account_ref, row_hash)` where `row_hash` exists; `(user_id, close_time)`; balance unique `(user_id, account_ref, source_ref)`; imports unique `(user_id, sha256)`.

- [ ] **Step 1:** Tests: upsert twice → second all `updated`; partial unique indexes reject duplicates; `list` filters (symbol, outcome, date range, profit range, account_ref, q on symbol/comment) and sorts (`close_time`, `open_time`, `profit`, `symbol`) with pagination totals; `get` of another user's id → None; `accounts` aggregates per account_ref; Decimal round-trip exact (e.g. `Decimal("0.1") + Decimal("0.2")`).
- [ ] **Step 2–4:** RED → implement → `pytest services/journal/tests -q -W error` green.
- [ ] **Step 5:** Commit `feat(journal): add Mongo repositories`

### Task 4: `journal` HTTP API and wiring

**Files:** `settings.py` (`JournalSettings`: `service_name="journal"`, `mongodb_url`, `database_name="journal_db"`, `jwt_secret_key` (≥ 32), `cors_origins`, `max_upload_mb=10`), `bootstrap.py`, `main.py` (lifespan: indexes; `RequestIdMiddleware`; CORS; `register_error_handlers`; domain error → `AppError` mapping in one place), `adapters/inbound/http/{router.py, schemas.py}`, `.env.example`, `README.md`; tests `tests/integration/test_http.py` (tokens minted with the test secret via `jwt.encode` with `sub/email/role/iat/exp`).

**Routes (prefix `/api/v1/journal`, Bearer required):** `POST /imports` (multipart `file`) → 201 `{import}` · `GET /imports` (paginated) · `GET /trades` (paginated; query `symbol, outcome, date_from, date_to, profit_min, profit_max, account_ref` + `page_params`; `sort_by` ∈ `close_time|open_time|profit|symbol`, else 422) · `GET /trades/{id}` → 404 `NOT_FOUND` for missing/other user's · `GET /accounts` · `GET /dataset?account_ref=` → `{trades, balance_events}` (unpaginated, for analytics) · `POST /ingest/mt5` `{account_ref, trades, balance_events}` → 200 `{created, updated, balance_events}`. Trade JSON: all decimals serialized as JSON numbers; money fields (`commission, swap, profit, net`) rounded to 2 dp; prices and volume unrounded; fields `id, account_ref, position_id, symbol, side, volume, open_time, close_time, open_price, close_price, stop_loss, take_profit, commission, swap, profit, net, outcome, duration_minutes, comment, source, import_id` (never `user_id`, `row_hash`).

- [ ] **Step 1:** Tests: upload `data/samples/sample_trades.csv` → 201, 10 created; same upload → 409 `DUPLICATE_IMPORT` with `details.import_id`; `.txt` → 400 `UNSUPPORTED_FILE`; > 10 MB → 413 `FILE_TOO_LARGE`; garbage `.csv` → 400 `UNREADABLE_REPORT`; list with filters/pagination; `sort_by=password` → 422; user B sees 0 trades and gets 404 on A's trade id; no token → 401; dataset returns trades + balance events; ingest twice → second `created == 0`.
- [ ] **Step 2–4:** RED → implement → green (`-W error`). Smoke: `uvicorn journal_service.main:app --port 8002` with a git-ignored `.env` (same `JWT_SECRET_KEY` as auth) → upload the sample with a token from the running auth service; stop the server.
- [ ] **Step 5:** Commit `feat(journal): add HTTP API, settings and wiring`

### Task 5: `analytics` domain (pure KPIs)

**Files:** create `services/analytics/` from the template (package `analytics_service`, prefix `/api/v1/analytics`, ruff first-party); `src/analytics_service/domain/{dataset.py, summary.py, series.py, rounding.py}`; tests `tests/unit/test_summary.py`, `tests/unit/test_series.py`, architecture test.

**Interfaces:** `TradeRecord(symbol, side, open_time, close_time, net: Decimal)` and `BalanceRecord(time, amount: Decimal)`; `Dataset(trades, balance_events)`. `summarize(dataset) -> Summary(total_trades, wins, losses, breakeven, win_rate, gross_profit, gross_loss, net_profit, profit_factor | None, payoff_ratio | None, average_trade | None, max_drawdown, max_drawdown_pct | None, longest_win_streak, longest_loss_streak, best_day | None, best_day_net | None, worst_day | None, worst_day_net | None, starting_balance | None, ending_balance | None)`. `equity_curve(dataset) -> list[EquityPoint(time, equity)]` (starts at starting balance when known, else 0), `daily(dataset)`, `monthly(dataset)`, `by_symbol(dataset)`, `hourly(dataset)` (UTC hour of `close_time`). Rules: trades ordered by `close_time`; starting balance = sum of balance events before the first trade, `None` if there are none; drawdown measured on equity including balance events at their times; `max_drawdown_pct = max_drawdown / peak_equity_at_that_point * 100` only when starting balance is known, else `None`; profit factor `None` when gross loss is 0; payoff `None` when no wins or no losses; all outputs rounded via `round_money(x) -> Decimal` (2 dp, ROUND_HALF_UP).

- [ ] **Step 1:** Failing tests with exact values: **sample** (10 trades from `data/samples/sample_trades.csv`, nets 200, 50, -150, 600, -100, 160, 240, 200, -50, 300): total 10, wins 7, losses 3, win_rate 70.00, gross_profit 1750.00, gross_loss -300.00, net_profit 1450.00, profit_factor 5.83, payoff 2.50, average_trade 145.00, max_drawdown -150.00, max_drawdown_pct None, starting_balance None, longest_win_streak 3, best_day 2025-01-16 (660.00), worst_day 2025-01-15 (100.00). **With balance:** deposit 1000 then trades +10, -400 → max_drawdown -400.00, max_drawdown_pct -39.60, starting_balance 1000.00, ending_balance 610.00. **Deposit mid-way** does not count as profit (deposit 1000, trade +100, deposit 500, trade -50 → net_profit 50.00, ending_balance 1550.00). **Empty dataset** → zeros and Nones, no exception. **All wins** → profit_factor None, payoff None. Equity curve, daily/monthly/by-symbol/hourly shapes on the sample.
- [ ] **Step 2–4:** RED → implement → `pytest services/analytics/tests -q -W error` green.
- [ ] **Step 5:** Commit `feat(analytics): add KPI domain`

### Task 6: `analytics` service app

**Files:** `application/ports/trade_source.py` (`TradeSource.fetch(token: str, account_ref: str | None) -> Dataset`, raises `SourceUnavailable`), `application/use_cases/{get_summary.py, get_series.py}`, `adapters/outbound/journal_client.py` (`JournalHttpTradeSource(base_url, transport=None)` with httpx, forwards `Authorization`, maps journal 401 → `UNAUTHENTICATED`, connection errors/5xx → `SourceUnavailable`), `settings.py` (`AnalyticsSettings`: `service_name="analytics"`, `jwt_secret_key` ≥ 32, `journal_url="http://localhost:8002"`, `cors_origins`), `bootstrap.py`, `main.py`, router/schemas, `.env.example`, README; tests `tests/integration/test_http.py`, `tests/integration/test_with_journal.py`.

**Routes (prefix `/api/v1/analytics`, Bearer required, all accept `account_ref`):** `GET /summary`, `/equity`, `/daily`, `/monthly`, `/by-symbol`, `/hourly`. Decimals serialized as numbers with 2 dp; `None` as `null`.

- [ ] **Step 1:** Tests: with a fake `TradeSource` → summary matches Task 5 sample values; journal unreachable (fake raising) → 503 `JOURNAL_UNAVAILABLE`; no token → 401; **end-to-end without ports**: `test_with_journal.py` builds the journal app (throwaway Mongo DB) and points `JournalHttpTradeSource` at it via `httpx.ASGITransport`; user A uploads the sample → A's summary net 1450.00; user B's summary total_trades 0.
- [ ] **Step 2–4:** RED → implement → `pytest services/analytics/tests services/journal/tests -q -W error` green.
- [ ] **Step 5:** Commit `feat(analytics): add analytics API backed by journal`

### Task 7: Dev runner, docs, verification

**Files:** `scripts/dev.ps1` (add journal 8002, analytics 8003; all three services share one `JWT_SECRET_KEY` — document), `docs/services-catalog.md` (journal, analytics → in-progress with ports), `AGENTS.md` run/test section, `docs/CHANGELOG.md`, `.agents/rules/api-contracts.md` (journal/analytics examples only if a rule changed — else untouched).

- [ ] **Step 1:** Full run `pytest libs/shared/tests services tests -q -rs` → 0 failed, 0 skipped (legacy acceptance `28 passed, 14 xfailed` within).
- [ ] **Step 2:** `ruff check libs services tests && ruff format --check libs services tests` clean.
- [ ] **Step 3:** Smoke with `scripts/dev.ps1`: sign up + verify + sign in on auth (code from console), upload `data/samples/sample_trades.csv` to journal, `GET /api/v1/analytics/summary` → net_profit 1450.00, win_rate 70.00; stop services; remove the throwaway user and its journal data by exact ids.
- [ ] **Step 4:** Commit `docs: document journal and analytics services`

## Execution notes (plan 2 done)

Executed subagent-driven; every task reviewed; final whole-branch review → one fix wave (I1–I4, absolute row numbers,
balance upsert count, legacy python-multipart) plus an addendum for a regression it introduced (MT5 account-summary block)
and a stricter drawdown-% rule. Real local MT5 reports: all six parse with 0 skipped rows.

**Carried to plan 4 (hardening before exposure beyond localhost):** fastapi 0.104 / starlette 0.27 upload DoS CVEs
(CVE-2024-47874, CVE-2025-54121) → upgrade or proxy body-size limit; upload body spooled before cap/auth; openpyxl
decompression-bomb limits.

**Carried to plan 3 (MT5 sync):** `/ingest/mt5` should be restricted to the mt5 service/role; IngestRequest list bounds and
`gt=0` on volume/prices; ordered bulk_write partial apply on concurrent duplicates; broker server time offset for report
times; MT5 CSV/HTML exports currently fall back to the flat parser.

**Small follow-ups:** `ending_balance` can be negative; trades imported before the `upload` ruling keep `upload:<id>`
(local data only); EU "1.234" with a lone dot is read as a decimal; `profit_min/max` and `sort_by=profit` act on net
(document or rename); `created_at` uses the wall clock; no indexes for open_time/symbol/net sorts; dev.ps1 ignores
`export KEY=` / inline `#` dotenv forms; analytics creates an AsyncClient per request.
