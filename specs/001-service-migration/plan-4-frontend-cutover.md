# 001 · Plan 4 of 4 — Frontend on real services, local gateway, retire `app/`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The web app works end to end against the four services with real login and real data only; the legacy
monolith `app/` is removed; an acceptance suite proves the services do what the legacy app did, minus its 14 known bugs.

**Architecture:** Frontend (repo `trading-bot-frontend`, branch `feat/001-real-data`) calls same-origin `/api/v1/<service>`;
in development Nuxt's Nitro dev proxy forwards each prefix to its service port (8001–8004), so no CORS and the same URLs
work behind a gateway later. Features from `features/_template`: `auth`, `journal`, `analytics`, `mt5-connection`.
Backend (repo `Trading-bot-backend`) gains a cross-service acceptance suite and `deploy/` (compose + Traefik config,
documented, not required to run), and drops `app/`.

**Spec:** backend `specs/001-service-migration/design.md` §5.8–§5.10; frontend `specs/001-feature-migration/design.md`.

## Global Constraints

- Both repos on `feat/001-real-data`; commits per task; push only in the final step (owner authorized).
- **Real data only:** no `Math.random` for data/candles anywhere (only `AppInput` ids), no hard-coded balances/demo
  accounts; unavailable data → explicit empty/error state ("No market data", "MT5 terminal not running", "—").
- Auth: access token in memory (Pinia), refresh token in `localStorage` (key `tb.refresh`); on `UNAUTHENTICATED` refresh
  once then retry, else clear and go to `/login`. Every page except `/login`, `/register`, `/verify-email`,
  `/forgot-password`, `/reset-password` requires a session (global route middleware).
- Only feature `api/` files call `useApiClient`; components never call `$fetch`; snake_case↔camelCase mapping in `api/`.
- Numbers shown rounded (money 2 dp with sign/color; percentages 2 dp + "%"); `null` → "—". i18n en/es for all visible text.
- Admin-only MT5 actions are hidden/disabled for non-admins with an explanation (upload reports instead).
- Frontend checks: `npm run build`, `npx nuxi typecheck`, `npx vitest run` green. Backend: full pytest green, ruff clean.

## Review Focus

1. Expired access token mid-session → transparent refresh; refresh also invalid → back to `/login`, no infinite loop. (Task 2)
2. Two users in two browsers never see each other's trades/KPIs/accounts. (Tasks 4, 7)
3. Journal or analytics down → the page shows an error state, not zeros or stale numbers. (Tasks 3, 4)
4. MT5 terminal closed → link/sync/candles show "terminal not running", charts show "No market data". (Task 5)
5. Upload with skipped rows → the user sees how many rows were skipped and why (row number + reason). (Task 3)

---

### Task 1 (frontend): dev proxy, API client with auth, test tooling
**Files:** `nuxt.config.ts` (`nitro.devProxy` for `/api/v1/auth|journal|analytics|mt5` → `NUXT_AUTH_URL` etc. defaulting to
`http://localhost:8001..8004`; `runtimeConfig.public.apiBaseUrl` default `''`), `composables/useApiClient.ts` (token getter from
auth store, one refresh-and-retry on 401, `ApiError` kept), `vitest.config.ts`, `package.json` (vitest, @nuxt/test-utils,
happy-dom, vue-tsc), `tests/unit/useApiClient.spec.ts`.
- [ ] Tests (RED first): envelope unwrap; error envelope → `ApiError(code)`; 401 → refresh called once → retried; refresh fails →
  `onSessionExpired` invoked; no token → no Authorization header. **Commit** `feat(api): same-origin dev proxy and authenticated API client`.

### Task 2 (frontend): `auth` feature and screens
**Files:** `features/auth/{api,types,stores,composables,components}`, pages `login, register, verify-email, forgot-password,
reset-password`, `middleware/auth.global.ts`, `layouts/default.vue` with `AppHeader`/`AppSidebar` (user menu, role badge,
sign-out), i18n keys. Backend contract: plan 1 `/api/v1/auth` routes.
- [ ] Tests: auth api mappers; store sign-in/refresh/sign-out (refresh token persisted under `tb.refresh`, access only in
  memory); middleware redirects signed-out users and lets auth pages through; verify flow navigates to login.
  **Commit** `feat(auth): login, registration, verification and session handling`.

### Task 3 (frontend): `journal` feature
**Files:** `features/journal/...`, page `/upload` (drag & drop, shows import result incl. skipped rows table and duplicate
409 message), page `/trades` (AppPagination, filters symbol/outcome/date/account, sort), account selector component
reused by analytics. Remove `stores/analytics.ts` upload/trades parts as they move.
- [ ] Tests: api mappers (trade/import/balance JSON → view types), store pagination/filter query building, upload error codes →
  messages (DUPLICATE_IMPORT, UNSUPPORTED_FILE, FILE_TOO_LARGE, UNREADABLE_REPORT). **Commit** `feat(journal): upload and trades on the journal service`.

### Task 4 (frontend): `analytics` feature and dashboard
**Files:** `features/analytics/...`, page `/journal` (dashboard) rebuilt: KPI cards (summary), equity curve (points),
calendar heatmap (daily), by-symbol table, hourly; account selector; trade detail/comparison charts fed by `/api/v1/mt5/rates`
via a small `features/market` api (or empty state); delete `stores/analytics.ts`, `stores/mt5.ts`, `components/Analytics/Mt5ConnectModal.vue`,
all `Math.random` candle code; `tests/unit/no-random-data.spec.ts` (grep guard over `features`, `components`, `pages`, `stores`).
- [ ] Tests: KPI formatting (null → "—", 2 dp, sign), analytics api mappers, error state when analytics returns 503, guard test.
  **Commit** `feat(analytics): dashboard on real analytics; remove simulated data`.

### Task 5 (frontend): `mt5-connection` feature
**Files:** `features/mt5-connection/...`, page `/mt5` (admin: "Link the account open in my terminal" showing what the terminal
reports after linking, accounts list with live status, Sync button with result counts incl. skipped positions; non-admin:
explanation + link to upload), errors mapped (TERMINAL_NOT_AVAILABLE, TERMINAL_ACCOUNT_MISMATCH, MULTIPLE_TERMINALS,
SERVER_TIMEZONE_MISMATCH, ACCOUNT_ALREADY_LINKED, JOURNAL_UNAVAILABLE).
- [ ] Tests: mappers, error-code → message map, admin vs non-admin rendering. **Commit** `feat(mt5): MT5 connection page`.

### Task 6 (frontend): cleanup, docs, checks
**Files:** remove dead legacy pages/components, `docs/features-catalog.md`, `AGENTS.md`, `docs/CHANGELOG.md`, `.agents/rules/testing.md`
(Vitest now real), README env vars. 
- [ ] `npm run build`, `npx nuxi typecheck`, `npx vitest run` green. **Commit** `docs: frontend on real services`.

### Task 7 (backend): cross-service acceptance suite and gateway config
**Files:** `tests/acceptance_services/` (in-process apps via `httpx.ASGITransport` with lifespans on throwaway DBs: auth, journal,
analytics, mt5 with a FakeTerminal; scenarios: sign-up → code from a recording sender → sign-in → upload sample → summary
1450.00/70.00; second user isolated; duplicate upload 409; refresh rotation; non-admin MT5 403; terminal unavailable 409; each of the
14 legacy known bugs rewritten as a passing test against the new services or explicitly dropped with reason (OAuth));
`deploy/docker-compose.yml` (mongo + traefik + auth/journal/analytics; mt5 routed to `host.docker.internal:8004`),
`deploy/traefik/dynamic.yml`, `deploy/README.md`; a backend guard test (no `random` market data / hard-coded balances in `services/`, `libs/`).
- [ ] RED → green; **Commit** `test: cross-service acceptance suite; deploy config`.

### Task 8 (backend): retire `app/`
**Files:** delete `app/`, legacy `tests/test_*.py`, `tests/acceptance/`, `tests/test_repository_hygiene.py` stays; root
`requirements.txt` replaced by per-service installs (document `pip install -e libs/shared -e services/<x>`); `scripts/dev.ps1`
unaffected; docs (AGENTS.md current-vs-target table now "done", services-catalog `app` → retired, architecture, CHANGELOG,
spec 001 status `done`).
- [ ] Full run `pytest libs/shared/tests services tests -q -rs` green, ruff clean. **Commit** `refactor!: retire legacy app`.
