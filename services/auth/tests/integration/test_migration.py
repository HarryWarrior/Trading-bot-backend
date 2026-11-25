import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import bcrypt
import pytest
import pytest_asyncio

from auth_service.adapters.outbound.bcrypt_hasher import BcryptPasswordHasher
from auth_service.adapters.outbound.mongo_repositories import (
    MongoSessionRepository,
    MongoUserRepository,
)
from auth_service.application.use_cases.sign_in import SignIn
from auth_service.domain.errors import InvalidCredentials
from auth_service.domain.user import Role
from trading_shared.mongo import create_mongo_client

pytestmark = pytest.mark.asyncio


MONGO_URL = "mongodb://localhost:27017"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Issuer:
    def issue(self, user) -> tuple[str, int]:
        return f"access-{user.id}", 900


class _Secrets:
    def verification_code(self) -> str:
        return "000000"

    def opaque_token(self) -> str:
        return uuid.uuid4().hex


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def dbs(monkeypatch):
    client = create_mongo_client(MONGO_URL)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip("MongoDB is not reachable at localhost:27017")
    source = client[f"test_auth_{uuid.uuid4().hex}"]
    target = client[f"test_auth_{uuid.uuid4().hex}"]
    monkeypatch.setenv("MONGODB_URL", MONGO_URL)
    monkeypatch.setenv("DATABASE_NAME", target.name)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-migration-tests")
    try:
        yield source, target
    finally:
        await client.drop_database(source.name)
        await client.drop_database(target.name)
        client.close()


async def _seed(source):
    await source["users"].insert_many(
        [
            {
                "email": "Old.User@Mail.com",
                "password_hash": bcrypt.hashpw(b"OldPass123!", bcrypt.gensalt(4)).decode(),
                "name": "Old User",
                "role": "trader",
                "email_verified": True,
                "created_at": datetime(2025, 1, 1),
                "updated_at": datetime(2025, 1, 2),
            },
            {
                "email": "bad@mail.com",
                "password_hash": "not-a-bcrypt-hash",
                "name": "Bad",
                "role": "user",
            },
        ]
    )


async def test_migrated_user_signs_in_with_old_password_and_rerun_is_idempotent(dbs, capsys):
    source, target = dbs
    await _seed(source)
    migrate = _load("migrate_legacy_users")
    args = ["--source-url", MONGO_URL, "--source-db", source.name]

    assert await migrate.run(args) == 0
    assert "imported=1 skipped_existing=0 skipped_invalid=1" in capsys.readouterr().out
    assert await migrate.run(args) == 0
    assert "imported=0 skipped_existing=1 skipped_invalid=1" in capsys.readouterr().out

    users = MongoUserRepository(target)
    sign_in = SignIn(
        users,
        MongoSessionRepository(target),
        BcryptPasswordHasher(rounds=4),
        _Issuer(),
        _Secrets(),
        _Clock(),
    )
    tokens = await sign_in.execute("old.user@mail.com", "OldPass123!")
    assert tokens.access_token
    with pytest.raises(InvalidCredentials):
        await sign_in.execute("old.user@mail.com", "wrong")
    migrated = await users.get_by_email("old.user@mail.com")
    assert migrated.role is Role.TRADER and migrated.name == "Old User"
    assert await users.get_by_email("bad@mail.com") is None
    # The legacy database is only read.
    assert await source["users"].count_documents({}) == 2


async def test_promote_admin_script(dbs, capsys):
    source, target = dbs
    await _seed(source)
    await _load("migrate_legacy_users").run(["--source-url", MONGO_URL, "--source-db", source.name])
    capsys.readouterr()
    promote = _load("promote_admin")

    assert await promote.run(["nobody@mail.com"]) == 1
    assert "nobody@mail.com" in capsys.readouterr().err
    assert await promote.run(["Old.User@Mail.com"]) == 0
    stored = await MongoUserRepository(target).get_by_email("old.user@mail.com")
    assert stored.role is Role.ADMIN


async def test_migration_refuses_when_source_equals_target(dbs, capsys):
    _, target = dbs
    await target["users"].insert_one({"email": "x@mail.com", "password_hash": "h"})
    before_indexes = await target["users"].index_information()

    code = await _load("migrate_legacy_users").run(
        ["--source-url", MONGO_URL + "/", "--source-db", target.name]
    )

    assert code == 2
    assert "same database" in capsys.readouterr().err
    assert await target["users"].count_documents({}) == 1
    assert await target["users"].index_information() == before_indexes
