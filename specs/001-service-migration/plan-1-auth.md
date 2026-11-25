# 001 · Plan 1 of 4 — Shared auth/Mongo + `auth` service + sample data

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real, standalone `auth` service (sign-up, email verification, sign-in, refresh, sign-out, password reset, me, admin) on MongoDB `auth_db`, with JWT verification available to every service via `trading_shared`, and example data moved out of code paths.

**Architecture:** `services/auth` copied from `services/_template` (hexagonal). Domain + use cases are pure and tested with fakes; adapters: Mongo repositories, bcrypt hasher, PyJWT issuer, SMTP/log email senders. `trading_shared.auth` verifies access tokens locally for all services.

**Tech Stack:** Python 3.11+, FastAPI 0.104.1, Pydantic 2.5, pydantic-settings 2.1, motor 3.7.1 / pymongo 4.18.0, PyJWT 2.8.0, bcrypt 4.1.2, email-validator 2.3.0, pytest 7.4.3, pytest-asyncio 0.21.1.

**Spec:** `specs/001-service-migration/design.md` (§2, §5.2, §5.3, §5.7, §5.9, §5.11-7). Plans 2–4 cover journal/analytics, mt5, frontend + cutover.

## Global Constraints

- Branch `feat/001-real-data`; one commit per task; never push without the owner.
- Follow `.agents/rules/` (hexagonal dependency rule, envelope via `trading_shared`, English only, `Depends(page_params)` for lists).
- **No data in code:** no demo users, no hard-coded secrets, no fallback balances. Secrets only from env.
- Verification codes / reset tokens are **never** returned by the API nor logged except: `environment=local` and no SMTP configured → the code is written to the server log via `LogEmailSender`.
- Codes and tokens generated with `secrets` (codes: 6 digits; refresh/reset tokens: `secrets.token_urlsafe(32)`), stored **hashed** (SHA-256) except the 6-digit code which is stored hashed too.
- Access JWT HS256, 15 min, claims `sub`, `email`, `role`, `iat`, `exp`. Refresh token 7 days, rotated on every refresh. Reset token 1 h, single use. Verification code 15 min, single use.
- Emails are normalized (`strip().lower()`) everywhere.
- Error codes (`AppError`): `EMAIL_ALREADY_REGISTERED` 409, `INVALID_CREDENTIALS` 401, `EMAIL_NOT_VERIFIED` 403, `INVALID_VERIFICATION_CODE` 400, `INVALID_TOKEN` 401, `UNAUTHENTICATED` 401, `FORBIDDEN` 403.
- Mongo database `auth_db`; collections `users`, `verification_codes`, `sessions`, `password_resets`; TTL index on `expires_at` where applicable; unique index `users.email`.

## Review Focus

1. `"  User@Mail.COM "` signs up, then signs in as `user@mail.com` → same account; second sign-up with any casing → 409. (Task 3)
2. A refresh token already used once (rotated) → 401 `INVALID_TOKEN`. (Task 3)
3. Verification code older than 15 min or already used → 400 `INVALID_VERIFICATION_CODE`. (Task 3)
4. After `reset-password`, every refresh token of that user → 401; the reset token cannot be used twice. (Task 3)
5. `resend-verification` / `forgot-password` for an unknown email → 200 with the same body as a known one (no account enumeration). (Task 5)

---

### Task 1: Example data out of code paths

**Files:**
- Move: `data/raw/sample_trades.csv` → `data/samples/sample_trades.csv` (`git mv`)
- Untrack: `data/raw/*` real reports (`git rm --cached`), move them locally to `data/private/`
- Modify: `.gitignore` (+ `data/raw/`, `data/private/`), `tests/acceptance/conftest.py` (`SAMPLE_REPORT` path), `tests/acceptance/test_analytics.py` (`SAMPLE` path), `data/samples/README.md` (new: what it is, never read by code at runtime)
- Test: `tests/test_repository_hygiene.py`

- [ ] **Step 1:** Write `test_only_samples_are_tracked_under_data`: `git ls-files data` output lines all start with `data/samples/`.
- [ ] **Step 2:** Run `pytest tests/test_repository_hygiene.py` → FAIL (real reports tracked).
- [ ] **Step 3:** Do the moves/untracking and edits above. Legacy `app/` keeps writing uploads into `data/raw/` (now ignored).
- [ ] **Step 4:** `pytest tests/test_repository_hygiene.py tests/acceptance -q` → hygiene PASS; acceptance `28 passed, 14 xfailed`.
- [ ] **Step 5:** Commit `chore(data): keep only sample data in repo; real reports move to ignored data/private`

### Task 2: `trading_shared` — JWT verification, Mongo client, request id

**Files:**
- Create: `libs/shared/src/trading_shared/auth.py`, `mongo.py`, `request_id.py`
- Modify: `libs/shared/pyproject.toml` (deps `PyJWT==2.8.0`, `motor==3.7.1`, `pymongo==4.18.0`), `libs/shared/README.md`
- Test: `libs/shared/tests/test_auth.py`, `test_request_id.py`

**Interfaces — Produces:**
- `auth.py`: `@dataclass(frozen=True) CurrentUser(id: str, email: str, role: str)`; `decode_access_token(token: str, secret: str) -> CurrentUser` (raises `AppError("UNAUTHENTICATED", ..., 401)` on missing/invalid/expired, HS256 only); `current_user_dependency(get_secret: Callable[[], str]) -> Callable[..., CurrentUser]` reading `Authorization: Bearer`; `require_role(dependency, *roles: str) -> Callable[..., CurrentUser]` raising `AppError("FORBIDDEN", ..., 403)`.
- `mongo.py`: `create_mongo_client(url: str) -> AsyncIOMotorClient`; `async ensure_indexes(collection, specs: list[IndexModel]) -> None`.
- `request_id.py`: `RequestIdMiddleware` (reuse incoming `X-Request-ID` or uuid4 hex; echo in response header).

- [ ] **Step 1:** Tests: `test_valid_token_returns_current_user`, `test_expired_token_is_rejected`, `test_wrong_secret_is_rejected`, `test_alg_none_is_rejected`, `test_missing_header_returns_401_envelope` (TestClient route using the dependency → 401, `error.code == "UNAUTHENTICATED"`), `test_require_role_rejects_other_roles` (403 `FORBIDDEN`), `test_request_id_is_echoed` and `test_request_id_is_generated`. Tokens created in tests with `jwt.encode`.
- [ ] **Step 2:** `pytest libs/shared/tests -q` → new tests FAIL.
- [ ] **Step 3:** Implement per Interfaces. `envelope.py` stays framework-free (existing test guards it).
- [ ] **Step 4:** `pytest libs/shared/tests -q` → all pass; ruff clean.
- [ ] **Step 5:** Commit `feat(shared): add JWT verification, Mongo client and request id middleware`

### Task 3: `auth` domain and use cases (pure)

**Files:**
- Create `services/auth/` by copying `services/_template` per `.agents/rules/new-service.md` (package `auth_service`, prefix `/api/v1/auth`, add `auth_service` to root ruff `known-first-party`); delete the sample `Item` code/tests.
- Create: `src/auth_service/domain/{user.py, tokens.py, errors.py}`, `application/ports/{repositories.py, security.py, email.py, clock.py}`, `application/use_cases/{sign_up.py, verify_email.py, resend_verification.py, sign_in.py, refresh_session.py, sign_out.py, forgot_password.py, reset_password.py, get_me.py, cleanup_expired_sessions.py}`
- Test: `tests/unit/fakes.py` (in-memory repos, fake hasher, fake token issuer, recording email sender, fixed clock), `tests/unit/test_use_cases.py`, `tests/unit/test_architecture.py` (kept)

**Interfaces — Produces:**
- Domain: `User(id, email, name, role: Role, password_hash, email_verified: bool, created_at)`; `Role(StrEnum)`: `user`, `trader`, `admin`; `normalize_email(raw: str) -> str`.
- Ports (Protocols): `UserRepository` (`add`, `get_by_email`, `get_by_id`, `mark_verified`, `set_password_hash`, `set_role`), `VerificationRepository` (`replace_code(email, code_hash, expires_at)`, `consume(email, code_hash, now) -> bool`), `SessionRepository` (`add(user_id, token_hash, expires_at)`, `consume(token_hash, now) -> str | None` returns user_id and deletes, `revoke(token_hash)`, `revoke_all(user_id)`, `delete_expired(now) -> int`), `PasswordResetRepository` (`add`, `consume(token_hash, now) -> str | None`), `PasswordHasher` (`hash`, `verify`), `AccessTokenIssuer` (`issue(user) -> tuple[str, int]` token + expires_in seconds), `SecretGenerator` (`verification_code() -> str`, `opaque_token() -> str`), `EmailSender` (`send_verification(email, code)`, `send_password_reset(email, token)`), `Clock` (`now() -> datetime`).
- Use case `execute` signatures: `SignUp(email, password, name) -> User`; `VerifyEmail(email, code) -> None`; `ResendVerification(email) -> None`; `SignIn(email, password) -> AuthTokens`; `RefreshSession(refresh_token) -> AuthTokens`; `SignOut(refresh_token) -> None`; `ForgotPassword(email) -> None`; `ResetPassword(token, new_password) -> None`; `GetMe(user_id) -> User`; `CleanupExpiredSessions() -> int`. `AuthTokens(access_token: str, refresh_token: str, expires_in: int, user: User)`.
- Domain errors → codes listed in Global Constraints.

- [ ] **Step 1:** Write failing tests (fakes, fixed clock):
  - `test_sign_up_normalizes_email_and_sends_code` (stored email `user@mail.com`; email sender got one code; user unverified)
  - `test_sign_up_duplicate_any_casing_raises_email_already_registered`
  - `test_sign_in_before_verification_raises_email_not_verified`
  - `test_verify_with_wrong_code_raises`, `test_verify_code_expires_after_15_minutes`, `test_verify_code_is_single_use`
  - `test_sign_in_wrong_password_raises_invalid_credentials`, `test_sign_in_unknown_email_raises_invalid_credentials`
  - `test_sign_in_returns_access_and_refresh_tokens` (`expires_in == 900`)
  - `test_refresh_rotates_token_and_old_one_is_rejected`
  - `test_sign_out_revokes_refresh_token`
  - `test_forgot_password_unknown_email_sends_nothing_and_does_not_raise`
  - `test_reset_password_changes_hash_revokes_all_sessions_and_is_single_use`, `test_reset_token_expires_after_1_hour`
  - `test_cleanup_deletes_only_expired_sessions`
- [ ] **Step 2:** `pytest services/auth/tests/unit -q` → FAIL (imports).
- [ ] **Step 3:** Implement domain, ports, use cases. Hash codes/tokens with SHA-256 in the use cases (domain helper `digest(value) -> str`).
- [ ] **Step 4:** `pytest services/auth/tests/unit -q` → all pass (incl. architecture test).
- [ ] **Step 5:** Commit `feat(auth): add auth domain and use cases`

### Task 4: `auth` outbound adapters

**Files:**
- Create: `adapters/outbound/{mongo_repositories.py, bcrypt_hasher.py, jwt_issuer.py, secrets_generator.py, email_senders.py, system_clock.py}`
- Test: `tests/integration/test_mongo_repositories.py` (throwaway DB `test_auth_<uuid>`, dropped after; skip if Mongo unreachable), `tests/unit/test_adapters.py`

**Interfaces — Produces:** `MongoUserRepository(db)`, `MongoVerificationRepository(db)`, `MongoSessionRepository(db)`, `MongoPasswordResetRepository(db)` each with `async create_indexes()`; `BcryptPasswordHasher(rounds: int = 12)`; `JwtAccessTokenIssuer(secret: str, minutes: int = 15)`; `SecretsGenerator`; `SmtpEmailSender(host, port, user, password, from_email, frontend_url)`; `LogEmailSender(logger)` (logs `"verification code for <email>: <code>"` / reset link); `SystemClock`.

- [ ] **Step 1:** Tests: unique email index rejects duplicates; session `consume` deletes and returns user id once; expired session not consumable; `JwtAccessTokenIssuer` output decodes with `trading_shared.auth.decode_access_token` to the same `CurrentUser`; `BcryptPasswordHasher` verifies and rejects; `SecretsGenerator.verification_code()` is 6 digits; `LogEmailSender` writes the code to the log (caplog).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Use `bcrypt` directly (not passlib).
- [ ] **Step 4:** `pytest services/auth/tests -q` → pass.
- [ ] **Step 5:** Commit `feat(auth): add Mongo, bcrypt, JWT and email adapters`

### Task 5: `auth` HTTP API, settings, wiring

**Files:**
- Modify/Create: `settings.py` (`AuthSettings`: `service_name="auth"`, `mongodb_url="mongodb://localhost:27017"`, `database_name="auth_db"`, `jwt_secret_key: SecretStr` **required**, `access_token_minutes=15`, `refresh_token_days=7`, `smtp_host/port/user/password/from_email: optional`, `frontend_url="http://localhost:3000"`, `cors_origins=["http://localhost:3000"]`; validator: `environment=="prod"` and no `smtp_host` → error), `bootstrap.py`, `main.py` (CORS, `RequestIdMiddleware`, `create_indexes` on startup), `adapters/inbound/http/{router.py, schemas.py}`, `.env.example`, `README.md`
- Test: `tests/integration/test_http.py`

**Routes (prefix `/api/v1/auth`, all envelopes):** `POST /sign-up` {email,password(min 8),name} → 201 `{user}` · `POST /verify-email` {email, code} → 200 · `POST /resend-verification` {email} → 200 · `POST /sign-in` {email,password} → 200 `{access_token, refresh_token, token_type:"bearer", expires_in, user}` · `POST /refresh` {refresh_token} → 200 same shape · `POST /sign-out` {refresh_token} (Bearer required) → 200 · `POST /forgot-password` {email} → 200 · `POST /reset-password` {token, new_password} → 200 · `GET /me` (Bearer) → 200 `{user}` · `DELETE /sessions/expired` (admin) → 200 `{deleted}`. `user` = `{id, email, name, role, email_verified, created_at}` — never `password_hash`.

- [ ] **Step 1:** Integration tests with `create_app(settings)` on a throwaway DB and a recording `EmailSender` injected via `build_container(settings, email_sender=...)`: full flow sign-up → code from recorder → verify → sign-in → me → refresh → sign-out; `test_sign_up_response_has_no_code`; `test_resend_unknown_email_same_response_as_known`; `test_forgot_unknown_email_same_response_as_known`; `test_me_without_token_401`; `test_cleanup_requires_admin_403`; `test_password_shorter_than_8_is_422`; `test_prod_without_smtp_fails_settings` (constructing `AuthSettings(environment="prod", jwt_secret_key="x")` raises).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; `build_container` picks `SmtpEmailSender` when `smtp_host` set, else `LogEmailSender` (only allowed when `environment != "prod"`).
- [ ] **Step 4:** `pytest services/auth/tests -q` → pass; smoke `uvicorn auth_service.main:app --port 8001` with a `.env` → `/health` 200, sign-up logs the code.
- [ ] **Step 5:** Commit `feat(auth): add HTTP API, settings and wiring`

### Task 6: Legacy user migration and first admin

**Files:**
- Create: `services/auth/scripts/migrate_legacy_users.py`, `services/auth/scripts/promote_admin.py`, `src/auth_service/application/use_cases/import_legacy_users.py`
- Test: `tests/integration/test_migration.py`

**Interfaces:** `ImportLegacyUsers(source: LegacyUserSource, users: UserRepository).execute() -> ImportReport(imported, skipped_existing)`; legacy fields mapped: `email`→normalized, `password_hash` (bcrypt, kept), `name`, `role`, `email_verified`, `created_at`. `promote_admin.py <email>` sets role `admin`, exits 1 if the user does not exist.

- [ ] **Step 1:** Tests on throwaway DBs: legacy users imported with same hash (user can sign in with old password); running twice imports 0 new (`skipped_existing` counts them); promote unknown email exits non-zero.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** pass.
- [ ] **Step 5:** Commit `feat(auth): add legacy user migration and admin promotion scripts`

### Task 7: Dev runner, docs, verification

**Files:** `scripts/dev.ps1` (starts `auth` on 8001 with its `.env`; later plans add services), `docs/services-catalog.md` (`auth` → in-progress), `AGENTS.md` run section, `docs/CHANGELOG.md` (Unreleased).

- [ ] **Step 1:** `pytest libs/shared/tests services/_template/tests services/auth/tests tests -q` → all green (legacy untouched: `28 passed, 14 xfailed` within).
- [ ] **Step 2:** `ruff check libs services tests && ruff format --check libs services tests` → clean.
- [ ] **Step 3:** `scripts/dev.ps1` then sign-up/verify/sign-in with curl against :8001; code appears only in the console.
- [ ] **Step 4:** Commit `docs(auth): document auth service and dev runner`

## Execution notes (plan 1 done, 2026-11-23)

Executed subagent-driven; every task reviewed; final whole-branch review clean after one fix wave.

**Carried to plan 4 (hardening before exposure beyond localhost):**
- bcrypt hashing/verification and SMTP run on the event loop → make the ports async (`asyncio.to_thread`).
- Rate limiting: sign-in, verification-code attempts (6-digit code is brute-forceable within 15 min without it), resend/forgot (email bombing).
- SMTP: timeout; implicit TLS (port 465) support.
- Remaining enumeration signals: SMTP failure → 500 only for known emails; sign-in timing for unknown emails.

**Small follow-ups (any later plan):** `get_me` returns `INVALID_TOKEN` for a deleted user (vs `UNAUTHENTICATED`);
`import_legacy_users` uses the wall clock instead of the `Clock` port; migration source==target guard does not normalize
host aliases/ports; scripts require `JWT_SECRET_KEY` via `AuthSettings`; OpenAPI security scheme and `WWW-Authenticate`
header; `allow_credentials` unnecessary for Bearer; X-Request-ID length/charset limit; missing migration tests (default
source URL, missing `created_at`, case-duplicate source emails); test hygiene (alg-none test isolation, index assertions,
hard-coded test Mongo URL).
