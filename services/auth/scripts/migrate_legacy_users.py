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


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=None, help="default: MONGODB_URL from settings")
    parser.add_argument("--source-db", default="trading_bot_db")
    args = parser.parse_args(argv)

    settings = AuthSettings()
    target_client = create_mongo_client(settings.mongodb_url)
    source_client = create_mongo_client(args.source_url or settings.mongodb_url)
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
