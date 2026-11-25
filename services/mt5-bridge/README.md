# MT5 bridge service (`mt5-bridge`, port 8005)

Receives what our MT5 Expert Advisor pushes (spec 002, ADR 0002): per-user **ingest tokens**, the
user's **broker accounts** with their heartbeat status, and raw deals forwarded to `journal`.
Never stores broker passwords.

Status: HTTP API and journal forwarding built. The EA source is in [`ea/`](ea/README.md)
*(awaiting compile and real-account verification, Task 8)*.

## API (prefix `/api/v1/mt5-bridge`, standard envelope)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/ingest/deals` | `Bearer <ingest token>` | `{account_login, server, deals: [...]}`, at most 200 deals, tz-aware times |
| POST | `/ingest/heartbeat` | `Bearer <ingest token>` | `{account_login, server, balance, equity, terminal_build?}`; upserts the account |
| POST | `/tokens` | JWT | `{name}` -> 201 with `plaintext_token` (the only time it is returned) |
| GET | `/tokens` | JWT | `Page` (`items`, `pagination`; `page`, `page_size`), newest first; never the plaintext or the hash |
| DELETE | `/tokens/{id}` | JWT | Revoke (idempotent); 404 for unknown or another user's token |
| GET | `/accounts` | JWT | `Page` by `account_ref`, each with `status` `connected` / `disconnected` (5 min rule) |
| GET | `/ea/download` | JWT | Serves `ea/TradingJournalBridge.ex5`; 404 `NOT_FOUND` until it is built |

Every ingest request updates the token's `last_used_at`; the owner always comes from the token.
Deals go to journal's `POST /api/v1/journal/ingest/deals` with `X-Service-Key`, and
`last_deal_at` of an existing account moves forward once journal accepts them.

The 200 answer is `{received, new, trades_upserted, balance_events, skipped: [{position_id, reason}]}`.
Positions journal cannot pair (reversals, exit volume above entry, mixed sides) are listed in `skipped`
and logged at WARNING (ids and reasons only). When journal refuses a batch (422 `JOURNAL_REJECTED`) the
bridge logs the ticket range and count at WARNING (never the payload), so a stuck batch can be skipped
by raising the EA high-water mark above its last ticket.

EA retry contract for `/ingest/deals`:

| Answer | Meaning for the EA |
|---|---|
| 200 | Accepted (idempotent: resending is harmless) |
| 401 `UNAUTHENTICATED` | Token unknown or revoked: stop and ask the user for a new token |
| 422 `VALIDATION_ERROR` / `INVALID_DEAL_BATCH` / `JOURNAL_REJECTED` | The batch can never be accepted: do not retry it |
| 503 `JOURNAL_UNAVAILABLE` | Journal down, timed out or misconfigured: keep the batch queued and retry |

## Layers

```
src/mt5_bridge_service/
  domain/            # IngestToken (hash only), BrokerAccount + Heartbeat (status: 5 min rule), RawDeal
  application/
    ports/           # TokenRepository, AccountRepository, JournalGateway, Clock, IdGenerator
    use_cases/       # IssueIngestToken, RevokeIngestToken, ListIngestTokens, AuthenticateIngestToken,
                     # RecordHeartbeat, ListAccounts, IngestDeals
  adapters/
    inbound/http/    # router, schemas, token_auth (ingest token bearer)
    outbound/        # JournalHttpGateway, MongoTokenRepository, MongoAccountRepository, SystemClock, UuidIdGenerator
  settings.py  bootstrap.py  main.py
```

## Data (`bridge_db`)

| Collection | Key | Notes |
|---|---|---|
| `ingest_tokens` | `_id`; unique `hash` | SHA-256 of the token only; `scope` `ingest:mt5`, `last_used_at`, `revoked_at` |
| `accounts` | unique `(user_id, account_ref)` | `account_ref = login@server`; balance, equity, `last_heartbeat`, `last_deal_at` |

Every query filters by `user_id`, except the token lookup by hash (that is how the owner is found).

## Configuration (`.env`, git-ignored; copy `.env.example`)

`JWT_SECRET_KEY` (same as auth), `INGEST_SERVICE_KEY` (same as journal), `JOURNAL_URL`, `MONGO_URL`,
`MONGO_DB` (default `bridge_db`), `CORS_ORIGINS`, `ENVIRONMENT`, `LOG_LEVEL`, optional
`JOURNAL_TIMEOUT_SECONDS` (default 10) and `EA_FILE_PATH` (default `ea/TradingJournalBridge.ex5` of
this folder; the Dockerfile sets it for the installed package).

## Run & test (from the repository root)

```bash
pip install -e libs/shared -e "services/mt5-bridge[dev]"
pytest services/mt5-bridge/tests          # Mongo adapter tests need local MongoDB
cd services/mt5-bridge && uvicorn mt5_bridge_service.main:app --reload --port 8005
docker build -f services/mt5-bridge/Dockerfile -t mt5-bridge-service .
```
