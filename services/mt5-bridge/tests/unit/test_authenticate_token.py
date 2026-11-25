from datetime import timedelta

import pytest

from mt5_bridge_service.application.use_cases.authenticate_token import AuthenticateIngestToken
from mt5_bridge_service.application.use_cases.issue_token import IssueIngestToken
from mt5_bridge_service.application.use_cases.revoke_token import RevokeIngestToken
from mt5_bridge_service.domain.errors import InvalidIngestToken


async def test_valid_token_returns_owner_and_updates_last_used_at(tokens, clock, ids):
    issued, plaintext = await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")
    clock.advance(timedelta(minutes=3))
    token = await AuthenticateIngestToken(tokens, clock).execute(plaintext)
    assert (token.id, token.user_id) == (issued.id, "u1")
    assert tokens.rows[issued.id].last_used_at == clock.now()


@pytest.mark.parametrize("plaintext", ["", "   ", "not-a-token"])
async def test_unknown_token_is_rejected(tokens, clock, ids, plaintext):
    await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")
    with pytest.raises(InvalidIngestToken):
        await AuthenticateIngestToken(tokens, clock).execute(plaintext)


async def test_revoked_token_is_rejected_and_not_touched(tokens, clock, ids):
    issued, plaintext = await IssueIngestToken(tokens, clock, ids).execute("u1", "ea")
    await RevokeIngestToken(tokens, clock).execute("u1", issued.id)
    with pytest.raises(InvalidIngestToken):
        await AuthenticateIngestToken(tokens, clock).execute(plaintext)
    assert tokens.rows[issued.id].last_used_at is None


def test_error_is_401_unauthenticated():
    assert (InvalidIngestToken.code, InvalidIngestToken.http_status) == ("UNAUTHENTICATED", 401)
