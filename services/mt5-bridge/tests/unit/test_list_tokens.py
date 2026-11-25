from datetime import timedelta

from mt5_bridge_service.application.use_cases.issue_token import IssueIngestToken
from mt5_bridge_service.application.use_cases.list_tokens import ListIngestTokens


async def test_list_tokens_only_own_user_newest_first(tokens, clock, ids):
    issue = IssueIngestToken(tokens, clock, ids)
    older, _ = await issue.execute("u1", "old")
    clock.advance(timedelta(minutes=1))
    newer, _ = await issue.execute("u1", "new")
    await issue.execute("u2", "other")

    listed = await ListIngestTokens(tokens).execute("u1")

    assert [t.id for t in listed] == [newer.id, older.id]
    assert await ListIngestTokens(tokens).execute("nobody") == []
