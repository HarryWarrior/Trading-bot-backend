# Service template (`_template`)

The canonical hexagonal service. **Every new backend service starts as a copy of this folder.**
Full procedure: [`.agents/rules/new-service.md`](../../.agents/rules/new-service.md).

## Layers

```
src/template_service/
  domain/                  # entities, value objects, domain errors. Pure Python only.
  application/
    ports/                 # Protocols the application needs (repositories, gateways)
    use_cases/             # one class per use case, depends only on ports + domain
  adapters/
    inbound/http/          # FastAPI router, request/response schemas, dependencies
    outbound/              # implementations of ports (memory, Mongo, broker, AI…)
  settings.py              # env-driven settings (extends trading_shared BaseServiceSettings)
  bootstrap.py             # composition root: wires adapters into use cases
  main.py                  # create_app() factory + module-level app
```

**Dependency rule:** `adapters → application → domain`. `tests/unit/test_architecture.py`
fails if `domain/` or `application/` import FastAPI, Starlette, Motor, PyMongo or pydantic-settings.

## Run & test (from the repository root)

```bash
pip install -e "libs/shared[dev]" -e "services/_template[dev]"
pytest services/_template/tests
uvicorn template_service.main:app --reload --port 8010
docker build -f services/_template/Dockerfile -t template-service .
```

## Sample API

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/template/items` | body `{"name": "EURUSD"}` → 201 envelope |
| `GET` | `/api/v1/template/items` | `page`, `page_size` (≤100), `sort_by`, `sort_dir`, `q` |
| `GET` | `/health` | liveness |

Identity comes from the temporary `X-User-Id` header until spec 001 adds JWT verification.
