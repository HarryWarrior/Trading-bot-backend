# analytics service

KPIs, equity curve and breakdowns computed from a user's journal data. It has no database: for each
request it fetches the caller's dataset from the `journal` service (`GET /api/v1/journal/dataset`),
forwarding the caller's own `Authorization: Bearer` token, and computes everything in a pure domain.
The token is verified locally first (same `JWT_SECRET_KEY` as `auth`); journal then applies its own
per-user filtering, so a user only ever sees their own numbers.

## Routes (prefix `/api/v1/analytics`, Bearer required, all accept `?account_ref=`)

| Route | `data` |
|---|---|
| `GET /summary` | `{summary: {...}}` |
| `GET /equity` | `{points: [{time, equity}]}` |
| `GET /daily` | `{days: [{day, trades, net}]}` |
| `GET /monthly` | `{months: [{month, trades, net}]}` |
| `GET /by-symbol` | `{symbols: [{symbol, trades, wins, win_rate, net}]}` |
| `GET /hourly` | `{hours: [{hour, trades, net}]}` |
| `GET /health` | no auth |

Everything is wrapped in the standard envelope. Money, ratios and percentages are JSON numbers with
2 decimals; unknown values are `null` (never 0 or invented). Days, months and hours are UTC, taken from
the trade close time. A user with no trades gets zeros/nulls with 200.

Errors: `401 UNAUTHENTICATED` (missing/invalid token, or journal rejects it),
`503 JOURNAL_UNAVAILABLE` (journal unreachable, timing out, answering 5xx or any other non-2xx, or
sending an unusable payload such as a naive datetime).

## KPI definitions

All KPIs use the **net** result of a trade (`profit + commission + swap`).

- `net_profit` = sum of net; `gross_profit` / `gross_loss` = sum of winning / losing nets.
- `win_rate` = wins / total trades x 100 (breakeven trades count in the total).
- `profit_factor` = gross profit / |gross loss| (`null` without losses); `payoff_ratio` = average
  win / average loss (`null` without both); `average_trade` = net / total (`null` without trades).
- `max_drawdown` = largest peak-to-trough fall of the equity curve (<= 0). It includes withdrawals,
  which lower equity like losses.
- `max_drawdown_pct` is only computed when the starting balance is known (balance events up to the
  first trade); otherwise `null`. It stays within [-100, 0].
- `starting_balance` / `ending_balance` are `null` without balance information.
- `/equity`: when the starting balance is known, the first point is the starting balance at the time of
  the first balance event; then one point per trade (at close time) and per later balance event. Without
  balance information the curve starts from 0 and has no synthetic opening point.

## Environment

See `.env.example`: `ENVIRONMENT`, `LOG_LEVEL`, `JWT_SECRET_KEY` (required, >= 32 chars, same as auth),
`JOURNAL_URL` (default `http://localhost:8002`), `CORS_ORIGINS`.

## Run and test

```bash
pip install -e libs/shared -e "services/journal[dev]" -e "services/analytics[dev]"
cp services/analytics/.env.example services/analytics/.env     # then set JWT_SECRET_KEY
cd services/analytics && uvicorn analytics_service.main:app --port 8003
pytest services/analytics/tests services/journal/tests -q -W error
```

`journal-service` is a **test-only** dependency (end-to-end test `test_with_journal.py`, which needs
MongoDB and is skipped when it is unreachable). Production code never imports `journal_service`.
