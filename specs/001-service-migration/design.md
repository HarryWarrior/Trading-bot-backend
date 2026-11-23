# 001 — Migrate legacy app to services (design)

- **Status:** draft
- **Date:** 2026-11-23
- **Repos:** backend (this doc) · frontend counterpart: `trading-bot-frontend/specs/001-feature-migration/design.md`
- **Services touched:** new `auth`, `journal`, `analytics`; `libs/shared`; legacy `app/` retired

## 1. Intent

Move the working functionality of the legacy monolith (`app/`) into hexagonal services built from
`services/_template`, make everything multi-user on MongoDB, and pay the known security debt, so that
specs 002–004 build on solid ground instead of on the monolith.

## 2. Goals, non-goals, anti-goals

**Goals**
- `deploy/docker-compose.yml` with MongoDB, Traefik gateway and the services; one command to run locally.
- `libs/shared` gains JWT verification dependency (`get_current_user`), Mongo client factory and
  `X-Request-ID` middleware.
- `auth` service: all current auth flows; issues short-lived JWT + refresh/session records.
- `journal` service: per-user trades storage in `journal_db`; report upload (CSV/XLSX) with the existing
  header detection/normalization; idempotent ingestion (SHA-256 per file, natural key per trade).
- `analytics` service: current KPIs computed from the user's journal trades (via journal API), not
  from `data/raw/`.
- All endpoints follow `.agents/rules/api-contracts.md`.
- Remove `app/` once parity is verified.

**Non-goals** — MT5 live sync (002), OAuth providers, billing/plans.

**Anti-goals** — losing any metric users see today; a "big bang" that leaves nothing running mid-way.

## 3. Constraints

- Hexagonal template and rules in `.agents/rules/`. Contracts already defined in `trading_shared`.
- Frontend keeps working during migration (frontend spec 001 switches it to the new endpoints).

## 4. Known debt to fix (from `dev`)

| Debt | Fix |
|---|---|
| MT5 passwords "encrypted" with XOR + base64 and a hard-coded default key | Remove password storage entirely (ADR 0002); until 002 lands, disable the endpoint or use Fernet with env key |
| MT5 sync returns simulated / `random` deals when the `MetaTrader5` package is missing | Delete simulation; real data only (002) |
| Analytics reads the most recent file in `data/raw/` for every user | Per-user `journal` storage |
| `JWT_SECRET_KEY` / MT5 key hard-coded fallbacks; CORS `*` | Required env secrets; explicit origins |
| Spanish strings and mixed envelopes in `app/` | English + standard envelope in new services |
| `bson` package conflicting with PyMongo | Already fixed on `dev`; keep it out of all requirements |

## 5. Approaches

1. **Strangler (recommended):** stand up gateway + new services next to `app/`, route prefix by prefix
   to the new services, delete `app/` at the end. Always runnable.
2. Big-bang rewrite then switch. Rejected (anti-goal).

## 6. Design sketch

- Order: `libs/shared` additions → compose + gateway → `auth` → `journal` → `analytics` → frontend switch
  → remove `app/`.
- `journal` domain: `Trade` (normalized round trip), `Execution` (raw deal), `ReportImport` (file hash,
  counts); ports `TradeRepository`, `ReportParser` (adapters: MT5 XLSX/CSV; later cTrader…).
- `analytics` is stateless: ports `TradeSource` (adapter: journal HTTP client), pure domain KPI functions
  ported from `analytics_service.py` with their tests.
- Data migration script: existing `trading_bot_db.users/sessions` → `auth_db`.

## 7. Open questions

- Keep existing user accounts (migrate) or start clean? Affects the migration script.
- Is any production deployment running `dev` today, or is local-only fine during migration?

## 8. Done when

Compose runs all services; frontend works against the gateway; legacy tests' behaviors are covered by
new service tests; `app/` removed; security debt table closed.
