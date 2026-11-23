# Architecture rules

Target architecture: **microservices, each built with hexagonal architecture (ports & adapters)**,
applying SOLID, KISS, DRY and YAGNI. Background and diagrams: `docs/architecture.md`.

## Layers inside a service

| Layer | Contains | May import |
|---|---|---|
| `domain/` | Entities, value objects, domain errors, pure domain services | stdlib only (+ `dataclasses`, `decimal`, `datetime`) |
| `application/ports/` | `Protocol`s for what the application needs (repositories, gateways, clocks) | domain |
| `application/use_cases/` | One class per use case with an `execute(...)` method | domain, ports, `trading_shared.envelope` models (framework-free; never `trading_shared.http`) |
| `adapters/inbound/` | HTTP routers, request/response schemas, CLI, message consumers | application, domain, FastAPI, `trading_shared` |
| `adapters/outbound/` | Port implementations: Mongo, brokers, AI, email, HTTP clients | application ports, domain, drivers/SDKs |
| `bootstrap.py` | Composition root: builds adapters and injects them into use cases | everything |

```python
# application/ports/trade_repository.py — the use case depends on this, never on Motor
class TradeRepository(Protocol):
    async def upsert_many(self, user_id: str, trades: list[Trade]) -> int: ...

# adapters/outbound/mongo_trade_repository.py — the only file that knows about Motor
class MongoTradeRepository:
    def __init__(self, collection: AsyncIOMotorCollection): ...
```

Enforced by `tests/unit/test_architecture.py` in every service. Never delete that test.

## Service boundaries

- A service owns **one business capability** (auth, journal, analytics, mt5-bridge, backtester…).
- A service owns **its data**: logical database `<service>_db`. No service reads another service's
  collections — it calls that service's HTTP API through an outbound adapter.
- Shared code goes to `libs/shared` **only** if every service needs it and it has no domain logic.
  Duplicating a small DTO between two services is fine; sharing domain models is not.
- External systems (MT5, IBKR, AI providers, data vendors, Telegram…) are always behind a port.
  Swapping MetaApi for the EA bridge, or OpenAI for Claude, must only touch adapters and bootstrap.

## Communication

- Synchronous HTTP through the gateway: `/api/v1/<service>/<resource>` *(gateway planned, spec 001)*.
- Authentication: `auth` issues short-lived HS256 JWTs; other services verify signature + expiry
  locally via `trading_shared` *(planned, spec 001)*. No per-request call to `auth`.
- Asynchronous events/queues are introduced only through an ADR when a real need appears (YAGNI).

## Multi-tenancy

Every user-owned document has `user_id`. Repository methods take `user_id` as their first argument
and always filter by it. Cross-user queries exist only in use cases named `Admin…`.

## Principles, concretely

- **SRP:** routers translate HTTP ↔ use case; use cases orchestrate; domain decides.
- **OCP:** new broker/report format = new adapter implementing an existing port.
- **DIP:** use cases receive ports via constructor; only `bootstrap.py` picks implementations.
- **KISS/YAGNI:** in-memory adapter first, Mongo adapter when persistence is needed; no abstraction
  without a second implementation or a test that needs it.
