# Spec 001 — Completion report

**Status:** done on code (2026-11-24). Pending: owner's manual smoke test and the real-MT5 link/sync.
**Branches / PRs:** backend `feat/001-real-data` (PR #4), frontend `feat/001-real-data` (PR #3), both into `dev`.

## Goals vs result

| Goal | Result |
|---|---|
| No demo mode / hardcoded data | Done. Guard tests (`tests/test_no_fake_data_guard.py`, frontend `no-random-data`); only example data is `data/samples/sample_trades.csv` |
| Working login | Done. auth service (8001): register, email code, login, rotating refresh, reset password, admin role |
| Real MT5 connection, rejects fake data | Done in code. mt5 service (8004) attaches to the open terminal, no credentials stored, 409 when terminal is closed, account re-verified before ingest. **Real-terminal link/sync NOT executed by the agent: owner to test** |
| Trades saved in MongoDB | Done. journal service (8002), idempotent imports (file hash + natural keys) |
| Analytics | Done. analytics service (8003): KPIs, equity, daily, symbol, hourly |
| Legacy `app/` retired | Done |
| Frontend on real services | Done. Feature modules + dev proxy |

## Verification
- Backend: 485 passed, 9 deselected (private/live), ruff clean.
- Frontend: 146 passed, `npm run build` and `nuxi typecheck` clean.
- Real browser run found 3 bugs invisible to unit tests, all fixed with tests: unresolved shared components, accounts `{items}` shape, outcome filter casing; plus cross-user stale state.

## Deferred (not blocking)
Local-vs-UTC time display; mount tests per page and backend-contract fixtures; email in URL query on register/verify; `text-white` in light-mode pagination; R:R sign on losing trades; messages for INVALID_TIMEFRAME / COUNT_OUT_OF_RANGE; devProxy hardcodes `v1`; plan-1..3 minors listed in each plan's "Execution notes".

## Decision kept by owner
Real reports remain in old git history (not purged); they live only in git-ignored `data/private/`.

## Next specs
See `specs/README.md`: 002 MT5 EA bridge sync, 003 strategy→backtest→paper→live, 004 AI journal (all draft). Proposed 005+: gateway/Traefik deploy, billing/multi-tenant plans.
