# trading-shared

Cross-cutting building blocks used by every backend service. **Only** code that every service needs
belongs here: settings base class, logging setup, the response/error envelope and pagination.
Domain logic never lives here.

| Module | Purpose |
|---|---|
| `envelope.py` | `SuccessResponse`, `Page`, `Pagination`, `PageParams`, `build_pagination`, `ok` |
| `errors.py` | `AppError`, `ErrorResponse`, `register_error_handlers` |
| `settings.py` | `BaseServiceSettings` (env-driven) |
| `logging.py` | `configure_logging` |

Planned (spec 001): JWT verification dependency, Mongo client factory.

```bash
pip install -e "libs/shared[dev]"
pytest libs/shared/tests
```
