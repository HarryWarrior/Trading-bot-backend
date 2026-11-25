# API contracts

All services expose the same contract, implemented in `libs/shared` (`trading_shared`).
Use its helpers — never hand-build envelopes.

## URLs

- `/api/v1/<service>/<resource>` — plural nouns, kebab-case: `/api/v1/journal/trades`.
- Actions that are not CRUD use a sub-resource verb: `POST /api/v1/mt5-bridge/tokens/{id}/revoke`.
- `GET /health` on every service (outside the prefix).
- Breaking change → new version prefix (`/api/v2/...`), never silently change v1.

## Success envelope

```json
{
  "success": true,
  "data": { "...": "..." },
  "message": "Operation completed successfully",
  "meta": { "timestamp": "2026-09-08T12:00:00Z", "version": "2.0.0" }
}
```

```python
return ok(ItemOut.from_domain(item), container.settings.version, "Item created")
```

## Collections: pagination and search

Every collection endpoint accepts `page` (≥1, default 1), `page_size` (1–100, default 20),
`sort_by`, `sort_dir` (`asc`|`desc`, default `desc`) and `q` (free-text search).

```python
@router.get("/items", response_model=SuccessResponse[Page[ItemOut]])
async def list_items(params: PageParams = Depends(page_params), ...):
    items, total = await container.list_items.execute(user_id, params)
    return ok(Page[ItemOut](items=..., pagination=build_pagination(params.page, params.page_size, total)), version)
```

Always `Depends(page_params)` (from `trading_shared.http`) — a bare `Depends()` on `PageParams` does not enforce the limits.
`data` is `{ "items": [...], "pagination": { page, page_size, total_items, total_pages, has_next, has_prev } }`.

## Errors

```json
{ "success": false, "error": { "code": "INVALID_FILE_FORMAT", "message": "...", "details": null } }
```

- `code` is UPPER_SNAKE_CASE and stable (clients branch on it); `message` is human-readable English.
- Raise `AppError(code, message, status_code, details)`. `register_error_handlers` renders everything
  else with the same envelope: validation → 422 `VALIDATION_ERROR` (details without submitted values),
  `HTTPException`/unknown route → `NOT_FOUND`, `FORBIDDEN`, … (`HTTP_<status>` otherwise), unhandled
  exception → 500 `INTERNAL_ERROR` (logged, message never leaks internals).

| Status | Use |
|---|---|
| 200 | Read/update succeeded |
| 201 | Resource created |
| 400 | Business rule violated (domain error) |
| 401 | Missing/invalid/expired token (`UNAUTHENTICATED`) |
| 403 | Authenticated but not allowed / email not verified (`FORBIDDEN`) |
| 404 | Resource not found for this user (`NOT_FOUND`) — never reveal other users' resources |
| 409 | Conflict / duplicate |
| 422 | Request validation (`VALIDATION_ERROR`) |
| 500 | Unhandled error — a bug |

## Data rules

- PnL and balances: USD rounded to **2 decimals**. Prices: FX 4–5 decimals, crypto up to 8.
- Timestamps: ISO 8601 UTC with `Z`.
- Field names: `snake_case` in JSON.
- Uploads and ingestion are idempotent: SHA-256 of the file, or a natural key such as
  `(user_id, account_login, deal_ticket)` for broker deals.
- Every request carries/echoes `X-Request-ID` for tracing *(middleware planned, spec 001)*.
