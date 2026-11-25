# trading-shared

Cross-cutting building blocks used by every backend service. **Only** code that every service needs
belongs here: settings base class, logging setup, the response/error envelope and pagination.
Domain logic never lives here.

| Module | Purpose |
|---|---|
| `envelope.py` | `SuccessResponse`, `Page`, `Pagination`, `PageParams`, `build_pagination`, `ok` — framework-free, safe for application layers |
| `http.py` | `page_params` FastAPI dependency — inbound adapters only |
| `errors.py` | `AppError`, `ErrorResponse`, `register_error_handlers` (AppError, validation, HTTP and unhandled errors) |
| `settings.py` | `BaseServiceSettings` (env-driven) |
| `logging.py` | `configure_logging` |
| `auth.py` | `CurrentUser`, `decode_access_token`, `current_user_dependency`, `require_role`: local HS256 JWT verification (401 `UNAUTHENTICATED`, 403 `FORBIDDEN`) |
| `mongo.py` | `create_mongo_client`, `ensure_indexes`: Motor client factory and idempotent index creation |
| `request_id.py` | `RequestIdMiddleware`: reuses or generates `X-Request-ID` and echoes it in the response |

```bash
pip install -e "libs/shared[dev]"
pytest libs/shared/tests
```
