# Security

This platform touches money and broker accounts. When unsure, choose the safer option and ask.

## Secrets

- Secrets come **only** from environment variables (via the service `Settings`). Never hard-code
  defaults for secrets; a missing secret must fail startup outside `environment=local`.
- `.env` files are git-ignored. Document variables in the service README (names only, no values).
- Never log passwords, tokens, API keys, full card/account numbers or request bodies containing them.

```python
class AuthSettings(BaseServiceSettings):
    jwt_secret_key: SecretStr          # required, no default
    access_token_minutes: int = 15
```

## Users and tokens

- Passwords: bcrypt, cost ≥ 12. Never stored or logged in plain text.
- Access tokens: HS256 JWT signed by `auth`, short-lived (15 min target), claims `sub` (user id),
  `role`, `exp`, `iat`. Services verify signature and expiry locally *(planned, spec 001)*.
- Refresh/session records live in `auth_db.sessions` with TTL; password reset revokes all sessions.
- Email OTP: 6 digits from `secrets`, 15-minute expiry, single use.
- Roles: `user`, `trader`, `admin`. Authorization checks happen in use cases, not only in routers.

## Broker and external access

- **Never store broker passwords.** MT5 connectivity uses the EA bridge (ADR 0002): the user's EA
  authenticates with a per-user **ingest token**.
- Ingest/API tokens: random 32+ bytes, shown once, stored only as SHA-256 hash, revocable, scoped
  (e.g. `ingest:mt5`), with `last_used_at`.
- If a credential must be stored for an integration (approved by ADR), encrypt it with
  `cryptography.Fernet` using a key from the environment. Never XOR/base64 "encryption".
- Live trading actions require explicit per-strategy enablement, risk limits and a kill switch (spec 003).

## Input and output

- Validate everything at the inbound adapter (Pydantic) and enforce business rules in the domain.
- Uploads: whitelist extensions (`.csv`, `.xlsx`, `.xls`), max 10 MB, never trust file names for paths.
- Return `404` (not `403`) for resources owned by other users, to avoid leaking existence.
- CORS: explicit origins from settings in production (no `*` with credentials).
