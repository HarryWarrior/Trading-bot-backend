import base64
import hashlib

import pytest

from mt5_bridge_service.application.use_cases.issue_token import IssueIngestToken
from mt5_bridge_service.domain.errors import InvalidTokenName
from mt5_bridge_service.domain.token import INGEST_MT5_SCOPE, hash_token


async def test_issue_token_returns_plaintext_once_and_stores_only_hash(tokens, clock, ids):
    token, plaintext = await IssueIngestToken(tokens, clock, ids).execute("u1", " Laptop EA ")

    assert token.user_id == "u1"
    assert token.name == "Laptop EA"
    assert token.scope == INGEST_MT5_SCOPE
    assert token.created_at == clock.now()
    assert token.last_used_at is None and token.revoked_at is None
    assert token.hash == hashlib.sha256(plaintext.encode()).hexdigest()
    assert token.hash == hash_token(plaintext)
    stored = tokens.rows[token.id]
    assert stored == token
    assert all(plaintext not in str(value) for value in vars(stored).values())
    assert plaintext not in repr(stored)


async def test_plaintext_is_at_least_32_bytes_of_entropy(tokens, clock, ids):
    use_case = IssueIngestToken(tokens, clock, ids)
    _, first = await use_case.execute("u1", "a")
    _, second = await use_case.execute("u1", "b")

    raw = base64.urlsafe_b64decode(first + "=" * (-len(first) % 4))
    assert len(raw) >= 32
    assert first != second


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_issue_token_rejects_invalid_name(tokens, clock, ids, name):
    with pytest.raises(InvalidTokenName):
        await IssueIngestToken(tokens, clock, ids).execute("u1", name)
    assert tokens.rows == {}
