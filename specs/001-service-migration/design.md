# 001 — Real data only: auth, journal, analytics and MT5 services (design)

- **Status:** done (2026-11-24)
- **Date:** 2026-11-23
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/001-feature-migration/design.md`
- **Branch:** `feat/001-real-data` (both repos, from `dev`)
- **Services:** new `auth`, `journal`, `analytics`, `mt5`; `libs/shared` (JWT, Mongo); legacy `app/` retired
- **Baseline:** `pytest tests/acceptance -rxX` (28 working behaviors, 14 known bugs)

## 1. Intent

Everything the product shows must be **real and working**: real users who log in, their own trades
stored in MongoDB, KPIs computed from those trades, and a real MetaTrader 5 connection that rejects
anything the terminal does not confirm. Today the app looks complete but much of it is fake:
simulated broker logins, random trades, random candles, invented balances, one shared dataset for
everybody, no login screen.

## 2. Goals, non-goals, anti-goals

**Goals**
1. **No data in code.** No demo mode, simulators, `random`/`Math.random` market data, hard-coded
   balances or prices. Example data lives only in external files (`data/samples/*.csv`) used by tests
   or uploaded by a user like any other report.
2. **Working login, end to end:** sign-up, email verification, sign-in, sign-out, password reset, and
   every API and page except auth requires a signed-in user.
3. **Trades in MongoDB, per user:** uploaded reports and MT5 history are stored in `journal_db`,
   isolated by `user_id`, idempotent (re-importing never duplicates).
4. **Correct analytics** from the user's own trades: rounded values, drawdown % never outside
   [-100, 0] and never invented when it cannot be computed.
5. **Real MT5 connection** by attaching to the MetaTrader 5 terminal already open and logged in on
   the host: the account is accepted only if the terminal confirms it; history and candles come from
   the terminal; no broker password is ever asked for or stored.
6. Built as hexagonal services from `services/_template`, following `.agents/rules/`.

**Non-goals** — EA bridge and remote users (spec 002), several MT5 accounts connected at the same
time, OAuth providers, billing, strategies/backtesting (003), AI journal (004).

**Anti-goals** (failure even if it "works")
- Any screen showing a number that did not come from the user's data or the broker.
- A placeholder that silently pretends to work (fake success, fake "connected", fake candles).
  When something is unavailable the UI says so ("MT5 terminal not running", "No market data").
- One user able to see another user's trades or accounts.
- Verification codes, passwords or tokens exposed in API responses or logs.

## 3. Constraints

- Owner decisions: **option A** (new services, retire `app/`), **MT5 option 1** (attach to the open
  terminal), MongoDB, two repos, rules in `.agents/rules/`.
- The `MetaTrader5` Python package runs **only on Windows**, in the same machine as a running
  terminal, and controls **one terminal session per process**. The `mt5` service therefore runs
  natively on the Windows host (not in a Linux container). MetaTrader 5 is installed on the owner's
  machine (`C:\Program Files\MetaTrader 5`).
- ADR 0002 stands (no broker passwords stored). This spec adds the terminal adapter as the first
  implementation of the broker port; the EA bridge is the second (002). An ADR 0004 records it.
- Docker is installed on the owner's machine but not always running; local development must also
  work without Docker (services via `uvicorn`, Mongo local).

## 4. Approaches

| Approach | Verdict |
|---|---|
| **A. New hexagonal services, strangle and retire `app/`** | **Chosen by owner** — nothing thrown away, matches architecture |
| B. Patch the legacy monolith | Rejected: throwaway work, breaks "app/ frozen" rule |

MT5 connectivity:

| Approach | Verdict |
|---|---|
| **1. Attach to the open, logged-in terminal (`MetaTrader5.initialize()` without credentials)** | **Chosen by owner** — real validation, no passwords stored; one account at a time, Windows only |
| 2. EA bridge | Spec 002 (second adapter of the same port) |
| 3. Log in with stored passwords | Rejected: ADR 0002 |

## 5. Design

### 5.1 Services, ports, data

| Service | Port (dev) | Database | Responsibility |
|---|---|---|---|
| `auth` | 8001 | `auth_db` | users, email verification codes, sessions/refresh tokens, JWT issuing, roles |
| `journal` | 8002 | `journal_db` | trades per user, report imports (CSV/XLSX), MT5 history ingest |
| `analytics` | 8003 | — | KPIs/time series computed from the caller's journal trades (HTTP to journal) |
| `mt5` | 8004 | `mt5_db` | link the terminal's account to the user, status, history sync into journal, candles |

All routes under `/api/v1/<service>/…`, envelope/pagination/errors from `trading_shared`
(`.agents/rules/api-contracts.md`).

### 5.2 `libs/shared` additions

- `trading_shared.auth`: `get_current_user` FastAPI dependency (verifies HS256 JWT signature and
  expiry with `JWT_SECRET_KEY`, returns `CurrentUser(id, email, role)`); `require_role`.
- `trading_shared.mongo`: `create_mongo_client(url)` / database accessor per service, index helper.
- `X-Request-ID` middleware.

### 5.3 `auth`

- Port of the working legacy flows (they pass the acceptance suite today), plus fixes:
  - Verification codes and reset tokens are **never returned** by the API. Codes from `secrets`.
  - Email via SMTP when configured. When `environment=local` and SMTP is not configured, the code is
    written to the server log (and only there). In `prod`, missing SMTP fails startup.
  - Tokens: access JWT 15 min (`sub`, `email`, `role`, `exp`, `iat`); refresh token 7 days, random,
    stored hashed in `auth_db.sessions`, rotated on refresh, revoked on sign-out and password reset.
  - `JWT_SECRET_KEY` required (no default) outside `local`.
- OAuth endpoints removed (they returned 501); OAuth stays out of scope.
- Migration script: legacy `trading_bot_db.users` → `auth_db.users` (users keep their password; they
  sign in again). Legacy sessions/verifications are not migrated.

### 5.4 `journal`

- Domain: `Trade` (round trip: open/close time, symbol, side, volume, prices, profit, commission,
  swap, source, source_ref), `ReportImport` (file SHA-256, name, counts, created_at).
- Report import: port the legacy parser (header detection, bilingual/duplicate columns, skip
  non-trade rows) behind a `ReportParser` port; unparseable rows are counted and reported, not hidden.
- Idempotency: same file (SHA-256) for the same user → 409 `DUPLICATE_IMPORT` with the previous
  import; trades upserted on natural key (`user_id`, `source`, `source_ref`) — `source_ref` is the
  MT5 position id when present, else a hash of the row.
- MT5 ingest endpoint used by the `mt5` service (service-to-service call carrying the user's JWT).
- Read API: trades list with pagination/search/filters (symbol, outcome, date range, profit range).

### 5.5 `analytics`

- Stateless; outbound port `TradeSource` (adapter: journal HTTP client forwarding the user's JWT).
- KPI functions ported from `analytics_service.py` **with tests**, fixing: rounding (money 2 dp,
  ratios 2 dp), drawdown % computed against peak equity including starting balance; when no starting
  balance is known (file uploads without balance rows) `max_drawdown_pct` is `null`, never invented.
- Same endpoints as today (summary, timeseries, by-symbol, hourly heatmap, daily/monthly stats).

### 5.6 `mt5` (terminal adapter)

- Port `BrokerTerminal`: `current_account() -> TerminalAccount | None`,
  `history_deals(from, to) -> list[Deal]`, `rates(symbol, timeframe, from, to) -> list[Candle]`.
  Adapter `MetaTrader5TerminalAdapter` uses `MetaTrader5.initialize()` **without credentials**
  (attaches to the running, logged-in terminal), calls run in a worker thread behind a lock
  (the package is process-global and synchronous).
- `POST /api/v1/mt5/accounts/link`: reads the terminal's current account (login, server, name,
  currency, balance, trade mode demo/real). If no terminal is running or it is not logged in →
  409 `TERMINAL_NOT_AVAILABLE`. If the account is already linked to another user → 409. The request
  body has **no credentials**.
- `POST /api/v1/mt5/accounts/{id}/sync`: only if the terminal is currently logged into that same
  account (else 409 `TERMINAL_ACCOUNT_MISMATCH`); reads deals since last sync (first sync: full
  history), builds trades by `position_id`, sends them to journal; reports created/updated counts.
- `GET /accounts`, `GET /accounts/{id}/status` (live: connected only if the terminal reports it now),
  `DELETE /accounts/{id}` (unlink; trades stay in journal).
- `GET /api/v1/mt5/rates`: real candles from the terminal; if unavailable → 409/503 with a clear code;
  the frontend shows "No market data".
- Balance/equity shown come from the terminal at the time of the call; stored values are labeled with
  their timestamp, never defaulted to 10 000/25 000.
- `MetaTrader5` added to the `mt5` service dependencies (Windows marker).

### 5.7 Data and repository hygiene

- `data/samples/sample_trades.csv` (moved from `data/raw/`) is the only example data in the repo; used
  by tests and documentation. The code never reads `data/` at runtime.
- Real reports (`ReportHistory-*.xlsx`, `reporte25-11.*`, `11119147_trades_*.csv`) are removed from
  the repo (`git rm --cached`) and moved to `data/private/` (git-ignored) on the owner's machine.
- Legacy collections in `trading_bot_db` (incl. the 3 duplicate "DEMO MT5" accounts) are not migrated
  except `users`; the database is left untouched for rollback until `app/` is deleted.

### 5.8 Local run

- `deploy/docker-compose.yml`: MongoDB + Traefik (gateway on :8000 routing `/api/v1/<service>` to the
  services; `mt5` routed to the Windows host via `host.docker.internal:8004`).
- Without Docker: `scripts/dev.ps1` starts the four services with `uvicorn`; the frontend's Nuxt dev
  proxy routes `/api/v1/<service>` to each port. Same URLs either way.
- `.env.example` per service (names only).

### 5.9 Tests and definition of real

- Each service: unit (domain, use cases with fakes), integration (HTTP, Mongo adapter on a throwaway DB),
  architecture test.
- `mt5`: unit/integration tests use a **fake `BrokerTerminal` defined in tests only**; a `live` test
  marker runs against the real terminal on demand (`pytest -m live`), skipped by default.
- A repository test fails if production code under `services/`, `libs/` contains `random` market data,
  `Math.random` candle generation, or hard-coded balances (grep guard over known patterns).
- New acceptance suite `tests/acceptance_services/` covering the 28 working behaviors + all 14 legacy
  known bugs, now expected to pass. When green, `app/`, legacy `tests/` and `tests/acceptance` are deleted.

### 5.10 Frontend (see companion doc)

Login/sign-up/verify/reset screens, route guard, token refresh, features `auth`, `journal`,
`analytics`, `mt5-connection` built from `features/_template`; legacy stores/pages removed; charts use
real candles or an empty state; no `Math.random` anywhere.

### 5.11 Clarifications (builder check — author's calls, owner may override)

1. **Legacy known bugs → new acceptance suite:** each of the 14 is rewritten against the new contract
   (not copied): OAuth test dropped (non-goal); "fake broker credentials" becomes "link is rejected
   when the terminal is not running / not logged in / account already linked"; "password not stored"
   becomes "link request accepts no credentials and stores none"; drawdown test asserts
   `null` or a value in [-100, 0]. "Green" = all rewritten tests pass.
2. **Balance and KPI scope:** `journal` stores `BalanceEvent`s (deposit, withdrawal, credit; from MT5
   balance deals, or from report rows when present). Every trade and event carries `account_ref`
   (MT5 `login@server`, or `upload` for flat files — one stable per-user ref so overlapping re-imports never duplicate; changed from `upload:<import id>` by plan 2 final-review ruling). Analytics accepts `account_ref` (default: all of the
   user's data). Starting balance = sum of balance events before the first trade of the scope; if
   none, drawdown % is `null`. Uploads do not ask for a manual balance (YAGNI).
3. **Same trade via two routes:** natural key is (`user_id`, `account_ref`, `position_id`) whenever a
   position id exists (MT5 sync and MT5 reports both have it), regardless of source; rows without a
   position id use a content hash. A report of an already-synced account therefore updates, never duplicates.
4. **Who links the terminal:** the host terminal belongs to the operator. Linking requires role
   `admin` in this spec (single-host deployment); other users get 403 `FORBIDDEN` and use report
   uploads until the EA bridge (002) lets each user connect their own terminal.
5. **Time zone:** everything stored in UTC. The terminal adapter derives the broker server offset
   (latest tick time vs. UTC, rounded to 30 min) and converts deal times. Report uploads are taken as
   broker server time with that same offset when the account is linked, else as UTC. Day/hour
   aggregations use UTC (user time zone display is a later spec). Acceptance expectations are
   recomputed accordingly.
6. **Trade comparison UI** (`BacktestingCompareModal`, `ComparisonGrid`, `TradeChartMini`): kept, moved
   into the `journal` feature, fed by real candles; trades without candles show the empty state.
7. **First admin:** `services/auth` ships `scripts/promote_admin.py <email>`; the user migration keeps
   existing roles.

## 6. Open questions (owner)

1. ~~Purge real reports from git history?~~ **Decided by owner: keep history**; reports are removed
   going forward only (`git rm --cached`, moved to git-ignored `data/private/`).

## 7. Left to the builder

Exact module names inside each service, port numbers if they collide, Traefik config style, the
grep-guard pattern list, migration script details.

## 8. Done when

- Owner signs up, verifies (code from email or local log), signs in on the web, uploads
  `data/samples/sample_trades.csv`, sees correct KPIs; a second user sees nothing of the first.
- With MT5 open and logged in, owner links the account, syncs, and sees the real history and real
  candles; with MT5 closed the app says so; a made-up account cannot be linked.
- No simulator/random/demo code remains (guard test green); `app/` removed; all service tests and the
  new acceptance suite green; frontend build green.
