# AGENTS.md — Trading Platform Backend

Entry point for every AI agent (Claude, Codex, Gemini, …) and human contributor.
Read this file first, then the rule files linked below that apply to your task.

## 1. Product

A **multi-user SaaS of trading tools**, usable privately or offered as a service. Goal: help traders
operate the markets — algorithmic/automated trading connected to MetaTrader 5 or Interactive
Brokers, and any tool that removes manual work (e.g. a journal filled automatically from executions
or by an AI agent).

- Companion repo: `trading-bot-frontend` (Nuxt 3 web app). Same rules layout, shared spec numbers.
- Every tool is a **microservice with hexagonal architecture**. External systems (brokers, AI, data
  providers, notifications) are adapters or their own services, pluggable without touching domains.
- Prefer reusing proven open-source projects; research is a required step of specs that need one.

## 2. Current vs target state

| Area | Today | Target |
|---|---|---|
| Code layout | One service per tool in `services/<name>/` (auth, journal, analytics, mt5); the legacy `app/` monolith is retired | Same, plus gateway/compose and new tools |
| Trades storage | `journal` service: MongoDB, per `user_id`; the only store | Same |
| MT5 | `mt5` service (port 8004, Windows host) attaches to the open terminal; manual CSV/XLSX upload also works | EA bridge pushes executions (spec 002) |
| Auth | `auth` service (port 8001) issues JWT; services verify locally | Same (spec 001, done) |

Migration to services was spec 001 (done). New features go into services.

## 3. Tech stack

Python 3.11+ · FastAPI 0.104 · Pydantic v2 · pydantic-settings · Motor/PyMongo (MongoDB) · pandas/NumPy
(analytics) · pytest + pytest-asyncio · Ruff · Docker · Traefik gateway (planned) · MQL5 for the MT5 EA (planned).

## 4. Repository map

```
AGENTS.md  CLAUDE.md  GEMINI.md     # agent entry points (the last two point here)
.agents/rules/                      # how we build — read before coding
.agents/templates/                  # spec, plan and ADR templates
services/_template/                 # canonical hexagonal service: COPY THIS for new services
services/<name>/                    # one folder per service (auth, journal, analytics, mt5; planned: mt5-bridge…)
libs/shared/                        # trading_shared: envelope, errors, settings, logging, auth, mongo, request_id (cross-cutting only)
tests/                              # repo hygiene, no-fake-data guard, cross-service acceptance suite
docs/                               # architecture, services catalog, ADRs, integrations research
specs/NNN-slug/                     # design.md + plan.md per piece of work
scripts/  .githooks/                # changelog script, pre-push hook
```

## 5. Run & test

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows (source .venv/bin/activate elsewhere)
pip install -e libs/shared -e "services/_template[dev]" -e "services/auth[dev]" -e "services/journal[dev]" -e "services/analytics[dev]" -e "services/mt5[dev]" ruff   # no root requirements.txt
cp services/auth/.env.example services/auth/.env         # then set JWT_SECRET_KEY (git-ignored)
cp services/journal/.env.example services/journal/.env   # and services/analytics/.env.example; all .env files (auth, journal, analytics, mt5) MUST share the same JWT_SECRET_KEY
cp services/mt5/.env.example services/mt5/.env           # INGEST_SERVICE_KEY MUST equal the one in services/journal/.env (>= 32 chars)
powershell -File scripts/dev.ps1 [-Only auth]             # dev runner: auth 8001, journal 8002, analytics 8003, mt5 8004 (checks the shared JWT secret and INGEST_SERVICE_KEY)
cd services/auth && uvicorn auth_service.main:app --reload --port 8001   # one service by hand (needs MongoDB); same pattern for journal 8002, analytics 8003 (JOURNAL_URL), mt5 8004
uvicorn template_service.main:app --reload --port 8010    # template service
cd services/auth && python scripts/migrate_legacy_users.py --help   # copy users of the retired legacy DB into auth_db (needs the venv active)
cd services/auth && python scripts/promote_admin.py <email>     # grant admin role (needs the venv active)
pytest libs/shared/tests services tests -q -rs            # everything: shared lib, services, cross-service acceptance (needs local MongoDB; expect 0 skipped)
pytest -m live services/mt5/tests                         # local only: needs an open, logged-in MT5 terminal (default runs deselect them)
pytest -m private services/journal/tests                  # local only: parse real reports in data/private/ (default runs deselect them)
ruff check . && ruff format --check .
git config core.hooksPath .githooks                       # enable pre-push checks
```

## 6. Golden rules

1. **Hexagonal dependency rule:** `adapters → application → domain`. Domain and application never
   import FastAPI, Motor, PyMongo or pydantic-settings.
2. **New service = copy `services/_template`** and follow `.agents/rules/new-service.md`. Never invent
   a new layout.
3. **Multi-tenant always:** every user-owned document has `user_id`; every repository query filters by it.
4. **One contract:** all endpoints use the envelope, pagination and errors from `trading_shared`.
5. **Secrets only from environment.** Never store broker passwords; never log tokens or passwords.
6. **English only** in code, identifiers, docs, logs and API messages.
7. **Tests first** for domain and use cases; every service keeps its architecture test.
8. **Spec before non-trivial work:** design → approval → plan → execute → verify (`specs/`).
9. **Docs tell the truth:** mark anything not built yet as *(planned)*; update the catalog and
   changelog with the change.
10. **Never push to `main` or `dev` directly**, never force-push shared branches; work on a feature branch.

## 7. How work is done

1. Find or create the spec in `specs/` (see `specs/README.md`). No spec → ask before large work.
2. `design.md` must be **approved** by the owner before code.
3. Write `plan.md` (bite-sized tasks, exact files, tests), then execute task by task with TDD.
4. Verify: tests, Ruff, run the service. Update `docs/` and `docs/CHANGELOG.md`. Mark spec `done`.

## 8. Rules index

| File | Read when |
|---|---|
| [architecture.md](.agents/rules/architecture.md) | Any backend change |
| [new-service.md](.agents/rules/new-service.md) | Creating a service or tool |
| [python-style.md](.agents/rules/python-style.md) | Writing Python |
| [api-contracts.md](.agents/rules/api-contracts.md) | Adding or changing endpoints |
| [data-and-mongo.md](.agents/rules/data-and-mongo.md) | Persisting data |
| [security.md](.agents/rules/security.md) | Auth, tokens, secrets, broker/external access |
| [testing.md](.agents/rules/testing.md) | Writing tests |
| [git-workflow.md](.agents/rules/git-workflow.md) | Branching, commits, PRs, changelog |
| [docs-and-specs.md](.agents/rules/docs-and-specs.md) | Writing specs, ADRs, docs |

## 9. Glossary

| Term | Meaning |
|---|---|
| Order | Instruction sent to a broker to buy/sell. |
| Deal | A single execution reported by MT5 (entry or exit). |
| Position | Open exposure resulting from one or more deals. |
| Trade | Our normalized round trip (open → close) built from deals. |
| PnL | Profit and loss, in account currency (USD, 2 decimals). |
| Drawdown | Peak-to-trough decline of the equity curve. |
| Profit factor | Gross profit / gross loss. |
| Payoff ratio | Average win / average loss. |
| EA | Expert Advisor: a program running inside the MT5 terminal (MQL5). |
| EA bridge | Our EA that pushes the user's executions to our API (spec 002). |
| Ingest token | Per-user, revocable token the EA uses to authenticate. |
| Tenant | A user (or later an organization) whose data is isolated from others. |
| Backtest / paper / live | Simulated on history / simulated in real time / real money. |
