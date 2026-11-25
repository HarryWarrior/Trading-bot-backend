"""Import users from the legacy app's MongoDB into the auth store (idempotent, read-only source).

Usage (from services/auth):
    python scripts/migrate_legacy_users.py [--source-url URL] [--source-db NAME]
"""

import argparse
import asyncio
import sys

from auth_service.adapters.outbound.mongo_legacy_users import MongoLegacyUserSource
from auth_service.adapters.outbound.mongo_repositories import MongoUserRepository
from auth_service.application.use_cases.import_legacy_users import ImportLegacyUsers
from auth_service.settings import AuthSettings
from trading_shared.mongo import create_mongo_client


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=None, help="default: MONGODB_URL from settings")
    parser.add_argument("--source-db", default="trading_bot_db")
    args = parser.parse_args(argv)

    settings = AuthSettings()
    source_url = args.source_url or settings.mongodb_url
    if _normalize_url(source_url) == _normalize_url(settings.mongodb_url) and (
        args.source_db == settings.database_name
    ):
        print(
            f"error: source and target are the same database ({args.source_db!r}); refusing to "
            "write into the legacy database. Check DATABASE_NAME.",
            file=sys.stderr,
        )
        return 2
    target_client = create_mongo_client(settings.mongodb_url)
    source_client = create_mongo_client(source_url)
    try:
        users = MongoUserRepository(target_client[settings.database_name])
        await users.create_indexes()
        source = MongoLegacyUserSource(source_client[args.source_db])
        report = await ImportLegacyUsers(source, users).execute()
    finally:
        source_client.close()
        target_client.close()
    print(
        f"imported={report.imported} skipped_existing={report.skipped_existing} "
        f"skipped_invalid={report.skipped_invalid}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    sys.exit(main())
