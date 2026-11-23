# 000 — Agents Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give both repos one agent entry point, one rule set, a runnable hexagonal service template (backend), a buildable feature template (frontend), a docs layout and the spec workflow with drafts 001–004.

**Architecture:** Backend gains `libs/shared` (envelope/settings/logging) and `services/_template` (domain → application(ports, use_cases) → adapters(inbound http, outbound memory)) next to the untouched legacy `app/`. Frontend gains `features/_template` (api → store → composable → component) wired through Nuxt `components`/`imports` dirs plus a shared `useApiClient`. Everything else is Markdown.

**Tech Stack:** Python 3.11+ (local 3.12), FastAPI 0.104.1, Pydantic 2.5.0, pydantic-settings 2.1.0, pytest 7.4.3, pytest-asyncio 0.21.1, httpx 0.25.2, hatchling · Nuxt 3, Vue 3, TypeScript, Pinia.

**Spec:** `specs/000-agents-foundation/design.md` (backend) and `trading-bot-frontend/specs/000-agents-foundation/design.md`.

## Global Constraints

- Work only on branch `feat/agents-foundation` in each repo (already created from `origin/dev`). Commit per task. **Never push.**
- All code, identifiers, docs, rules, logs and messages in **English**.
- Do not modify legacy `app/`, `tests/`, existing `pages/`, `components/`, `stores/`, `composables/` (except adding `composables/useApiClient.ts`).
- `AGENTS.md` ≤ 200 lines; max 10 golden rules; each rule file ≤ 150 lines with at least one concrete example.
- Response envelope, pagination and error shapes exactly as design §5.8 item 3.
- `page_size` default 20, max 100; `page` ≥ 1; `sort_dir` ∈ {`asc`,`desc`}, default `desc`.
- Docs mark every not-yet-built thing as **(planned)**.
- Spec numbers shared across repos; each spec header has `Status: draft|approved|in-progress|done|dropped`.

## Review Focus

1. `page_size=101` or `page=0` → 422 with error envelope `code="VALIDATION_ERROR"`, not FastAPI's default body. (Task 2)
2. Name empty or whitespace-only → 400 `code="INVALID_ITEM_NAME"`. (Task 2)
3. User A must never see user B's items (multi-tenancy). (Task 2)
4. Request without `X-User-Id` → 401 `code="UNAUTHENTICATED"`. (Task 2)
5. Zero items → `total_pages=0`, `has_next=false`, `has_prev=false`; page beyond the last → empty `items`, `has_prev=true`. (Task 1)

---

## Backend (`Trading-bot-backend`)

Run all backend commands from the repo root with `.venv` active (`.venv\Scripts\Activate.ps1`).

### Task 1: `libs/shared` — envelope, pagination, errors, settings, logging

**Files:**
- Create: `libs/shared/pyproject.toml` (hatchling, name `trading-shared`, package `trading_shared`, deps `fastapi==0.104.1`, `pydantic==2.5.0`, `pydantic-settings==2.1.0`; optional `dev`: `pytest==7.4.3`, `httpx==0.25.2`; `[tool.pytest.ini_options] addopts="--import-mode=importlib"`)
- Create: `libs/shared/src/trading_shared/__init__.py`, `envelope.py`, `errors.py`, `settings.py`, `logging.py`
- Create: `libs/shared/README.md` (what belongs here: cross-cutting only; JWT + Mongo factory arrive in spec 001)
- Test: `libs/shared/tests/test_envelope.py`, `libs/shared/tests/test_errors.py`

**Interfaces — Produces:**
- `envelope.py`: `Pagination(page, page_size, total_items, total_pages, has_next, has_prev)`; `Page[T](items: list[T], pagination: Pagination)`; `Meta(timestamp: datetime, version: str)`; `SuccessResponse[T](success: Literal[True]=True, data: T, message: str="Operation completed successfully", meta: Meta)`; `PageParams(page: int=1 ge=1, page_size: int=20 ge=1 le=100, sort_by: str|None=None, sort_dir: Literal["asc","desc"]="desc", q: str|None=None)`; `build_pagination(page: int, page_size: int, total_items: int) -> Pagination`; `ok(data: T, version: str, message: str = ...) -> SuccessResponse[T]` (timestamp = UTC now).
- `errors.py`: `ErrorBody(code: str, message: str, details: Any=None)`; `ErrorResponse(success: Literal[False]=False, error: ErrorBody)`; `AppError(Exception)(code: str, message: str, status_code: int=400, details: Any=None)`; `register_error_handlers(app: FastAPI) -> None` mapping `AppError` → its status + envelope and `RequestValidationError` → 422 `VALIDATION_ERROR` with `details=exc.errors()`.
- `settings.py`: `BaseServiceSettings(BaseSettings)` with `service_name: str`, `version: str="0.1.0"`, `environment: Literal["local","test","prod"]="local"`, `log_level: str="INFO"`, `env_file=".env"`.
- `logging.py`: `configure_logging(level: str) -> None` (stdlib, format `%(asctime)s %(levelname)s %(name)s %(message)s`).

- [ ] **Step 1: Write failing tests** in `test_envelope.py`:
  - `test_build_pagination_middle_page`: `build_pagination(2, 20, 45)` → `total_pages=3, has_next=True, has_prev=True`.
  - `test_build_pagination_zero_items`: `build_pagination(1, 20, 0)` → `total_pages=0, has_next=False, has_prev=False`.
  - `test_build_pagination_beyond_last`: `build_pagination(5, 20, 45)` → `has_next=False, has_prev=True`.
  - `test_page_params_rejects_page_size_over_100`: `PageParams(page_size=101)` raises `ValidationError`.
  - `test_ok_wraps_data`: `ok({"a": 1}, "1.0.0").model_dump()` has `success is True`, `data == {"a": 1}`, `meta["version"] == "1.0.0"`.
  And in `test_errors.py` (FastAPI app + `TestClient`):
  - `test_app_error_rendered_as_envelope`: route raising `AppError("X_CODE","boom",409)` → status 409, body `{"success": False, "error": {"code": "X_CODE", "message": "boom", "details": None}}`.
  - `test_validation_error_rendered_as_envelope`: route with `q: int` called with `?q=abc` → 422, `body["error"]["code"] == "VALIDATION_ERROR"`.
- [ ] **Step 2:** `pip install -e "libs/shared[dev]"` then `pytest libs/shared/tests -v` → FAIL (import errors).
- [ ] **Step 3:** Implement the modules per Interfaces. `total_pages = ceil(total_items / page_size)`; `has_next = page < total_pages`; `has_prev = page > 1`.
- [ ] **Step 4:** `pytest libs/shared/tests -v` → 7 passed. `ruff check libs && ruff format --check libs` → clean.
- [ ] **Step 5: Commit** `feat(shared): add envelope, errors, settings and logging library`

### Task 2: `services/_template` — canonical hexagonal service

**Files:**
- Create: `services/_template/pyproject.toml` (hatchling, name `template-service`, package `template_service`, deps: `trading-shared` (installed editable from `libs/shared`), `fastapi==0.104.1`, `uvicorn==0.24.0`; optional `dev`: `pytest==7.4.3`, `pytest-asyncio==0.21.1`, `httpx==0.25.2`; pytest `asyncio_mode="auto"`, `addopts="--import-mode=importlib"`)
- Create under `services/_template/src/template_service/`:
  - `domain/item.py`, `domain/errors.py`
  - `application/ports/item_repository.py`, `application/use_cases/create_item.py`, `application/use_cases/list_items.py`
  - `adapters/outbound/memory_item_repository.py`
  - `adapters/inbound/http/router.py`, `adapters/inbound/http/schemas.py`, `adapters/inbound/http/dependencies.py`
  - `settings.py`, `bootstrap.py`, `main.py` (+ `__init__.py` in every package)
- Create: `services/_template/Dockerfile` (python:3.12-slim, copies `libs/shared` + service, `uvicorn template_service.main:app --host 0.0.0.0 --port 8000`; build context = repo root, documented in README)
- Create: `services/_template/README.md` (layer map, dependency rule, how to copy/rename, run & test commands)
- Test: `services/_template/tests/unit/test_item.py`, `tests/unit/test_use_cases.py`, `tests/integration/test_http.py`

**Interfaces — Consumes:** Task 1 (`ok`, `Page`, `PageParams`, `build_pagination`, `AppError`, `register_error_handlers`, `BaseServiceSettings`, `configure_logging`).
**Produces:**
- `domain/item.py`: frozen dataclass `Item(id: str, user_id: str, name: str, created_at: datetime)`; classmethod `Item.create(user_id: str, name: str) -> Item` (uuid4 hex id, UTC now, name stripped, 1–100 chars else raises `InvalidItemName`).
- `domain/errors.py`: `DomainError(Exception)` with `code: str`; `InvalidItemName(DomainError)` code `"INVALID_ITEM_NAME"`.
- `application/ports/item_repository.py`: `class ItemRepository(Protocol)`: `async def add(self, item: Item) -> None`; `async def list_by_user(self, user_id: str, page: int, page_size: int) -> tuple[list[Item], int]` (newest first).
- `CreateItem(repository: ItemRepository).execute(user_id: str, name: str) -> Item`; `ListItems(repository).execute(user_id: str, params: PageParams) -> tuple[list[Item], int]`.
- `InMemoryItemRepository` implements `ItemRepository`.
- `dependencies.py`: `get_current_user_id(x_user_id: str | None = Header(None)) -> str` raising `AppError("UNAUTHENTICATED", ..., 401)` when missing. **Temporary**: replaced by JWT verification in spec 001 (docstring says so).
- Routes (prefix `/api/v1/template`): `POST /items` body `{"name": str}` → 201 `SuccessResponse[ItemOut]`; `GET /items` with `PageParams` query → 200 `SuccessResponse[Page[ItemOut]]`. `ItemOut(id, name, created_at)`. `GET /health` → `{"status": "healthy", "service": settings.service_name}`.
- `bootstrap.py`: `build_container(settings: TemplateSettings) -> Container` (dataclass holding `create_item`, `list_items`); `main.py`: `create_app(settings: TemplateSettings | None = None) -> FastAPI` and module-level `app = create_app()`. `DomainError` is mapped to `AppError(code, str(exc), 400)` in the router.

- [ ] **Step 1: Write failing tests**
  - `test_item.py`: `test_create_strips_name` (`"  EURUSD  "` → `"EURUSD"`); `test_create_rejects_blank_name` (`"   "` raises `InvalidItemName`); `test_create_rejects_name_over_100_chars`.
  - `test_use_cases.py`: `test_list_items_isolated_by_user` (A creates 2, B creates 1 → A lists total 2, B total 1); `test_list_items_newest_first`.
  - `test_http.py` (`TestClient(create_app())`): `test_create_item_returns_201_envelope` (`data.name == "EURUSD"`, `success is True`); `test_missing_user_header_returns_401` (`error.code == "UNAUTHENTICATED"`); `test_blank_name_returns_400` (`error.code == "INVALID_ITEM_NAME"`); `test_page_size_over_100_returns_422` (`error.code == "VALIDATION_ERROR"`); `test_list_paginates` (create 3, `?page=2&page_size=2` → 1 item, `pagination.has_prev is True`, `has_next is False`); `test_users_do_not_see_each_other` (via headers `X-User-Id: a` / `b`); `test_health`.
- [ ] **Step 2:** `pip install -e "services/_template[dev]"`; `pytest services/_template/tests -v` → FAIL.
- [ ] **Step 3:** Implement per Interfaces. Domain and application modules must not import `fastapi`, `pydantic_settings` or `motor`.
- [ ] **Step 4:** `pytest services/_template/tests -v` → 12 passed. Add `tests/unit/test_architecture.py::test_domain_and_application_have_no_framework_imports` that scans `domain/` and `application/` source for `fastapi`, `motor`, `pymongo`, `pydantic_settings` → passes. Run again → 13 passed.
- [ ] **Step 5:** Smoke: `uvicorn template_service.main:app --port 8010`, then `GET http://localhost:8010/health` → 200. Stop server.
- [ ] **Step 6:** `ruff check services libs && ruff format --check services libs` → clean.
- [ ] **Step 7: Commit** `feat(template): add canonical hexagonal service template`

### Task 3: Backend agent files and rules

**Files:**
- Create: `AGENTS.md`, `CLAUDE.md` (single line `@AGENTS.md`), `GEMINI.md` (one line: read `AGENTS.md`)
- Create: `.agents/rules/architecture.md`, `new-service.md`, `python-style.md`, `api-contracts.md`, `data-and-mongo.md`, `security.md`, `testing.md`, `git-workflow.md`, `docs-and-specs.md`
- Create: `.agents/templates/spec-design.md`, `.agents/templates/spec-plan.md`, `.agents/templates/adr.md`, `.agents/templates/README.md` (points to `services/_template` as the service template)
- Delete: `.gemini/` (after merging its 7 bullets into `python-style.md`, `api-contracts.md`, `git-workflow.md`)

Content requirements (wording is the builder's):
- `AGENTS.md` sections in order: Product (design §1 condensed) · Current vs target state (legacy `app/` frozen; new work in `services/`) · Tech stack · Repository map · Run & test commands (legacy app, template, shared) · Golden rules (≤10: hexagonal dependency rule; new service = copy `_template`; every user document has `user_id`; envelope/pagination contract; secrets only from env, never broker passwords; English only; tests first for domain/use cases; spec before non-trivial work; mark planned vs implemented; never push to `main`/`dev` directly) · Workflow (spec lifecycle) · Rules index · Glossary (deal, position, order, PnL, drawdown, profit factor, payoff, EA, MT5, ingest token, tenant).
- `api-contracts.md` and `security.md` carry design §5.8 item 3 verbatim shapes, the status code table, `X-Request-ID`, money rounding (2 dp USD; FX 4–5 dp; crypto 8 dp), SHA-256 upload idempotency, and a "legacy gaps" list (legacy `app/` does not use the envelope everywhere; MT5 password XOR → Fernet in 001).
- `architecture.md`: layer diagram, dependency rule, one-DB-per-service (`<service>_db`), HTTP via Traefik `/api/v1/<service>/…`, JWT verified locally (planned), events only via ADR.
- `git-workflow.md`: branches `feat|fix|docs|chore|refactor/<slug>` from `dev`; Conventional Commits; PR → `dev`; `main` = releases; `.githooks/pre-push` (`git config core.hooksPath .githooks`); `python scripts/update_changelog.py`.

- [ ] **Step 1:** Write the files.
- [ ] **Step 2:** Verify: `wc -l AGENTS.md` ≤ 200; `wc -l .agents/rules/*.md` each ≤ 150; `grep -c "^[0-9]\+\." ` on golden rules section ≤ 10; `test ! -d .gemini`; every rule file contains a fenced code block (`grep -L '```' .agents/rules/*.md` prints nothing).
- [ ] **Step 3: Commit** `docs(agents): add AGENTS.md, agent rules and templates; retire .gemini rules`

### Task 4: Backend docs

**Files:**
- Create: `docs/README.md` (index), `docs/architecture.md` (context + container diagram in Mermaid; current vs target; services table), `docs/services-catalog.md` (columns: service, purpose, status, database, routes, spec; rows: template=active, auth/journal/analytics=planned(001), mt5-bridge=planned(002), strategies/backtester/execution=planned(003), journal-ai/mcp=planned(004))
- Create: `docs/adr/0001-hexagonal-microservices.md`, `0002-mt5-ea-bridge.md`, `0003-two-repos-docs-in-repo.md` (template from `.agents/templates/adr.md`; context/decision/consequences from design §3–§4)
- Create: `docs/integrations/README.md` (research log table: name, url, license, purpose, verdict, spec; empty rows + candidate list from design §5.6)
- Modify: `docs/README.md` from `dev` replaced by the new index (its still-true setup content moves into `AGENTS.md` run section or `docs/architecture.md`)
- Delete: `docs/project-spec.md`, `docs/tech-spec.md` after their still-true content is in `architecture.md`/rules (translate any Spanish)
- Move: `inspect_excel.py` → `scripts/inspect_excel.py`

- [ ] **Step 1:** Write/move/delete files.
- [ ] **Step 2:** Verify no broken relative links: `grep -rhoE '\]\(([^)#]+\.md)' AGENTS.md docs .agents specs` and check each target exists (small script or manual list). `grep -rn "file:///" docs AGENTS.md .agents` → nothing (dev docs had absolute local links).
- [ ] **Step 3: Commit** `docs: restructure docs into architecture, catalog, ADRs and integrations log`

### Task 5: Backend specs workflow and drafts 001–004

**Files:**
- Create: `specs/README.md` (workflow from design §5.5 + index table with 000–004)
- Modify: `specs/000-agents-foundation/design.md` header → `Status: approved`
- Create: `specs/001-service-migration/design.md`, `specs/002-mt5-ea-bridge-sync/design.md`, `specs/003-strategy-backtest-live/design.md`, `specs/004-ai-journal/design.md` from `.agents/templates/spec-design.md`, `Status: draft`, each with: intent, goals/non-goals, constraints, open questions, candidate approaches, research task (002/003/004 list candidates from design §5.6 plus criteria: license, maintenance, Python fit, multi-user fit), frontend counterpart link.
  - 001 must list the debt items: XOR password encryption → Fernet; remove simulated/random MT5 deals; analytics reading latest file in `data/raw` → per-user `journal` storage; `bson` already fixed on dev.
  - 002 must state: EA uses `OnTradeTransaction` + `WebRequest`; per-user ingest token (hashed at rest, revocable); idempotent upsert keyed by `(user_id, account_login, deal_ticket)`; history backfill on first connect; heartbeat for connection status.
  - 003 must state: paper → live promotion gate; per-strategy risk limits (max daily loss, max position size); global kill switch; broker adapter port with MT5 first, IBKR later.
  - 004 must state: MCP server and REST with user tokens; AI can create/annotate entries linked to synced executions; human stays owner of edits.

- [ ] **Step 1:** Write files.
- [ ] **Step 2:** Verify each spec has a `Status:` line: `grep -L "Status:" specs/*/design.md` prints nothing.
- [ ] **Step 3: Commit** `docs(specs): add spec workflow and draft specs 001-004`

---

## Frontend (`trading-bot-frontend`)

### Task 6: `features/_template` + `useApiClient` + Nuxt wiring

**Files:**
- Create: `composables/useApiClient.ts`
- Create: `features/_template/api/templateApi.ts`, `features/_template/types/index.ts`, `features/_template/stores/templateItems.ts`, `features/_template/composables/useTemplateItems.ts`, `features/_template/components/TemplateItemList.vue`, `features/_template/index.ts`, `features/_template/README.md`
- Modify: `nuxt.config.ts` — add `components: [{ path: '~/components', pathPrefix: true }, { path: '~/features', pattern: '*/components/**/*.vue', pathPrefix: false }]` and `imports: { dirs: ['features/*/composables', 'features/*/stores'] }`

**Interfaces — Produces:**
- `useApiClient()` returns `{ get<T>(path: string, query?: Record<string, unknown>): Promise<T>, post<T>(path: string, body?: unknown): Promise<T> }`; base URL `${config.public.apiBaseUrl}/api/${config.public.apiVersion}`; sends `Authorization: Bearer <token>` when a token is available (placeholder getter, wired in spec 001); unwraps `SuccessResponse.data`; on error envelope throws `ApiError(code: string, message: string, status: number)` (exported class).
- `types/index.ts`: `ApiPage<T> { items: T[]; pagination: Pagination }`, `Pagination` (fields as backend), `TemplateItem { id: string; name: string; createdAt: string }`.
- `templateApi.ts`: `listItems(params: { page?: number; pageSize?: number }): Promise<ApiPage<TemplateItem>>`, `createItem(name: string): Promise<TemplateItem>` (maps snake_case ↔ camelCase here only).
- `useTemplateItemsStore` (Pinia setup store): `items`, `pagination`, `loading`, `error`, `load(page?)`, `add(name)`.
- `useTemplateItems()` composable exposing the store's state as refs plus actions.
- `TemplateItemList.vue` uses `AppSkeleton`, `AppEmptyState`, `AppPagination` (explicit imports, as current pages do).

- [ ] **Step 1:** Write files.
- [ ] **Step 2:** `npm run build` → success.
- [ ] **Step 3:** Verify wiring: `grep -c "TemplateItemList" .nuxt/components.d.ts` ≥ 1 and `grep -c "useTemplateItems" .nuxt/imports.d.ts` ≥ 1.
- [ ] **Step 4:** `npm run dev`, open `/journal` → still renders (no regression from the `components` config change). Stop server.
- [ ] **Step 5: Commit** `feat(template): add feature-module template and shared API client`

### Task 7: Frontend agent files, docs and specs

**Files:**
- Create: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.agents/rules/architecture.md`, `new-feature.md`, `vue-style.md`, `ui-standards.md`, `api-client.md`, `state.md`, `testing.md`, `git-workflow.md`, `docs-and-specs.md`, `.agents/templates/` (same spec/ADR templates as backend)
- Create: `docs/README.md`, `docs/architecture.md`, `docs/features-catalog.md`, `docs/adr/0001-feature-modules.md`
- Delete: `.gemini/` (merged into `ui-standards.md`, `vue-style.md`), `docs/project-spec.md`, `docs/tech-spec.md` (folded), `TROUBLESHOOTING-DATOS.md` → `docs/legacy/troubleshooting-data.md` (translated)
- Create: `specs/README.md`, set `specs/000-agents-foundation/design.md` → `Status: approved`, `specs/001-feature-migration/`, `002-mt5-connection-ui/`, `003-strategies-ui/`, `004-ai-journal-ui/` `design.md` drafts linking to the backend spec of the same number (scope from frontend design §6).
- `testing.md` states Vitest is the target runner, introduced in frontend spec 001 (planned).

- [ ] **Step 1:** Write files.
- [ ] **Step 2:** Same checks as Tasks 3–5 (line limits, code block per rule file, no `.gemini`, no `file:///`, every spec has `Status:`).
- [ ] **Step 3:** `npm run build` → success.
- [ ] **Step 4: Commit** `docs(agents): add AGENTS.md, rules, docs and spec drafts`

### Task 8: Final verification

- [ ] Backend: `pytest libs/shared/tests services/_template/tests -v` → 20 passed; legacy `pytest tests -v` result unchanged vs `dev` (record pass/fail counts before and after).
- [ ] Frontend: `npm run build` → success.
- [ ] Both: `git status` clean, `git log --oneline origin/dev..HEAD` shows the task commits, nothing pushed.
