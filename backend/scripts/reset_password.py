"""One-off script to reset a User's password directly, bypassing the API.

There is no "forgot password" flow yet, so a lost/forgotten password for an
already-onboarded user (the invitation token is single-use and can't be
replayed) has no self-service recovery path. This script does it directly
against the database, same bootstrap-style approach as create_admin.py.

Usage:
    uv run python scripts/reset_password.py owner@example.com "NewSecret!23"
"""

import asyncio
import sys
from pathlib import Path

# Not installed as an editable package (package = false in pyproject.toml),
# so running this file directly puts scripts/ on sys.path instead of
# backend/. Add backend/ explicitly so `app` is importable regardless of
# how this is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows defaults to ProactorEventLoop, which psycopg's async driver cannot
# use. Only matters when running this script directly on native Windows
# (e.g. against a docker-compose Postgres exposed on localhost); inside the
# Linux backend container this branch never runs.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.security import hash_password
from app.db.session import async_session_factory
from app.repositories.user import UserRepository


async def main(email: str, new_password: str) -> None:
    async with async_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.get_by_email(email)
        if user is None:
            print(f"No user found with email {email}")
            sys.exit(1)

        user.hashed_password = hash_password(new_password)
        session.add(user)
        await session.commit()
        print(f"Password reset for {user.email} ({user.id})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: uv run python scripts/reset_password.py <email> "<new password>"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
