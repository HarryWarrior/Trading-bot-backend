# Auth service

Issues access/refresh tokens, verifies emails and handles password resets (spec 001).
Hexagonal layout: domain and use cases are framework-free; Mongo, bcrypt, JWT and email are adapters.

## Run

    pip install -e "libs/shared[dev]" -e "services/auth[dev]"
    cp services/auth/.env.example services/auth/.env   # set JWT_SECRET_KEY (required)
    cd services/auth && uvicorn auth_service.main:app --reload --port 8001

Needs MongoDB (default `mongodb://localhost:27017`, database `auth_db`). Indexes are created on startup.
Settings come from environment variables or `services/auth/.env`; see `.env.example`.

## Test

    pytest services/auth/tests -q -W error

Integration tests use a throwaway `test_auth_<uuid>` database and are skipped when MongoDB is not reachable.

## Endpoints (`/api/v1/auth`)

`POST sign-up`, `verify-email`, `resend-verification`, `sign-in`, `refresh`, `sign-out` (Bearer + refresh token),
`forgot-password`, `reset-password`; `GET me` (Bearer); `DELETE sessions/expired` (admin).
Responses use the shared envelope. Verification codes and reset tokens are never returned by the API.

## Local email behavior

With `ENVIRONMENT=local` (or `test`) and no `SMTP_HOST`, emails are not sent: the verification code and
reset link are written to the server log (logger `auth_service.email`). This is the only place they appear.
With `ENVIRONMENT=prod`, `SMTP_HOST` is mandatory and settings validation fails without it.
