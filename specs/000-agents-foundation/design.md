# 000 — Agents Foundation (design)

- **Status:** in-progress (approved 2026-11-23)
- **Date:** 2026-11-23
- **Repos:** `Trading-bot-backend` (this doc, source of truth) · `trading-bot-frontend` (companion doc `specs/000-agents-foundation/design.md`)
- **Branch:** `feat/agents-foundation`, created from `origin/dev`

## 1. Intent

The project is evolving from a single manual trading journal into a **multi-user SaaS of trading tools**
that can be used privately by the owner or sold as a service. The goal is to help traders operate
markets — not only through algorithmic/automated trading connected to MetaTrader 5 or Interactive
Brokers, but with any tool that removes manual work (e.g. a journal filled automatically from
executions or by an AI agent).

Development is done largely by AI agents (Claude, Codex, Gemini, …). Today each agent invents its own
structure, and the docs no longer match the code. **This spec creates the foundation that makes
every future agent build new services and features the same way**: one set of agent rules, one
service template, one docs layout and one spec workflow — inside each repo, versioned in git.

## 2. Goals, non-goals, anti-goals

**Goals**
- `AGENTS.md` + `.agents/` in both repos, so any agent learns the project, stack, architecture and
  rules from one place.
- A single **hexagonal microservice template** that every backend tool/service copies.
- A single **feature-module template** for the frontend.
- `docs/` describing the target architecture, the service catalog, ADRs and integration research.
- `specs/` with a lightweight, superpowers-style workflow and the first specs (001–004) written.

**Non-goals (this spec)**
- Moving or refactoring existing code (that is spec 001).
- Implementing MT5 sync, backtesting, live trading or AI journal (specs 002–004).
- Creating new GitHub repos, CI pipelines or cloud deployments.
- Pushing to GitHub (only after explicit owner approval).

**Anti-goals** (failure even if "done")
- Rules so long or abstract that agents ignore them. Rules must be short, concrete, with examples.
- A template so heavy that a small tool needs 30 files. KISS beats purity.
- Two sources of truth (e.g. `.gemini/rules` and `.agents/rules` disagreeing).
- Docs describing things that don't exist without marking them as *planned*.

## 3. Constraints (decided by the owner)

- **Two repos stay**: `Trading-bot-backend` and `trading-bot-frontend`. No monorepo, no docs repo.
- **Docs, specs and agent files live inside each repo** and are committed.
- **Microservices for everything, hexagonal architecture** (ports & adapters), SOLID, KISS, DRY, YAGNI.
- **Multi-user** from the start, **MongoDB** as the database.
- Anything external (brokers, AI, data providers, notification channels) is an **integration/adapter
  or its own service**, pluggable without touching domain code.
- Reuse proven open-source projects when they fit instead of building from zero — research is a
  required step in specs that touch external tools.
- **MT5 connectivity uses an EA bridge**: an Expert Advisor in the user's terminal pushes executions
  to our API with a per-user token; we never store broker passwords.
- Spec workflow inspired by superpowers (design → plan → execute → verify), lighter than spec-kit.
- Starting point is `origin/dev` (newest work, Sep 2026). The `Documents/Harry` copies are the old
  `main` and are not used.

## 4. Approaches considered

| Approach | Verdict |
|---|---|
| Monorepo with backend + frontend | Rejected by owner: keep two repos. |
| Separate docs/specs repo | Rejected by owner: docs live with the code. |
| Modular monolith, only externals as services | Rejected by owner: microservices for everything. |
| **Two repos, backend = collection of hexagonal microservices under `services/`, shared template + rules** | **Chosen.** |

## 5. Design

### 5.1 Agent entry points (both repos)

```
AGENTS.md            # THE entry point. ≤ 200 lines. Project, stack, map, golden rules, links.
CLAUDE.md            # one line: @AGENTS.md  (Claude Code import)
GEMINI.md            # one line pointing to AGENTS.md
.agents/
  rules/             # short, concrete, example-driven rule files (see 5.2)
  templates/         # copy-paste templates: service/, spec/, adr.md
```

`.gemini/rules/*.md` content is merged into `.agents/rules/` and the `.gemini/` folder is removed,
so there is one source of truth.

`AGENTS.md` sections: what the product is (§1 of this doc, short) · current state vs target state ·
tech stack · repository map · how to run/test · **golden rules** (10 max) · how work is done
(spec workflow) · index of `.agents/rules/` · glossary (trading terms: deal, position, PnL,
drawdown, EA, …).

### 5.2 Backend rules (`.agents/rules/`)

| File | Content |
|---|---|
| `architecture.md` | Hexagonal layers, dependency rule, service boundaries, data ownership, how services talk, multi-tenancy rule |
| `new-service.md` | Step-by-step: copy `_template`, rename, register in gateway + compose + catalog, write spec |
| `python-style.md` | Merged from `.gemini/rules` + tech-spec: English only, Google docstrings, no trivial comments, Ruff, typing, Pydantic v2 |
| `api-contracts.md` | URL scheme, response envelope, pagination/search contract, error format, versioning, idempotency (SHA-256 on uploads) |
| `data-and-mongo.md` | One logical DB per service, `user_id` on every document, index rules, money rounding, UTC datetimes |
| `security.md` | JWT verification, secrets only via env, no broker passwords, encryption with a real library (Fernet), per-user API tokens |
| `testing.md` | Domain tests pure (no I/O), use-case tests with fake ports, adapter tests against local Mongo, pytest layout |
| `git-workflow.md` | Branches from `dev`, naming, Conventional Commits, PR to `dev`, `main` = release, pre-push hook, changelog script |
| `docs-and-specs.md` | When to write a spec/ADR, spec lifecycle, keeping docs in sync, marking *planned* vs *implemented* |

### 5.3 Backend target layout

```
Trading-bot-backend/
  AGENTS.md  CLAUDE.md  GEMINI.md  .agents/
  services/
    _template/                    # canonical hexagonal service (copy me)
      src/<service_name>/
        domain/                   # entities, value objects, domain services. No framework imports.
        application/
          ports/                  # inbound (use-case interfaces) + outbound (repo/gateway Protocols)
          use_cases/              # one class/function per use case
        adapters/
          inbound/http/           # FastAPI routers + request/response schemas
          outbound/               # mongo repos, broker clients, AI clients…
        bootstrap.py              # composition root: wires adapters to ports
        main.py                   # FastAPI app factory
      tests/ (unit/ integration/)
      pyproject.toml  Dockerfile  README.md
    auth/  journal/  analytics/  mt5-bridge/  …   # created by spec 001+ (planned)
  libs/shared/                    # cross-cutting ONLY: settings, logging, JWT verification,
                                  # envelope/pagination models, Mongo client factory
  deploy/docker-compose.yml       # Mongo + Traefik gateway + services (planned in 001)
  app/                            # LEGACY until spec 001 migrates it. Do not add features here.
  docs/  specs/  scripts/  .githooks/
```

**Dependency rule:** `adapters → application → domain`. Domain imports nothing from FastAPI,
Motor or Pydantic-settings. Use cases depend on ports (Python `Protocol`s), never on adapters.

**Service rules**
- Each service is independently runnable (own `pyproject.toml`, Dockerfile, tests) and installs
  `libs/shared` as a local path dependency.
- Each service **owns its data**: its own logical Mongo database (`<service>_db`) in the shared
  cluster. No service reads another service's collections; it calls its API.
- Communication: synchronous HTTP via the gateway for now. Async events are introduced only through
  an ADR when a real need appears (YAGNI).
- Gateway: Traefik routes `/api/v1/<service>/…` to each service. The `auth` service issues JWTs;
  other services verify them locally via `libs/shared` (no call to auth per request).
- Multi-tenancy: every user-owned document carries `user_id`; repository adapters always filter by
  it. Cross-user queries only in explicitly admin use cases.

### 5.4 Docs layout (backend)

```
docs/
  README.md               # index
  architecture.md         # system context + container diagram (text/mermaid), current vs target
  services-catalog.md     # table: service, purpose, status (planned/active), owner DB, routes
  adr/0001-hexagonal-microservices.md
  adr/0002-mt5-ea-bridge.md
  adr/0003-two-repos-docs-in-repo.md
  integrations/README.md  # research log: external repos/APIs evaluated, verdict, license
  CHANGELOG.md            # kept (existing script)
```
`docs/project-spec.md` and `docs/tech-spec.md` from `dev` are folded into `architecture.md` and the
rules; their still-true content is kept, the rest is removed or marked legacy.

### 5.5 Spec workflow (`specs/`)

```
specs/
  README.md                       # workflow + index table (id, title, status, repo parts)
  NNN-short-slug/
    design.md                     # what & why, goals/non-goals, approaches, decisions
    plan.md                       # step-by-step tasks with checkboxes, written after design approval
```
Lifecycle in each `design.md` header: `draft → approved → in-progress → done` (or `dropped`).
Steps: (1) design, approved by the owner; (2) plan; (3) execute task by task, TDD where code;
(4) verify (tests + run the app); (5) update docs/catalog/changelog; (6) mark `done`.
Spec numbers are **shared across both repos**: a feature touching both has `specs/NNN-x/` in each,
the frontend one linking to the backend one.

### 5.6 Specs written in this phase (design drafts only, status `draft`)

- **001 — Migrate to service layout.** Create `libs/shared`, `deploy/docker-compose.yml`, the gateway;
  move `auth`, `journal` (trades storage, multi-user, replaces `data/raw` file reading), `analytics`
  into services. Fix known debt from `dev`: XOR "encryption" of MT5 passwords, simulated MT5 data
  fallback, `random`-based fake deals.
- **002 — MT5 auto-sync via EA bridge.** `mt5-bridge` service: per-user ingest tokens; endpoint
  receiving deals/positions from the EA; idempotent upsert into `journal`; MQL5 EA (`OnTradeTransaction`
  + `WebRequest`) with retry/backfill of history; connection status for the UI. Includes research of
  existing open-source MT5 bridge EAs.
- **003 — Strategy → backtest → live bot.** `strategies` + `backtester` + `execution` services; research
  and pick an engine (candidates: backtesting.py, vectorbt, backtrader, NautilusTrader, Lean);
  paper → live promotion with risk limits and kill switch; live execution through the broker adapter
  (MT5 EA bridge commands first, Interactive Brokers later).
- **004 — AI-filled journal.** Expose journal operations through an MCP server and/or public API with
  user tokens, so an AI agent can create/annotate journal entries (notes, emotions, screenshots,
  setup tags) on top of auto-synced executions.

### 5.7 Frontend (companion doc)

Same `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.agents/`, `docs/`, `specs/`. Target structure:
feature modules (`features/<feature>/{components,composables,stores,api,types}`) wired through Nuxt
config; UI talks to the backend **only** through a typed API client per feature (the frontend's
"outbound adapter"), never raw `$fetch` in components; shared UI only from `components/Common/App*`.
Existing `.gemini/rules/frontend_rules.md` merged into `.agents/rules/ui-standards.md`.
Migration of existing pages into feature modules is frontend spec 001.

### 5.8 Clarifications (builder check, decided by the author — owner may override)

1. **Frontend companion doc** is written in this spec (`trading-bot-frontend/specs/000-agents-foundation/design.md`)
   and approved together with this one.
2. **`libs/shared` minimal now:** this spec creates `libs/shared` with only settings, logging and the
   response envelope/pagination/error models, so `_template` can depend on it and run. JWT
   verification and the Mongo client factory are added in spec 001 (the template's outbound Mongo
   adapter uses an in-memory fake until then).
3. **Contracts = the existing ones from `dev` `docs/project-spec.md` §4–§6**, now normative in
   `api-contracts.md`/`security.md`: success envelope `{success, data, message, meta}`, paginated
   `data: {items, pagination{page, page_size, total_items, total_pages, has_next, has_prev}}`, error
   `{success:false, error{code, message, details}}`, status code table, `X-Request-ID`, money rounding.
   Auth target: `auth` signs HS256 JWT access tokens (short-lived) — already what `app/utils/security.py`
   does — and other services verify signature + expiry locally; the `sessions` collection stays in
   `auth` for refresh/revocation. Rules mark which parts legacy `app/` does not yet follow.
4. **Research depth:** drafts 001–004 list candidates and evaluation criteria; the actual research is
   the first task of each spec's plan and is recorded in `docs/integrations/README.md`.
   **All four specs** get a frontend counterpart (001 touches auth/journal API contracts too).
5. **Language:** all repo docs, rules and code in English. Content folded from `project-spec.md`/
   `tech-spec.md` is translated. Legacy `app/` (and current frontend pages) are exempt until their
   migration spec; new code is never exempt.
6. **Frontend template** is a real `features/_template/` that must build, wired by adding
   `features/*/components` to Nuxt `components.dirs` and `features/*/{composables,stores}` to
   `imports.dirs`. Nuxt layers rejected for now (heavier, KISS).

## 6. Left to the builder

- Exact wording of rule files and `AGENTS.md`, within the size limits above.
- Concrete template code for `_template` (must import, start and pass its sample test).
- Mermaid vs ASCII diagrams.
- Whether `TROUBLESHOOTING-DATOS.md` and `inspect_excel.py` are deleted or moved to `docs/legacy/`.

## 7. Done when

- Both repos on `feat/agents-foundation` contain the files in §5, committed (not pushed).
- `services/_template` runs (`uvicorn`) and its sample test passes.
- `.gemini/rules` removed; no rule exists in two places.
- Specs 001–004 exist as `draft` designs in the backend (and frontend counterparts where UI is involved).
- Owner has reviewed and approved pushing.
