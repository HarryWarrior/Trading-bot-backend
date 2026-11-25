# Services catalog

Single list of backend services. Update it in the same PR that creates or changes a service.
Status: `active` · `in-progress` · `planned` · `legacy` · `retired`.

| Service | Purpose | Status | Database | Routes | Spec |
|---|---|---|---|---|---|
| `_template` | Canonical hexagonal service to copy | active | — (in-memory) | `/api/v1/template` | [000](../specs/000-agents-foundation/design.md) |
| `app` (legacy monolith) | Auth, analytics, MT5 accounts in one app; replaced by `auth`, `journal`, `analytics`, `mt5` | retired | `trading_bot_db` (unused) | — | [001](../specs/001-service-migration/design.md) |
| `auth` | Users, sessions, email OTP, roles, JWT issuing (port 8001) | active | `auth_db` | `/api/v1/auth` | [001](../specs/001-service-migration/design.md) |
| `journal` | Per-user trades and balance events; MT5/CSV/XLSX report upload and parsing (port 8002) | active | `journal_db` | `/api/v1/journal` (`/imports`, `/trades`, `/accounts`, `/dataset`, `/ingest/mt5`, `/ingest/deals`) | [001](../specs/001-service-migration/design.md) |
| `analytics` | KPIs, equity, drawdown, daily/monthly/symbol/hourly stats computed from journal (port 8003, stateless) | active | — (reads journal API) | `/api/v1/analytics` (`/summary`, `/equity`, `/daily`, `/monthly`, `/by-symbol`, `/hourly`) | [001](../specs/001-service-migration/design.md) |
| `mt5` | Attaches to the open, logged-in MetaTrader 5 terminal (Windows host only): links the account, syncs closed trades to journal, serves candles; admin-only link/sync/unlink (port 8004) | active | `mt5_db` | `/api/v1/mt5` (`/accounts/link`, `/accounts`, `/accounts/{id}/status`, `/accounts/{id}/sync`, `DELETE /accounts/{id}`, `/rates`) | [ADR 0004](adr/0004-mt5-terminal-adapter.md) |
| `mt5-bridge` | Per-user revocable ingest tokens, broker accounts with heartbeat status, and raw-deal intake forwarded to journal (port 8005). The MT5 EA that calls it is *(planned, spec 002 Task 7)* | in-progress | `bridge_db` | `/api/v1/mt5-bridge` (`POST /tokens`, `GET /tokens`, `DELETE /tokens/{id}`, `GET /accounts`, `POST /ingest/deals`, `POST /ingest/heartbeat`, `GET /ea/download`) | [002](../specs/002-mt5-ea-bridge-sync/design.md) |
| `strategies` | Strategy definitions and versions | planned | `strategies_db` | `/api/v1/strategies` | [003](../specs/003-strategy-backtest-live/design.md) |
| `backtester` | Run backtests, store results | planned | `backtester_db` | `/api/v1/backtester` | [003](../specs/003-strategy-backtest-live/design.md) |
| `execution` | Paper/live execution, risk limits, kill switch | planned | `execution_db` | `/api/v1/execution` | [003](../specs/003-strategy-backtest-live/design.md) |
| `journal-ai` | MCP server + API for AI-assisted journaling | planned | — (uses journal API) | `/api/v1/journal-ai` | [004](../specs/004-ai-journal/design.md) |
