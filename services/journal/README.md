# Journal service

Stores each user's trades and balance events and serves them back. Trades arrive by uploading a
broker report (MT5 HTML/XLSX or a flat CSV) or, later, pushed by the MT5 EA bridge (`/ingest/mt5`).
The `analytics` service reads the unpaginated `/dataset` endpoint to compute KPIs.
Port `8002` by convention. Data lives in MongoDB (`journal_db`); every document carries `user_id`
and every query filters by it, so one user never sees another's data.

## Layers

```
src/journal_service/
  domain/                  # Trade, BalanceEvent, ReportImport, errors. Pure Python.
  application/             # ports + use cases (import, ingest, list, dataset)
  adapters/
    inbound/http/          # FastAPI router and schemas
    outbound/              # Mongo repositories, report parsers, clock, id generator
  settings.py  bootstrap.py  main.py
```

`tests/unit/test_architecture.py` fails if `domain/` or `application/` import framework code.

## Routes

All routes live under `/api/v1/journal` and require `Authorization: Bearer <access token>`
(issued by the `auth` service). `GET /health` is public.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/imports` | multipart field `file` (`.csv`, `.xlsx`, `.xls`, max 10 MB) -> 201 `{import}` |
| `GET` | `/imports` | paginated import history |
| `GET` | `/trades` | paginated; filters `symbol, outcome, date_from, date_to, profit_min, profit_max, account_ref`; `sort_by` in `close_time, open_time, profit, symbol` (else 422) |
| `GET` | `/trades/{id}` | 404 `NOT_FOUND` when missing or owned by someone else |
| `GET` | `/accounts` | accounts with trade counts and first/last close |
| `GET` | `/dataset?account_ref=` | `{trades, balance_events}`, unpaginated, for analytics |
| `POST` | `/ingest/mt5` | requires header `X-Service-Key` (else 403 `FORBIDDEN`) plus the user token; `{account_ref, trades, balance_events}` -> `{created, updated, balance_events}` (idempotent; `balance_events` counts new events only) |
| `POST` | `/ingest/deals` | requires header `X-Service-Key` only; the body names the owner: `{user_id, account_ref, deals: [...]}` (raw MT5 deals, at most 200) -> `{received, new, trades_upserted, balance_events, skipped}`. Idempotent per deal ticket: `new` counts unseen deals only; positions are paired by `position_id` and upserted as trades. Called by `mt5-bridge`, never by browsers |

Errors: `DUPLICATE_IMPORT` 409 (`details.import_id`), `UNSUPPORTED_FILE` 400, `FILE_TOO_LARGE` 413,
`UNREADABLE_REPORT` 400 (`details.reason`), `NOT_FOUND` 404, `UNAUTHENTICATED` 401, `FORBIDDEN` 403 (ingest without a valid service key).
Money fields are rounded to 2 decimals in responses; prices and volume are not.

## Report formats

- **MT5 report** (HTML or XLSX "Trade History Report"): account `"<login>@<server>"` is read from
  the header; positions are matched by position id, so re-importing a newer report of the same
  account creates only the new positions and updates the existing ones.
- **Flat CSV**: columns `Open Time, Close Time, Symbol, Type, Volume, Open Price, Close Price,
  Profit, Comment` (see `data/samples/sample_trades.csv`); account is the stable per-user
  `"upload"` (also used by MT5 reports without a parseable Account line), so overlapping
  uploads update the rows they share instead of duplicating them.
- Malformed rows are skipped and reported in `skipped_rows` (reason and the absolute 1-based
  row number as Excel or a text editor shows it, header and blank rows included); a file with no
  recognizable table is rejected with `UNREADABLE_REPORT`.
- The same file (SHA-256) uploaded twice by the same user is rejected as a duplicate.
- The 10 MB cap bounds parsing only; deploy behind a proxy or ASGI body-size limit.

- MT5 Deals rows: `balance` -> `deposit`/`withdrawal`, `credit` -> `credit`; correction, charge,
  bonus, commission, fee, interest, dividend and tax rows (and their Spanish names) -> signed
  `adjustment` events whose amount is Profit + Commission + Fee + Swap (blank cells count as 0).
  Zero-amount rows are ignored; buy/sell deals are covered by the Positions section; any other
  deal type is reported in `skipped_rows` as `unsupported balance deal type '<type>'`.
- Balance event kinds: `deposit`, `withdrawal`, `credit`, `adjustment` (signed amounts).

**Times are taken as UTC** until MT5 account linking (plan 3) provides the broker's UTC offset.

## Analytics definitions (computed by the analytics service)

Withdrawals and other balance events never create drawdown; only trade results do. Drawdown %,
starting and ending balance are `null` unless every account in scope that has trades has balance
events at or before its first trade. See `services/analytics/README.md`.

## Security note

fastapi 0.104 / starlette 0.27 have known multipart-upload DoS advisories (e.g. CVE-2024-47874,
which affects `POST /imports`). Run the service on localhost only until plan 4 upgrades them.

## Run & test (from the repository root)

```bash
pip install -e "libs/shared[dev]" -e "services/journal[dev]"
cp services/journal/.env.example services/journal/.env     # set JWT_SECRET_KEY (same as auth) and INGEST_SERVICE_KEY
cd services/journal && uvicorn journal_service.main:app --reload --port 8002   # needs MongoDB
pytest services/journal/tests           # integration tests skip without MongoDB
pytest services/journal/tests -m private  # optional: parses real reports in data/private/
```

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | required | >= 32 characters, same value as `auth` |
| `INGEST_SERVICE_KEY` | required | >= 32 characters; the same value is configured in the mt5 service; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `MONGODB_URL` | `mongodb://localhost:27017` | |
| `DATABASE_NAME` | `journal_db` | |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON list |
| `MAX_UPLOAD_MB` | `10` | upload cap |
| `ENVIRONMENT`, `LOG_LEVEL` | `local`, `INFO` | |
