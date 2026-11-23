"""The configured refresh lifetime is honored by sign-in and refresh."""

from datetime import timedelta

import pytest

from auth_service.domain.errors import InvalidToken

pytestmark = pytest.mark.asyncio

ONE_DAY = timedelta(days=1)


async def test_refresh_token_rejected_after_configured_ttl(world):
    await world.registered_verified()
    tokens = await world.sign_in(refresh_ttl=ONE_DAY).execute("user@mail.com", "Secret123!")
    world.clock.advance(ONE_DAY + timedelta(seconds=1))
    with pytest.raises(InvalidToken):
        await world.refresh(refresh_ttl=ONE_DAY).execute(tokens.refresh_token)


async def test_refresh_token_valid_just_before_configured_ttl(world):
    await world.registered_verified()
    tokens = await world.sign_in(refresh_ttl=ONE_DAY).execute("user@mail.com", "Secret123!")
    world.clock.advance(ONE_DAY - timedelta(seconds=1))
    rotated = await world.refresh(refresh_ttl=ONE_DAY).execute(tokens.refresh_token)
    stored = [exp for _, exp in world.sessions.sessions.values()]
    assert stored == [world.clock.now() + ONE_DAY]
    assert rotated.refresh_token != tokens.refresh_token
