# Data and MongoDB

MongoDB is the database for all services (one cluster; local default `mongodb://localhost:27017`).

## Ownership

- Each service owns one logical database: `<service>_db` (e.g. `journal_db`, `auth_db`).
- Only that service's outbound adapters touch its collections. Other services call its API.
- Legacy `app/` uses `trading_bot_db` until spec 001 splits it.

## Documents

- Every user-owned document has `user_id: str` and `created_at` / `updated_at` (UTC).
- Store ids as `ObjectId` in Mongo but expose them as strings; conversion happens only in adapters.
- Domain entities never contain `_id`, `ObjectId` or Motor types — map in the adapter.

```python
class MongoTradeRepository:
    async def list_by_user(self, user_id: str, page: int, page_size: int) -> tuple[list[Trade], int]:
        query = {"user_id": user_id}
        total = await self._collection.count_documents(query)
        cursor = (self._collection.find(query)
                  .sort("close_time", -1).skip((page - 1) * page_size).limit(page_size))
        return [self._to_domain(doc) async for doc in cursor], total
```

## Indexes

- Create indexes at service startup in the Mongo adapter (`create_indexes()`), idempotently.
- Every index used by a per-user query starts with `user_id`: `[("user_id", 1), ("close_time", -1)]`.
- Natural keys for idempotent ingestion get a **unique** compound index, e.g.
  `[("user_id", 1), ("account_login", 1), ("deal_ticket", 1)]`.
- Expiring data (sessions, OTP codes) uses TTL indexes on `expires_at`.

## Writes

- Ingestion is idempotent: `update_one(..., upsert=True)` or `bulk_write` with `UpdateOne(upsert=True)`
  on the natural key — never blind `insert_many` of external data.
- Money stored as numbers rounded to 2 decimals (or `Decimal128` when exactness matters).
- No multi-document transactions unless an ADR justifies them.

## Testing

Adapter tests run against a real local MongoDB using a throwaway database name
(`test_<service>_<uuid>`) dropped in teardown. Use-case tests use in-memory fakes, never Mongo.
