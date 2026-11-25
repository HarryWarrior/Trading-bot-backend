# MT5 bridge service (`mt5-bridge`, port 8005)

Receives what our MT5 Expert Advisor pushes (spec 002, ADR 0002): per-user **ingest tokens**, the
user's **broker accounts** with their heartbeat status, and (planned) raw deals forwarded to `journal`.
Never stores broker passwords.

Status: domain, use cases and Mongo storage built. HTTP API (tokens, accounts, EA ingest/heartbeat,
EA download) and the journal gateway are *(planned, spec 002 Task 4)*; today only `/health` is served.

## Layers

```
src/mt5_bridge_service/
  domain/            # IngestToken (hash only), BrokerAccount + Heartbeat (status: 5 min rule), RawDeal
  application/
    ports/           # TokenRepository, AccountRepository, JournalGateway, Clock, IdGenerator
    use_cases/       # IssueIngestToken, RevokeIngestToken, ListIngestTokens, RecordHeartbeat, ListAccounts
  adapters/
    inbound/http/    # FastAPI router (prefix /api/v1/mt5-bridge)
    outbound/        # MongoTokenRepository, MongoAccountRepository, SystemClock, UuidIdGenerator
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
`MONGO_DB` (default `bridge_db`), `CORS_ORIGINS`, `ENVIRONMENT`, `LOG_LEVEL`.

## Run & test (from the repository root)

```bash
pip install -e libs/shared -e "services/mt5-bridge[dev]"
pytest services/mt5-bridge/tests          # Mongo adapter tests need local MongoDB
cd services/mt5-bridge && uvicorn mt5_bridge_service.main:app --reload --port 8005
docker build -f services/mt5-bridge/Dockerfile -t mt5-bridge-service .
```
