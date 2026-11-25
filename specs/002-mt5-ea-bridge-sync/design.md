# 002 — MT5 automatic sync via EA bridge (design)

- **Status:** draft — awaiting owner approval
- **Date:** 2026-11-24
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/002-mt5-connection-ui/design.md`
- **Services touched:** new `mt5-bridge`; `journal` (raw-deal ingest + pairing); new MQL5 EA under `services/mt5-bridge/ea/`
- **Depends on:** 001 (`auth` JWT, `journal` service)
- **Decision record:** [ADR 0002](../../docs/adr/0002-mt5-ea-bridge.md)
- **Follow-up:** [005](../005-ea-distribution-and-market/design.md) (polished distribution, MQL5 Market, selling)

## 1. Intent

Manual uploads and the current terminal-reading `mt5` service do not scale to other users: `mt5` reads
the terminal on the host machine, so it only ever sees the owner's account. A trader connects their MT5
account once and every execution lands in their own journal automatically, with no broker password ever
given to us.

First user today: the owner only. Built multi-user from day one (per-user tokens, tenant isolation) so
opening it to other traders, and later selling the EA, needs no redesign. The same channel will feed the
bot of spec 003.

## 2. Goals, non-goals, anti-goals

**Goals**
- User generates an **ingest token** in the web app (shown once), downloads our EA from the web app,
  attaches it to a chart and pastes the token.
- EA pushes every closed deal (`OnTradeTransaction`) as a raw deal with its `deal_ticket`.
- On first connect and after downtime the EA **backfills history** (`HistorySelect`) in batches.
- EA sends a **heartbeat** (login, server, balance, equity, terminal build); UI shows connected /
  last seen / last deal.
- Multiple MT5 accounts per user.
- Old `mt5` service stays for private local use; both paths dedupe to the same trades.

**Non-goals** — sending orders to MT5 (003), MT4, cTrader, IBKR, EA signing/Market publishing (005), billing.

**Anti-goals** — duplicated trades after reconnects; lost deals when the API is down; storing any broker
password; a setup so hard users give up; EA logic that must change when opened to other users.

## 3. Constraints

- Ingest tokens: 32+ random bytes, shown once, stored as SHA-256 hash, revocable, scope `ingest:mt5`,
  `last_used_at` tracked (`.agents/rules/security.md`). Never logged.
- Idempotent upsert keyed `(user_id, account_login, deal_ticket)` with a unique index (raw deals), so
  retries and backfills never duplicate.
- Trade pairing (entry/exit by `position_id`) lives in `journal`, reusing the pairing/normalization logic
  of the existing `mt5` service; `account_ref = login@server` as today.
- The bridge calls journal with `X-Service-Key` (`INGEST_SERVICE_KEY`), like `mt5` does.
- MT5 requires the user to whitelist the API URL in *Tools → Options → Expert Advisors → Allow WebRequest*.
- EA queues locally (file) and retries with exponential backoff when the API is unreachable.
- Hexagonal rule, envelope, `user_id` on every document, English only.

## 4. Research (first task of the plan)

| Candidate | Purpose | Verdict |
|---|---|---|
| Open-source MQL5 REST/WebRequest bridge EAs on GitHub | Reuse transport/JSON/retry code | TBD |
| ZeroMQ-based MT5 bridges | Alternative transport | TBD |
| MetaApi (cloud) | Fallback adapter for users who cannot run a terminal 24/7 | TBD |

Criteria: license, maintenance, JSON handling in MQL5, retry/queue support. Record in
`docs/integrations/README.md`.

## 5. Approaches

1. **A (chosen): EA sends raw deals to `mt5-bridge`, which forwards to `journal`, which pairs them.**
   EA stays simple (deal + ticket); bridge owns tokens, accounts, status, heartbeat; journal owns
   trades. Costs one more service and pairing work in journal; EA barely changes when opened to others
   and serves spec 003.
2. B: EA pairs entry/exit and posts straight to journal. Rejected: complex MQL5 logic, broker concerns
   leak into the journal domain, hard to fix once distributed.
3. C: keep only the terminal-reading `mt5` service. Rejected: cannot serve other users' accounts.

## 6. Design

- `mt5-bridge` domain: `IngestToken`, `BrokerAccount` (login, server, user_id, status, last_heartbeat,
  last_deal_at), `RawDeal`, `DealBatch`. Use cases: `IssueIngestToken`, `RevokeIngestToken`,
  `IngestDeals`, `RecordHeartbeat`, `ListAccounts`. Ports: `TokenRepository`, `AccountRepository`,
  `JournalGateway`.
- EA-facing endpoints (token auth): `POST /api/v1/mt5-bridge/ingest/deals`,
  `POST /api/v1/mt5-bridge/ingest/heartbeat`.
- User-facing (JWT): token create/list/revoke, accounts list/status, `GET .../ea/download`.
- `journal`: new service-key endpoint accepting raw deals, storing them (unique key above) and
  (re)building the affected trades by `position_id`.
- EA `ea/TradingJournalBridge.mq5`: inputs `ApiUrl`, `IngestToken`; JSON serialization; file queue;
  batched backfill.

## 7. Decisions on former open questions (my proposals, correct if wrong)

- **Distribution:** compiled `.ex5` downloaded from the web app for now; MQL5 Market and signing in 005.
- **Heartbeat:** every 60 s; account shown as disconnected after 5 min without one.
- **Prop-firm/broker EA restrictions:** not blocking for the owner's own accounts; documented as a
  per-user caveat in the setup guide and revisited in 005.

## 8. Done when

A real MT5 demo account with the EA produces journal trades within seconds of closing a deal; restart
and outage scenarios produce no duplicates and no gaps; token revocation stops ingestion immediately;
two users' data stay isolated.
