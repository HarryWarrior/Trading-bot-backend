# Auth service

Issues access/refresh tokens, verifies emails and handles password resets (spec 001).
Domain and use cases are in place; adapters and the HTTP router come in later tasks (planned).

    pip install -e "libs/shared[dev]" -e "services/auth[dev]"
    pytest services/auth/tests
