# 002 — MT5 automatic sync via EA bridge (design)

- **Status:** draft
- **Date:** 2026-11-23
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/002-mt5-connection-ui/design.md`
- **Services touched:** new `mt5-bridge`; `journal` (ingest API); new MQL5 EA under `services/mt5-bridge/ea/`
- **Depends on:** 001 (`auth` JWT, `journal` service)
- **Decision record:** [ADR 0002](../../docs/adr/0002-mt5-ea-bridge.md)

## 1. Intent

Manual uploads do not work for users. A trader connects their MT5 account once and every execution
lands in their journal automatically, stored in MongoDB under their user, with no broker password
ever given to us.

## 2. Goals, non-goals, anti-goals

**Goals**
- User generates an **ingest token** in the web app (shown once), installs our EA, pastes the token.
- EA pushes every closed deal (`OnTradeTransaction`) and open-position snapshots via `WebRequest`.
- On first connect (and after downtime) the EA **backfills history** (`HistorySelect`) in batches.
- EA sends a **heartbeat** (account login, server, balance, equity, terminal build) every N seconds;
  the UI shows connected / last seen / last deal.
- Multiple MT5 accounts per user.

**Non-goals** — sending orders to MT5 (003), MT4, cTrader, IBKR.

**Anti-goals** — duplicated trades after reconnects; lost deals when the API is down; storing any
broker password; a setup so hard users give up.

## 3. Constraints

- Ingest tokens: 32+ random bytes, shown once, stored as SHA-256 hash, revocable, scope `ingest:mt5`,
  `last_used_at` tracked (`.agents/rules/security.md`).
- Idempotent upsert keyed by `(user_id, account_login, deal_ticket)` with a unique index.
- MT5 requires the user to whitelist our API URL in *Tools → Options → Expert Advisors → Allow WebRequest*.
- The EA must queue locally (file) and retry with backoff when the API is unreachable.

## 4. Research (first task of the plan)

| Candidate | Purpose | Verdict |
|---|---|---|
| Open-source MQL5 REST/WebRequest bridge EAs on GitHub | Reuse transport/JSON/retry code | TBD |
| ZeroMQ-based MT5 bridges | Alternative transport | TBD |
| MetaApi (cloud) | Fallback adapter for users who cannot run a terminal 24/7 | TBD |

Criteria: license, maintenance, JSON handling in MQL5, retry/queue support. Record in
`docs/integrations/README.md`.

## 5. Approaches

1. **EA pushes to `mt5-bridge`, which forwards normalized deals to `journal` (recommended).** Bridge
   owns tokens, accounts and connection status; journal owns trades.
2. EA pushes straight to `journal`. Rejected: mixes broker concerns into the journal domain.

## 6. Design sketch

- `mt5-bridge` domain: `IngestToken`, `BrokerAccount` (login, server, user_id, status, last_heartbeat),
  `DealBatch`. Use cases: `IssueIngestToken`, `RevokeIngestToken`, `IngestDeals`, `RecordHeartbeat`,
  `ListAccounts`. Ports: `TokenRepository`, `AccountRepository`, `JournalGateway`.
- Endpoints (EA-facing, token auth): `POST /api/v1/mt5-bridge/ingest/deals`,
  `POST /api/v1/mt5-bridge/ingest/heartbeat`. User-facing (JWT): tokens CRUD, accounts list/status,
  EA download.
- Deal → trade matching (entry/exit deals by `position_id`) lives in `journal`.
- EA (`ea/TradingJournalBridge.mq5`): inputs `ApiUrl`, `IngestToken`; JSON serialization; local queue file.

## 7. Open questions

- EA distribution: compiled `.ex5` download from the web app, MQL5 Market, or both?
- Heartbeat interval and "disconnected" threshold (proposal: 60 s / 5 min).
- Are prop-firm/broker restrictions on third-party EAs a concern for target users?

## 8. Done when

A real MT5 demo account with the EA produces journal trades within seconds of closing a deal; restart
and outage scenarios produce no duplicates and no gaps; token revocation stops ingestion immediately.
