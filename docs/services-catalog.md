# Services catalog

Single list of backend services. Update it in the same PR that creates or changes a service.
Status: `active` · `in-progress` · `planned` · `legacy` · `retired`.

| Service | Purpose | Status | Database | Routes | Spec |
|---|---|---|---|---|---|
| `_template` | Canonical hexagonal service to copy | active | — (in-memory) | `/api/v1/template` | [000](../specs/000-agents-foundation/design.md) |
| `app` (legacy monolith) | Auth, analytics, MT5 accounts in one app | legacy | `trading_bot_db` | `/api/v1/auth`, `/api/v1/analytics`, `/api/v1/mt5` | [001](../specs/001-service-migration/design.md) retires it |
| `auth` | Users, sessions, email OTP, roles, JWT issuing | planned | `auth_db` | `/api/v1/auth` | [001](../specs/001-service-migration/design.md) |
| `journal` | Per-user trades/executions, notes, tags, report upload | planned | `journal_db` | `/api/v1/journal` | [001](../specs/001-service-migration/design.md) |
| `analytics` | KPIs, equity, drawdown, heatmaps computed from journal | planned | — (reads journal API) | `/api/v1/analytics` | [001](../specs/001-service-migration/design.md) |
| `mt5-bridge` | Ingest tokens, receive deals/heartbeats from the MT5 EA | planned | `mt5_bridge_db` | `/api/v1/mt5-bridge` | [002](../specs/002-mt5-ea-bridge-sync/design.md) |
| `strategies` | Strategy definitions and versions | planned | `strategies_db` | `/api/v1/strategies` | [003](../specs/003-strategy-backtest-live/design.md) |
| `backtester` | Run backtests, store results | planned | `backtester_db` | `/api/v1/backtester` | [003](../specs/003-strategy-backtest-live/design.md) |
| `execution` | Paper/live execution, risk limits, kill switch | planned | `execution_db` | `/api/v1/execution` | [003](../specs/003-strategy-backtest-live/design.md) |
| `journal-ai` | MCP server + API for AI-assisted journaling | planned | — (uses journal API) | `/api/v1/journal-ai` | [004](../specs/004-ai-journal/design.md) |
