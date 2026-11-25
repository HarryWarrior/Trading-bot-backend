from datetime import timedelta

import pytest

from mt5_bridge_service.application.use_cases.issue_token import IssueIngestToken
from mt5_bridge_service.application.use_cases.revoke_token import RevokeIngestToken
from mt5_bridge_service.domain.errors import TokenNotFound
from mt5_bridge_service.domain.token import hash_token


async def test_revoked_token_not_found_active(tokens, clock, ids):
    token, plaintext = await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")
    assert await tokens.find_active_by_hash(hash_token(plaintext)) == token

    clock.advance(timedelta(minutes=1))
    revoked = await RevokeIngestToken(tokens, clock).execute("u1", token.id)

    assert revoked.revoked_at == clock.now()
    assert not revoked.is_active
    assert await tokens.find_active_by_hash(hash_token(plaintext)) is None


async def test_revoke_is_idempotent_and_keeps_first_revocation_time(tokens, clock, ids):
    token, _ = await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")
    first = await RevokeIngestToken(tokens, clock).execute("u1", token.id)
    clock.advance(timedelta(hours=1))

    second = await RevokeIngestToken(tokens, clock).execute("u1", token.id)

    assert second.revoked_at == first.revoked_at


async def test_cannot_revoke_another_users_token(tokens, clock, ids):
    token, plaintext = await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")

    with pytest.raises(TokenNotFound):
        await RevokeIngestToken(tokens, clock).execute("u2", token.id)
    assert await tokens.find_active_by_hash(hash_token(plaintext)) == token


async def test_revoke_unknown_token_raises(tokens, clock):
    with pytest.raises(TokenNotFound):
        await RevokeIngestToken(tokens, clock).execute("u1", "missing")
