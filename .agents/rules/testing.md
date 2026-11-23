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
- Async tests: mark the module with `pytestmark = pytest.mark.asyncio` so they also run from the
  repository root.
- No mocks of what you own when a fake is simple; mock only third-party boundaries.

```python
pytestmark = pytest.mark.asyncio

async def test_list_items_isolated_by_user():
    repository = InMemoryItemRepository()
    await CreateItem(repository).execute("user-a", "EURUSD")
    _, total = await ListItems(repository).execute("user-b", PageParams())
    assert total == 0
```

## Acceptance suite (legacy `app/`)

`tests/acceptance/` exercises the real legacy API end to end against a throwaway MongoDB database
and a temporary `data/raw/` with only `sample_trades.csv` (real data is never touched).

- Passing tests = behavior that works today.
- `@known_bug("...")` tests (`xfail(strict=True)`) describe the **correct** behavior the legacy app
  lacks. When you fix one, it XPASSes and fails the run: remove its `@known_bug` in the same commit.
- Found a new bug? Add a `@known_bug` test first, then fix it (or leave it documented).

```bash
pytest tests/acceptance -rxX     # -rxX prints the list of known bugs
```

## Commands

```bash
pytest services/<name>/tests           # one service
pytest libs/shared/tests services      # all new code
pytest tests                           # legacy app (frozen; keep it passing)
```

A task is done only when its tests ran green in your session and you read the output.
