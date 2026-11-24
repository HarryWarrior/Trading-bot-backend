# Changelog - Trading Bot Backend API

## [Unreleased]

### Changed (plan 3 final review)
- mt5: never launches the terminal (process probe via `psutil`, `initialize(path=...)` only for exactly one running terminal; new `MULTIPLE_TERMINALS` 409); new `MT5_SERVER_TIMEZONE` (IANA zone with optional shift such as `America/New_York+7`, needs `tzdata` on Windows) converts deals and candles per timestamp (DST and weekend safe, `SERVER_TIMEZONE_MISMATCH` 409 when it contradicts the live tick); history end bound is local now + 2 days; positions with entry deals of both sides are skipped (`mixed entry sides`).

### Changed (plan 2 final review)
- analytics: withdrawals/adjustments shift the equity peak (only trades create drawdown); starting balance, ending balance and drawdown % are `null` unless every traded account in scope has balance data, and drawdown % is `null` if equity ever goes below 0.
- journal: MT5 correction/charge/bonus/commission-type deals become signed `adjustment` balance events; unknown deal types are reported in `skipped_rows`; the account-summary block after Deals is ignored; skipped rows report absolute file/sheet row numbers; flat-file uploads share the stable account ref `upload` (overlapping re-imports never duplicate).
- root `requirements.txt` (legacy app): `python-multipart` 0.0.6 → 0.0.20.

### Added
- `AGENTS.md`, `.agents/rules/` and `.agents/templates/`: single source of rules for AI agents (replaces `.gemini/rules`).
- `libs/shared` (`trading_shared`): response envelope, pagination (`page_params`), error envelope, settings, logging.
- `services/_template`: canonical hexagonal microservice with architecture test.
- `docs/`: architecture, services catalog, ADRs 0001-0003, integrations research log.
- `specs/`: spec workflow and drafts 001-004 (service migration, MT5 EA bridge, backtest-to-live, AI journal).

- `tests/acceptance/`: end-to-end acceptance suite of the legacy API (28 passing behaviors, 14 known bugs as strict xfail).

- `libs/shared`: `trading_shared.auth` (local JWT verification, `require_role`), `trading_shared.mongo` (Motor client, idempotent indexes) and `trading_shared.request_id` (`X-Request-ID` middleware).
- `services/auth` (port 8001, `auth_db`): sign-up with email code, sign-in, rotating refresh tokens, sign-out, password reset, roles; codes are only logged locally when no SMTP is set.
- `services/auth/scripts/migrate_legacy_users.py` and `promote_admin.py`.
- `scripts/dev.ps1`: dev runner for the new services (auth, journal, analytics); refuses to start if their `JWT_SECRET_KEY` values differ.
- `services/journal` (port 8002, `journal_db`): MT5 HTML/XLSX and flat CSV/XLSX report parsers, idempotent per-user trade and balance-event import, trades/accounts/dataset queries, MT5 ingest endpoint. Uses `python-multipart` 0.0.20.
- `services/analytics` (port 8003, stateless): KPI summary, equity/drawdown, daily, monthly, by-symbol and hourly stats computed from the journal API (503 `JOURNAL_UNAVAILABLE` when journal is down).
- Root pytest config: `asyncio_mode = "auto"`, `--import-mode=importlib`, default `-m 'not private'`; `-m private` reads real reports from git-ignored `data/private/`.
- `services/mt5` (port 8004, `mt5_db`): attaches to the open, logged-in MetaTrader 5 terminal on the Windows host (ADR 0004); admin-only link, status, sync and unlink of the terminal account, closed-trade sync into journal, and candles (`/rates`). No broker credentials are stored.
- journal: service-to-service ingest authenticated with `INGEST_SERVICE_KEY` (shared with mt5; at least 32 characters).
- `MetaTrader5` Python package dependency (Windows only) for `services/mt5`.
- pytest marker `live` (needs a running, logged-in MT5 terminal; run with `-m live`, deselected by default).
- `scripts/dev.ps1`: starts mt5 (8004) and refuses to start if `INGEST_SERVICE_KEY` of journal and mt5 is missing or differs.
- ADR 0004: MT5 terminal adapter.

### Changed
- Sample data moved to `data/samples/`; real reports go in git-ignored `data/private/`.
- `scripts/inspect_excel.py` takes the report path as an argument.

### Removed
- `docs/project-spec.md`, `docs/tech-spec.md` (folded into `docs/architecture.md` and `.agents/rules/`).

---

## [2.0.4] - 2026-09-08

### ✨ Added
- MetaTrader 5 multi-account management with live telemetry handshake and account switcher

---

## [2.0.2] - 2026-09-08

### ✨ Added
- MetaTrader 5 live integration and conflict resolution for pymongo/bson

---

## [2.0.0] - 2025-12-03 - Sistema de Autenticación Completo 🔐

### ✨ Nuevas características principales

#### Sistema de Autenticación (Auth Service Microservice)
- **Registro de usuarios (Sign-up)**
  - Validación de email único
  - Hash seguro de contraseñas con bcrypt
  - Generación automática de código de verificación
  - Envío de email de verificación con template HTML profesional

- **Autenticación (Sign-in/Sign-out)**
  - Login con email y password
  - Generación de JWT tokens (HS256)
  - Sesiones persistentes en MongoDB
  - Invalidación de sesiones (logout)
  - Validación de email verificado antes de login

- **Verificación de Email**
  - Código de 6 dígitos con expiración de 15 minutos
  - Endpoint para reenviar código
  - Email de bienvenida después de verificar
  - Templates HTML profesionales con gradientes

- **Recuperación de Contraseña**
  - Solicitud de reset con envío de email
  - Token JWT con expiración de 1 hora
  - Flow completo de password reset
  - Invalidación de todas las sesiones al resetear

- **Gestión de Sesiones**
  - Almacenamiento en MongoDB con índices optimizados
  - Validación automática en cada request
  - Limpieza de sesiones expiradas (endpoint admin)
  - Token incluye user_id, email, y role

- **Roles de Usuario**
  - `user`: Usuario normal
  - `trader`: Trader con permisos especiales
  - `admin`: Administrador del sistema

- **OAuth (Estructura preparada)**
  - Endpoints definidos para Google y GitHub
  - Schema para cuentas OAuth
  - Base de datos lista (colección `accounts`)

### 🗄️ Base de Datos MongoDB

#### Colecciones
- **users**: email (unique), password_hash, name, role, email_verified, created_at
- **sessions**: user_id, token (unique), expires_at, created_at
- **verifications**: identifier, code, expires_at, created_at
- **accounts**: user_id, [provider, provider_id] (compound unique), created_at

---

## [1.1.0] - 2025-11-25 - Soporte para archivos Excel

### ✨ Nuevas características
- **Soporte para archivos XLSX/XLS**: Ahora el sistema acepta archivos de Excel además de CSV
  - Formatos soportados: `.csv`, `.xlsx`, `.xls`
  - Validación automática de extensiones en el endpoint de upload
  - Detección automática del formato de archivo para procesamiento
- **TradeParserService**: Detección dinámica de cabeceras y soporte bilingüe.
