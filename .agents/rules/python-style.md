# Python style

## Language

**English only**: identifiers, file names, docstrings, comments, log messages, error messages and
API response strings. Legacy `app/` still contains Spanish; do not add more, translate when touched.

## Formatting and linting

Ruff is the only linter/formatter (config in root `pyproject.toml`: line length 100, rules E, F, W, I, UP).

```bash
ruff check . --fix
ruff format .
```

The pre-push hook (`.githooks/pre-push`) refuses pushes that fail these checks.

## Typing and models

- Python 3.11+ syntax: `list[str]`, `str | None`, `datetime.UTC`.
- Type every public function signature. Use `Protocol` for ports, frozen `@dataclass` for domain
  entities and value objects, Pydantic v2 `BaseModel` only at the edges (HTTP schemas, settings).
- Money: `Decimal` in domain calculations when precision matters; serialize PnL rounded to 2 decimals.
- Datetimes are timezone-aware UTC (`datetime.now(UTC)`), never naive.

## Docstrings and comments

- Google-style docstrings (`Args:`, `Returns:`, `Raises:`) on public modules, classes and functions
  whose behavior is not obvious from the signature.
- **No trivial comments.** Comment only non-obvious algorithms, formulas, edge-case workarounds or
  performance tricks.

```python
# Bad
# return the response
return response

# Good
# MT5 reports duplicate headers (Time, Time.1); the second one is the close time.
df = df.rename(columns={"Time": "open_time", "Time.1": "close_time"})
```

## Structure

- One use case per file, one class per use case, public method `execute`.
- Functions small and single-purpose; early returns over nested `if`s.
- Raise domain errors (subclasses of the service's `DomainError` with a stable `code`) inside the
  domain; translate them to `AppError` in inbound adapters only.
- No global mutable state; configuration comes from the service's `Settings` class.
- Async all the way for I/O (`async def` use cases and adapters).
