"""Grant the admin role to an existing user.

Usage (from services/auth):
    python scripts/promote_admin.py <email>
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Run from anywhere: make the service and the shared lib importable without installing them.
_ROOT = Path(__file__).resolve().parents[3]
for _p in (_ROOT / 'services' / 'auth' / 'src', _ROOT / 'libs' / 'shared' / 'src', _ROOT / 'libs' / 'shared'):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from auth_service.adapters.outbound.mongo_repositories import MongoUserRepository
from auth_service.application.use_cases.promote_to_admin import PromoteToAdmin, UserNotFound
from auth_service.settings import AuthSettings
from trading_shared.mongo import create_mongo_client


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()

    settings = AuthSettings()
    client = create_mongo_client(settings.mongodb_url)
    try:
        await PromoteToAdmin(MongoUserRepository(client[settings.database_name])).execute(email)
    except UserNotFound:
        print(f"error: no user with email {email!r}", file=sys.stderr)
        return 1
    finally:
        client.close()
    print(f"{email} is now an admin")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(argv))


if __name__ == "__main__":
    sys.exit(main())
