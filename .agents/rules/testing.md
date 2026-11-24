# Testing

TDD is the default: write the failing test, watch it fail, write the minimal code, watch it pass.

## Layout per service

```
services/<name>/tests/
  unit/            # domain + use cases (fakes for ports), architecture test. No I/O.
  integration/     # HTTP via TestClient, Mongo/HTTP adapters against real local dependencies
```

| What | How | Speed |
|---|---|---|
| Domain entities/value objects | Plain pytest, no fixtures needed | ms |
| Use cases | In-memory fake adapters implementing the port | ms |
| HTTP adapter | `TestClient(create_app())`, assert status + envelope `code` | ms |
| Mongo adapter | Real local MongoDB, throwaway DB per test session | s |
| External APIs (brokers, AI) | Contract test against recorded fixtures; live tests marked `@pytest.mark.live`, skipped by default | — |

## Rules

- Test behavior, not implementation: assert on returned values, HTTP status and error `code`.
- Every bug fix starts with a test that reproduces it.
- Every service keeps `tests/unit/test_architecture.py`.
- Multi-tenancy is always tested: user A must not see user B's data.
- Async tests: the root `pyproject.toml` sets `asyncio_mode = "auto"` (and `--import-mode=importlib`),
  so `async def` tests run from the repository root without markers. `pytestmark = pytest.mark.asyncio`
  is optional.
- Real broker reports in git-ignored `data/private/` are only read by tests marked `@pytest.mark.private`.
  The default run deselects them (`-m 'not private'`); run them locally with `pytest -m private`.
  Never commit those reports or their contents.
- No mocks of what you own when a fake is simple; mock only third-party boundaries.

```python
async def test_list_items_isolated_by_user():
    repository = InMemoryItemRepository()
    await CreateItem(repository).execute("user-a", "EURUSD")
    _, total = await ListItems(repository).execute("user-b", PageParams())
    assert total == 0
```

## Acceptance suite (cross-service)

`tests/acceptance_services/` starts auth, journal, analytics and mt5 (fake terminal) in process against a
throwaway MongoDB database and exercises the real flows end to end, including regression tests for the bugs
of the retired legacy app. Needs local MongoDB; expect 0 skipped.

```bash
pytest tests/acceptance_services -q
```

## Commands

```bash
pytest services/<name>/tests           # one service
pytest libs/shared/tests services tests   # everything: shared lib, services, cross-service suite
pytest -m private services/journal/tests   # local only: parse real reports from data/private/
pytest tests                           # repo hygiene, no-fake-data guard, cross-service acceptance
```

A task is done only when its tests ran green in your session and you read the output.
