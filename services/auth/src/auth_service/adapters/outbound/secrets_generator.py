"""Cryptographically secure code/token generator (adapter for SecretGenerator)."""

import secrets


class SecretsGenerator:
    def verification_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def opaque_token(self) -> str:
        return secrets.token_urlsafe(32)
