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

Planned (spec 001): JWT verification dependency, Mongo client factory.

```bash
pip install -e "libs/shared[dev]"
pytest libs/shared/tests
```
