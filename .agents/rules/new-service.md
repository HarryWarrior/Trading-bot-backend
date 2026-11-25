# Creating a new service

Every tool or capability is a service under `services/`. Never start from scratch: copy the template.

## Before

1. A spec exists in `specs/NNN-slug/` with an **approved** `design.md` naming the service.
2. Check `docs/services-catalog.md`: the capability does not already belong to another service.
3. If the service wraps an external tool, the spec's research task is done and recorded in
   `docs/integrations/README.md`.

## Steps

```bash
# 1. Copy and rename (example: mt5-bridge → package mt5_bridge_service)
cp -r services/_template services/mt5-bridge
mv services/mt5-bridge/src/template_service services/mt5-bridge/src/mt5_bridge_service
```

2. Replace every `template_service` / `template-service` / `template` occurrence:
   - `pyproject.toml` (`name`, `packages`), imports, `settings.py` (`service_name`),
     router prefix `/api/v1/<service>`, Dockerfile paths, README.
3. Add the package to `known-first-party` in the root `pyproject.toml` (`[tool.ruff.lint.isort]`).
4. Delete the sample `Item` domain, use cases, schemas and their tests; write your domain **test first**.
   Keep `tests/unit/test_architecture.py` (update `PACKAGE_ROOT`).
5. Add the service to `docs/services-catalog.md` (status `in-progress`) and to
   `deploy/docker-compose.yml` + gateway routing *(once spec 001 creates them)*.
6. Install and verify:

```bash
pip install -e "libs/shared[dev]" -e "services/mt5-bridge[dev]"   # trading-shared is not on PyPI
pytest services/mt5-bridge/tests
ruff check services/mt5-bridge && ruff format --check services/mt5-bridge
uvicorn mt5_bridge_service.main:app --port 8011
```

## Naming

| Thing | Convention | Example |
|---|---|---|
| Folder | kebab-case | `services/mt5-bridge` |
| Python package | snake_case + `_service` | `mt5_bridge_service` |
| Route prefix | `/api/v1/<folder-name>` | `/api/v1/mt5-bridge` |
| Database | `<package without _service>_db` | `bridge_db` (short name is allowed; keep it equal to `MONGO_DB` in `.env.example`) |
| Use case | Verb + noun class | `IngestDeals`, `RevokeIngestToken` |
| Port | Noun + role | `DealRepository`, `BrokerGateway` |
| Adapter | Technology + port | `MongoDealRepository`, `MetaApiBrokerGateway` |

## Done when

Tests green, Ruff clean, `/health` responds, catalog updated, spec plan tasks checked.
