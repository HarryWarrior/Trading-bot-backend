# Deploy: local gateway stack

`docker-compose.yml` starts MongoDB, a Traefik gateway on `http://localhost:8000` and the `auth`,
`journal` and `analytics` services. Clients talk only to the gateway:
`/api/v1/auth`, `/api/v1/journal`, `/api/v1/analytics`, `/api/v1/mt5`.

> Status: documented but **not run** (no Docker daemon was available when written). The same paths
> are exercised in process by the cross-service acceptance suite (`tests/acceptance_services`).

## Run

    $env:JWT_SECRET_KEY = "<at least 32 random characters>"
    $env:INGEST_SERVICE_KEY = "<at least 32 random characters; same value in mt5>"
    docker compose -f deploy/docker-compose.yml up --build

Secrets come from the environment only; the compose file has no defaults for them. Without
`SMTP_HOST` the auth service only starts with `ENVIRONMENT=local` and logs verification codes
instead of emailing them (`docker compose logs auth`); any other environment requires SMTP.

## mt5 runs on the host, not in Docker

`mt5` attaches to the open, logged-in MetaTrader 5 terminal, which exists only on the Windows host.
Run it there on port 8004; Traefik routes `/api/v1/mt5` to `host.docker.internal:8004`:

    cd services/mt5 && uvicorn mt5_service.main:app --port 8004

Its `.env` needs the same `JWT_SECRET_KEY` and `INGEST_SERVICE_KEY` as the stack, and
`JOURNAL_URL=http://localhost:8000` (the journal is only reachable through the gateway). Keep a
single terminal open (see `services/mt5/README.md`). Link and sync are admin-only.

## Make an admin

    cd services/auth && python scripts/promote_admin.py <email>

(point `MONGODB_URL` at the compose Mongo, which is not published to the host by default.)

## Without Docker

`scripts/dev.ps1` starts the four services with `uvicorn` on ports 8001-8004 and the Nuxt dev proxy
routes `/api/v1/<service>` to each port. URLs are the same either way.
