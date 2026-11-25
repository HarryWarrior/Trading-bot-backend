from datetime import UTC, datetime

import bcrypt
import pytest

from auth_service.application.ports.legacy_users import LegacyUser
from auth_service.application.use_cases.import_legacy_users import ImportLegacyUsers
from auth_service.application.use_cases.promote_to_admin import PromoteToAdmin, UserNotFound
from auth_service.domain.user import Role

pytestmark = pytest.mark.asyncio


GOOD_HASH = bcrypt.hashpw(b"pw", bcrypt.gensalt(4)).decode()


class FakeSource:
    def __init__(self, users):
        self._users = users

    async def list_users(self):
        return self._users


def legacy(**kw) -> LegacyUser:
    base = {
        "id": "1",
        "email": " Old@Mail.com ",
        "password_hash": GOOD_HASH,
        "name": "Old",
        "role": "trader",
        "email_verified": True,
        "created_at": datetime(2025, 1, 1),
    }
    return LegacyUser(**{**base, **kw})


async def test_maps_fields_and_defaults(world):
    source = FakeSource(
        [legacy(), legacy(id="2", email="b@mail.com", role="weird", email_verified=None)]
    )
    report = await ImportLegacyUsers(source, world.users).execute()
    assert (report.imported, report.skipped_existing, report.skipped_invalid) == (2, 0, 0)
    first = await world.users.get_by_email("old@mail.com")
    assert first.id == "1" and first.role is Role.TRADER and first.email_verified is True
    assert first.password_hash == GOOD_HASH
    assert first.created_at == datetime(2025, 1, 1, tzinfo=UTC)
    second = await world.users.get_by_email("b@mail.com")
    assert second.role is Role.USER and second.email_verified is False


async def test_second_run_imports_nothing(world):
    source = FakeSource([legacy()])
    await ImportLegacyUsers(source, world.users).execute()
    report = await ImportLegacyUsers(source, world.users).execute()
    assert (report.imported, report.skipped_existing) == (0, 1)


async def test_invalid_hashes_are_skipped_and_counted(world):
    source = FakeSource(
        [
            legacy(id="1", email="a@mail.com", password_hash="plaintext"),
            legacy(id="2", email="b@mail.com", password_hash=None),
            legacy(id="3", email="c@mail.com"),
        ]
    )
    report = await ImportLegacyUsers(source, world.users).execute()
    assert (report.imported, report.skipped_existing, report.skipped_invalid) == (1, 0, 2)


async def test_promote_to_admin(world):
    user = await world.registered_verified()
    await PromoteToAdmin(world.users).execute(" User@Mail.com ")
    assert (await world.users.get_by_id(user.id)).role is Role.ADMIN
    with pytest.raises(UserNotFound):
        await PromoteToAdmin(world.users).execute("nobody@mail.com")
